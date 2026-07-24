"""Review documentale offline dei gruppi multi-intervento non risolti.

Il modulo legge esclusivamente fonti già congelate localmente. Non modifica
adapter, corpus, retriever, scoring, approval o gold e non effettua accessi di
rete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmarks.mtb_evidence.evaluation.scripts.candidate_coverage_audit import (
    _aggregate,
)
from benchmarks.mtb_evidence.evaluation.scripts.multi_intervention_adapter_review import (
    EXPECTED_ADAPTER_HASH,
    EXPECTED_ADAPTER_OUTPUT_HASH,
    EXPECTED_ALIAS_FIX_HASH,
    EXPECTED_CANDIDATE_AUDIT_HASH,
    EXPECTED_CONJUNCTIVE_FIX_HASH,
    EXPECTED_DISEASE_REVIEW_HASH,
    EXPECTED_FROZEN_V2_SERIALIZATION_HASH,
    EXPECTED_RAW_V2_INPUT_HASH,
    EXPECTED_REPOSITORY_HASH,
    EXPECTED_RETRIEVER_HASH,
    _integrity as _previous_integrity,
)


REVIEW_VERSION = "multi-intervention-source-review/1.0"
TARGET_BRANCH = "review/v3-multi-intervention-source-batch"
SOURCE_SHA = "3444d931990b0f5e20a1f0a0ae26313b96071b8f"
EXPECTED_PREVIOUS_REVIEW_HASH = (
    "6167ca9d44a1f40b5edeea04ce300bce97ac864771c6adb0c2bbfcac832c1266"
)
EXPECTED_ABSTRACT_CACHE_HASH = (
    "5d19b152a19c3ca26c69bb8b3bbf5fa9d0354c8e5db5aa6653dbd63716a75318"
)
EXPECTED_FULLTEXT_HASH = (
    "086c0cb4e777b9a187b3a71ef6796f1c27c481a6f4671e0b8b0c90044fbcf90e"
)
EXPECTED_FIRST_REVIEW_PACKET_HASH = (
    "4b3c51731859ec375cd30f6ff6f84e52a7ce4780e3de5a85aae1cea83aa54d24"
)
EXPECTED_SECOND_REVIEW_PACKET_HASH = (
    "6bb4ee225e4c273a6f24378dc5c982490cdbf3482a1e780e4c173695fe131bb6"
)
EXPECTED_AUTHOR_APPROVAL_HASH = (
    "8bdafc1188d9050898ffdfab69626ad0d8780b2f137de24bb6d0716d2129c278"
)

EXPECTED_GROUP_IDS = (
    "evidence:229",
    "evidence:275",
    "evidence:296",
    "evidence:841",
    "evidence:1483",
    "evidence:1484",
    "evidence:1851",
    "evidence:1853",
    "evidence:3811",
    "evidence:4759",
    "evidence:11240",
    "evidence:12131",
    "evidence:12156",
)

REVIEW_METADATA = {
    "reviewer_role": "author_review",
    "review_independence": "non_independent",
    "review_status": "first_review_complete",
    "propagation_policy": "prototype_only",
    "hard_filterable": False,
    "final_evaluable": False,
}


def _item(
    status: str,
    locator: str,
    unit: str,
    paraphrase: str,
    population_model: str,
    support: str,
    confidence: str,
    *,
    locator_status: str = "complete",
    note: str = "",
) -> dict[str, Any]:
    return {
        "classification": status,
        "locator": locator,
        "locator_status": locator_status,
        "documentary_unit": unit,
        "result_paraphrase": paraphrase,
        "population_or_model": population_model,
        "support_level": support,
        "confidence": confidence,
        "reviewer_note": note,
    }


# Le decisioni seguenti sono una trascrizione strutturata della prima review
# delle fonti locali. Nessun campo deriva dal gold o da metriche di retrieval.
REVIEW_SPECS: dict[str, dict[str, Any]] = {
    "evidence:229": {
        "decision": "atomic_children_supported",
        "source_supported_biomarker": (
            "EGFR Exon 19 Deletion OR EGFR L858R"
        ),
        "rationale": (
            "L'abstract riporta coorti gefitinib ed erlotinib distinte e risultati "
            "per ciascun trattamento; il biomarcatore resta il gruppo exon19del/L858R."
        ),
        "interventions": {
            "erlotinib": _item(
                "directly_tested_with_separate_result",
                "abstract#METHODS; abstract#RESULTS",
                "matched clinical cohort: erlotinib-treated patients",
                "La coorte erlotinib ha un outcome riportato separatamente dalla coorte gefitinib.",
                "recurrent/metastatic NSCLC, exon19 deletion or L858R",
                "direct clinical cohort result",
                "high",
                note="Non restringere il risultato aggregato al solo L858R.",
            ),
            "gefitinib": _item(
                "directly_tested_with_separate_result",
                "abstract#METHODS; abstract#RESULTS",
                "matched clinical cohort: gefitinib-treated patients",
                "La coorte gefitinib ha un outcome riportato separatamente dalla coorte erlotinib.",
                "recurrent/metastatic NSCLC, exon19 deletion or L858R",
                "direct clinical cohort result",
                "high",
                note="Non restringere il risultato aggregato al solo L858R.",
            ),
        },
    },
    "evidence:275": {
        "decision": "aggregate_parent_only",
        "rationale": (
            "L'abstract riporta outcome per pazienti che hanno ricevuto EGFR-TKI "
            "senza separare gefitinib da erlotinib."
        ),
        "interventions": {
            "erlotinib": _item(
                "directly_tested_in_shared_aggregate_result",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "retrospective EGFR-TKI cohort",
                "Gli outcome sono aggregati a livello di EGFR-TKI e non per singolo farmaco.",
                "70 EGFR-mutant NSCLC patients",
                "shared clinical aggregate",
                "high",
            ),
            "gefitinib": _item(
                "directly_tested_in_shared_aggregate_result",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "retrospective EGFR-TKI cohort",
                "Gli outcome sono aggregati a livello di EGFR-TKI e non per singolo farmaco.",
                "70 EGFR-mutant NSCLC patients",
                "shared clinical aggregate",
                "high",
            ),
        },
    },
    "evidence:296": {
        "decision": "atomic_children_supported",
        "rationale": (
            "Lo stesso paziente FGFR2-TACC3 ha risultati temporali distinti per "
            "pazopanib e ponatinib."
        ),
        "interventions": {
            "pazopanib hydrochloride": _item(
                "directly_tested_with_separate_result",
                "abstract#UNLABELLED, FGFR2-TACC3 patient, pazopanib sentence",
                "single FGFR2-TACC3 patient: pazopanib treatment",
                "È riportata attività antitumorale preliminare con pazopanib.",
                "single patient with sporadic intrahepatic cholangiocarcinoma",
                "direct case-level clinical result",
                "high",
            ),
            "ponatinib": _item(
                "directly_tested_with_separate_result",
                "abstract#UNLABELLED, FGFR2-TACC3 patient, post-pazopanib sentence",
                "same single patient: ponatinib after pazopanib progression",
                "Dopo progressione a pazopanib è riportata malattia stabile con ponatinib.",
                "same single FGFR2-TACC3 patient",
                "direct case-level clinical result",
                "high",
            ),
        },
    },
    "evidence:841": {
        "decision": "mixed_parent_and_children",
        "rationale": (
            "Crizotinib e ceritinib hanno risultati clinici separati; la fonte usa "
            "AUY922, mentre il record V2 usa luminespib senza mapping locale approvato."
        ),
        "interventions": {
            "ceritinib": _item(
                "directly_tested_with_separate_result",
                "full_text#Case Report, first restaging CT at 5 weeks",
                "single patient: ceritinib treatment after crizotinib",
                "La prima ristadiazione durante ceritinib mostra progressione con nuove metastasi epatiche.",
                "single patient with ALK-rearranged metastatic NSCLC and C1156Y",
                "direct case-level negative treatment result",
                "high",
            ),
            "crizotinib": _item(
                "directly_tested_with_separate_result",
                "full_text#Case Report; Figure 1A and 1E",
                "single patient: first crizotinib course",
                "La progressione durante crizotinib è associata alla selezione di ALK C1156Y.",
                "single patient with ALK-rearranged metastatic NSCLC",
                "direct case-level resistance result",
                "high",
                note="La successiva risensibilizzazione riguarda C1156Y-L1198F e resta un'unità distinta.",
            ),
            "luminespib": _item(
                "possible_alias_not_verified",
                "full_text#Case Report, HSP90 inhibitor paragraph",
                "single patient: AUY922 exposure",
                "La fonte nomina AUY922 e progressione rapida, ma non usa il nome luminespib.",
                "single patient with ALK-rearranged metastatic NSCLC and C1156Y",
                "name mapping unresolved",
                "medium",
                note="AUY922/luminespib non è promosso a alias verificato.",
            ),
        },
    },
    "evidence:1483": {
        "decision": "should_not_materialize_missing_interventions",
        "rationale": (
            "I1171N è rilevata nella biopsia di resistenza ad alectinib; crizotinib "
            "precede la comparsa documentata della mutazione."
        ),
        "interventions": {
            "alectinib hydrochloride": _item(
                "directly_tested_with_separate_result",
                "abstract#UNLABELLED, HIP1-ALK patient and I1171N clause",
                "HIP1-ALK single patient: alectinib resistance biopsy",
                "La resistenza acquisita ad alectinib coincide con I1171N nella biopsia.",
                "single HIP1-ALK NSCLC patient",
                "direct case-level resistance result",
                "high",
            ),
            "crizotinib": _item(
                "mentioned_background_only",
                "abstract#UNLABELLED, sequential treatment history",
                "HIP1-ALK single patient: treatment before I1171N detection",
                "La risposta a crizotinib è precedente alla mutazione I1171N documentata.",
                "same patient before I1171N detection",
                "temporal background only for this biomarker claim",
                "high",
            ),
        },
    },
    "evidence:1484": {
        "decision": "should_not_materialize_missing_interventions",
        "rationale": (
            "I1171S è rilevata nella biopsia di resistenza ad alectinib; crizotinib "
            "precede la comparsa documentata della mutazione."
        ),
        "interventions": {
            "alectinib hydrochloride": _item(
                "directly_tested_with_separate_result",
                "abstract#UNLABELLED, EML4-ALK patient and I1171S clause",
                "EML4-ALK single patient: alectinib resistance biopsy",
                "La resistenza acquisita ad alectinib coincide con I1171S nella biopsia.",
                "single EML4-ALK NSCLC patient",
                "direct case-level resistance result",
                "high",
            ),
            "crizotinib": _item(
                "mentioned_background_only",
                "abstract#UNLABELLED, sequential treatment history",
                "EML4-ALK single patient: treatment before I1171S detection",
                "La risposta a crizotinib è precedente alla mutazione I1171S documentata.",
                "same patient before I1171S detection",
                "temporal background only for this biomarker claim",
                "high",
            ),
        },
    },
    "evidence:1851": {
        "decision": "aggregate_parent_only",
        "rationale": (
            "L'abstract aggrega BGJ398 e PD173074 come FGFR inhibitors; "
            "BGJ398/infigratinib non è un mapping approvato in questo corpus."
        ),
        "interventions": {
            "infigratinib": _item(
                "possible_alias_not_verified",
                "abstract#UNLABELLED, final transformation-suppression sentence",
                "NIH3T3 FGFR2-BICC1 transformation experiment",
                "La fonte nomina BGJ398, non infigratinib, in un risultato condiviso con PD173074.",
                "NIH3T3 cells and xenograft transformation model",
                "development-code mapping unresolved",
                "medium",
            ),
            "pd173074": _item(
                "directly_tested_in_shared_aggregate_result",
                "abstract#UNLABELLED, final transformation-suppression sentence",
                "NIH3T3 FGFR2-BICC1 transformation experiment",
                "PD173074 è incluso nel risultato aggregato di soppressione della trasformazione.",
                "NIH3T3 cells and xenograft transformation model",
                "shared preclinical aggregate",
                "high",
            ),
        },
    },
    "evidence:1853": {
        "decision": "aggregate_parent_only",
        "rationale": (
            "L'abstract aggrega BGJ398 e PD173074 come FGFR inhibitors; "
            "BGJ398/infigratinib non è un mapping approvato in questo corpus."
        ),
        "interventions": {
            "infigratinib": _item(
                "possible_alias_not_verified",
                "abstract#UNLABELLED, final transformation-suppression sentence",
                "NIH3T3 FGFR2-AHCYL1 transformation experiment",
                "La fonte nomina BGJ398, non infigratinib, in un risultato condiviso con PD173074.",
                "NIH3T3 cells and xenograft transformation model",
                "development-code mapping unresolved",
                "medium",
            ),
            "pd173074": _item(
                "directly_tested_in_shared_aggregate_result",
                "abstract#UNLABELLED, final transformation-suppression sentence",
                "NIH3T3 FGFR2-AHCYL1 transformation experiment",
                "PD173074 è incluso nel risultato aggregato di soppressione della trasformazione.",
                "NIH3T3 cells and xenograft transformation model",
                "shared preclinical aggregate",
                "high",
            ),
        },
    },
    "evidence:3811": {
        "decision": "insufficient_for_atomicity_decision",
        "rationale": (
            "L'abstract conferma profili separati per i tre inibitori, ma non "
            "localizza il risultato specifico di L858R nel pannello di 30 mutazioni."
        ),
        "interventions": {
            "erlotinib": _item(
                "directly_tested_with_separate_result",
                "abstract#EXPERIMENTAL DESIGN AND RESULTS",
                "Ba/F3 panel of 30 EGFR mutations",
                "Sono calcolati IC50 e profili per erlotinib, ma il risultato L858R non è isolato nell'abstract.",
                "Ba/F3 activating EGFR-mutant panel",
                "intervention-specific panel result; biomarker locator insufficient",
                "medium",
                locator_status="insufficient",
            ),
            "gefitinib": _item(
                "directly_tested_with_separate_result",
                "abstract#EXPERIMENTAL DESIGN AND RESULTS",
                "Ba/F3 panel of 30 EGFR mutations",
                "Sono calcolati IC50 e profili per gefitinib, ma il risultato L858R non è isolato nell'abstract.",
                "Ba/F3 activating EGFR-mutant panel",
                "intervention-specific panel result; biomarker locator insufficient",
                "medium",
                locator_status="insufficient",
            ),
            "multikinase inhibitor aee788": _item(
                "directly_tested_with_separate_result",
                "abstract#EXPERIMENTAL DESIGN AND RESULTS",
                "Ba/F3 panel of 30 EGFR mutations",
                "Sono calcolati IC50 e profili per AEE788, ma il risultato L858R non è isolato nell'abstract.",
                "Ba/F3 activating EGFR-mutant panel",
                "intervention-specific panel result; biomarker locator insufficient",
                "medium",
                locator_status="insufficient",
            ),
        },
    },
    "evidence:4759": {
        "decision": "aggregate_parent_only",
        "rationale": (
            "I pazienti ricevono gefitinib oppure erlotinib, ma gli outcome sono "
            "riportati come EGFR-TKI aggregati."
        ),
        "interventions": {
            "erlotinib": _item(
                "directly_tested_in_shared_aggregate_result",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "62-patient uncommon-EGFR-mutation treatment cohort",
                "Gli outcome sono aggregati per pazienti trattati con uno dei due TKI.",
                "NSCLC patients with uncommon EGFR mutations",
                "shared clinical aggregate",
                "high",
            ),
            "gefitinib": _item(
                "directly_tested_in_shared_aggregate_result",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "62-patient uncommon-EGFR-mutation treatment cohort",
                "Gli outcome sono aggregati per pazienti trattati con uno dei due TKI.",
                "NSCLC patients with uncommon EGFR mutations",
                "shared clinical aggregate",
                "high",
            ),
        },
    },
    "evidence:11240": {
        "decision": "combination_regimen_required",
        "rationale": (
            "Il risultato riguarda ramucirumab più erlotinib rispetto a placebo "
            "più erlotinib; i componenti non sono claim indipendenti."
        ),
        "interventions": {
            "erlotinib": _item(
                "directly_tested_in_combination_regimen",
                "abstract#METHODS; abstract#FINDINGS",
                "RELAY trial backbone in both arms",
                "Erlotinib è il backbone in entrambi i bracci e non ha un effetto separabile nel confronto.",
                "untreated EGFR-mutated metastatic NSCLC",
                "combination-regimen component",
                "high",
            ),
            "ramucirumab": _item(
                "directly_tested_in_combination_regimen",
                "abstract#METHODS; abstract#FINDINGS",
                "RELAY ramucirumab-plus-erlotinib arm",
                "L'effetto è attribuito al regime ramucirumab più erlotinib.",
                "untreated EGFR-mutated metastatic NSCLC",
                "combination-regimen component",
                "high",
            ),
        },
    },
    "evidence:12131": {
        "decision": "combination_regimen_required",
        "rationale": (
            "Amivantamab e lazertinib sono somministrati come regime congiunto; "
            "l'abstract non separa l'effetto dei componenti."
        ),
        "interventions": {
            "amivantamab": _item(
                "directly_tested_in_combination_regimen",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "MARIPOSA amivantamab-lazertinib arm",
                "L'outcome è riportato per amivantamab-lazertinib contro osimertinib.",
                "treatment-naive EGFR-mutated advanced NSCLC",
                "combination-regimen component",
                "high",
            ),
            "lazertinib": _item(
                "directly_tested_in_combination_regimen",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "MARIPOSA amivantamab-lazertinib arm",
                "L'outcome è riportato per amivantamab-lazertinib contro osimertinib.",
                "treatment-naive EGFR-mutated advanced NSCLC",
                "combination-regimen component",
                "high",
            ),
        },
    },
    "evidence:12156": {
        "decision": "combination_regimen_required",
        "rationale": (
            "Amivantamab e carboplatino appartengono a regimi con "
            "carboplatino-pemetrexed, con o senza lazertinib."
        ),
        "interventions": {
            "amivantamab": _item(
                "directly_tested_in_combination_regimen",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "MARIPOSA-2 amivantamab-chemotherapy arms",
                "Gli outcome sono riportati per regimi contenenti amivantamab e chemioterapia.",
                "EGFR-mutated advanced NSCLC after osimertinib progression",
                "combination-regimen component",
                "high",
            ),
            "carboplatin": _item(
                "directly_tested_in_combination_regimen",
                "abstract#PATIENTS AND METHODS; abstract#RESULTS",
                "MARIPOSA-2 carboplatin-pemetrexed chemotherapy backbone",
                "Carboplatino è parte della combinazione carboplatino-pemetrexed, non un claim singolo.",
                "EGFR-mutated advanced NSCLC after osimertinib progression",
                "combination-regimen component",
                "high",
            ),
        },
    },
}


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(value))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_jsonl_bytes(rows))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_text_sha(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _numeric_key(value: str) -> tuple[int, str]:
    suffix = value.rsplit(":", 1)[-1]
    return (int(suffix), value) if suffix.isdigit() else (10**12, value)


def _blind_id(prefix: str, graph_id: str) -> str:
    digest = hashlib.sha256(f"{REVIEW_VERSION}|{graph_id}".encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _child_id(
    graph_id: str,
    intervention: str,
    direction: str,
    polarity: str,
    source_unit_id: str,
) -> str:
    material = "|".join(
        (graph_id, intervention.casefold(), direction, polarity, source_unit_id)
    )
    return f"ES-CHILD-{hashlib.sha256(material.encode()).hexdigest()[:20]}"


def _groups(root: Path, *, reverse_inputs: bool = False) -> list[dict[str, Any]]:
    rows = _read_jsonl(
        root
        / "benchmarks/mtb_evidence/v3/multi_intervention_adapter_review"
        / "multi_intervention_groups.jsonl"
    )
    rows = [
        row
        for row in rows
        if row["primary_classification"] == "unresolved_without_document_review"
    ]
    rows.sort(key=lambda row: _numeric_key(str(row["graph_evidence_id"])))
    if reverse_inputs:
        rows.reverse()
    actual = tuple(
        sorted((str(row["graph_evidence_id"]) for row in rows), key=_numeric_key)
    )
    if actual != EXPECTED_GROUP_IDS:
        raise RuntimeError(f"review scope mismatch: {actual} != {EXPECTED_GROUP_IDS}")
    return rows


def _source_cache(root: Path) -> dict[str, dict[str, Any]]:
    path = (
        root
        / "benchmarks/mtb_evidence/v3/priority_curation/source_abstract_cache.jsonl"
    )
    return {str(row["pmid"]): row for row in _read_jsonl(path)}


def _source_access(
    root: Path, groups: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    cache = _source_cache(root)
    source_ids = sorted({str(source) for group in groups for source in group["source_ids"]})
    rows: list[dict[str, Any]] = []
    lookup: dict[str, dict[str, Any]] = {}
    for source_id in source_ids:
        review_text = ""
        source = cache.get(source_id)
        if not source or not source.get("abstract_available"):
            row = {
                "source_id": f"PMID:{source_id}",
                "source_access_status": "unavailable_locally",
                "locator_status": "insufficient",
                "local_material": [],
                "title": source.get("title", "") if source else "",
            }
        else:
            fulltext = source_id == "26698910"
            review_text = str(source.get("abstract_text") or "")
            local_material = [
                {
                    "kind": "abstract",
                    "logical_path": (
                        "benchmarks/mtb_evidence/v3/priority_curation/"
                        "source_abstract_cache.jsonl"
                    ),
                    "sha256": source["abstract_sha256"],
                }
            ]
            if fulltext:
                fulltext_path = (
                    root.parent
                    / "data_expl/benchmark/benchmark_papers/fulltext_26698910.txt"
                )
                fulltext_text = fulltext_path.read_text(encoding="utf-8")
                start_marker = "Case Report A 52-year-old woman"
                end_marker = "Methods Patient"
                start = fulltext_text.index(start_marker)
                end = fulltext_text.index(end_marker, start)
                review_text = fulltext_text[start:end].strip()
                local_material.append(
                    {
                        "kind": "full_text",
                        "logical_path": (
                            "local_source://data_expl/benchmark/benchmark_papers/"
                            "fulltext_26698910.txt"
                        ),
                        "sha256": EXPECTED_FULLTEXT_HASH,
                    }
                )
            row = {
                "source_id": f"PMID:{source_id}",
                "source_access_status": "full_text" if fulltext else "abstract_only",
                "locator_status": "available",
                "local_material": local_material,
                "title": source["title"],
                "abstract_sections": [
                    str(section["label"]) for section in source["abstract_sections"]
                ],
            }
        rows.append(row)
        lookup[source_id] = {
            **row,
            "source_record": source,
            "review_text": review_text,
        }
    return rows, lookup


def _integrity(root: Path, gold_bundle: Path) -> dict[str, Any]:
    values = _previous_integrity(root, gold_bundle)
    checks = {
        "previous_multi_intervention_review": (
            [root / "benchmarks/mtb_evidence/v3/multi_intervention_adapter_review"],
            EXPECTED_PREVIOUS_REVIEW_HASH,
        ),
        "previous_first_review_packets": (
            [
                root
                / "benchmarks/mtb_evidence/v3/priority_curation/annotation_packets"
                / "first_review"
            ],
            EXPECTED_FIRST_REVIEW_PACKET_HASH,
        ),
        "previous_second_review_packets": (
            [
                root
                / "benchmarks/mtb_evidence/v3/priority_curation/annotation_packets"
                / "second_review"
            ],
            EXPECTED_SECOND_REVIEW_PACKET_HASH,
        ),
        "previous_author_approvals": (
            sorted((root / "benchmarks/mtb_evidence/v3").glob("author_approval*")),
            EXPECTED_AUTHOR_APPROVAL_HASH,
        ),
        "local_abstract_cache": (
            [
                root
                / "benchmarks/mtb_evidence/v3/priority_curation"
                / "source_abstract_cache.jsonl"
            ],
            EXPECTED_ABSTRACT_CACHE_HASH,
        ),
    }
    for label, (paths, expected) in checks.items():
        result = _aggregate(root, paths)
        if result["aggregate_sha256"] != expected:
            raise RuntimeError(
                f"{label} hash mismatch: {result['aggregate_sha256']} != {expected}"
            )
        values[label] = result
    fulltext = (
        root.parent / "data_expl/benchmark/benchmark_papers/fulltext_26698910.txt"
    )
    if not fulltext.is_file() or _sha(fulltext) != EXPECTED_FULLTEXT_HASH:
        raise RuntimeError("local full text 26698910 hash mismatch or missing")
    values["local_fulltext_26698910"] = {
        "logical_path": (
            "local_source://data_expl/benchmark/benchmark_papers/"
            "fulltext_26698910.txt"
        ),
        "sha256": EXPECTED_FULLTEXT_HASH,
    }
    values["frozen_hash_contract"] = {
        "evidence_statement_repository": EXPECTED_REPOSITORY_HASH,
        "v2_adapter": EXPECTED_ADAPTER_HASH,
        "qualified_retriever": EXPECTED_RETRIEVER_HASH,
        "frozen_v2_serialization": EXPECTED_FROZEN_V2_SERIALIZATION_HASH,
        "raw_v2_adapter_inputs": EXPECTED_RAW_V2_INPUT_HASH,
        "adapter_outputs": EXPECTED_ADAPTER_OUTPUT_HASH,
        "candidate_coverage_audit": EXPECTED_CANDIDATE_AUDIT_HASH,
        "conjunctive_biomarker_fix": EXPECTED_CONJUNCTIVE_FIX_HASH,
        "disease_normalization_review": EXPECTED_DISEASE_REVIEW_HASH,
        "verified_disease_alias_fix": EXPECTED_ALIAS_FIX_HASH,
    }
    return values


def _source_excerpt(access: dict[str, Any]) -> str:
    if access["source_access_status"] == "unavailable_locally":
        return ""
    return str(access.get("review_text") or "")


def _packet(group: dict[str, Any], access: dict[str, Any], *, second: bool) -> dict[str, Any]:
    packet = {
        "packet_version": REVIEW_VERSION,
        "blind_annotation_id": _blind_id("MI-B" if second else "MI-A", group["graph_evidence_id"]),
        "graph_evidence_id": group["graph_evidence_id"],
        "source_ids": [f"PMID:{value}" for value in group["source_ids"]],
        "statement_id": group["statement_id"],
        "biomarker": group["biomarker"],
        "disease": group["disease"],
        "directions": group["directions"],
        "assertion_polarities": group["assertion_polarities"],
        "current_statement_intervention": group["statement_intervention"],
        "candidate_interventions": group["v2_interventions_normalized"],
        "source_access_status": access["source_access_status"],
        "source_title": access["title"],
        "local_material": access["local_material"],
        "source_text_kind": (
            "full_text_excerpt"
            if access["source_access_status"] == "full_text"
            else "abstract"
        ),
        "source_text": _source_excerpt(access),
        "review_questions": [
            "Il risultato è attribuibile separatamente a ogni intervento?",
            "Il risultato è aggregato, un regime, un comparatore o una menzione?",
            "Il locator identifica l'unità documentale e il biomarcatore?",
        ],
        "prohibited_inferences": [
            "aggregate_to_specific",
            "class_to_member",
            "comparator_to_support",
            "mention_to_tested",
            "preclinical_to_clinical",
            "pending_mapping_to_verified_alias",
        ],
    }
    if not second:
        packet["review_assignment"] = {
            "reviewer_role": "author_review",
            "review_independence": "non_independent",
        }
    return packet


def _build_review(
    groups: list[dict[str, Any]], access_by_source: dict[str, dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    annotations: list[dict[str, Any]] = []
    source_units: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for group in sorted(groups, key=lambda row: _numeric_key(row["graph_evidence_id"])):
        graph_id = str(group["graph_evidence_id"])
        spec = REVIEW_SPECS[graph_id]
        source_id = str(group["source_ids"][0])
        source_unit_id = str(group["qualification_profile_unit_ids"][0])
        for intervention in sorted(group["v2_interventions_normalized"]):
            detail = spec["interventions"][intervention]
            row = {
                "annotation_id": hashlib.sha256(
                    f"{graph_id}|{intervention}".encode()
                ).hexdigest()[:20],
                "graph_evidence_id": graph_id,
                "statement_id": group["statement_id"],
                "source_id": f"PMID:{source_id}",
                "source_unit_id": source_unit_id,
                "biomarker": spec.get("source_supported_biomarker", group["biomarker"]),
                "parent_biomarker": group["biomarker"],
                "disease": group["disease"],
                "intervention": intervention,
                "direction": group["directions"][0],
                "polarity": group["assertion_polarities"][0],
                **detail,
                **REVIEW_METADATA,
            }
            annotations.append(row)
            source_units.append(
                {
                    "source_unit_annotation_id": (
                        f"SUA-{hashlib.sha256((graph_id + '|' + intervention).encode()).hexdigest()[:16]}"
                    ),
                    "graph_evidence_id": graph_id,
                    "source_id": f"PMID:{source_id}",
                    "source_unit_id": source_unit_id,
                    "documentary_unit": detail["documentary_unit"],
                    "locator": detail["locator"],
                    "locator_status": detail["locator_status"],
                    "population_or_model": detail["population_or_model"],
                    "clinical_preclinical_context": (
                        "preclinical"
                        if any(
                            token in detail["population_or_model"].casefold()
                            for token in ("ba/f3", "nih3t3", "xenograft")
                        )
                        else "clinical"
                    ),
                    "intervention": intervention,
                    "result_paraphrase": detail["result_paraphrase"],
                    **REVIEW_METADATA,
                }
            )
        decisions.append(
            {
                "graph_evidence_id": graph_id,
                "statement_id": group["statement_id"],
                "source_ids": [f"PMID:{value}" for value in group["source_ids"]],
                "source_access_status": access_by_source[source_id][
                    "source_access_status"
                ],
                "atomicity_decision": spec["decision"],
                "rationale": spec["rationale"],
                "intervention_count": len(group["v2_interventions_normalized"]),
                "locators": sorted(
                    {
                        detail["locator"]
                        for detail in spec["interventions"].values()
                    }
                ),
                "locator_statuses": sorted(
                    {
                        detail["locator_status"]
                        for detail in spec["interventions"].values()
                    }
                ),
                "all_interventions_classified": True,
                "all_decisions_have_locator": True,
                **REVIEW_METADATA,
            }
        )
    annotations.sort(key=lambda row: (_numeric_key(row["graph_evidence_id"]), row["intervention"]))
    source_units.sort(
        key=lambda row: (_numeric_key(row["graph_evidence_id"]), row["intervention"])
    )
    decisions.sort(key=lambda row: _numeric_key(row["graph_evidence_id"]))
    return {
        "annotations": annotations,
        "source_units": source_units,
        "decisions": decisions,
    }


def _simulation(
    groups: list[dict[str, Any]], review: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    allowed_status = {"directly_tested_with_separate_result"}
    decision_by_id = {
        row["graph_evidence_id"]: row["atomicity_decision"]
        for row in review["decisions"]
    }
    child_allowed_decisions = {
        "atomic_children_supported",
        "mixed_parent_and_children",
        "should_not_materialize_missing_interventions",
    }
    children: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    for row in review["annotations"]:
        decision = decision_by_id[row["graph_evidence_id"]]
        if row["classification"] in allowed_status and decision in child_allowed_decisions:
            child = {
                "simulated_child_statement_id": _child_id(
                    row["graph_evidence_id"],
                    row["intervention"],
                    row["direction"],
                    row["polarity"],
                    row["source_unit_id"],
                ),
                "parent_graph_evidence_id": row["graph_evidence_id"],
                "parent_statement_id": row["statement_id"],
                "source_id": row["source_id"],
                "source_unit_id": row["source_unit_id"],
                "biomarker": row["biomarker"],
                "intervention": row["intervention"],
                "direction": row["direction"],
                "polarity": row["polarity"],
                "locator": row["locator"],
            }
            children.append(child)
        else:
            unsupported.append(
                {
                    "graph_evidence_id": row["graph_evidence_id"],
                    "statement_id": row["statement_id"],
                    "intervention": row["intervention"],
                    "classification": row["classification"],
                    "atomicity_decision": decision,
                    "reason": (
                        "no separate claim-level child authorized by first review"
                    ),
                }
            )
    children.sort(
        key=lambda row: (_numeric_key(row["parent_graph_evidence_id"]), row["intervention"])
    )
    unsupported.sort(
        key=lambda row: (_numeric_key(row["graph_evidence_id"]), row["intervention"])
    )
    child_ids = [row["simulated_child_statement_id"] for row in children]
    if len(child_ids) != len(set(child_ids)):
        raise RuntimeError("simulated child statement ID collision")
    decisions = Counter(row["atomicity_decision"] for row in review["decisions"])
    return {
        "simulation_version": "post-source-review-schema-simulation/1.0",
        "operational_corpus_modified": False,
        "parent_statements_preserved": len(groups),
        "parent_graph_evidence_ids_preserved": len(groups),
        "simulated_child_statement_count": len(children),
        "simulated_child_statements": children,
        "non_materializable_intervention_count": len(unsupported),
        "non_materializable_interventions": unsupported,
        "combination_regimen_group_count": decisions["combination_regimen_required"],
        "verified_alias_merge_count": decisions["verified_alias_merge"],
        "unresolved_group_count": decisions["insufficient_for_atomicity_decision"],
        "current_operational_statement_count": 147,
        "simulated_resulting_statement_count": 147 + len(children),
        "new_qualification_links_required": len(children),
        "qualified_evidence_views_to_regenerate": len(children),
        "source_units_involved": len(
            {row["source_unit_id"] for row in review["annotations"]}
        ),
        "id_strategy": {
            "formula": (
                "sha256(graph_evidence_id + canonical_intervention + direction + "
                "polarity + source_unit_id)"
            ),
            "prefix": "ES-CHILD-",
            "digest_characters": 20,
            "order_independent": True,
            "collision_count": 0,
            "parent_graph_evidence_id_preserved": True,
            "alias_stability_condition": (
                "canonical intervention may be used only after verified mapping"
            ),
        },
    }


def _architecture(review: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    counts = Counter(row["atomicity_decision"] for row in review["decisions"])
    return {
        "recommendation": "mixed_policy",
        "recommendation_basis": "documentary_patterns_only",
        "gold_used": False,
        "retrieval_metrics_used": False,
        "observed_pattern_counts": dict(sorted(counts.items())),
        "rationale": (
            "Le fonti locali mostrano contemporaneamente risultati separabili, "
            "aggregati, regimi di combinazione, esposizioni antecedenti e mapping "
            "terminologici non verificati. Conservare un parent evidence record e "
            "creare child atomici solo per risultati separati, mantenendo parent-only "
            "e regimen negli altri casi, è la rappresentazione più fedele."
        ),
        "adapter_changes_proposed": [
            "introduce parent evidence identity distinct from atomic therapeutic claims",
            "materialize child claims only after claim-level source support",
            "represent combination regimen as a unit, not independent components",
            "preserve aggregate-only and unresolved parent records",
            "store intervention-to-result locator and review status",
        ],
        "regenerations_required_if_approved": [
            "adapter output regeneration",
            "qualification corpus regeneration",
            "qualification link regeneration",
            "QualifiedEvidenceView regeneration",
            "retrieval benchmark regeneration",
        ],
        "changes_forbidden_without_further_review": [
            "aggregate-to-specific attribution",
            "pending mapping promotion",
            "automatic atomization of regimen components",
            "gold-driven representation choice",
        ],
        "second_independent_review_required": True,
    }


def _expected_output_relpaths(
    groups: list[dict[str, Any]], *, include_docs: bool
) -> set[str]:
    names = {
        "review_scope.json",
        "source_access_inventory.jsonl",
        "intervention_level_annotations.jsonl",
        "source_unit_annotations.jsonl",
        "group_atomicity_decisions.jsonl",
        "unsupported_interventions.jsonl",
        "aggregate_results.jsonl",
        "combination_regimens.jsonl",
        "verified_aliases.jsonl",
        "unresolved_groups.jsonl",
        "post_review_schema_simulation.json",
        "architectural_recommendation.json",
        "review_manifest.json",
    }
    for group in groups:
        graph_id = str(group["graph_evidence_id"])
        names.add(f"group_review_packets/{_blind_id('MI-A', graph_id)}.json")
        names.add(f"second_review_packets/{_blind_id('MI-B', graph_id)}.json")
    if include_docs:
        names.update(
            {
                "MULTI_INTERVENTION_SOURCE_REVIEW.md",
                "ATOMICITY_DECISION_REPORT.md",
                "ADAPTER_MIGRATION_READINESS.md",
            }
        )
    return names


def _validate_output_inventory(output_dir: Path, expected: set[str]) -> None:
    if not output_dir.exists():
        return
    actual = {
        path.relative_to(output_dir).as_posix()
        for path in output_dir.rglob("*")
        if path.is_file()
    }
    unexpected = sorted(actual - expected)
    if unexpected:
        raise RuntimeError(f"unexpected output artifacts: {unexpected}")


def _markdown_reports(
    output_dir: Path,
    access: list[dict[str, Any]],
    review: dict[str, list[dict[str, Any]]],
    simulation: dict[str, Any],
    architecture: dict[str, Any],
) -> None:
    source_counts = Counter(row["source_access_status"] for row in access)
    decision_counts = Counter(row["atomicity_decision"] for row in review["decisions"])
    class_counts = Counter(row["classification"] for row in review["annotations"])
    rows = [
        "| Graph evidence | PMID | Decisione | Interventi |",
        "|---|---|---|---:|",
    ]
    for decision in review["decisions"]:
        rows.append(
            f"| `{decision['graph_evidence_id']}` | "
            f"{', '.join(decision['source_ids'])} | "
            f"`{decision['atomicity_decision']}` | "
            f"{decision['intervention_count']} |"
        )
    main = f"""# Multi-intervention source review

Review offline claim-level dei 13 gruppi congelati. Sono stati consultati solo
materiali locali: {source_counts['full_text']} fonte full-text,
{source_counts['abstract_only']} abstract-only e
{source_counts['unavailable_locally']} non disponibili.

{chr(10).join(rows)}

## Vincoli

- Gold e metriche di retrieval non sono stati usati per le decisioni.
- Nessun aggregate è stato trasformato in claim specifico.
- Nessun mapping pending è stato promosso.
- Le decisioni sono `prototype_only`, non hard-filterable e non final.

## Esito

La raccomandazione è `{architecture['recommendation']}`. Sono simulati
{simulation['simulated_child_statement_count']} child statement e sono
preservati {simulation['parent_statements_preserved']} parent; il corpus
operativo non è stato modificato.
"""
    atomicity = f"""# Atomicity decision report

## Decisioni per gruppo

{chr(10).join(f"- `{key}`: {value}" for key, value in sorted(decision_counts.items()))}

## Classificazioni intervention-level

{chr(10).join(f"- `{key}`: {value}" for key, value in sorted(class_counts.items()))}

## Regole applicate

Un child è autorizzato solo con intervento, risultato, direzione/polarità,
fonte e locator distinti. Risultati aggregati, componenti di regimen,
comparatori, menzioni e alias non verificati non diventano child.
"""
    readiness = f"""# Adapter migration readiness

- source_review_complete: true
- atomic_groups_identified: true
- aggregate_groups_identified: true
- regimen_groups_identified: true
- unresolved_groups_remaining: {str(simulation['unresolved_group_count'] > 0).lower()}
- unresolved_group_count: {simulation['unresolved_group_count']}
- second_review_required: true
- architectural_decision_ready: true
- adapter_schema_revision_ready: false
- corpus_regeneration_ready: false
- hierarchy_policy_ready: false
- full_exploratory_rerun_ready: false

La decisione architetturale è pronta come proposta, ma migrazione e
rigenerazione restano bloccate dalla seconda review indipendente, dal gruppo
con locator biomarcatore insufficiente e dai mapping pending.
"""
    (output_dir / "MULTI_INTERVENTION_SOURCE_REVIEW.md").write_text(
        main, encoding="utf-8", newline="\n"
    )
    (output_dir / "ATOMICITY_DECISION_REPORT.md").write_text(
        atomicity, encoding="utf-8", newline="\n"
    )
    (output_dir / "ADAPTER_MIGRATION_READINESS.md").write_text(
        readiness, encoding="utf-8", newline="\n"
    )


def generate(
    root: Path,
    output_dir: Path,
    gold_bundle: Path,
    *,
    reverse_inputs: bool = False,
    include_docs: bool = True,
) -> dict[str, Any]:
    integrity = _integrity(root, gold_bundle)
    groups = _groups(root, reverse_inputs=reverse_inputs)
    groups.sort(key=lambda row: _numeric_key(row["graph_evidence_id"]))
    expected_output = _expected_output_relpaths(groups, include_docs=include_docs)
    _validate_output_inventory(output_dir, expected_output)
    access, access_by_source = _source_access(root, groups)
    review = _build_review(groups, access_by_source)
    simulation = _simulation(groups, review)
    architecture = _architecture(review)

    output_dir.mkdir(parents=True, exist_ok=True)
    scope = {
        "review_version": REVIEW_VERSION,
        "branch": TARGET_BRANCH,
        "source_sha": SOURCE_SHA,
        "graph_evidence_group_count": len(groups),
        "graph_evidence_ids": [row["graph_evidence_id"] for row in groups],
        "source_count": len(access),
        "intervention_count": len(review["annotations"]),
        "source_priority": [
            "local_full_text",
            "local_supplement",
            "local_abstract",
            "local_structured_metadata",
        ],
        "network_used": False,
        "neo4j_used": False,
        "llm_completion_used": False,
        "gold_used_for_decision": False,
    }
    _write_json(output_dir / "review_scope.json", scope)
    _write_jsonl(output_dir / "source_access_inventory.jsonl", access)
    for group in groups:
        source_id = str(group["source_ids"][0])
        _write_json(
            output_dir
            / "group_review_packets"
            / f"{_blind_id('MI-A', group['graph_evidence_id'])}.json",
            _packet(group, access_by_source[source_id], second=False),
        )
        _write_json(
            output_dir
            / "second_review_packets"
            / f"{_blind_id('MI-B', group['graph_evidence_id'])}.json",
            _packet(group, access_by_source[source_id], second=True),
        )
    _write_jsonl(
        output_dir / "intervention_level_annotations.jsonl", review["annotations"]
    )
    _write_jsonl(output_dir / "source_unit_annotations.jsonl", review["source_units"])
    _write_jsonl(
        output_dir / "group_atomicity_decisions.jsonl", review["decisions"]
    )
    _write_jsonl(
        output_dir / "unsupported_interventions.jsonl",
        simulation["non_materializable_interventions"],
    )
    _write_jsonl(
        output_dir / "aggregate_results.jsonl",
        [
            row
            for row in review["decisions"]
            if row["atomicity_decision"] == "aggregate_parent_only"
        ],
    )
    _write_jsonl(
        output_dir / "combination_regimens.jsonl",
        [
            row
            for row in review["decisions"]
            if row["atomicity_decision"] == "combination_regimen_required"
        ],
    )
    _write_jsonl(
        output_dir / "verified_aliases.jsonl",
        [
            row
            for row in review["annotations"]
            if row["classification"] == "development_code_verified_same_intervention"
        ],
    )
    _write_jsonl(
        output_dir / "unresolved_groups.jsonl",
        [
            row
            for row in review["decisions"]
            if row["atomicity_decision"] == "insufficient_for_atomicity_decision"
        ],
    )
    _write_json(output_dir / "post_review_schema_simulation.json", simulation)
    _write_json(output_dir / "architectural_recommendation.json", architecture)
    if include_docs:
        _markdown_reports(output_dir, access, review, simulation, architecture)

    artifact_hashes = {
        relative: _sha(output_dir / relative)
        for relative in sorted(expected_output - {"review_manifest.json"})
    }
    decisions_hash = hashlib.sha256(
        _jsonl_bytes(review["decisions"])
    ).hexdigest()
    manifest = {
        "manifest_version": REVIEW_VERSION,
        "branch": TARGET_BRANCH,
        "source_sha": SOURCE_SHA,
        "generator_sha256": _canonical_text_sha(Path(__file__)),
        "review_phase": "targeted_first_source_review",
        "reviewer_role": "author_review",
        "review_independence": "non_independent",
        "propagation_policy": "prototype_only",
        "hard_filterable": False,
        "final_evaluable": False,
        "source_review_complete": len(review["decisions"]) == 13,
        "group_count": len(review["decisions"]),
        "source_count": len(access),
        "intervention_count": len(review["annotations"]),
        "decisions_frozen_before_gold_access": True,
        "decision_hash": decisions_hash,
        "gold_content_loaded": False,
        "gold_used_for_decision": False,
        "gold_bundle_hash": integrity["gold_bundle"]["aggregate_sha256"],
        "network_used": False,
        "neo4j_used": False,
        "llm_completion_used": False,
        "adapter_modified": False,
        "corpus_modified": False,
        "retriever_modified": False,
        "scoring_modified": False,
        "integrity": integrity,
        "artifact_hashes": artifact_hashes,
    }
    _write_json(output_dir / "review_manifest.json", manifest)
    return {
        "scope": scope,
        "access": access,
        "review": review,
        "simulation": simulation,
        "architecture": architecture,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(
            _PROJECT_ROOT
            / "benchmarks/mtb_evidence/v3/multi_intervention_source_review"
        ),
    )
    parser.add_argument(
        "--gold-bundle",
        type=Path,
        default=_PROJECT_ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle",
    )
    parser.add_argument("--reverse-inputs", action="store_true")
    parser.add_argument("--without-docs", action="store_true")
    args = parser.parse_args()
    result = generate(
        _PROJECT_ROOT,
        args.output_dir,
        args.gold_bundle,
        reverse_inputs=args.reverse_inputs,
        include_docs=not args.without_docs,
    )
    print(
        json.dumps(
            {
                "groups": result["scope"]["graph_evidence_group_count"],
                "sources": result["scope"]["source_count"],
                "interventions": result["scope"]["intervention_count"],
                "children": result["simulation"]["simulated_child_statement_count"],
                "recommendation": result["architecture"]["recommendation"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
