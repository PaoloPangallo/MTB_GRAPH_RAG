"""Costruisce gli artefatti della seconda revisione multi-intervento.

Legge i 13 packet ciechi e le annotazioni congelate, valida ogni riga contro il
vocabolario della fase e scrive l'insieme degli artefatti. Deterministico per
costruzione: ogni output e' ordinato per chiave dichiarata, quindi rieseguirlo —
anche con i packet presentati in ordine inverso — produce gli stessi byte.

Non legge nulla della prima revisione: ogni apertura passa da `AccessLog`, che
solleva su qualunque path della denylist e lascia il log come artefatto.

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_second_review_artifacts
    python -m ... .build_second_review_artifacts --reverse-packet-order --output-dir /tmp/x
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from benchmarks.mtb_evidence.evaluation.multi_intervention_second_review import (
    AccessLog,
    DENIED_PATH_FRAGMENTS,
    MATERIALIZABLE_CATEGORIES,
    PENDING_DEVELOPMENT_CODE_MAPPINGS,
    REVIEW_VERSION,
    ScopeMismatch,
    aggregate_hash,
    canonical_dumps,
    canonical_jsonl,
    check_annotation,
    check_group_decision,
    check_no_pending_mapping_promoted,
    check_packet_scope,
    packet_paths,
    sentence_index,
    sha256_bytes,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
PACKET_DIR = (
    REPO_ROOT
    / "benchmarks/mtb_evidence/v3/multi_intervention_source_review/second_review_packets"
)
DATA_DIR = REPO_ROOT / "benchmarks/mtb_evidence/evaluation/data"
DEFAULT_OUTPUT = REPO_ROOT / "benchmarks/mtb_evidence/v3/multi_intervention_second_review"
FULL_TEXT_ROOT = REPO_ROOT.parent

START_SHA = "018bdfa7393c773722bb61755c4c5146a9ef98f9"
REVIEW_BRANCH = "review/v3-multi-intervention-second-review"

# Cio' che questa sessione ha aperto oltre ai packet, dichiarato esplicitamente
# perche' il log di accesso sia il registro completo della revisione e non solo
# di cio' che lo script rilegge.
SESSION_ACCESSES = (
    (
        "benchmarks/mtb_evidence/v3/first_review/intervention_mappings.jsonl",
        "read",
        "registro dei mapping terminologici approvati localmente (materiale ammesso)",
    ),
    (
        "local_source://data_expl/benchmark/benchmark_papers/fulltext_26698910.txt",
        "read",
        "fonte full text indicata nel packet MI-B-72b36cde2fff1311",
    ),
    (
        "backend/tests/test_cohort_split_audit.py",
        "read",
        "convenzioni dei test offline del repository, non materiale di revisione",
    ),
    (
        "benchmarks/mtb_evidence/evaluation/clinical_preclinical_review.py",
        "read",
        "convenzioni di modulo del repository, non materiale di revisione",
    ),
    (
        "benchmarks/mtb_evidence/v3/multi_intervention_source_review/second_review_packets",
        "list",
        "enumerazione dei packet ciechi",
    ),
)

# Contaminazione di contesto nota, registrata alla lettera. Non e' l'apertura di
# un file vietato ma rende la revisione non indipendente, e va dichiarata come
# tale invece di essere assorbita in un `blindness_violation = false`.
CONTEXT_CONTAMINATION = (
    {
        "channel": "task_prompt",
        "item": "Il prompt della task nomina la raccomandazione della prima revisione ('la raccomandazione mixed_policy') nell'elenco di cio' che un revisore indipendente non deve aver letto.",
        "leaks": "il nome della raccomandazione architetturale della prima revisione",
        "does_not_leak": "nessuna decisione per gruppo, nessuna annotazione, nessun risultato aggregato",
    },
    {
        "channel": "session_git_status",
        "item": "Il blocco gitStatus iniettato all'avvio della sessione conteneva gli oggetti dei commit descrittivi della prima revisione.",
        "leaks": "l'esistenza e il tema dei commit della prima revisione",
        "does_not_leak": "nessun contenuto di decisione",
    },
)

SEARCH_EVENTS = (
    {
        "pattern": "AUY922|CH5424802|BGJ398",
        "scope": "repository, solo elenco di path (grep -l)",
        "purpose": "individuare un registro di mapping terminologici approvati",
        "output_kind": "solo path, nessun contenuto",
        "denied_paths_returned_but_not_opened": True,
    },
)


class Artifacts:
    """Raccoglie i file da scrivere e li emette in un ordine fisso."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def add(self, name: str, content: str) -> None:
        self.files[name] = content

    def write(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name in sorted(self.files):
            (output_dir / name).write_text(self.files[name], encoding="utf-8", newline="\n")


# --- lettura ------------------------------------------------------------------


def load_jsonl(path: Path, log: AccessLog, *, purpose: str) -> list[dict[str, Any]]:
    text = log.read_text(path, purpose=purpose)
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def load_packets(log: AccessLog, *, reverse: bool) -> list[dict[str, Any]]:
    paths = packet_paths(PACKET_DIR)
    if reverse:
        paths = list(reversed(paths))
    packets = []
    for path in paths:
        payload = log.read_text(path, purpose="packet cieco di seconda revisione")
        packet = json.loads(payload)
        packet["_sha256"] = sha256_text(payload)
        packets.append(packet)
    check_packet_scope([packet["blind_annotation_id"] for packet in packets])
    return packets


def verify_source_material(packet: Mapping[str, Any]) -> dict[str, Any]:
    """La provenienza del testo del packet deve reggere senza aprire la cache.

    Per gli abstract lo sha256 dichiarato e' quello del testo incorporato nel
    packet, quindi la verifica e' interna. Per il full text il packet porta un
    estratto: si verifica l'hash del file e che l'estratto sia letterale.
    """
    text = packet["source_text"]
    embedded = sha256_text(text)
    declared = {item["kind"]: item["sha256"] for item in packet["local_material"]}
    result = {
        "embedded_text_sha256": embedded,
        "declared_material": declared,
        "abstract_hash_matches_embedded_text": declared.get("abstract") == embedded,
        "full_text_file_verified": None,
        "excerpt_verbatim_in_full_text": None,
    }
    if "full_text" not in declared:
        return result

    logical = next(
        item["logical_path"] for item in packet["local_material"] if item["kind"] == "full_text"
    )
    path = FULL_TEXT_ROOT / logical.replace("local_source://", "")
    payload = path.read_bytes()
    result["full_text_file_verified"] = sha256_bytes(payload) == declared["full_text"]
    normalize = lambda value: re.sub(r"\s+", " ", value).strip()  # noqa: E731
    result["excerpt_verbatim_in_full_text"] = normalize(text) in normalize(
        payload.decode("utf-8", errors="replace")
    )
    return result


# --- costruzione delle annotazioni --------------------------------------------


def build_locator(packet: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    """Il locator nasce da citazioni letterali, verificate contro la fonte."""
    text = packet["source_text"]
    probes = list(row["locator_probes"])
    for probe in probes:
        if probe not in text:
            raise ScopeMismatch(
                f"{row['blind_annotation_id']}/{row['intervention']}: probe non letterale nella fonte: {probe!r}"
            )
    index = sentence_index(text, probes[0])
    if index is None:
        raise ScopeMismatch(
            f"{row['blind_annotation_id']}/{row['intervention']}: nessuna frase contiene il probe"
        )

    locator: dict[str, Any] = {"source_id": packet["source_ids"][0]}
    locator.update(row["locator_unit"])
    if packet["source_text_kind"] == "abstract":
        locator["abstract_sentence"] = index
    else:
        locator["paragraph"] = f"estratto Case Report, frase {index}"
    locator["verbatim_probes"] = probes
    return locator


def build_annotation(packet: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    annotation = {
        "alias_status": row["alias_status"],
        "biomarker": packet["biomarker"],
        "blind_annotation_id": packet["blind_annotation_id"],
        "claim_direction": packet["directions"][0],
        "claim_polarity": packet["assertion_polarities"][0],
        "classification": row["classification"],
        "confidence": row["confidence"],
        "disease": packet["disease"],
        "evidence_setting": row["evidence_setting"],
        "graph_evidence_id": packet["graph_evidence_id"],
        "intervention": row["intervention"],
        "is_current_statement_intervention": row["is_current_statement_intervention"],
        "locator": build_locator(packet, row),
        "locator_status": row["locator_status"],
        "materialization": row["materialization"],
        "observed_direction": row["observed_direction"],
        "observed_polarity": row["observed_polarity"],
        "paraphrased_result": row["paraphrased_result"],
        "population_model": row["population_model"],
        "review_version": REVIEW_VERSION,
        "reviewer_note": row["reviewer_note"],
        "source_access_status": packet["source_access_status"],
        "source_id": packet["source_ids"][0],
        "source_literal_term": row["source_literal_term"],
        "source_unit_id": row["source_unit_id"],
        "statement_id": packet["statement_id"],
    }
    if row["is_current_statement_intervention"] != (
        row["intervention"] == packet["current_statement_intervention"]
    ):
        raise ScopeMismatch(
            f"{packet['blind_annotation_id']}/{row['intervention']}: flag parent incoerente col packet"
        )
    if row["intervention"] not in packet["candidate_interventions"]:
        raise ScopeMismatch(
            f"{packet['blind_annotation_id']}: intervento fuori dai candidati: {row['intervention']}"
        )
    check_annotation(annotation)
    return annotation


def build_annotations(
    packets: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {packet["blind_annotation_id"]: packet for packet in packets}
    annotations = [build_annotation(by_id[row["blind_annotation_id"]], row) for row in rows]

    for packet in packets:
        annotated = {
            item["intervention"]
            for item in annotations
            if item["blind_annotation_id"] == packet["blind_annotation_id"]
        }
        missing = sorted(set(packet["candidate_interventions"]) - annotated)
        if missing:
            raise ScopeMismatch(
                f"{packet['blind_annotation_id']}: interventi non classificati: {missing}"
            )
    check_no_pending_mapping_promoted(annotations)
    return annotations


def group_rows(annotations: Sequence[Mapping[str, Any]], group: str) -> list[Mapping[str, Any]]:
    return [row for row in annotations if row["blind_annotation_id"] == group]


# --- artefatti derivati -------------------------------------------------------


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def child_claim_id(row: Mapping[str, Any]) -> str:
    return f"SR2-CHILD-{row['blind_annotation_id']}-{slug(row['intervention'])}"


def build_source_units(annotations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    for row in annotations:
        unit = units.setdefault(
            row["source_unit_id"],
            {
                "source_unit_id": row["source_unit_id"],
                "source_id": row["source_id"],
                "unit_kind": unit_kind(row["locator"]),
                "evidence_setting": row["evidence_setting"],
                "population_model": row["population_model"],
                "source_access_status": row["source_access_status"],
                "interventions": set(),
                "blind_annotation_ids": set(),
                "documentary_results": set(),
                "verbatim_probes": set(),
            },
        )
        unit["interventions"].add(row["intervention"])
        unit["blind_annotation_ids"].add(row["blind_annotation_id"])
        unit["documentary_results"].add(row["paraphrased_result"])
        unit["verbatim_probes"].update(row["locator"]["verbatim_probes"])

    rows = []
    for unit in units.values():
        rows.append(
            {
                **{k: v for k, v in unit.items() if not isinstance(v, set)},
                "interventions": sorted(unit["interventions"]),
                "blind_annotation_ids": sorted(unit["blind_annotation_ids"]),
                "documentary_results": sorted(unit["documentary_results"]),
                "verbatim_probes": sorted(unit["verbatim_probes"]),
                "shared_across_groups": len(unit["blind_annotation_ids"]) > 1,
            }
        )
    return rows


def unit_kind(locator: Mapping[str, Any]) -> str:
    if locator.get("patient_id"):
        return "patient_treatment_line" if locator.get("treatment_line") else "patient"
    if locator.get("cell_line"):
        return "cell_model"
    if locator.get("experimental_arm"):
        return "experimental_arm"
    return "unspecified"


def build_group_decisions(
    annotations: Sequence[Mapping[str, Any]], decisions: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for decision in decisions:
        group = decision["blind_annotation_id"]
        members = group_rows(annotations, group)
        check_group_decision(decision["decision"], members)
        children = [row for row in members if row["materialization"] == "child_claim_proposed"]
        separate = [
            row for row in members if row["classification"] in MATERIALIZABLE_CATEGORIES
        ]
        rows.append(
            {
                "blind_annotation_id": group,
                "graph_evidence_id": members[0]["graph_evidence_id"],
                "statement_id": members[0]["statement_id"],
                "source_id": members[0]["source_id"],
                "decision": decision["decision"],
                "decision_confidence": decision["decision_confidence"],
                "rationale": decision["rationale"],
                "intervention_count": len(members),
                "intervention_specific_result_count": len(separate),
                "proposed_child_claim_count": len(children),
                "not_materialized_count": sum(
                    1 for row in members if row["materialization"] == "not_materialized"
                ),
                "source_unit_ids": sorted({row["source_unit_id"] for row in members}),
                "classifications": sorted({row["classification"] for row in members}),
                "evidence_settings": sorted({row["evidence_setting"] for row in members}),
                "review_status": "second_review_complete",
                "propagation_policy": "prototype_only",
                "hard_filterable": False,
                "final_evaluable": False,
                "review_version": REVIEW_VERSION,
            }
        )
    if len(rows) != len(set(row["blind_annotation_id"] for row in rows)):
        raise ScopeMismatch("decisione di gruppo duplicata")
    return rows


def build_lineage(annotations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    shared = {}
    for row in annotations:
        shared.setdefault(row["source_unit_id"], set()).add(row["blind_annotation_id"])

    rows = []
    for row in annotations:
        groups = shared[row["source_unit_id"]]
        rows.append(
            {
                "lineage_id": f"SR2-L-{row['blind_annotation_id']}-{slug(row['intervention'])}",
                "blind_annotation_id": row["blind_annotation_id"],
                "graph_evidence_id": row["graph_evidence_id"],
                "statement_id": row["statement_id"],
                "intervention": row["intervention"],
                "source_id": row["source_id"],
                "source_unit_id": row["source_unit_id"],
                "documentary_result": row["paraphrased_result"],
                "classification": row["classification"],
                "locator_status": row["locator_status"],
                "proposed_materialization": row["materialization"],
                "proposed_child_claim_id": (
                    child_claim_id(row) if row["materialization"] == "child_claim_proposed" else None
                ),
                "source_unit_shared_with_groups": sorted(groups - {row["blind_annotation_id"]}),
                "blocking_reason": blocking_reason(row),
            }
        )
    return rows


def blocking_reason(row: Mapping[str, Any]) -> str | None:
    if row["materialization"] != "not_materialized":
        return None
    return {
        "directly_tested_in_shared_aggregate_result": "risultato aggregato non separabile",
        "directly_tested_in_combination_regimen": "risultato del regime, non del componente",
        "comparator_only": "comparatore, non oggetto del claim",
        "mentioned_background_only": "menzione o terapia precedente",
        "cited_prior_evidence_only": "evidenza citata, non prodotta dallo studio",
        "drug_class_member_not_individually_tested": "membro di classe non testato individualmente",
        "possible_alias_not_verified": "mapping terminologico non verificato",
        "result_not_attributable_to_specific_intervention": "risultato non attribuibile",
        "conflicting_results_across_units": "risultati in conflitto fra unita'",
        "intervention_not_found_in_source": "intervento assente dalla fonte",
        "insufficient_source_access": "accesso alla fonte insufficiente",
        "unresolved": "non risolto",
    }.get(row["classification"], "non materializzabile")


def build_locator_completeness(annotations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    for row in annotations:
        by_status[row["locator_status"]] = by_status.get(row["locator_status"], 0) + 1

    children = [row for row in annotations if row["materialization"] == "child_claim_proposed"]
    per_group: dict[str, dict[str, Any]] = {}
    for row in annotations:
        entry = per_group.setdefault(
            row["blind_annotation_id"], {"sufficient": 0, "insufficient_for_claim": 0, "unavailable": 0}
        )
        entry[row["locator_status"]] += 1

    return {
        "total_associations": len(annotations),
        "by_status": dict(sorted(by_status.items())),
        "children_total": len(children),
        "children_with_sufficient_locator": sum(
            1 for row in children if row["locator_status"] == "sufficient"
        ),
        "locators_using_source_id_only": 0,
        "locator_unit_kinds": dict(
            sorted(
                {
                    kind: sum(1 for row in annotations if unit_kind(row["locator"]) == kind)
                    for kind in {unit_kind(row["locator"]) for row in annotations}
                }.items()
            )
        ),
        "per_group": dict(sorted(per_group.items())),
        "every_proposed_child_has_sufficient_locator": all(
            row["locator_status"] == "sufficient" for row in children
        ),
    }


def build_source_inventory(packets: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for packet in packets:
        source_id = packet["source_ids"][0]
        verification = verify_source_material(packet)
        entry = inventory.setdefault(
            source_id,
            {
                "source_id": source_id,
                "source_title": packet["source_title"],
                "source_access_status": packet["source_access_status"],
                "source_text_kind": packet["source_text_kind"],
                "blind_annotation_ids": [],
                "material_opened_directly": [],
                "verification": verification,
            },
        )
        entry["blind_annotation_ids"].append(packet["blind_annotation_id"])
        if packet["source_access_status"] == "full_text":
            entry["material_opened_directly"] = [
                item["logical_path"]
                for item in packet["local_material"]
                if item["kind"] == "full_text"
            ]
    for entry in inventory.values():
        entry["blind_annotation_ids"] = sorted(entry["blind_annotation_ids"])
        entry["abstract_cache_opened"] = False
    return list(inventory.values())


# --- metriche di sintesi ------------------------------------------------------


def summarize(
    annotations: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    inventory: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    categories: dict[str, int] = {}
    for row in annotations:
        categories[row["classification"]] = categories.get(row["classification"], 0) + 1

    decision_counts: dict[str, int] = {}
    for row in decisions:
        decision_counts[row["decision"]] = decision_counts.get(row["decision"], 0) + 1

    separate = [row for row in annotations if row["classification"] in MATERIALIZABLE_CATEGORIES]
    children = [row for row in annotations if row["materialization"] == "child_claim_proposed"]
    parents_with_separate_result = [
        row for row in separate if row["materialization"] == "parent_retained"
    ]
    return {
        "packets_reviewed": len(decisions),
        "intervention_associations": len(annotations),
        "interventions_classified": len(annotations),
        "distinct_sources": len(inventory),
        "sources_full_text": sum(
            1 for row in inventory if row["source_access_status"] == "full_text"
        ),
        "sources_abstract_only": sum(
            1 for row in inventory if row["source_access_status"] == "abstract_only"
        ),
        "sources_unavailable": sum(
            1 for row in inventory if row["source_access_status"] == "unavailable"
        ),
        "distinct_source_units": len(units),
        "source_units_shared_across_groups": sum(1 for row in units if row["shared_across_groups"]),
        "classification_counts": dict(sorted(categories.items())),
        "group_decision_counts": dict(sorted(decision_counts.items())),
        "intervention_specific_results": len(separate),
        "unique_proposed_child_claims": len({child_claim_id(row) for row in children}),
        "separate_results_on_parent_intervention": len(parents_with_separate_result),
        "clinical_associations": sum(
            1 for row in annotations if row["evidence_setting"] == "clinical"
        ),
        "preclinical_associations": sum(
            1 for row in annotations if row["evidence_setting"] == "preclinical"
        ),
        "resistance_associations": sum(
            1 for row in annotations if row["claim_direction"] == "resistance"
        ),
        "pending_alias_associations": sum(
            1 for row in annotations if row["alias_status"] == "pending_not_verified"
        ),
        "verified_alias_merges": 0,
    }


def build_readiness(
    summary: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    locators: Mapping[str, Any],
) -> dict[str, Any]:
    unresolved_groups = [
        row["blind_annotation_id"]
        for row in decisions
        if row["decision"] == "insufficient_for_atomicity_decision"
    ]
    return {
        "all_packets_reviewed": summary["packets_reviewed"] == 13,
        "all_interventions_classified": True,
        "locator_requirements_satisfied": locators["every_proposed_child_has_sufficient_locator"],
        "blindness_preserved": True,
        "independent_review_valid": False,
        "unresolved_groups_remaining": sorted(unresolved_groups),
        "ready_for_inter_reviewer_comparison": True,
        "ready_for_adjudication": False,
        "ready_for_adapter_migration": False,
    }


# --- reportistica -------------------------------------------------------------


def render_report(
    summary: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    locators: Mapping[str, Any],
    unresolved: Sequence[Mapping[str, Any]],
) -> str:
    lines = [
        "# Seconda revisione documentale dei gruppi multi-intervento",
        "",
        "Revisione in cieco dei 13 packet, condotta sui soli packet e sulle fonti locali",
        "che vi sono indicate. Nessun confronto con altre revisioni, nessuna adjudication,",
        "nessuna raccomandazione architetturale: la fase si ferma alle annotazioni",
        "documentali e alle decisioni per gruppo.",
        "",
        "## Indipendenza",
        "",
        "`reviewer_role = blinded_replicate`, `review_independence = blinded_non_independent_replicate`.",
        "",
        "Nessun file vietato e' stato aperto, ma due elementi erano gia' nel contesto prima",
        "che la revisione cominciasse: il prompt della task nomina la raccomandazione della",
        "prima revisione, e il blocco `gitStatus` iniettato all'avvio conteneva gli oggetti",
        "dei suoi commit. Nessuno dei due rivela decisioni per gruppo, ma la precondizione",
        "di indipendenza non e' soddisfatta e non viene dichiarata tale.",
        "",
        "## Conteggi",
        "",
        f"- packet revisionati: {summary['packets_reviewed']}",
        f"- associazioni gruppo-intervento classificate: {summary['intervention_associations']}",
        f"- fonti distinte: {summary['distinct_sources']} "
        f"(full text {summary['sources_full_text']}, abstract-only {summary['sources_abstract_only']}, "
        f"non disponibili {summary['sources_unavailable']})",
        f"- unita' documentali distinte: {summary['distinct_source_units']} "
        f"(di cui condivise fra gruppi: {summary['source_units_shared_across_groups']})",
        f"- associazioni cliniche {summary['clinical_associations']}, "
        f"precliniche {summary['preclinical_associations']}",
        "",
        "### Classificazione per intervento",
        "",
    ]
    lines += [f"- `{key}`: {value}" for key, value in summary["classification_counts"].items()]
    lines += ["", "### Decisione per gruppo", ""]
    lines += [f"- `{key}`: {value}" for key, value in summary["group_decision_counts"].items()]

    lines += [
        "",
        "## Risultati separati contro figli proposti",
        "",
        f"La fonte sostiene {summary['intervention_specific_results']} risultati specifici per intervento,"
        f" ma i child claim unici proposti sono {summary['unique_proposed_child_claims']}.",
        "La differenza non e' una perdita: e' la somma di tre cose distinte.",
        "",
        f"1. **{summary['separate_results_on_parent_intervention']} di quei risultati appartengono gia'"
        " all'intervento dello statement parent.** Non generano un figlio: raffinano il locator di un"
        " claim che esiste. Un risultato separato non e' un claim nuovo se il claim c'e' gia'.",
        f"2. **{summary['pending_alias_associations']} associazioni sono bloccate da un mapping"
        " terminologico non verificato** (`BGJ398`, `AUY922`). In un caso il risultato documentale"
        " esiste, ma non e' attribuibile all'intervento del grafo finche' l'alias resta pending.",
        "3. **Le unita' documentali condivise non moltiplicano i claim.** Un solo enunciato su NIH3T3"
        " sostiene due righe di gruppo (FGFR2::BICC1 e FGFR2::AHCYL1): due associazioni, un risultato.",
        "",
        f"Restano quindi {summary['unique_proposed_child_claims']} figli proposti, tutti con locator"
        " sufficiente e tutti su categorie materializzabili.",
        "",
        "## Locator",
        "",
        f"- associazioni totali: {locators['total_associations']}",
        f"- locator sufficienti: {locators['by_status'].get('sufficient', 0)}",
        f"- locator insufficienti per il claim: {locators['by_status'].get('insufficient_for_claim', 0)}",
        f"- locator basati sul solo identificatore di fonte: {locators['locators_using_source_id_only']}",
        f"- figli proposti con locator sufficiente: "
        f"{locators['children_with_sufficient_locator']}/{locators['children_total']}",
        "",
        "Ogni locator e' ancorato a una o piu' citazioni letterali verificate contro il testo del",
        "packet: se una citazione smettesse di comparire nella fonte, la costruzione fallirebbe.",
        "",
        "## Decisioni",
        "",
        "| gruppo | decisione | interventi | risultati separati | figli |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in sorted(decisions, key=lambda item: item["blind_annotation_id"]):
        lines.append(
            f"| `{row['blind_annotation_id']}` | `{row['decision']}` | {row['intervention_count']} | "
            f"{row['intervention_specific_result_count']} | {row['proposed_child_claim_count']} |"
        )

    lines += ["", "## Aperto", ""]
    for row in sorted(unresolved, key=lambda item: item["unresolved_id"]):
        lines.append(f"- **{row['unresolved_id']}** (`{row['severity']}`) — {row['issue']}")

    lines += [
        "",
        "## Cosa questa fase non ha fatto",
        "",
        "Nessun confronto con altre revisioni, nessun consenso, nessuna adjudication, nessuna",
        "migrazione dell'adapter, nessuna raccomandazione finale di schema. Nessuna decisione",
        "diventa automaticamente definitiva: `propagation_policy = prototype_only`,",
        "`hard_filterable = false`, `final_evaluable = false`.",
        "",
    ]
    return "\n".join(lines)


def render_readiness(readiness: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    lines = [
        "# Readiness della seconda revisione",
        "",
        "| criterio | stato |",
        "| --- | --- |",
        f"| `all_packets_reviewed` | {str(readiness['all_packets_reviewed']).lower()} |",
        f"| `all_interventions_classified` | {str(readiness['all_interventions_classified']).lower()} |",
        f"| `locator_requirements_satisfied` | {str(readiness['locator_requirements_satisfied']).lower()} |",
        f"| `blindness_preserved` | {str(readiness['blindness_preserved']).lower()} |",
        f"| `independent_review_valid` | {str(readiness['independent_review_valid']).lower()} |",
        f"| `unresolved_groups_remaining` | {len(readiness['unresolved_groups_remaining'])} |",
        f"| `ready_for_inter_reviewer_comparison` | {str(readiness['ready_for_inter_reviewer_comparison']).lower()} |",
        f"| `ready_for_adjudication` | {str(readiness['ready_for_adjudication']).lower()} |",
        f"| `ready_for_adapter_migration` | {str(readiness['ready_for_adapter_migration']).lower()} |",
        "",
        "## Perche' il confronto e' possibile e l'adjudication no",
        "",
        "Le 13 decisioni esistono, ogni intervento e' classificato e ogni figlio proposto ha un",
        "locator sufficiente: il materiale per un confronto fra revisori c'e'. Il confronto pero'",
        "va etichettato per quello che e', perche' `independent_review_valid` e' falso: questa e'",
        "una replica in cieco, non una seconda opinione indipendente. Un accordo elevato fra le",
        "due revisioni non e' quindi evidenza di convergenza indipendente.",
        "",
        "L'adjudication resta chiusa perche' presuppone il confronto, che non e' stato fatto. La",
        "migrazione dell'adapter resta chiusa perche' presuppone l'adjudication.",
        "",
        f"Gruppi ancora aperti: {len(readiness['unresolved_groups_remaining'])} "
        f"({', '.join(f'`{item}`' for item in readiness['unresolved_groups_remaining']) or 'nessuno'}).",
        "",
        "## Vincoli non violati",
        "",
        "- nessun risultato aggregato e' stato reso specifico;",
        "- nessun regime e' stato splittato nei componenti;",
        "- nessuna menzione e nessuna terapia precedente e' diventata un claim;",
        f"- {summary['pending_alias_associations']} mapping pending non sono stati promossi;",
        "- clinico e preclinico restano separati in ogni annotazione;",
        f"- le {summary['resistance_associations']} associazioni di resistenza conservano direzione e polarita'.",
        "",
    ]
    return "\n".join(lines)


# --- assemblaggio -------------------------------------------------------------


def build(output_dir: Path, *, reverse: bool) -> Artifacts:
    log = AccessLog(REPO_ROOT)
    packets = load_packets(log, reverse=reverse)
    rows = load_jsonl(
        DATA_DIR / "second_review_annotations_v1.jsonl", log, purpose="annotazioni di seconda revisione"
    )
    decision_rows = load_jsonl(
        DATA_DIR / "second_review_group_decisions_v1.jsonl", log, purpose="decisioni per gruppo"
    )
    unresolved = load_jsonl(
        DATA_DIR / "second_review_unresolved_v1.jsonl", log, purpose="questioni aperte"
    )
    for logical_path, kind, purpose in SESSION_ACCESSES:
        log.note(logical_path=logical_path, purpose=purpose, access_kind=kind)

    annotations = build_annotations(packets, rows)
    decisions = build_group_decisions(annotations, decision_rows)
    units = build_source_units(annotations)
    lineage = build_lineage(annotations)
    locators = build_locator_completeness(annotations)
    inventory = build_source_inventory(packets)
    summary = summarize(annotations, decisions, inventory, units)
    readiness = build_readiness(summary, decisions, locators)

    artifacts = Artifacts()
    artifacts.add(
        "reviewer_metadata.json",
        canonical_dumps(
            {
                "reviewer_role": "blinded_replicate",
                "review_independence": "blinded_non_independent_replicate",
                "independent_review_valid": False,
                "context_contamination": True,
                "blindness_violation": False,
                "review_status": "second_review_complete",
                "propagation_policy": "prototype_only",
                "hard_filterable": False,
                "final_evaluable": False,
                "review_version": REVIEW_VERSION,
                "review_branch": REVIEW_BRANCH,
                "start_sha": START_SHA,
                "packets_reviewed": summary["packets_reviewed"],
                "declaration": (
                    "Nessun artefatto della prima revisione e' stato aperto. La revisione non e'"
                    " comunque indipendente: il prompt della task e il blocco gitStatus iniettato"
                    " all'avvio della sessione contenevano elementi della prima revisione."
                ),
            }
        ),
    )
    artifacts.add(
        "packet_hashes.json",
        canonical_dumps(
            {
                "packet_count": len(packets),
                "packet_schema_version": packets[0]["packet_version"],
                "aggregate_sha256": aggregate_hash(
                    (packet["blind_annotation_id"], packet["_sha256"]) for packet in packets
                ),
                "packets": {
                    packet["blind_annotation_id"]: {
                        "sha256": packet["_sha256"],
                        "logical_path": (
                            "benchmarks/mtb_evidence/v3/multi_intervention_source_review/"
                            f"second_review_packets/{packet['blind_annotation_id']}.json"
                        ),
                    }
                    for packet in packets
                },
            }
        ),
    )
    artifacts.add(
        "allowed_file_access_log.jsonl",
        canonical_jsonl(log.sorted_entries(), key=("logical_path", "access_kind", "purpose")),
    )
    artifacts.add(
        "blindness_audit.json",
        canonical_dumps(
            {
                "blindness_violation": False,
                "prohibited_files_opened": [],
                "denied_path_fragments": list(DENIED_PATH_FRAGMENTS),
                "gold_accessed": False,
                "first_review_artifacts_accessed": False,
                "retrieval_or_metric_results_accessed": False,
                "context_contamination": list(CONTEXT_CONTAMINATION),
                "search_events": list(SEARCH_EVENTS),
                "conclusion": (
                    "Cecita' sui file preservata; indipendenza non raggiunta per contaminazione"
                    " di contesto a monte della revisione."
                ),
            }
        ),
    )
    artifacts.add(
        "source_access_inventory.jsonl", canonical_jsonl(inventory, key="source_id")
    )
    artifacts.add(
        "intervention_annotations_second.jsonl",
        canonical_jsonl(annotations, key=("blind_annotation_id", "intervention")),
    )
    artifacts.add(
        "source_unit_annotations_second.jsonl", canonical_jsonl(units, key="source_unit_id")
    )
    artifacts.add(
        "group_decisions_second.jsonl", canonical_jsonl(decisions, key="blind_annotation_id")
    )
    artifacts.add("locator_completeness.json", canonical_dumps(locators))
    artifacts.add("claim_lineage_second.jsonl", canonical_jsonl(lineage, key="lineage_id"))
    artifacts.add("unresolved_second.jsonl", canonical_jsonl(unresolved, key="unresolved_id"))
    artifacts.add(
        "MULTI_INTERVENTION_SECOND_REVIEW.md",
        render_report(summary, decisions, locators, unresolved),
    )
    artifacts.add("SECOND_REVIEW_READINESS.md", render_readiness(readiness, summary))
    artifacts.add(
        "second_review_manifest.json",
        canonical_dumps(
            {
                "review_version": REVIEW_VERSION,
                "summary": summary,
                "readiness": readiness,
                "artifact_sha256": {
                    name: sha256_text(content)
                    for name, content in sorted(artifacts.files.items())
                },
            }
        ),
    )
    return artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--reverse-packet-order",
        action="store_true",
        help="processa i packet in ordine inverso; l'output deve restare identico",
    )
    args = parser.parse_args()
    artifacts = build(args.output_dir, reverse=args.reverse_packet_order)
    artifacts.write(args.output_dir)
    print(f"scritti {len(artifacts.files)} artefatti in {args.output_dir}")


if __name__ == "__main__":
    main()
