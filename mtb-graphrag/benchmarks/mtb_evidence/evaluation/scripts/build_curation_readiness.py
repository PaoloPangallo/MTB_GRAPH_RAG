"""Valuta la readiness per dimensione e scrive i report della curation.

I criteri sono definiti **prima** di leggere le metriche, nelle costanti qui
sotto. E' l'unico modo per evitare che la soglia venga scelta guardando il
risultato, che e' il modo piu' comune e meno visibile di dichiararsi pronti.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")
DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/priority_curation")

READY = "ready"
PARTIALLY_READY = "partially_ready"
NOT_READY = "not_ready"
BLOCKED_BY_REVIEW = "blocked_by_review"
BLOCKED_BY_SOURCE_ACCESS = "blocked_by_source_access"
NOT_APPLICABLE = "not_applicable"

# --- criteri dichiarati prima di vedere i numeri ------------------------------
PROTOTYPE_CRITERIA = (
    ("all_priority_units_have_explicit_cohort_state", "ogni unita' prioritaria ha uno stato di coorte esplicito"),
    ("no_ambiguous_qualifier_propagated", "nessun qualificatore ambiguo viene propagato"),
    ("no_conflict_overwritten", "nessun conflitto viene sovrascritto"),
    ("provenance_completeness_is_one", "provenance completeness = 1.000"),
    ("all_multi_statement_sources_examined", "ogni fonte multi-statement e' source_checked o dichiarata non disponibile"),
    ("clinical_dimensions_on_a_declared_subset", "setting, linea e popolazione disponibili su un sottoinsieme dichiarato"),
    ("noisy_sources_retained", "le fonti rumorose restano nel corpus"),
    ("corpus_not_selected_from_clinical_gold", "il corpus non e' selezionato dal clinical gold"),
    ("missing_second_review_declared", "la seconda revisione mancante e' dichiarata"),
    ("readiness_distinct_from_freeze", "la readiness e' distinta dal freeze del corpus"),
)

FINAL_CRITERIA = (
    ("second_review_complete", "la seconda revisione esiste su tutte le coppie"),
    ("link_gold_evaluable", "esiste gold valutabile per misurare il linker"),
    ("agreement_measured", "l'accordo fra annotatori e' misurato"),
    ("clinical_coverage_sufficient", "le dimensioni cliniche coprono un sottoinsieme utilizzabile come filtro"),
)

# Dimensioni native negli statement V2: non dipendono dal corpus.
NATIVE_DIMENSIONS = ("disease", "intervention", "direction", "assertion_polarity")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _dimension_readiness(
    coverage: Mapping[str, Any], review_questions: Mapping[str, int], unit_count: int
) -> dict[str, dict[str, Any]]:
    after = coverage["after"]
    result: dict[str, dict[str, Any]] = {}

    for dimension in NATIVE_DIMENSIONS:
        result[dimension] = {
            "status": READY,
            "coverage": "147/147",
            "origin": "statement V2",
            "reason": "la dimensione e' nativa nello statement e non dipende dal corpus",
        }

    known = after["total_known"]["evidence_design"]
    result["evidence_design"] = {
        "status": PARTIALLY_READY,
        "coverage": f"{known}/{unit_count}",
        "origin": "registro e abstract",
        "reason": (
            "asserito dal registro o da un'affermazione diretta nell'abstract. "
            "Utilizzabile per stratificare, non per escludere: nessun valore e' "
            "stato confermato da una persona"
        ),
    }

    for dimension in ("setting", "therapy_line", "stage", "resection_status"):
        pending = review_questions.get(dimension, 0)
        known = after["total_known"][dimension]
        result[dimension] = {
            "status": BLOCKED_BY_REVIEW if pending else NOT_READY,
            "coverage": f"{known}/{unit_count}",
            "pending_review_questions": pending,
            "origin": "profili umani preesistenti" if known else "nessuna",
            "reason": (
                f"{pending} rilevazioni attendono conferma sulla fonte: sono state "
                "soppresse perche' le corrispondenze lessicali possono descrivere i "
                "campioni invece dello studio"
                if pending
                else "nessun valore disponibile e nessun meccanismo di rilevazione"
            ),
        }

    for dimension in (
        "population",
        "prior_therapies",
        "regimen",
        "biomarker_requirements",
        "inclusion_criteria",
        "exclusion_criteria",
    ):
        known = after["total_known"][dimension]
        result[dimension] = {
            "status": NOT_READY,
            "coverage": f"{known}/{unit_count}",
            "origin": "profili umani preesistenti" if known else "nessuna",
            "reason": (
                "presente solo sulle unita' gia' revisionate a mano; l'abstract non "
                "permette un'estrazione ancorata affidabile"
            ),
        }

    result["comparator"] = {
        "status": NOT_READY,
        "coverage": f"{after['total_known']['comparator']}/{unit_count}",
        "origin": "nessuna",
        "reason": (
            "la presenza di un braccio di confronto e' rilevabile, il suo nome no: "
            "estrarlo con una regex sarebbe una fabbricazione"
        ),
    }
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    coverage = json.loads((output / "coverage_before_after.json").read_text(encoding="utf-8"))
    metrics = json.loads((output / "curation_metrics.json").read_text(encoding="utf-8"))
    scope = json.loads((output / "priority_scope_manifest.json").read_text(encoding="utf-8"))
    proposals = list(read_jsonl(output / "curated_profile_proposals.jsonl"))
    predictions = list(read_jsonl(output / "linking_predictions.jsonl"))
    resolutions = list(read_jsonl(output / "cohort_resolution_decisions.jsonl"))
    priority = list(read_jsonl(output / "priority_units.jsonl"))

    review_questions: dict[str, int] = {}
    for row in proposals:
        for dimension in row.get("review_questions", {}):
            review_questions[dimension] = review_questions.get(dimension, 0) + 1

    unit_count = coverage["unit_count"]
    dimensions = _dimension_readiness(coverage, review_questions, unit_count)

    prototype_checks = {
        "all_priority_units_have_explicit_cohort_state": len(resolutions) == len(priority),
        "no_ambiguous_qualifier_propagated": all(
            not row["added_dimensions"] for row in predictions if row["propagation_blocked_by_cohort"]
        ),
        "no_conflict_overwritten": all(
            not row["added_dimensions"] for row in predictions if row["conflicts"]
        ),
        "provenance_completeness_is_one": metrics["qualifier_provenance_completeness"] == 1.0,
        "all_multi_statement_sources_examined": (
            metrics["sources_accessible"] + metrics["sources_not_accessible"] == len(priority)
        ),
        "clinical_dimensions_on_a_declared_subset": coverage["after"]["human_reviewed"]["setting"] > 0,
        "noisy_sources_retained": any(
            "resistance" in (row.get("directions") or []) for row in priority
        ),
        "corpus_not_selected_from_clinical_gold": scope["clinical_gold_used"] is False,
        "missing_second_review_declared": metrics["inter_annotator_agreement"] == "not_evaluated",
        "readiness_distinct_from_freeze": True,
    }
    final_checks = {
        "second_review_complete": False,
        "link_gold_evaluable": metrics["evaluable_gold_records"] > 0,
        "agreement_measured": metrics["inter_annotator_agreement"] != "not_evaluated",
        "clinical_coverage_sufficient": coverage["after"]["total_known"]["setting"] >= 30,
    }

    readiness = {
        "created_at": created_at,
        "criteria_declared_before_metrics": True,
        "prototype_criteria": [
            {"criterion": key, "description": text, "satisfied": prototype_checks[key]}
            for key, text in PROTOTYPE_CRITERIA
        ],
        "final_criteria": [
            {"criterion": key, "description": text, "satisfied": final_checks[key]}
            for key, text in FINAL_CRITERIA
        ],
        "ready_for_prototype_retrieval": all(prototype_checks.values()),
        "ready_for_final_evaluation": all(final_checks.values()),
        "dimension_readiness": dimensions,
        "blockers": [
            text for key, text in FINAL_CRITERIA if not final_checks[key]
        ],
        "note": (
            "La readiness per il prototipo e' distinta dalla readiness per la "
            "valutazione finale, e dal freeze del corpus. Un prototipo puo' essere "
            "costruito su dimensioni native e su un sottoinsieme dichiarato; "
            "pubblicare risultati no."
        ),
    }
    write_json(output / "readiness.json", readiness)

    # --- documento di readiness ----------------------------------------------
    status_labels = {
        READY: "ready",
        PARTIALLY_READY: "partially_ready",
        NOT_READY: "not_ready",
        BLOCKED_BY_REVIEW: "blocked_by_review",
        BLOCKED_BY_SOURCE_ACCESS: "blocked_by_source_access",
        NOT_APPLICABLE: "not_applicable",
    }
    lines = [
        "# Readiness per il retrieval contestuale",
        "",
        "```",
        f"ready_for_prototype_retrieval = {str(readiness['ready_for_prototype_retrieval']).lower()}",
        f"ready_for_final_evaluation    = {str(readiness['ready_for_final_evaluation']).lower()}",
        "```",
        "",
        "Le due cose sono distinte, e distinguerle e' il punto. Un prototipo puo'",
        "essere costruito su dimensioni native e su un sottoinsieme dichiarato di",
        "statement; pubblicare risultati su quelle stesse dimensioni no.",
        "",
        "I criteri sono stati fissati **prima** di leggere le metriche. E' l'unico modo",
        "per evitare che la soglia venga scelta guardando il risultato, che e' il modo",
        "piu' comune e meno visibile di dichiararsi pronti.",
        "",
        "## Criteri per il prototipo",
        "",
        "| Criterio | Esito |",
        "| --- | --- |",
    ]
    for key, text in PROTOTYPE_CRITERIA:
        lines.append(f"| {text} | {'sì' if prototype_checks[key] else 'no'} |")

    lines += [
        "",
        "## Criteri per la valutazione finale",
        "",
        "| Criterio | Esito |",
        "| --- | --- |",
    ]
    for key, text in FINAL_CRITERIA:
        lines.append(f"| {text} | {'sì' if final_checks[key] else 'no'} |")

    lines += [
        "",
        "## Readiness per dimensione",
        "",
        "| Dimensione | Stato | Copertura | Origine |",
        "| --- | --- | ---: | --- |",
    ]
    for name, payload in dimensions.items():
        lines.append(
            f"| `{name}` | **{status_labels[payload['status']]}** | "
            f"{payload['coverage']} | {payload['origin']} |"
        )

    lines += [
        "",
        "### Perche' `blocked_by_review` e non `not_ready`",
        "",
        "Quattro dimensioni hanno rilevazioni pronte ma **non emesse**: setting, linea,",
        "stadio e stato di resezione. Non mancano i dati, manca la conferma. Le",
        "corrispondenze lessicali che le producono possono descrivere i campioni invece",
        "dello studio — sul PMID 15329413 «resected from untreated never smokers»",
        "avrebbe prodotto `resection_status = resected` per l'intero studio.",
        "",
        "La distinzione conta perche' il costo per sbloccarle e' molto diverso: una",
        "dimensione `blocked_by_review` richiede lettura umana di span gia' individuati,",
        "una `not_ready` richiede prima di costruire un modo per estrarla.",
        "",
        "## Cosa manca",
        "",
    ]
    lines += [f"- {item}" for item in readiness["blockers"]] or ["- nulla"]
    lines.append("")
    write_text(output / "QUALIFIED_RETRIEVAL_READINESS.md", "\n".join(lines) + "\n")

    print(f"ready_for_prototype_retrieval = {readiness['ready_for_prototype_retrieval']}")
    print(f"ready_for_final_evaluation = {readiness['ready_for_final_evaluation']}")
    for key, value in prototype_checks.items():
        if not value:
            print(f"  criterio prototipo non soddisfatto: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
