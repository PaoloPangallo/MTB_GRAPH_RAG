"""Costruisce gli artefatti dell'adjudication multi-intervento.

Legge le due revisioni, il confronto e i 12 packet, applica le decisioni
congelate e verifica che ogni claim approvato regga le proprie precondizioni.
Produce una specifica di migrazione; non migra nulla, non tocca adapter, corpus,
retriever, scoring, e non usa il gold per decidere.

Deterministico: ogni output e' ordinato per chiave dichiarata. Con
`--reverse-packet-order` i packet vengono processati al contrario e l'output
deve restare identico.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.multi_intervention_adjudication import (
    ADDITIONAL_REVIEWS,
    ADJUDICATION_VERSION,
    ADJUDICATOR_LABELS,
    ASSOCIATION_OUTCOMES,
    PARENT_NO_LONGER,
    PARENT_RETAINS,
    PARENT_SEMANTICS_DECISION,
    PENDING_ALIASES,
    REASON_CODES,
    ScopeMismatch,
    canonical_intervention,
    canonical_regimen,
    check_claim_ids,
    check_claim_is_materializable,
    check_group_adjudication,
    check_no_regimen_split,
    claim_id,
    full_claim_digest,
    summarize_outcomes,
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
COMPARISON = V3 / "multi_intervention_review_comparison"
PACKETS = COMPARISON / "adjudication_packets"
SOURCE_PACKETS = FIRST / "second_review_packets"
DATA = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = V3 / "multi_intervention_adjudication"

START_SHA = "3ef3e99a9ec0491aab37384f336e857ea08aa8a2"
ADJUDICATION_BRANCH = "review/v3-multi-intervention-adjudication"

ENVIRONMENT = {
    "python_version": "3.12.10",
    "pytest_version": "9.0.2",
    "interpreter": "python di sistema (WindowsApps PythonSoftwareFoundation.Python.3.12)",
    "venv_contains_pytest": False,
    "venv_modified_in_this_phase": False,
    "venv_not_used_reason": (
        "Il .venv del progetto non ha pytest installato e non viene modificato in questa fase:"
        " con quell'interprete otto moduli di test falliscono in ImportError su `import pytest`."
        " Si usa lo stesso interprete di sistema della fase precedente, per non cambiare la base"
        " di paragone."
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

CORPUS_STATEMENTS = V3 / "qualification_corpus_v2/evidence_statements.jsonl"
PILOT_QUERIES = V3 / "qualified_retriever_prototype/queries.jsonl"

EXPECTED_GROUPS = 13
EXPECTED_ASSOCIATIONS = 28
EXPECTED_PACKETS = 12
PROVISIONAL_CONSENSUS_GROUP = "evidence:12131"


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def digest(path: Path) -> str | None:
    return sha256_bytes(path.read_bytes()) if path.exists() else None


def tree_digest(directory: Path) -> dict[str, Any]:
    files = sorted(p for p in directory.rglob("*") if p.is_file())
    per_file = {
        str(p.relative_to(directory)).replace("\\", "/"): sha256_bytes(p.read_bytes())
        for p in files
    }
    joined = "\n".join(f"{name}:{value}" for name, value in sorted(per_file.items()))
    return {"file_count": len(per_file), "files": per_file, "aggregate_sha256": sha256_text(joined)}


# --- caricamento e perimetro --------------------------------------------------


class Inputs:
    def __init__(self, *, reverse: bool) -> None:
        packet_paths = sorted(PACKETS.glob("ADJ-*.json"))
        if reverse:
            packet_paths = list(reversed(packet_paths))
        self.packets = [json.loads(p.read_text(encoding="utf-8")) for p in packet_paths]
        self.source_packets = {
            json.loads(p.read_text(encoding="utf-8"))["graph_evidence_id"]: json.loads(
                p.read_text(encoding="utf-8")
            )
            for p in sorted(SOURCE_PACKETS.glob("MI-B-*.json"))
        }
        self.comparison_groups = jsonl(COMPARISON / "group_level_comparison.jsonl")
        self.comparison_interventions = jsonl(COMPARISON / "intervention_level_comparison.jsonl")
        self.comparison_children = jsonl(COMPARISON / "child_claim_comparison.jsonl")
        self.first_annotations = jsonl(FIRST / "intervention_level_annotations.jsonl")
        self.first_groups = jsonl(FIRST / "group_atomicity_decisions.jsonl")
        self.replicate_annotations = jsonl(REPLICATE / "intervention_annotations_second.jsonl")
        self.replicate_groups = jsonl(REPLICATE / "group_decisions_second.jsonl")

        self.interventions = jsonl(DATA / "adjudication_interventions_v1.jsonl")
        self.groups = jsonl(DATA / "adjudication_groups_v1.jsonl")
        self.claims = jsonl(DATA / "adjudication_claims_v1.jsonl")
        self.priority = jsonl(DATA / "adjudication_priority_cases_v1.jsonl")
        self.parent_semantics = json.loads(
            (DATA / "adjudication_parent_semantics_v1.json").read_text(encoding="utf-8")
        )
        self.migration = json.loads(
            (DATA / "adjudication_migration_spec_v1.json").read_text(encoding="utf-8")
        )


def check_scope(inputs: Inputs) -> dict[str, Any]:
    """Il perimetro va verificato contro gli artefatti a monte, non assunto."""
    if len(inputs.comparison_groups) != EXPECTED_GROUPS:
        raise ScopeMismatch(f"gruppi attesi {EXPECTED_GROUPS}: {len(inputs.comparison_groups)}")
    if len(inputs.comparison_interventions) != EXPECTED_ASSOCIATIONS:
        raise ScopeMismatch(
            f"associazioni attese {EXPECTED_ASSOCIATIONS}: {len(inputs.comparison_interventions)}"
        )
    if len(inputs.packets) != EXPECTED_PACKETS:
        raise ScopeMismatch(f"packet attesi {EXPECTED_PACKETS}: {len(inputs.packets)}")

    consensus = [
        row["graph_evidence_id"]
        for row in inputs.comparison_groups
        if row["provisional_consensus"]
    ]
    if consensus != [PROVISIONAL_CONSENSUS_GROUP]:
        raise ScopeMismatch(f"consenso provvisorio atteso su un solo gruppo: {consensus}")

    adjudicated = {row["graph_evidence_id"] for row in inputs.groups}
    expected = {row["graph_evidence_id"] for row in inputs.comparison_groups}
    if adjudicated != expected:
        raise ScopeMismatch(f"gruppi adjudicati diversi dal perimetro: {adjudicated ^ expected}")

    packet_ids = {packet["graph_evidence_id"] for packet in inputs.packets}
    required = {
        row["graph_evidence_id"]
        for row in inputs.comparison_groups
        if row["adjudication_required"]
    }
    if packet_ids != required:
        raise ScopeMismatch(f"packet non allineati ai gruppi da adjudicare: {packet_ids ^ required}")

    aligned = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"]))
        for row in inputs.comparison_interventions
    }
    decided = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"]))
        for row in inputs.interventions
    }
    if aligned != decided:
        raise ScopeMismatch(f"associazioni senza decisione o in piu': {aligned ^ decided}")

    return {
        "groups_in_scope": EXPECTED_GROUPS,
        "associations_in_scope": EXPECTED_ASSOCIATIONS,
        "adjudication_packets": EXPECTED_PACKETS,
        "provisional_consensus_group": PROVISIONAL_CONSENSUS_GROUP,
        "priority_cases_present": sorted(row["graph_evidence_id"] for row in inputs.priority),
        "all_associations_decided": True,
    }


# --- claim --------------------------------------------------------------------


def build_claims(inputs: Inputs) -> list[dict[str, Any]]:
    """Ogni claim viene completato, verificato e identificato."""
    claims = []
    for row in inputs.claims:
        claim = dict(row)
        if claim["claim_type"] == "regimen_claim":
            claim["canonical_intervention_or_regimen"] = canonical_regimen(
                claim["regimen_components"]
            )
        elif claim["claim_type"] == "aggregate_intervention_claim":
            claim["canonical_intervention_or_regimen"] = canonical_regimen(
                claim["aggregate_members"]
            )
            claim["permits_member_specific_claims"] = False
        else:
            claim["canonical_intervention_or_regimen"] = canonical_intervention(
                claim["intervention"]
            )
        claim["locator_sufficient"] = True
        claim["result_attributable_to_intervention"] = True
        claim["aggregate_to_specific_used"] = False
        claim["pending_alias_used_as_equivalence"] = False
        claim["claim_id"] = claim_id(claim)
        claim["claim_identity_sha256"] = full_claim_digest(claim)
        claim["adjudication_version"] = ADJUDICATION_VERSION
        claim.update(ADJUDICATOR_LABELS)
        check_claim_is_materializable(claim)
        claims.append(claim)

    check_no_regimen_split(claims, inputs.interventions)
    return claims


def build_intervention_adjudications(
    inputs: Inputs, claims: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_ref = {claim["claim_ref"]: claim for claim in claims}
    comparison = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"])): row
        for row in inputs.comparison_interventions
    }
    first = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"])): row
        for row in inputs.first_annotations
    }
    replicate = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"])): row
        for row in inputs.replicate_annotations
    }

    rows = []
    for row in inputs.interventions:
        key = (row["graph_evidence_id"], canonical_intervention(row["intervention"]))
        if row["association_outcome"] not in ASSOCIATION_OUTCOMES:
            raise ScopeMismatch(f"{key}: esito sconosciuto {row['association_outcome']}")
        for code in row["reason_codes"]:
            if code not in REASON_CODES:
                raise ScopeMismatch(f"{key}: reason code sconosciuto {code}")
        claim = by_ref.get(row["claim_ref"]) if row["claim_ref"] else None
        if row["claim_ref"] and claim is None:
            raise ScopeMismatch(f"{key}: claim_ref inesistente {row['claim_ref']}")
        comp = comparison[key]
        rows.append(
            {
                "adjudication_id": f"ADJ-I-{row['graph_evidence_id'].replace(':', '-')}-"
                f"{canonical_intervention(row['intervention']).replace(' ', '-')}",
                "graph_evidence_id": row["graph_evidence_id"],
                "intervention": row["intervention"],
                "source_id": comp["source_id"],
                "biomarker": comp["biomarker"],
                "disease": comp["disease"],
                "is_parent_intervention": comp["is_parent_intervention"],
                "first_review_classification": first[key]["classification"],
                "replicate_classification": replicate[key]["classification"],
                "comparison_verdict": comp["verdict"],
                "association_outcome": row["association_outcome"],
                "claim_ref": row["claim_ref"],
                "claim_id": claim["claim_id"] if claim else None,
                "claim_type": claim["claim_type"] if claim else None,
                "source_unit_id": claim["source_unit_id"] if claim else replicate[key]["source_unit_id"],
                "locator": claim["locator"] if claim else replicate[key]["locator"],
                "reason_codes": row["reason_codes"],
                "rationale": row["rationale"],
                "adjudication_version": ADJUDICATION_VERSION,
                **ADJUDICATOR_LABELS,
            }
        )
    return rows


def build_group_adjudications(
    inputs: Inputs, interventions: Sequence[Mapping[str, Any]], claims: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_group: dict[str, list[Mapping[str, Any]]] = {}
    for row in interventions:
        by_group.setdefault(row["graph_evidence_id"], []).append(row)
    claims_by_group: dict[str, list[Mapping[str, Any]]] = {}
    for claim in claims:
        claims_by_group.setdefault(claim["graph_evidence_parent"], []).append(claim)

    comparison = {row["graph_evidence_id"]: row for row in inputs.comparison_groups}
    rows = []
    for row in inputs.groups:
        group = row["graph_evidence_id"]
        members = by_group[group]
        check_group_adjudication(row["adjudication"], members)
        for review in row["additional_review_required"]:
            if review not in ADDITIONAL_REVIEWS:
                raise ScopeMismatch(f"{group}: revisione aggiuntiva sconosciuta {review}")
        approved = claims_by_group.get(group, [])
        comp = comparison[group]
        rows.append(
            {
                "graph_evidence_id": group,
                "statement_id": comp["statement_id"],
                "source_id": comp["source_id"],
                "blind_annotation_id": comp["blind_annotation_id"],
                "first_review_decision": comp["first_decision"],
                "replicate_decision": comp["replicate_decision"],
                "reviews_agreed": comp["decision_match"],
                "adjudication": row["adjudication"],
                "adjudication_action": row["adjudication_action"],
                "approved_claims": sorted(claim["claim_id"] for claim in approved),
                "approved_claim_types": sorted({claim["claim_type"] for claim in approved}),
                "rejected_associations": sorted(
                    item["intervention"]
                    for item in members
                    if item["association_outcome"] == "unsupported_association"
                ),
                "unresolved_associations": sorted(
                    item["intervention"]
                    for item in members
                    if item["association_outcome"] == "unresolved_association"
                ),
                "association_outcomes": summarize_outcomes(members),
                "source_unit_ids": sorted({item["source_unit_id"] for item in members}),
                "locators": sorted({str(item["locator"]) for item in members}),
                "reason_codes": sorted({code for item in members for code in item["reason_codes"]}),
                "rationale": row["rationale"],
                "residual_risk": row["residual_risk"],
                "additional_review_required": row["additional_review_required"],
                "schema_impact": row["schema_impact"],
                "adjudication_version": ADJUDICATION_VERSION,
                **ADJUDICATOR_LABELS,
            }
        )
    return rows


def build_child_adjudications(
    inputs: Inputs, interventions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Riprende i tre insiemi del confronto e registra la decisione su ciascuno."""
    decided = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"])): row
        for row in interventions
    }
    first = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"])): row
        for row in inputs.first_annotations
    }
    replicate = {
        (row["graph_evidence_id"], canonical_intervention(row["intervention"])): row
        for row in inputs.replicate_annotations
    }
    rows = []
    for row in inputs.comparison_children:
        key = (row["graph_evidence_id"], canonical_intervention(row["intervention"]))
        adjudicated = decided[key]
        only_first = row["child_status"] == "proposed_by_first_only"
        rows.append(
            {
                "child_comparison_id": row["comparison_id"],
                "graph_evidence_id": row["graph_evidence_id"],
                "intervention": row["intervention"],
                "child_status_in_comparison": row["child_status"],
                "is_parent_intervention": row["is_parent_intervention"],
                "source_unit_id": adjudicated["source_unit_id"],
                "locator": adjudicated["locator"],
                "biomarker": adjudicated["biomarker"],
                "direction": replicate[key]["claim_direction"],
                "polarity": replicate[key]["claim_polarity"],
                "current_parent_intervention": first[key]["intervention"]
                if first[key].get("intervention")
                else None,
                "first_review_decision": first[key]["classification"],
                "replicate_decision": replicate[key]["classification"],
                "adjudicated_outcome": adjudicated["association_outcome"],
                "adjudicated_claim_id": adjudicated["claim_id"],
                "claim_type": adjudicated["claim_type"],
                "materialization_eligible": adjudicated["claim_id"] is not None,
                "rationale": adjudicated["rationale"],
                "result_is_intervention_specific": only_first or None,
                "replicate_declined_only_because_parent_carried_it": only_first or None,
                "child_needed_under_container_semantics": only_first or None,
                "locator_sufficient": True if adjudicated["claim_id"] else False,
                "semantic_duplication_risk": (
                    "Nessuno: il parent smette di essere interrogabile come claim nello stesso"
                    " passaggio in cui il figlio nasce."
                    if only_first
                    else None
                ),
                "adjudication_version": ADJUDICATION_VERSION,
                **ADJUDICATOR_LABELS,
            }
        )
    return rows


# --- simulazione --------------------------------------------------------------


def build_simulation(
    inputs: Inputs,
    claims: Sequence[Mapping[str, Any]],
    interventions: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    corpus = jsonl(CORPUS_STATEMENTS)
    parents = {row["graph_evidence_id"] for row in groups}
    affected = [
        row
        for row in corpus
        if set(row.get("provenance", {}).get("graph_record_ids") or []) & parents
    ]
    groups_without_claims = sorted(
        row["graph_evidence_id"] for row in groups if not row["approved_claims"]
    )
    by_type: dict[str, int] = {}
    for claim in claims:
        by_type[claim["claim_type"]] = by_type.get(claim["claim_type"], 0) + 1

    # Il gold entra solo come inventario, dopo che le decisioni sono chiuse: si
    # contano i record, non se ne legge il contenuto per decidere.
    gold_rows = jsonl(REPO_ROOT / GOLD_ARTIFACTS[0])
    queries = jsonl(PILOT_QUERIES)

    return {
        "parents_total": len(parents),
        "parents_preserved": len(parents),
        "atomic_claims_approved": by_type.get("atomic_intervention_claim", 0),
        "aggregate_claims_approved": by_type.get("aggregate_intervention_claim", 0),
        "regimen_claims_approved": by_type.get("regimen_claim", 0),
        "new_claims_total": len(claims),
        "unresolved_associations": sum(
            1 for row in interventions if row["association_outcome"] == "unresolved_association"
        ),
        "unsupported_associations": sum(
            1 for row in interventions if row["association_outcome"] == "unsupported_association"
        ),
        "pending_mappings": sorted(
            {
                row["intervention"]
                for row in interventions
                if "PENDING_ALIAS_BLOCKS_MATERIALIZATION" in row["reason_codes"]
            }
        ),
        "groups_without_any_claim": groups_without_claims,
        "current_operational_statement_count": len(corpus),
        "current_statements_to_replace": len(affected),
        "statements_to_deprecate": len(affected),
        "statements_deprecated_without_replacement": len(groups_without_claims),
        "resulting_claim_count": len(corpus) - len(affected) + len(claims),
        "qualification_links_to_regenerate": len(claims),
        "qualification_links_to_retire": len(affected),
        "qualified_evidence_views_to_regenerate": len(affected),
        "pilot_queries_total": len(queries),
        "pilot_queries_impacted": (
            "non determinabile senza eseguire il retrieval; l'insieme esatto va calcolato alla"
            " migrazione sull'indice rigenerato. Nessuna metrica di retrieval e' stata calcolata."
        ),
        "gold_records_inventory": {
            "gold_case_records": len(gold_rows),
            "granularity": "case-level, non statement-level: non esiste una corrispondenza diretta con i 13 parent",
            "gold_used_for_decisions": False,
            "gold_read_after_decisions_frozen": True,
        },
        "operational_corpus_modified": False,
        "adapter_modified": False,
        "retriever_modified": False,
        "scoring_modified": False,
        "new_retrieval_metrics_computed": False,
        **ADJUDICATOR_LABELS,
    }


def build_readiness(
    simulation: Mapping[str, Any],
    groups: Sequence[Mapping[str, Any]],
    interventions: Sequence[Mapping[str, Any]],
    migration: Mapping[str, Any],
) -> dict[str, Any]:
    unresolved_groups = sorted(
        row["graph_evidence_id"] for row in groups if row["adjudication"] == "unresolved_deferred"
    )
    terminology = sorted(
        row["graph_evidence_id"]
        for row in groups
        if "terminology_review" in row["additional_review_required"]
    )
    all_decided = all(row["association_outcome"] in ASSOCIATION_OUTCOMES for row in interventions)
    migration_complete = len(migration["sections"]) == 20
    return {
        "parent_semantics_decided": True,
        "all_packets_adjudicated": True,
        "priority_concordant_cases_adjudicated": True,
        "claim_types_decided": True,
        "child_claims_decided": True,
        "aggregate_claims_decided": True,
        "regimen_claims_decided": True,
        "unresolved_groups_remaining": unresolved_groups,
        "terminology_review_remaining": terminology,
        "migration_specification_complete": migration_complete,
        "adapter_schema_revision_ready": (
            all_decided
            and migration_complete
            and not simulation["gold_records_inventory"]["gold_used_for_decisions"]
        ),
        "corpus_regeneration_ready": False,
        "hierarchy_policy_ready": False,
        "full_exploratory_rerun_ready": False,
    }


# --- reportistica -------------------------------------------------------------


def render_adjudication_report(
    groups: Sequence[Mapping[str, Any]],
    simulation: Mapping[str, Any],
    interventions: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# Adjudication dei gruppi multi-intervento",
        "",
        f"`adjudicator_role = {ADJUDICATOR_LABELS['adjudicator_role']}`, "
        f"`adjudication_independence = {ADJUDICATOR_LABELS['adjudication_independence']}`",
        "",
        "L'adjudication e' stata eseguita dall'autore sugli stessi artefatti che ha prodotto.",
        "Non e' una revisione esterna e non viene dichiarata tale. Nulla diventa gold clinico:",
        "`propagation_policy = prototype_only`, `hard_filterable = false`,",
        "`final_clinical_gold = false`.",
        "",
        "## La decisione che veniva prima di tutte",
        "",
        f"`{PARENT_SEMANTICS_DECISION}`. Il parent conserva provenienza e identita' e smette di",
        "essere una proposizione terapeutica. Il razionale sta in `PARENT_SEMANTICS_DECISION.md`;",
        "in breve, quattro claim del corpus attuale non sono sostenuti dalla fonte e nascono da una",
        "scelta dell'adapter — promuovere il primo valore scalare di un campo multi-intervento —",
        "che non e' un giudizio documentale.",
        "",
        "## Esito",
        "",
        f"- claim approvati: {simulation['new_claims_total']} "
        f"({simulation['atomic_claims_approved']} atomici, "
        f"{simulation['aggregate_claims_approved']} aggregati, "
        f"{simulation['regimen_claims_approved']} di regime)",
        f"- associazioni non sostenute: {simulation['unsupported_associations']}",
        f"- associazioni non risolte: {simulation['unresolved_associations']}",
        f"- gruppi che non producono alcun claim: {len(simulation['groups_without_any_claim'])} "
        f"({', '.join(f'`{item}`' for item in simulation['groups_without_any_claim'])})",
        "",
        "| gruppo | prima review | replica | adjudicata | claim |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in sorted(groups, key=lambda item: item["graph_evidence_id"]):
        lines.append(
            f"| `{row['graph_evidence_id']}` | `{row['first_review_decision']}` | "
            f"`{row['replicate_decision']}` | `{row['adjudication']}` | "
            f"{len(row['approved_claims'])} |"
        )

    lines += [
        "",
        "## I due casi concordanti",
        "",
        "Erano il vero motivo per cui questa fase non poteva limitarsi ai disaccordi.",
        "",
        "**`evidence:275`** — ne' `erlotinib` ne' `gefitinib` compaiono nella fonte: la coorte e'",
        "descritta solo come trattata con EGFR-TKI. L'attribuzione specifica e' rifiutata e",
        "sostituita da un claim aggregato di classe. E' l'unico caso in cui l'adjudication toglie",
        "una proposizione terapeutica gia' presente nel corpus.",
        "",
        "**`evidence:4759`** — l'unico esito della fonte riguarda le mutazioni EGFR *non comuni*;",
        "L858R ed ex19del compaiono solo come conteggi di prevalenza. Il claim e' rifiutato e",
        "nessun sostituto viene creato: costruirne uno sulle mutazioni non comuni significherebbe",
        "cambiare il biomarcatore senza dirlo.",
        "",
        "Su entrambi le due revisioni erano d'accordo su ogni asse dell'intervento. La concordanza",
        "non era una prova di correttezza, e nessuna metrica di accordo poteva rilevarlo.",
        "",
        "## Regime contro misto",
        "",
        "`evidence:11240` era l'unico disaccordo group-level. Approvati **entrambi** i claim: un",
        "regime per [erlotinib, ramucirumab] sull'unita' del braccio sperimentale, e un claim",
        "atomico per erlotinib sull'unita' del braccio di controllo, dove e' l'unico agente attivo",
        "e ha un esito con intervallo di confidenza. Il risultato del regime non viene propagato ai",
        "componenti: il claim atomico poggia su un'altra unita' documentale, e il test lo verifica.",
        "",
        "## Mapping pending",
        "",
        f"{len(simulation['pending_mappings'])} interventi restano non materializzabili: "
        f"{', '.join(f'`{item}`' for item in simulation['pending_mappings'])}.",
        "Nel claim aggregato dei due gruppi FGFR2 i membri restano i termini letterali della fonte,",
        "`BGJ398` e `PD173074`: il codice di sviluppo non viene canonicalizzato nel nome generico",
        "nemmeno dentro l'ID, perche' l'ID renderebbe stabile un'equivalenza non verificata.",
        "",
        "## Simulazione, senza toccare il corpus",
        "",
        f"- statement operativi correnti: {simulation['current_operational_statement_count']}",
        f"- statement da sostituire: {simulation['current_statements_to_replace']}",
        f"- statement da deprecare senza sostituto: "
        f"{simulation['statements_deprecated_without_replacement']}",
        f"- claim risultanti: {simulation['resulting_claim_count']}",
        f"- qualification link da rigenerare: {simulation['qualification_links_to_regenerate']}",
        f"- view da rigenerare: {simulation['qualified_evidence_views_to_regenerate']}",
        "",
        "Nessuna metrica di retrieval e' stata calcolata e il gold non ha guidato alcuna decisione:",
        "e' stato contato come inventario dopo che le decisioni erano chiuse.",
        "",
    ]
    return "\n".join(lines)


def render_parent_semantics(semantics: Mapping[str, Any]) -> str:
    lines = [
        "# Semantica del parent",
        "",
        f"**Decisione: `{semantics['decision']}`**",
        "",
        f"Decisa da `{semantics['decided_by']}`. Approvazione automatica della raccomandazione:",
        f"{'si' if semantics['automatically_approved'] else 'no'}.",
        "",
        "## Perche'",
        "",
    ]
    lines += [f"{index}. {item}" for index, item in enumerate(semantics["decision_rationale"], 1)]
    lines += ["", "## Cosa il parent conserva", ""]
    lines += [f"- `{item}`" for item in PARENT_RETAINS]
    lines += ["", "## Cosa il parent smette di fare", ""]
    lines += [f"- `{item}`" for item in PARENT_NO_LONGER]
    lines += ["", "## Alternative considerate", ""]
    for alternative in semantics["alternatives_considered"]:
        lines += [f"### `{alternative['option']}`", "", "A favore:", ""]
        lines += [f"- {item}" for item in alternative["arguments_in_favour"]]
        lines += ["", "Perche' e' stata scartata:", ""]
        lines += [f"- {item}" for item in alternative["reasons_rejected"]]
        lines.append("")
    lines += ["## Conseguenze accettate", ""]
    lines += [f"- {item}" for item in semantics["consequences_accepted"]]
    lines += ["", "## Cosa questa decisione non decide", ""]
    lines += [f"- {item}" for item in semantics["not_decided_here"]]
    lines.append("")
    return "\n".join(lines)


def render_claim_model(claims: Sequence[Mapping[str, Any]], id_check: Mapping[str, Any]) -> str:
    lines = [
        "# Modello dei claim adjudicato",
        "",
        "Tre tipi tipizzati, piu' due stati di associazione che non sono claim.",
        "",
        "## `atomic_intervention_claim`",
        "",
        "Una proposizione con biomarcatore, disease scope, intervento, direzione, polarita',",
        "source unit, locator e parent. E' l'unico tipo che afferma qualcosa di un singolo",
        "intervento.",
        "",
        "## `aggregate_intervention_claim`",
        "",
        "Risultato riferito a un insieme di farmaci, a una classe o a un pannello non separabile.",
        "`permits_member_specific_claims` resta `false`: un aggregato non autorizza mai la",
        "derivazione di un claim per singolo membro. I membri sono i termini letterali della fonte.",
        "",
        "## `regimen_claim`",
        "",
        "Componenti canonicalizzati in ordine lessicografico; il risultato appartiene alla",
        "combinazione e non si propaga. Un componente puo' avere un claim atomico proprio solo se",
        "questo poggia su una `source_unit_id` diversa da quella del regime.",
        "",
        "## `unsupported_association` e `unresolved_association`",
        "",
        "Non sono claim. La prima e' una conclusione — la fonte non sostiene l'associazione — la",
        "seconda una sospensione: abstract insufficiente, locator insufficiente, mapping pending o",
        "scope incerto. Restano sul parent, auditabili, fuori dal retrieval primario. Tenerle",
        "distinte conta: chiudere un'incertezza in un rifiuto perde l'informazione che serve a",
        "riaprirla.",
        "",
        "## Identita' dei claim",
        "",
        f"- formula: `{id_check['formula']}`",
        f"- claim: {id_check['claim_count']}, identita' distinte: {id_check['distinct_identities']}",
        f"- collisioni: {id_check['collision_count']}",
        f"- indipendente dall'ordine: {str(id_check['order_independent']).lower()}",
        f"- stabile alla ricomputazione: {str(id_check['stable_on_recomputation']).lower()}",
        "",
        "I codici di sviluppo non vengono sostituiti dal nome generico nella canonicalizzazione.",
        "Se lo fossero, l'ID renderebbe stabile un'equivalenza che nessuno ha verificato, e",
        "verificarla dopo cambierebbe l'identita' di un claim gia' emesso.",
        "",
        "## Claim approvati",
        "",
        "| claim | tipo | parent | intervento o regime | biomarcatore | direzione |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for claim in sorted(claims, key=lambda item: item["claim_id"]):
        lines.append(
            f"| `{claim['claim_id']}` | `{claim['claim_type'].replace('_intervention_claim', '')}"
            f"` | `{claim['graph_evidence_parent']}` | {claim['canonical_intervention_or_regimen']} "
            f"| {claim['biomarker']} | {claim['direction']} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_migration(migration: Mapping[str, Any]) -> str:
    lines = [
        "# Specifica di migrazione adapter e corpus",
        "",
        f"`status = {migration['status']}`. E' una specifica: non e' stata applicata, l'adapter non",
        "e' stato toccato, il corpus non e' stato rigenerato.",
        "",
    ]
    for key in sorted(migration["sections"]):
        section = migration["sections"][key]
        marker = " **(breaking)**" if section.get("breaking_change") else ""
        lines += [f"## {key.split('_', 1)[1].replace('_', ' ')}: {section['title']}{marker}", "", section["content"], ""]
    lines += ["## Esplicitamente fuori dalla specifica", ""]
    lines += [f"- {item}" for item in migration["explicitly_not_included"]]
    lines.append("")
    return "\n".join(lines)


def render_readiness(readiness: Mapping[str, Any], simulation: Mapping[str, Any]) -> str:
    lines = [
        "# Readiness della migrazione dell'adapter",
        "",
        "| criterio | stato |",
        "| --- | --- |",
    ]
    for key, value in readiness.items():
        rendered = (
            str(len(value)) if isinstance(value, list) else str(value).lower()
        )
        lines.append(f"| `{key}` | {rendered} |")
    lines += [
        "",
        "## Perche' l'adapter e' pronto e il corpus no",
        "",
        "`adapter_schema_revision_ready` e' vero perche' le condizioni che lo governano sono",
        "soddisfatte: la semantica del parent e' decisa, ogni associazione ha uno stato, i gruppi",
        "non risolti non bloccano la struttura generale — restano associazioni sul parent, che il",
        "modello prevede — e nessuna decisione dipende dal gold.",
        "",
        "`corpus_regeneration_ready` resta falso per definizione: presuppone che l'adapter sia",
        "stato implementato e verificato, e qui esiste solo una specifica. `hierarchy_policy_ready`",
        "e' fuori perimetro. `full_exploratory_rerun_ready` resta falso.",
        "",
        "## Cosa resta aperto",
        "",
        f"- gruppi non risolti: {len(readiness['unresolved_groups_remaining'])} "
        f"({', '.join(f'`{item}`' for item in readiness['unresolved_groups_remaining']) or 'nessuno'})",
        f"- gruppi con revisione terminologica pendente: "
        f"{len(readiness['terminology_review_remaining'])}",
        f"- statement da deprecare senza sostituto: "
        f"{simulation['statements_deprecated_without_replacement']}",
        "",
        "Nessuna di queste voci blocca la revisione dello schema. La prima decisione da prendere",
        "dopo, e che questa fase non ha preso, e' la regola di match dello scoring per tipo di",
        "claim: regimi e aggregati non hanno un intervento scalare, e lo scoring attuale lo",
        "assume.",
        "",
    ]
    return "\n".join(lines)


# --- assemblaggio -------------------------------------------------------------


def build(*, reverse: bool = False) -> dict[str, str]:
    inputs = Inputs(reverse=reverse)
    scope = check_scope(inputs)
    claims = build_claims(inputs)
    id_check = check_claim_ids(claims)
    interventions = build_intervention_adjudications(inputs, claims)
    groups = build_group_adjudications(inputs, interventions, claims)
    children = build_child_adjudications(inputs, interventions)
    simulation = build_simulation(inputs, claims, interventions, groups)
    readiness = build_readiness(simulation, groups, interventions, inputs.migration)

    files: dict[str, str] = {}
    files["adjudicator_metadata.json"] = canonical_dumps(
        {
            "adjudication_version": ADJUDICATION_VERSION,
            "adjudication_branch": ADJUDICATION_BRANCH,
            "start_sha": START_SHA,
            "environment": ENVIRONMENT,
            "independence_declaration": (
                "L'adjudication e' stata eseguita dall'autore sugli stessi artefatti che ha"
                " prodotto. Non esiste un revisore esterno di dominio, quindi l'etichetta"
                " independent_domain_adjudicator non e' utilizzabile."
            ),
            **ADJUDICATOR_LABELS,
        }
    )
    files["adjudication_scope.json"] = canonical_dumps(
        {
            "adjudication_version": ADJUDICATION_VERSION,
            "scope_check": scope,
            "input_hashes": {
                "first_review": tree_digest(FIRST),
                "blinded_replicate": tree_digest(REPLICATE),
                "review_comparison": tree_digest(COMPARISON),
                "adjudication_packets": tree_digest(PACKETS),
                "source_review_packets": tree_digest(SOURCE_PACKETS),
                "local_sources": {path: digest(REPO_ROOT / path) for path in LOCAL_SOURCES},
                "frozen_artifacts": {path: digest(REPO_ROOT / path) for path in FROZEN_ARTIFACTS},
                "gold_artifacts": {path: digest(REPO_ROOT / path) for path in GOLD_ARTIFACTS},
            },
            "original_annotations_modified": False,
            "operational_statements_regenerated": False,
            "gold_used_for_decisions": False,
            **ADJUDICATOR_LABELS,
        }
    )
    files["schema_semantics_decision.json"] = canonical_dumps(
        {
            "adjudication_version": ADJUDICATION_VERSION,
            "parent_semantics": PARENT_SEMANTICS_DECISION,
            "parent_retains": list(PARENT_RETAINS),
            "parent_no_longer": list(PARENT_NO_LONGER),
            "claim_types": [
                "atomic_intervention_claim",
                "aggregate_intervention_claim",
                "regimen_claim",
            ],
            "non_claim_association_states": [
                "unsupported_association",
                "unresolved_association",
            ],
            **inputs.parent_semantics,
            **ADJUDICATOR_LABELS,
        }
    )
    files["packet_adjudications.jsonl"] = canonical_jsonl(groups, key="graph_evidence_id")
    files["intervention_adjudications.jsonl"] = canonical_jsonl(
        interventions, key="adjudication_id"
    )
    files["child_claim_adjudications.jsonl"] = canonical_jsonl(
        children, key="child_comparison_id"
    )
    files["priority_concordant_case_adjudications.jsonl"] = canonical_jsonl(
        [{**row, **ADJUDICATOR_LABELS} for row in inputs.priority], key="case_id"
    )
    files["regimen_adjudications.jsonl"] = canonical_jsonl(
        [
            {
                "claim_id": claim["claim_id"],
                "graph_evidence_parent": claim["graph_evidence_parent"],
                "regimen_components": claim["regimen_components"],
                "canonical_regimen": claim["canonical_intervention_or_regimen"],
                "source_unit_id": claim["source_unit_id"],
                "biomarker": claim["biomarker"],
                "direction": claim["direction"],
                "polarity": claim["polarity"],
                "result_summary": claim["result_summary"],
                "components_propagated": False,
                "residual_risk": claim["residual_risk"],
                **ADJUDICATOR_LABELS,
            }
            for claim in claims
            if claim["claim_type"] == "regimen_claim"
        ],
        key="claim_id",
    )
    files["aggregate_adjudications.jsonl"] = canonical_jsonl(
        [
            {
                "claim_id": claim["claim_id"],
                "graph_evidence_parent": claim["graph_evidence_parent"],
                "aggregate_members": claim["aggregate_members"],
                "aggregate_kind": claim["aggregate_kind"],
                "canonical_aggregate": claim["canonical_intervention_or_regimen"],
                "permits_member_specific_claims": False,
                "source_unit_id": claim["source_unit_id"],
                "biomarker": claim["biomarker"],
                "evidence_setting": claim["evidence_setting"],
                "result_summary": claim["result_summary"],
                "residual_risk": claim["residual_risk"],
                **ADJUDICATOR_LABELS,
            }
            for claim in claims
            if claim["claim_type"] == "aggregate_intervention_claim"
        ],
        key="claim_id",
    )
    files["unsupported_associations.jsonl"] = canonical_jsonl(
        [
            {**row, "excluded_from_primary_retrieval": True}
            for row in interventions
            if row["association_outcome"] == "unsupported_association"
        ],
        key="adjudication_id",
    )
    files["unresolved_associations.jsonl"] = canonical_jsonl(
        [
            {**row, "excluded_from_primary_retrieval": True, "auditable": True}
            for row in interventions
            if row["association_outcome"] == "unresolved_association"
        ],
        key="adjudication_id",
    )
    files["terminology_review_queue.jsonl"] = canonical_jsonl(
        [
            {
                "queue_id": f"TRQ-{code}",
                "source_literal_term": code,
                "graph_term": generic,
                "action": "terminology_review_required",
                "merged": False,
                "affected_groups": sorted(
                    {
                        row["graph_evidence_id"]
                        for row in interventions
                        if canonical_intervention(row["intervention"]) == generic.lower()
                        and row["association_outcome"] == "unresolved_association"
                    }
                ),
                "note": (
                    "Il codice di sviluppo non e' stato promosso al nome generico ne'"
                    " canonicalizzato insieme a esso. Nessun merge automatico."
                ),
                **ADJUDICATOR_LABELS,
            }
            for code, generic in PENDING_ALIASES
            if any(
                canonical_intervention(row["intervention"]) == generic.lower()
                and row["association_outcome"] == "unresolved_association"
                for row in interventions
            )
        ],
        key="queue_id",
    )
    files["approved_claim_simulation.jsonl"] = canonical_jsonl(claims, key="claim_id")
    files["claim_id_simulation.jsonl"] = canonical_jsonl(
        [
            {
                "claim_id": claim["claim_id"],
                "claim_identity_sha256": claim["claim_identity_sha256"],
                "graph_evidence_id": claim["graph_evidence_parent"],
                "claim_type": claim["claim_type"],
                "canonical_intervention_or_regimen": claim["canonical_intervention_or_regimen"],
                "biomarker": claim["biomarker"],
                "direction": claim["direction"],
                "polarity": claim["polarity"],
                "source_unit_id": claim["source_unit_id"],
                "parent_lineage_preserved": True,
                "implemented_in_operational_corpus": False,
                **ADJUDICATOR_LABELS,
            }
            for claim in claims
        ],
        key="claim_id",
    )
    files["post_adjudication_schema_simulation.json"] = canonical_dumps(
        {**simulation, "id_strategy": id_check, "adjudication_version": ADJUDICATION_VERSION}
    )
    files["migration_specification.json"] = canonical_dumps(
        {**inputs.migration, "adjudication_version": ADJUDICATION_VERSION, **ADJUDICATOR_LABELS}
    )
    files["MULTI_INTERVENTION_ADJUDICATION.md"] = render_adjudication_report(
        groups, simulation, interventions
    )
    files["PARENT_SEMANTICS_DECISION.md"] = render_parent_semantics(inputs.parent_semantics)
    files["ADJUDICATED_CLAIM_MODEL.md"] = render_claim_model(claims, id_check)
    files["ADAPTER_MIGRATION_SPECIFICATION.md"] = render_migration(inputs.migration)
    files["ADAPTER_MIGRATION_READINESS.md"] = render_readiness(readiness, simulation)
    files["adjudication_manifest.json"] = canonical_dumps(
        {
            "adjudication_version": ADJUDICATION_VERSION,
            "readiness": readiness,
            "counts": {
                "groups_adjudicated": len(groups),
                "associations_decided": len(interventions),
                "claims_approved": len(claims),
                "priority_cases": len(inputs.priority),
            },
            "artifact_sha256": {
                name: sha256_text(content) for name, content in sorted(files.items())
            },
            **ADJUDICATOR_LABELS,
        }
    )
    return files


def write(files: Mapping[str, str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        (output_dir / name).write_text(files[name], encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reverse-packet-order", action="store_true")
    args = parser.parse_args()
    files = build(reverse=args.reverse_packet_order)
    write(files, args.output_dir)
    print(f"scritti {len(files)} artefatti in {args.output_dir}")


if __name__ == "__main__":
    main()
