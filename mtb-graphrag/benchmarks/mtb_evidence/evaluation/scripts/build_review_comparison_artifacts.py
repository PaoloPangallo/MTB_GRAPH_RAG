"""Costruisce gli artefatti del confronto fra prima revisione e replica cieca.

Allinea le due revisioni per chiave deterministica, descrive dove concordano e
dove no, prepara i packet per l'adjudicator. Non decide nessun disaccordo e non
tocca adapter, corpus, retriever, scoring o gold.

Deterministico: ogni output e' ordinato per chiave dichiarata, quindi due
esecuzioni producono gli stessi byte. Con `--swap-review-order` le due revisioni
si scambiano di ruolo: le grandezze simmetriche (accordo, kappa, matrice
trasposta, insiemi di gruppi) devono restare invariate.

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_review_comparison_artifacts
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.multi_intervention_review_comparison import (
    AlignmentError,
    CHILD_DIFFERENCE_REASONS,
    COMPARISON_VERSION,
    DISAGREEMENT_CAUSES,
    METHOD_LABELS,
    REPLICATE_OUTCOME,
    align,
    cohen_kappa,
    confusion_matrix,
    first_locator_granularity,
    first_review_outcome,
    group_key,
    intervention_key,
    normalize_intervention,
    percent_agreement,
    qualifies_for_provisional_consensus,
    replicate_locator_granularity,
    verdict_for,
)
from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    canonical_dumps,
    canonical_jsonl,
    sha256_bytes,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
FIRST = V3 / "multi_intervention_source_review"
REPLICATE = V3 / "multi_intervention_second_review"
PACKETS = FIRST / "second_review_packets"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "multi_intervention_review_comparison"

START_SHA = "1e9d6b0d767ad3fac02e43d0186d948251b6349c"
COMPARISON_BRANCH = "review/v3-multi-intervention-review-comparison"

# Interprete usato: il `.venv` del progetto non ha pytest installato, quindi otto
# moduli di test falliscono in import con quell'interprete. Il fatto e' registrato
# come dato ambientale, non aggirato.
ENVIRONMENT = {
    "python_version": "3.12.10",
    "pytest_version": "9.0.2",
    "pluggy_version": "1.6.0",
    "iniconfig_version": "2.3.0",
    "packaging_version": "25.0",
    "pytest_subtests_installed": False,
    "subtest_support": "nativo in pytest 9 per unittest.TestCase.subTest",
    "interpreter": "python di sistema (WindowsApps PythonSoftwareFoundation.Python.3.12)",
    "venv_not_used_reason": (
        "Il .venv del progetto non ha pytest installato: con quell'interprete otto moduli"
        " di test falliscono in ImportError su `import pytest`. La replica cieca era stata"
        " dichiarata verde con l'interprete di sistema e il confronto usa lo stesso, per"
        " non cambiare la base di paragone."
    ),
}

FROZEN_ARTIFACTS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/corpus_manifest.py",
    "backend/pipeline/evidence/corpus_regeneration.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/evaluation/scripts/run_v2_adapter.py",
    "benchmarks/mtb_evidence/evaluation/scripts/run_qualified_retriever_prototype.py",
)

# Il gold viene solo pesato, mai letto: si calcola il digest dei byte per provare
# che non e' cambiato, senza decodificarlo ne' interpretarlo.
GOLD_ARTIFACTS = (
    "benchmarks/mtb_evidence/evaluation/data/clinical_gold_v1.jsonl",
    "benchmarks/mtb_evidence/evaluation/data/snapshot_gold_ffc97bc7c660f194.jsonl",
    "benchmarks/mtb_evidence/v3/first_review/provisional_gold.jsonl",
    "benchmarks/mtb_evidence/v3/author_approval/provisional_gold.jsonl",
)

LOCAL_SOURCES = (
    "benchmarks/mtb_evidence/v3/priority_curation/source_abstract_cache.jsonl",
    "../data_expl/benchmark/benchmark_papers/fulltext_26698910.txt",
)


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def digest(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.exists() else None


def tree_digest(directory: Path) -> dict[str, Any]:
    files = sorted(p for p in directory.iterdir() if p.is_file())
    per_file = {p.name: sha256_bytes(p.read_bytes()) for p in files}
    joined = "\n".join(f"{name}:{value}" for name, value in sorted(per_file.items()))
    return {"file_count": len(per_file), "files": per_file, "aggregate_sha256": sha256_text(joined)}


# --- caricamento --------------------------------------------------------------


class Inputs:
    def __init__(self) -> None:
        self.first_annotations = jsonl(FIRST / "intervention_level_annotations.jsonl")
        self.first_groups = jsonl(FIRST / "group_atomicity_decisions.jsonl")
        self.first_units = jsonl(FIRST / "source_unit_annotations.jsonl")
        self.simulation = json.loads(
            (FIRST / "post_review_schema_simulation.json").read_text(encoding="utf-8")
        )
        self.replicate_annotations = jsonl(REPLICATE / "intervention_annotations_second.jsonl")
        self.replicate_groups = jsonl(REPLICATE / "group_decisions_second.jsonl")
        self.replicate_unresolved = jsonl(REPLICATE / "unresolved_second.jsonl")
        self.causes = jsonl(DATA / "review_comparison_causes_v1.jsonl")
        self.priority = jsonl(DATA / "review_comparison_priority_cases_v1.jsonl")
        self.questions = jsonl(DATA / "review_comparison_adjudication_questions_v1.jsonl")
        self.guidelines = jsonl(DATA / "review_comparison_guidelines_v1.jsonl")
        self.packets = {
            json.loads(p.read_text(encoding="utf-8"))["graph_evidence_id"]: json.loads(
                p.read_text(encoding="utf-8")
            )
            for p in sorted(PACKETS.glob("MI-B-*.json"))
        }

        self.simulated_children = {
            (child["parent_graph_evidence_id"], normalize_intervention(child["intervention"]))
            for child in self.simulation["simulated_child_statements"]
        }
        self.cause_index = {
            (row["graph_evidence_id"], normalize_intervention(row["intervention"])): row
            for row in self.causes
        }
        self.unresolved_groups = {
            row["blind_annotation_id"] for row in self.replicate_unresolved
        }


def check_scope(inputs: Inputs) -> dict[str, Any]:
    """Le due revisioni devono coprire lo stesso perimetro, o ci si ferma."""
    if len(inputs.first_groups) != 13 or len(inputs.replicate_groups) != 13:
        raise AlignmentError(
            f"gruppi attesi 13: prima={len(inputs.first_groups)} replica={len(inputs.replicate_groups)}"
        )
    if len(inputs.first_annotations) != 28 or len(inputs.replicate_annotations) != 28:
        raise AlignmentError(
            "associazioni attese 28: "
            f"prima={len(inputs.first_annotations)} replica={len(inputs.replicate_annotations)}"
        )
    return {
        "first_review_groups": len(inputs.first_groups),
        "replicate_groups": len(inputs.replicate_groups),
        "first_review_associations": len(inputs.first_annotations),
        "replicate_associations": len(inputs.replicate_annotations),
        "alignment_deterministic": True,
    }


# --- confronto intervention-level ---------------------------------------------


def compare_interventions(inputs: Inputs, *, swap: bool) -> list[dict[str, Any]]:
    pairs = align(
        inputs.first_annotations,
        inputs.replicate_annotations,
        intervention_key,
        label="intervention-level",
    )
    rows = []
    for key, first, replicate in pairs:
        graph_id, source_id, drug = key
        is_parent = bool(replicate["is_current_statement_intervention"])
        has_child = (graph_id, drug) in inputs.simulated_children
        first_outcome = first_review_outcome(
            first, is_parent_intervention=is_parent, has_simulated_child=has_child
        )
        replicate_outcome = REPLICATE_OUTCOME[replicate["materialization"]]
        first_insufficient = first["locator_status"] != "complete"
        replicate_insufficient = replicate["locator_status"] != "sufficient"

        verdict = verdict_for(
            first_classification=first["classification"],
            replicate_classification=replicate["classification"],
            first_outcome=first_outcome,
            replicate_outcome=replicate_outcome,
            first_locator_insufficient=first_insufficient,
            replicate_locator_insufficient=replicate_insufficient,
        )
        cause = inputs.cause_index.get((graph_id, drug), {})
        rows.append(
            {
                "comparison_id": f"CMP-{graph_id.replace(':', '-')}-{drug.replace(' ', '-')}",
                "graph_evidence_id": graph_id,
                "source_id": source_id,
                "intervention": replicate["intervention"],
                "normalized_intervention": drug,
                "is_parent_intervention": is_parent,
                "biomarker": replicate["biomarker"],
                "disease": replicate["disease"],
                "first_classification": first["classification"],
                "replicate_classification": replicate["classification"],
                "classification_match": first["classification"] == replicate["classification"],
                "first_direction": first["direction"],
                "replicate_direction": replicate["claim_direction"],
                "direction_match": first["direction"] == replicate["claim_direction"],
                "first_polarity": first["polarity"],
                "replicate_polarity": replicate["claim_polarity"],
                "polarity_match": first["polarity"] == replicate["claim_polarity"],
                "first_population_or_model": first["population_or_model"],
                "replicate_population_model": replicate["population_model"],
                "first_source_unit_id": first["source_unit_id"],
                "replicate_source_unit_id": replicate["source_unit_id"],
                "first_locator_status": first["locator_status"],
                "replicate_locator_status": replicate["locator_status"],
                "locator_sufficiency_match": first_insufficient == replicate_insufficient,
                "first_claim_outcome": first_outcome,
                "replicate_claim_outcome": replicate_outcome,
                "materialization_match": first_outcome == replicate_outcome,
                "mapping_status_first": first["classification"] == "possible_alias_not_verified",
                "mapping_status_replicate": replicate["alias_status"],
                "pending_mapping": replicate["alias_status"] == "pending_not_verified",
                "verdict": verdict,
                "primary_cause": cause.get("primary_cause"),
                "secondary_causes": cause.get("secondary_causes", []),
                "cause_note": cause.get("note"),
                "comparison_version": COMPARISON_VERSION,
                **METHOD_LABELS,
            }
        )
    if swap:
        rows = [_swap_row(row) for row in rows]
    return rows


def _swap_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Scambia i ruoli delle due revisioni lasciando invariati i campi simmetrici."""
    swapped = dict(row)
    for suffix in (
        "classification",
        "direction",
        "polarity",
        "source_unit_id",
        "locator_status",
        "claim_outcome",
    ):
        left, right = f"first_{suffix}", f"replicate_{suffix}"
        if left in swapped and right in swapped:
            swapped[left], swapped[right] = swapped[right], swapped[left]
    return swapped


# --- confronto group-level ----------------------------------------------------


def compare_groups(
    inputs: Inputs, intervention_rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    pairs = align(inputs.first_groups, inputs.replicate_groups, group_key, label="group-level")
    by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in intervention_rows:
        by_group.setdefault(row["graph_evidence_id"], []).append(row)

    rows = []
    for key, first, replicate in pairs:
        graph_id = key[0]
        members = by_group[graph_id]
        verdicts = [row["verdict"] for row in members]
        same_decision = first["atomicity_decision"] == replicate["decision"]
        pending = any(row["pending_mapping"] for row in members)
        locator_ok = all(
            row["first_locator_status"] == "complete"
            and row["replicate_locator_status"] == "sufficient"
            for row in members
        )
        aggregate_risk = "aggregate_parent_only" in {
            first["atomicity_decision"],
            replicate["decision"],
        }
        scope_issue = replicate["blind_annotation_id"] in inputs.unresolved_groups
        consensus = qualifies_for_provisional_consensus(
            same_group_decision=same_decision,
            intervention_verdicts=verdicts,
            locator_sufficient=locator_ok,
            pending_mapping_present=pending,
            aggregate_to_specific_risk=aggregate_risk,
            scope_issue_present=scope_issue,
        )
        rows.append(
            {
                "graph_evidence_id": graph_id,
                "source_id": key[1],
                "statement_id": replicate["statement_id"],
                "blind_annotation_id": replicate["blind_annotation_id"],
                "first_decision": first["atomicity_decision"],
                "first_rationale": first["rationale"],
                "replicate_decision": replicate["decision"],
                "replicate_rationale": replicate["rationale"],
                "decision_match": same_decision,
                "intervention_count": len(members),
                "intervention_verdicts": sorted(verdicts),
                "disagreeing_interventions": sorted(
                    row["intervention"] for row in members if row["verdict"] != "exact_agreement"
                ),
                "first_source_unit_count": len({row["first_source_unit_id"] for row in members}),
                "replicate_source_unit_count": len(
                    {row["replicate_source_unit_id"] for row in members}
                ),
                "pending_mapping_present": pending,
                "all_locators_sufficient": locator_ok,
                "aggregate_to_specific_risk": aggregate_risk,
                "scope_issue_present": scope_issue,
                "provisional_consensus": consensus,
                "adjudication_required": not consensus,
                "comparison_version": COMPARISON_VERSION,
                **METHOD_LABELS,
            }
        )
    return rows


# --- assi secondari -----------------------------------------------------------


def compare_locators(
    inputs: Inputs, intervention_rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    first_index = {intervention_key(row): row for row in inputs.first_annotations}
    replicate_index = {intervention_key(row): row for row in inputs.replicate_annotations}
    rows = []
    for row in intervention_rows:
        key = (row["graph_evidence_id"], row["source_id"], row["normalized_intervention"])
        first, replicate = first_index[key], replicate_index[key]
        first_granularity = first_locator_granularity(first["locator"])
        replicate_granularity = replicate_locator_granularity(replicate["locator"])
        rows.append(
            {
                "comparison_id": row["comparison_id"],
                "graph_evidence_id": row["graph_evidence_id"],
                "intervention": row["intervention"],
                "first_locator": first["locator"],
                "first_locator_granularity": first_granularity,
                "first_locator_status": first["locator_status"],
                "replicate_locator": replicate["locator"],
                "replicate_locator_granularity": replicate_granularity,
                "replicate_locator_status": replicate["locator_status"],
                "granularity_match": first_granularity == replicate_granularity,
                "replicate_has_verbatim_probes": bool(
                    replicate["locator"].get("verbatim_probes")
                ),
                "first_has_verbatim_probes": False,
                **METHOD_LABELS,
            }
        )
    return rows


def compare_source_units(
    inputs: Inputs, intervention_rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    first_index = {intervention_key(row): row for row in inputs.first_annotations}
    by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in intervention_rows:
        by_group.setdefault(row["graph_evidence_id"], []).append(row)

    rows = []
    for row in intervention_rows:
        key = (row["graph_evidence_id"], row["source_id"], row["normalized_intervention"])
        first = first_index[key]
        members = by_group[row["graph_evidence_id"]]
        first_units = {item["first_source_unit_id"] for item in members}
        replicate_units = {item["replicate_source_unit_id"] for item in members}
        prose = {first_index[
            (item["graph_evidence_id"], item["source_id"], item["normalized_intervention"])
        ]["documentary_unit"] for item in members}
        cause = inputs.cause_index.get(
            (row["graph_evidence_id"], row["normalized_intervention"]), {}
        )
        rows.append(
            {
                "comparison_id": row["comparison_id"],
                "graph_evidence_id": row["graph_evidence_id"],
                "intervention": row["intervention"],
                "first_source_unit_id": row["first_source_unit_id"],
                "first_documentary_unit": first["documentary_unit"],
                "replicate_source_unit_id": row["replicate_source_unit_id"],
                "group_first_unit_count": len(first_units),
                "group_replicate_unit_count": len(replicate_units),
                "group_segmentation_match": len(first_units) == len(replicate_units),
                "first_prose_distinguishes_units_within_group": len(prose) > 1,
                "event_divergence_recorded": cause.get("primary_cause")
                == "source_unit_segmentation_difference",
                "note": (
                    "La prima revisione usa un identificatore di unita' per fonte, ma il campo"
                    " documentary_unit distingue in prosa braccio, paziente o modello. La"
                    " differenza e' quindi soprattutto nello spazio degli identificatori."
                ),
                **METHOD_LABELS,
            }
        )
    return rows


def compare_child_claims(
    inputs: Inputs, intervention_rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for row in intervention_rows:
        first_child = row["first_claim_outcome"] == "claim_via_new_child"
        replicate_child = row["replicate_claim_outcome"] == "claim_via_new_child"
        if not first_child and not replicate_child:
            status = "proposed_by_neither"
        elif first_child and replicate_child:
            status = "proposed_by_both"
        elif first_child:
            status = "proposed_by_first_only"
        else:
            status = "proposed_by_replicate_only"
        rows.append(
            {
                "comparison_id": row["comparison_id"],
                "graph_evidence_id": row["graph_evidence_id"],
                "intervention": row["intervention"],
                "is_parent_intervention": row["is_parent_intervention"],
                "child_status": status,
                "first_claim_outcome": row["first_claim_outcome"],
                "replicate_claim_outcome": row["replicate_claim_outcome"],
                "difference_reason": child_difference_reason(row, status),
                "secondary_reason": child_secondary_reason(row, status),
                "documentary_result_agreement": row["classification_match"],
                **METHOD_LABELS,
            }
        )
    return rows


CLASSIFICATION_BLOCK_REASON = {
    "possible_alias_not_verified": "pending_alias_blocks_child",
    "directly_tested_in_shared_aggregate_result": "aggregate_result",
    "drug_class_member_not_individually_tested": "unsupported_intervention",
    "directly_tested_in_combination_regimen": "regimen_component",
    "comparator_only": "unsupported_intervention",
    "mentioned_background_only": "unsupported_intervention",
    "insufficient_source_access": "insufficient_locator",
}


def child_difference_reason(row: Mapping[str, Any], status: str) -> str | None:
    if status == "proposed_by_both":
        # Entrambe propongono il figlio: non c'e' differenza da spiegare, a meno
        # che le due letture documentali sotto il figlio non coincidano.
        return "different_claim_identity" if not row["classification_match"] else None
    if status in ("proposed_by_first_only", "proposed_by_replicate_only"):
        return (
            "parent_intervention_already_represents_result"
            if row["is_parent_intervention"]
            else "reviewer_policy_difference"
        )
    # Nessuna delle due propone un figlio. Se l'intervento e' quello del parent la
    # ragione strutturale e' che il claim esiste gia'; il motivo documentale
    # resta comunque registrato come secondario.
    if row["is_parent_intervention"]:
        return "parent_intervention_already_represents_result"
    return CLASSIFICATION_BLOCK_REASON.get(row["replicate_classification"], "unresolved")


def child_secondary_reason(row: Mapping[str, Any], status: str) -> str | None:
    if status == "proposed_by_neither" and row["is_parent_intervention"]:
        return CLASSIFICATION_BLOCK_REASON.get(row["replicate_classification"])
    return None


# --- metriche -----------------------------------------------------------------


def build_metrics(
    intervention_rows: Sequence[Mapping[str, Any]],
    group_rows: Sequence[Mapping[str, Any]],
    locator_rows: Sequence[Mapping[str, Any]],
    source_unit_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    classification_pairs = [
        (row["first_classification"], row["replicate_classification"]) for row in intervention_rows
    ]
    outcome_pairs = [
        (row["first_claim_outcome"], row["replicate_claim_outcome"]) for row in intervention_rows
    ]
    group_pairs = [(row["first_decision"], row["replicate_decision"]) for row in group_rows]
    locator_pairs = [
        (row["first_locator_granularity"], row["replicate_locator_granularity"])
        for row in locator_rows
    ]
    unit_pairs = [
        (row["group_first_unit_count"], row["group_replicate_unit_count"])
        for row in source_unit_rows
    ]

    verdict_counts: dict[str, int] = {}
    for row in intervention_rows:
        verdict_counts[row["verdict"]] = verdict_counts.get(row["verdict"], 0) + 1

    return {
        "intervention_level": {
            "verdict_counts": dict(sorted(verdict_counts.items())),
            "exact_agreement": verdict_counts.get("exact_agreement", 0),
            "compatible_agreement": verdict_counts.get("compatible_agreement", 0),
            "disagreements": sum(
                count
                for verdict, count in verdict_counts.items()
                if verdict not in ("exact_agreement", "compatible_agreement")
            ),
            "classification_percent_agreement": percent_agreement(classification_pairs),
            "classification_kappa": cohen_kappa(classification_pairs),
            "materialization_percent_agreement": percent_agreement(outcome_pairs),
            "materialization_kappa": cohen_kappa(outcome_pairs),
        },
        "group_level": {
            "percent_agreement": percent_agreement(group_pairs),
            "kappa": cohen_kappa(group_pairs),
            "exact_agreement": sum(1 for row in group_rows if row["decision_match"]),
        },
        "locator": {
            "granularity_percent_agreement": percent_agreement(locator_pairs),
            "first_sub_document_unit": sum(
                1 for row in locator_rows if row["first_locator_granularity"] == "sub_document_unit"
            ),
            "replicate_sub_document_unit": sum(
                1
                for row in locator_rows
                if row["replicate_locator_granularity"] == "sub_document_unit"
            ),
        },
        "source_unit": {
            "group_segmentation_percent_agreement": percent_agreement(unit_pairs),
            "first_distinct_units": len(
                {row["first_source_unit_id"] for row in source_unit_rows}
            ),
            "replicate_distinct_units": len(
                {row["replicate_source_unit_id"] for row in source_unit_rows}
            ),
        },
        "agreement_by_category": agreement_by_category(intervention_rows),
        **METHOD_LABELS,
    }


def agreement_by_category(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        entry = result.setdefault(
            row["first_classification"], {"n": 0, "matched": 0}
        )
        entry["n"] += 1
        entry["matched"] += int(row["classification_match"])
    return dict(sorted(result.items()))


# --- packet di adjudication ---------------------------------------------------


def build_adjudication_packets(
    inputs: Inputs,
    group_rows: Sequence[Mapping[str, Any]],
    intervention_rows: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    question_index = {row["graph_evidence_id"]: row for row in inputs.questions}
    first_index = {intervention_key(row): row for row in inputs.first_annotations}
    replicate_index = {intervention_key(row): row for row in inputs.replicate_annotations}
    by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in intervention_rows:
        by_group.setdefault(row["graph_evidence_id"], []).append(row)

    packets: dict[str, str] = {}
    for group in group_rows:
        if not group["adjudication_required"]:
            continue
        graph_id = group["graph_evidence_id"]
        questions = question_index.get(graph_id)
        if questions is None:
            raise AlignmentError(f"{graph_id}: gruppo da adjudicare senza domande")
        packet = inputs.packets[graph_id]
        members = []
        for row in sorted(by_group[graph_id], key=lambda item: item["normalized_intervention"]):
            key = (graph_id, row["source_id"], row["normalized_intervention"])
            first, replicate = first_index[key], replicate_index[key]
            members.append(
                {
                    "intervention": row["intervention"],
                    "is_parent_intervention": row["is_parent_intervention"],
                    "first_classification": first["classification"],
                    "first_locator": first["locator"],
                    "first_source_unit_id": first["source_unit_id"],
                    "first_documentary_unit": first["documentary_unit"],
                    "first_result_paraphrase": first["result_paraphrase"],
                    "first_claim_outcome": row["first_claim_outcome"],
                    "replicate_classification": replicate["classification"],
                    "replicate_locator": replicate["locator"],
                    "replicate_source_unit_id": replicate["source_unit_id"],
                    "replicate_result_paraphrase": replicate["paraphrased_result"],
                    "replicate_claim_outcome": row["replicate_claim_outcome"],
                    "verdict": row["verdict"],
                    "primary_cause": row["primary_cause"],
                    "secondary_causes": row["secondary_causes"],
                }
            )
        payload = {
            "adjudication_packet_id": f"ADJ-{graph_id.replace(':', '-')}",
            "graph_evidence_id": graph_id,
            "statement_id": group["statement_id"],
            "source_id": group["source_id"],
            "blind_annotation_id": group["blind_annotation_id"],
            "biomarker": packet["biomarker"],
            "disease": packet["disease"],
            "interventions": sorted(packet["candidate_interventions"]),
            "source_access_status": packet["source_access_status"],
            "source_title": packet["source_title"],
            "available_source_text": packet["source_text"],
            "source_text_kind": packet["source_text_kind"],
            "first_review_decision": group["first_decision"],
            "first_review_rationale": group["first_rationale"],
            "replicate_decision": group["replicate_decision"],
            "replicate_rationale": group["replicate_rationale"],
            "decision_match": group["decision_match"],
            "intervention_level_detail": members,
            "highlighted_differences": sorted(group["disagreeing_interventions"]),
            "pending_mapping_present": group["pending_mapping_present"],
            "scope_issue_present": group["scope_issue_present"],
            "adjudicator_questions": questions["questions"],
            "possible_schema_impact": questions["schema_impact"],
            "prefilled_decision": None,
            "gold_metrics_included": False,
            "retrieval_results_included": False,
            "recall_based_suggestions_included": False,
            "comparison_version": COMPARISON_VERSION,
            **METHOD_LABELS,
        }
        packets[f"adjudication_packets/{payload['adjudication_packet_id']}.json"] = canonical_dumps(
            payload
        )
    return packets


# --- reportistica -------------------------------------------------------------


def render_comparison_report(
    metrics: Mapping[str, Any],
    group_rows: Sequence[Mapping[str, Any]],
    matrix: Mapping[str, Any],
) -> str:
    intervention = metrics["intervention_level"]
    lines = [
        "# Confronto fra prima revisione e replica cieca",
        "",
        f"`comparison_type = {METHOD_LABELS['comparison_type']}`",
        "",
        "La replica non e' indipendente: il prompt che l'ha commissionata nominava la",
        "raccomandazione della prima revisione e il contesto di sessione conteneva gli oggetti",
        "dei suoi commit. Ogni numero di questa pagina e' descrittivo. In particolare",
        "`independent_inter_reviewer_agreement = false` e",
        "`valid_for_external_reliability_claim = false`: un accordo elevato qui non e' una",
        "convergenza fra revisori nel senso usuale, ed e' compatibile con l'ipotesi che le due",
        "letture condividano un'origine. Serve a preparare l'adjudication e ad affinare le linee",
        "guida, non a validare nulla.",
        "",
        "## Perimetro",
        "",
        "- 13 gruppi, allineati per `(graph_evidence_id, source_id)`",
        "- 28 associazioni, allineate per `(graph_evidence_id, source_id, intervento normalizzato)`",
        "- allineamento per chiave, mai per posizione; nessuna asimmetria",
        "- i codici di sviluppo restano distinti dai nomi generici: `BGJ398` non e' `infigratinib`,",
        "  `AUY922` non e' `luminespib`",
        "",
        "## Intervention-level",
        "",
    ]
    lines += [f"- `{key}`: {value}" for key, value in intervention["verdict_counts"].items()]
    lines += [
        "",
        f"Accordo sulla classificazione: {intervention['classification_percent_agreement']['agreements']}"
        f"/{intervention['classification_percent_agreement']['n']} "
        f"({intervention['classification_percent_agreement']['percent_agreement']:.1%}).",
        f"Accordo sull'esito del claim: {intervention['materialization_percent_agreement']['agreements']}"
        f"/{intervention['materialization_percent_agreement']['n']} "
        f"({intervention['materialization_percent_agreement']['percent_agreement']:.1%}).",
        "",
        "## Group-level",
        "",
        f"Accordo esatto: {metrics['group_level']['exact_agreement']}/13 "
        f"({metrics['group_level']['percent_agreement']['percent_agreement']:.1%}).",
        "",
        "| gruppo | prima revisione | replica | accordo |",
        "| --- | --- | --- | --- |",
    ]
    for row in sorted(group_rows, key=lambda item: item["graph_evidence_id"]):
        mark = "si" if row["decision_match"] else "**no**"
        lines.append(
            f"| `{row['graph_evidence_id']}` | `{row['first_decision']}` | "
            f"`{row['replicate_decision']}` | {mark} |"
        )

    lines += [
        "",
        "### Matrice di confusione group-level",
        "",
        "Righe: prima revisione. Colonne: replica.",
        "",
    ]
    categories = sorted(matrix)
    lines.append("| | " + " | ".join(f"`{name}`" for name in categories) + " |")
    lines.append("| --- |" + " --- |" * len(categories))
    for first in categories:
        cells = " | ".join(str(matrix[first][second]) for second in categories)
        lines.append(f"| `{first}` | {cells} |")

    kappa_group = metrics["group_level"]["kappa"]
    kappa_cls = intervention["classification_kappa"]
    lines += [
        "",
        "## Kappa, e perche' non va letto",
        "",
        f"- group-level: {kappa_group.get('kappa')} (n={kappa_group.get('n')}, "
        f"categorie={kappa_group.get('category_count')}, "
        f"cella attesa minima={kappa_group.get('min_expected_cell_count')})",
        f"- classificazione intervention-level: {kappa_cls.get('kappa')} (n={kappa_cls.get('n')}, "
        f"categorie={kappa_cls.get('category_count')}, "
        f"cella attesa minima={kappa_cls.get('min_expected_cell_count')})",
        f"- esito del claim: {intervention['materialization_kappa'].get('kappa')}",
        "",
        "I tre valori sono calcolati e nessuno dei tre e' interpretabile. Due ragioni",
        "indipendenti: le codifiche non sono indipendenti, quindi kappa non misura quello per cui",
        "esiste; e con 13 e 28 item su sei-otto categorie piu' celle attese restano sotto 5, quindi",
        "il valore oscilla con la prevalenza. Sono riportati per completezza, non come risultato.",
        "",
        "## Locator e unita' documentali",
        "",
        f"- accordo di granularita' del locator: "
        f"{metrics['locator']['granularity_percent_agreement']['agreements']}/28 "
        f"({metrics['locator']['granularity_percent_agreement']['percent_agreement']:.1%})",
        f"- locator a livello di unita' interna: prima {metrics['locator']['first_sub_document_unit']}/28, "
        f"replica {metrics['locator']['replicate_sub_document_unit']}/28",
        f"- unita' documentali distinte: prima {metrics['source_unit']['first_distinct_units']}, "
        f"replica {metrics['source_unit']['replicate_distinct_units']}",
        f"- accordo sulla segmentazione dentro il gruppo: "
        f"{metrics['source_unit']['group_segmentation_percent_agreement']['agreements']}/28",
        "",
        "La differenza sulle unita' e' soprattutto nello spazio degli identificatori: la prima",
        "revisione ne usa uno per fonte, ma il campo `documentary_unit` distingue in prosa braccio,",
        "paziente e modello. L'eccezione e' `evidence:841`, dove le due revisioni ancorano lo stesso",
        "claim a due eventi clinici diversi pur restando in accordo su tutto il resto.",
        "",
        "## Consenso provvisorio",
        "",
        f"Gruppi che soddisfano tutti i criteri: "
        f"{sum(1 for row in group_rows if row['provisional_consensus'])}/13.",
        "",
        "Il criterio e' congiuntivo e severo: stessa decisione, verdetti intervention-level tutti in",
        "accordo, locator sufficienti in entrambe, nessun mapping pending, nessun rischio",
        "aggregate-to-specific, nessun problema di scope. Basta un elemento perche' il gruppo vada",
        "comunque all'adjudicator. Il consenso resta `prototype_only`: non finale, non",
        "hard-filterable, non validato in modo indipendente.",
        "",
    ]
    return "\n".join(lines)


def render_child_report(
    child_rows: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]
) -> str:
    both = [row for row in child_rows if row["child_status"] == "proposed_by_both"]
    first_only = [row for row in child_rows if row["child_status"] == "proposed_by_first_only"]
    replicate_only = [
        row for row in child_rows if row["child_status"] == "proposed_by_replicate_only"
    ]
    neither = [row for row in child_rows if row["child_status"] == "proposed_by_neither"]

    lines = [
        "# Child claim: da 11 a 8 e da 9 a 3",
        "",
        f"`comparison_type = {METHOD_LABELS['comparison_type']}`",
        "",
        "Le due revisioni leggono la stessa fonte quasi sempre allo stesso modo, e propongono",
        "numeri di figli molto diversi. La ragione non e' documentale.",
        "",
        "## I due percorsi",
        "",
        "**Prima revisione: 11 risultati separati, 8 figli.** Undici associazioni classificate",
        "`directly_tested_with_separate_result`; tre appartengono a `evidence:3811`, il cui gruppo",
        "e' chiuso come `insufficient_for_atomicity_decision`, quindi non generano nulla. Restano 8.",
        "",
        "**Replica: 9 risultati separati, 3 figli.** Nove associazioni con risultato separato — le",
        "stesse undici meno le tre di `evidence:3811`, piu' erlotinib in `evidence:11240`, letto sul",
        "braccio placebo + erlotinib. Di queste nove, sei riguardano l'intervento gia' portato dal",
        "parent e ne raffinano il locator invece di creare un claim. Restano 3.",
        "",
        "## Dove nasce la differenza",
        "",
        f"I figli proposti da entrambe sono {len(both)}. Quelli proposti solo dalla prima revisione",
        f"sono {len(first_only)}, e sono **tutti** figli sull'intervento del parent. Quelli proposti",
        f"solo dalla replica sono {len(replicate_only)}.",
        "",
        "Non e' un disaccordo sulla lettura della fonte: su quelle cinque associazioni le due",
        "revisioni concordano su classificazione, direzione, polarita' e risultato. Divergono su",
        "cosa sia il parent. Per la prima revisione il parent e' un contenitore di evidenza e non",
        "un claim terapeutico — e' quanto propone la sua raccomandazione architetturale — quindi",
        "ogni risultato separato ha bisogno del suo figlio, incluso quello del parent. Per la",
        "replica il parent e' gia' il claim di quell'intervento, e duplicarlo creerebbe due",
        "rappresentazioni della stessa affermazione.",
        "",
        "Le due posizioni sono internamente coerenti e incompatibili fra loro. La conseguenza e' che",
        "il numero di figli non e' decidibile guardando le fonti: dipende da una scelta di modello",
        "che va fatta prima, ed e' la prima domanda dei packet di adjudication.",
        "",
        "## Elenco",
        "",
        "### Proposti da entrambe",
        "",
    ]
    lines += [
        f"- `{row['graph_evidence_id']}` — {row['intervention']}" for row in sorted(both, key=str)
    ] or ["- nessuno"]
    lines += ["", "### Proposti solo dalla prima revisione", ""]
    lines += [
        f"- `{row['graph_evidence_id']}` — {row['intervention']} "
        f"(`{row['difference_reason']}`)"
        for row in sorted(first_only, key=str)
    ] or ["- nessuno"]
    lines += ["", "### Proposti solo dalla replica", ""]
    lines += [
        f"- `{row['graph_evidence_id']}` — {row['intervention']}"
        for row in sorted(replicate_only, key=str)
    ] or ["- nessuno"]
    parent_side = [row for row in neither if row["is_parent_intervention"]]
    other_side = [row for row in neither if not row["is_parent_intervention"]]
    lines += [
        "",
        f"### Non proponibili da nessuna delle due: {len(neither)}",
        "",
        f"**{len(parent_side)} sono l'intervento del parent**, gia' rappresentato dal claim",
        "esistente in entrambe le letture. Il motivo documentale che comunque ne impedirebbe",
        "l'autonomia resta registrato come secondario:",
        "",
    ]
    secondary: dict[str, int] = {}
    for row in parent_side:
        key = row["secondary_reason"] or "nessun blocco documentale"
        secondary[key] = secondary.get(key, 0) + 1
    lines += [f"- `{key}`: {value}" for key, value in sorted(secondary.items())]
    lines += [
        "",
        f"**{len(other_side)} sono interventi aggiuntivi** bloccati dalla lettura della fonte:",
        "",
    ]
    reasons: dict[str, int] = {}
    for row in other_side:
        reasons[row["difference_reason"]] = reasons.get(row["difference_reason"], 0) + 1
    lines += [f"- `{key}`: {value}" for key, value in sorted(reasons.items())]
    lines += [
        "",
        "## Nota di consistenza",
        "",
        "La prima revisione conserva i 13 parent e aggiunge 8 figli. Per cinque interventi questo",
        "significa un parent e un figlio con lo stesso intervento, direzione, polarita' e",
        "biomarcatore. La contraddizione si scioglie solo se il parent smette di essere",
        "interrogabile come claim nello stesso passaggio in cui il figlio nasce. E' la proposta",
        "GL-02.",
        "",
    ]
    return "\n".join(lines)


def render_readiness(readiness: Mapping[str, Any], group_rows: Sequence[Mapping[str, Any]]) -> str:
    required = [row for row in group_rows if row["adjudication_required"]]
    consensus = [row for row in group_rows if row["provisional_consensus"]]
    lines = [
        "# Readiness dell'adjudication",
        "",
        f"`comparison_type = {METHOD_LABELS['comparison_type']}`",
        "",
        "| criterio | stato |",
        "| --- | --- |",
    ]
    for key in (
        "reviews_aligned",
        "all_groups_compared",
        "all_interventions_compared",
        "descriptive_agreement_available",
        "independent_agreement_available",
        "provisional_consensus_available",
        "adjudication_packets_complete",
        "guideline_refinement_ready",
        "ready_for_adjudication",
        "ready_for_adapter_migration",
    ):
        lines.append(f"| `{key}` | {str(readiness[key]).lower()} |")

    lines += [
        "",
        "## Cosa e' pronto",
        "",
        f"{len(required)} gruppi hanno un packet completo: contesto documentale, decisione e",
        "razionale di entrambe le revisioni, differenze evidenziate e domande binarie o",
        "categoriali. Nessun packet contiene una decisione precompilata, metriche gold, risultati",
        "di retrieval o suggerimenti basati sul recall.",
        "",
        f"{len(consensus)} gruppo soddisfa i criteri del consenso provvisorio, e resta comunque",
        "`prototype_only`.",
        "",
        "## Cosa resta chiuso",
        "",
        "`independent_agreement_available` e' falso e non puo' diventare vero con questi dati: la",
        "replica non e' indipendente, e nessuna elaborazione successiva puo' produrre indipendenza",
        "a posteriori. Servirebbe una terza revisione condotta senza contaminazione di contesto.",
        "",
        "`ready_for_adapter_migration` resta falso perche' presuppone l'adjudication, che non e'",
        "stata fatta. La domanda strutturale — il parent e' un claim o un contenitore — non e'",
        "decisa, e da sola sposta il numero di statement risultanti.",
        "",
    ]
    return "\n".join(lines)


# --- assemblaggio -------------------------------------------------------------


def build(*, swap: bool = False) -> dict[str, str]:
    inputs = Inputs()
    scope = check_scope(inputs)
    intervention_rows = compare_interventions(inputs, swap=False)
    group_rows = compare_groups(inputs, intervention_rows)
    locator_rows = compare_locators(inputs, intervention_rows)
    unit_rows = compare_source_units(inputs, intervention_rows)
    child_rows = compare_child_claims(inputs, intervention_rows)
    metrics = build_metrics(intervention_rows, group_rows, locator_rows, unit_rows)
    matrix = confusion_matrix(
        (row["first_decision"], row["replicate_decision"]) for row in group_rows
    )
    if swap:
        matrix = confusion_matrix(
            (row["replicate_decision"], row["first_decision"]) for row in group_rows
        )
        intervention_rows = [_swap_row(row) for row in intervention_rows]

    readiness = {
        "reviews_aligned": True,
        "all_groups_compared": len(group_rows) == 13,
        "all_interventions_compared": len(intervention_rows) == 28,
        "descriptive_agreement_available": True,
        "independent_agreement_available": False,
        "provisional_consensus_available": any(row["provisional_consensus"] for row in group_rows),
        "adjudication_packets_complete": True,
        "guideline_refinement_ready": bool(inputs.guidelines),
        "ready_for_adjudication": True,
        "ready_for_adapter_migration": False,
    }

    files: dict[str, str] = {}
    files["comparison_scope.json"] = canonical_dumps(
        {
            "comparison_version": COMPARISON_VERSION,
            "comparison_branch": COMPARISON_BRANCH,
            "start_sha": START_SHA,
            "environment": ENVIRONMENT,
            "scope_check": scope,
            "alignment_keys": {
                "intervention_level": [
                    "graph_evidence_id",
                    "source_id",
                    "normalized_intervention",
                    "source_unit_id (registrato, non usato per l'allineamento perche' le due"
                    " revisioni segmentano le unita' in modo diverso)",
                ],
                "group_level": ["graph_evidence_id", "source_id"],
                "positional_alignment_used": False,
            },
            "input_hashes": {
                "first_review": tree_digest(FIRST),
                "blinded_replicate": tree_digest(REPLICATE),
                "second_review_packets": tree_digest(PACKETS),
                "local_sources": {
                    path: digest(REPO_ROOT / path) for path in LOCAL_SOURCES
                },
                "frozen_artifacts": {path: digest(REPO_ROOT / path) for path in FROZEN_ARTIFACTS},
                "gold_artifacts": {path: digest(REPO_ROOT / path) for path in GOLD_ARTIFACTS},
            },
            "gold_content_read": False,
            "gold_hashed_for_integrity_only": True,
            "new_sources_read": False,
            "original_annotations_modified": False,
            **METHOD_LABELS,
        }
    )
    files["review_alignment.jsonl"] = canonical_jsonl(
        [
            {
                "comparison_id": row["comparison_id"],
                "graph_evidence_id": row["graph_evidence_id"],
                "source_id": row["source_id"],
                "normalized_intervention": row["normalized_intervention"],
                "intervention_as_written": row["intervention"],
                "first_source_unit_id": row["first_source_unit_id"],
                "replicate_source_unit_id": row["replicate_source_unit_id"],
                "aligned_by": "deterministic_key",
                **METHOD_LABELS,
            }
            for row in intervention_rows
        ],
        key="comparison_id",
    )
    files["intervention_level_comparison.jsonl"] = canonical_jsonl(
        intervention_rows, key="comparison_id"
    )
    files["group_level_comparison.jsonl"] = canonical_jsonl(group_rows, key="graph_evidence_id")
    files["group_confusion_matrix.json"] = canonical_dumps(
        {
            "rows": "first_review" if not swap else "blinded_replicate",
            "columns": "blinded_replicate" if not swap else "first_review",
            "matrix": matrix,
            "total": sum(sum(cells.values()) for cells in matrix.values()),
            **METHOD_LABELS,
        }
    )
    files["descriptive_agreement_metrics.json"] = canonical_dumps(metrics)
    files["locator_comparison.jsonl"] = canonical_jsonl(locator_rows, key="comparison_id")
    files["source_unit_comparison.jsonl"] = canonical_jsonl(unit_rows, key="comparison_id")
    files["child_claim_comparison.jsonl"] = canonical_jsonl(child_rows, key="comparison_id")
    files["disagreement_taxonomy.json"] = canonical_dumps(
        {
            "cause_vocabulary": list(DISAGREEMENT_CAUSES),
            "child_difference_reasons": list(CHILD_DIFFERENCE_REASONS),
            "primary_cause_counts": count_causes(intervention_rows),
            "records": sorted(
                (
                    {
                        "graph_evidence_id": row["graph_evidence_id"],
                        "intervention": row["intervention"],
                        "verdict": row["verdict"],
                        "primary_cause": row["primary_cause"],
                        "secondary_causes": row["secondary_causes"],
                        "note": row["cause_note"],
                    }
                    for row in intervention_rows
                    if row["primary_cause"]
                ),
                key=lambda item: (item["graph_evidence_id"], item["intervention"]),
            ),
            **METHOD_LABELS,
        }
    )
    files["priority_case_analysis.jsonl"] = canonical_jsonl(
        [{**row, **METHOD_LABELS} for row in inputs.priority], key="case_id"
    )
    files["provisional_consensus_groups.jsonl"] = canonical_jsonl(
        [
            {
                "graph_evidence_id": row["graph_evidence_id"],
                "statement_id": row["statement_id"],
                "agreed_decision": row["first_decision"],
                "consensus_kind": "provisional_consensus_without_adjudication",
                "propagation_policy": "prototype_only",
                "final": False,
                "hard_filterable": False,
                "independently_validated": False,
                "corpus_modified": False,
                **METHOD_LABELS,
            }
            for row in group_rows
            if row["provisional_consensus"]
        ],
        key="graph_evidence_id",
    )
    files["adjudication_required_groups.jsonl"] = canonical_jsonl(
        [
            {
                "graph_evidence_id": row["graph_evidence_id"],
                "statement_id": row["statement_id"],
                "adjudication_packet_id": f"ADJ-{row['graph_evidence_id'].replace(':', '-')}",
                "first_decision": row["first_decision"],
                "replicate_decision": row["replicate_decision"],
                "decision_match": row["decision_match"],
                "disagreeing_interventions": row["disagreeing_interventions"],
                "pending_mapping_present": row["pending_mapping_present"],
                "scope_issue_present": row["scope_issue_present"],
                "all_locators_sufficient": row["all_locators_sufficient"],
                **METHOD_LABELS,
            }
            for row in group_rows
            if row["adjudication_required"]
        ],
        key="graph_evidence_id",
    )
    files["guideline_refinement_proposals.jsonl"] = canonical_jsonl(
        [{**row, **METHOD_LABELS} for row in inputs.guidelines], key="proposal_id"
    )
    files.update(build_adjudication_packets(inputs, group_rows, intervention_rows))
    files["MULTI_INTERVENTION_REVIEW_COMPARISON.md"] = render_comparison_report(
        metrics, group_rows, matrix
    )
    files["CHILD_CLAIM_DISAGREEMENT_REPORT.md"] = render_child_report(child_rows, metrics)
    files["ADJUDICATION_READINESS.md"] = render_readiness(readiness, group_rows)
    files["comparison_manifest.json"] = canonical_dumps(
        {
            "comparison_version": COMPARISON_VERSION,
            "readiness": readiness,
            "counts": {
                "groups_compared": len(group_rows),
                "interventions_compared": len(intervention_rows),
                "adjudication_packets": sum(
                    1 for name in files if name.startswith("adjudication_packets/")
                ),
                "provisional_consensus_groups": sum(
                    1 for row in group_rows if row["provisional_consensus"]
                ),
                "guideline_proposals": len(inputs.guidelines),
                "priority_cases": len(inputs.priority),
            },
            "artifact_sha256": {name: sha256_text(content) for name, content in sorted(files.items())},
            **METHOD_LABELS,
        }
    )
    return files


def count_causes(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row["primary_cause"]:
            counts[row["primary_cause"]] = counts.get(row["primary_cause"], 0) + 1
    return dict(sorted(counts.items()))


def write(files: Mapping[str, str], output_dir: Path) -> None:
    for name in sorted(files):
        path = output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[name], encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--swap-review-order", action="store_true")
    args = parser.parse_args()
    files = build(swap=args.swap_review_order)
    write(files, args.output_dir)
    print(f"scritti {len(files)} artefatti in {args.output_dir}")


if __name__ == "__main__":
    main()
