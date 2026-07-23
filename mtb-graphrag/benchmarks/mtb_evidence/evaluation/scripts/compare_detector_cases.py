"""Confronta il verdetto del rilevatore source-level con la verifica documentale.

Tre casi, tutti positivi selezionati. Non e' un campione: e' l'insieme delle
fonti che il rilevatore aveva marcato `clinical_preclinical_split_required`, e
guardare solo dove il rilevatore ha detto «si'» non permette di sapere quante
volte ha detto «no» sbagliando.

Per questo le metriche qui sono descrittive e si chiamano come sono: conferme,
conferme parziali, rifiuti, copertura dei segnali. Chiamarle precision o
sensitivity le farebbe leggere come proprieta' del rilevatore, mentre sono
proprieta' di tre casi scelti dal rilevatore stesso.

`detector_promotion_ready` resta `false`.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import FINDINGS  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    AUDIT_SPLIT_CONFIRMED_MORE,
    AUDIT_SPLIT_NOT_SUPPORTED,
    AUDIT_SPLIT_PARTIALLY_SUPPORTED,
    REVIEW_VERSION,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")

CONFIRMED = "confirmed_positive"
PARTIAL = "partially_confirmed"
REJECTED = "rejected_positive"
INSUFFICIENT = "insufficient_evidence"

CONCORDANCE_BY_DECISION = {
    AUDIT_SPLIT_CONFIRMED_MORE: CONFIRMED,
    AUDIT_SPLIT_PARTIALLY_SUPPORTED: PARTIAL,
    AUDIT_SPLIT_NOT_SUPPORTED: REJECTED,
}

# Giudizio sui segnali, fonte per fonte. Un segnale e' «corretto» se punta a
# qualcosa che la lettura ha trovato, «errato» se punta a qualcosa che non
# esiste, «mancante» se la lettura ha trovato una struttura che nessun segnale
# poteva vedere.
SIGNAL_REVIEW: dict[str, dict[str, Any]] = {
    "PU-PMID-22235099-cohort-1": {
        "correct_signals": [
            "preclinical.baf3",
            "preclinical.cell_lines",
            "preclinical.in_vitro",
            "clinical.patients",
            "clinical.phase",
        ],
        "wrong_signals": [],
        "missing_signals": ["molteplicita' dei modelli preclinici"],
        "rationale": (
            "il rilevatore ha visto entrambe le componenti, e le ha viste bene: 9 "
            "occorrenze di Ba/F3, 26 di «cell lines», 11 di «in vitro». Non ha visto "
            "che i sistemi preclinici sono quattro, perche' nessun segnale conta i "
            "modelli distinti: il verdetto era giusto, il numero di unita' no"
        ),
    },
    "PU-PMID-23344087-cohort-1": {
        "correct_signals": ["preclinical.in_vitro", "clinical.patients"],
        "wrong_signals": [],
        "missing_signals": ["composizione della componente preclinica"],
        "rationale": (
            "il verdetto poggia su **una sola** occorrenza di «in vitro», e questa "
            "volta e' genuina: sta nei metodi dell'abstract e descrive un esperimento "
            "della fonte"
        ),
    },
    "PU-PMID-31358542-cohort-1": {
        "correct_signals": ["clinical.patients", "clinical.phase", "group.plural"],
        "wrong_signals": ["preclinical.in_vitro"],
        "missing_signals": ["otto sottopopolazioni cliniche sovrapposte"],
        "rationale": (
            "il verdetto poggia anche qui su **una sola** occorrenza di «in vitro», e "
            "questa volta e' una citazione del lavoro di altri. Stesso segnale, stesso "
            "conteggio, verita' opposta: il rilevatore non distingue un esperimento "
            "proprio da uno citato, perche' non ha alcuna nozione di provenienza "
            "dentro il documento"
        ),
    },
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def build_report(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> str:
    lines = [
        "# Il rilevatore source-level su tre casi",
        "",
        "## In una riga",
        "",
        "Su tre positivi selezionati dal rilevatore stesso, **uno e' un falso "
        "positivo** — e la causa non e' una soglia da tarare.",
        "",
        "## I tre casi",
        "",
        "| Fonte | Verdetto | Revisione | Esito | Segnali |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['profile_unit_id']}` | {row['detector_verdict']} | "
            f"{row['structural_review_verdict']} | **{row['concordance']}** | "
            f"{row['signal_count']} |"
        )

    lines += [
        "",
        "## Il reperto",
        "",
        "Due fonti su tre hanno ricevuto il verdetto `split_required` sulla base di",
        "**una sola** occorrenza di `preclinical.in_vitro`.",
        "",
        "In PMID 23344087 quell'occorrenza sta nei metodi dell'abstract e descrive un",
        "esperimento della fonte. In PMID 31358542 sta in una frase che cita i modelli",
        "di altri. Stesso segnale, stesso conteggio, verita' opposta.",
        "",
        "Il punteggio non aiuta a distinguerli: 14 contro 125, e il caso col punteggio",
        "piu' alto e' quello sbagliato. Il problema non e' la soglia — e' che il",
        "rilevatore non ha nozione di **provenienza dentro il documento**, e non",
        "distingue cio' che la fonte fa da cio' che la fonte cita.",
        "",
        "## Che cosa nessun segnale poteva vedere",
        "",
        "In PMID 22235099 il verdetto era giusto e il numero di unita' no: i sistemi",
        "preclinici sono quattro, e nessun segnale conta i modelli distinti. Un",
        "rilevatore che dica «c'e' del preclinico» non dice **quanto** preclinico, e la",
        "differenza fra una unita' e quattro e' quella fra un profilo utilizzabile e un",
        "profilo che fonde quattro esperimenti diversi.",
        "",
        "## Metriche",
        "",
        f"- conferme piene: **{metrics['confirmed_positives']}**",
        f"- conferme parziali: **{metrics['partially_confirmed']}**",
        f"- positivi respinti: **{metrics['rejected_positives']}**",
        f"- evidenza insufficiente: {metrics['insufficient_evidence']}",
        f"- copertura delle componenti trovate: **{metrics['component_signal_coverage']:.3f}**",
        f"- componenti segnalate ma inesistenti: **{metrics['spurious_components']}**",
        f"- fonti in cui il numero di unita' era corretto: **{metrics['unit_count_coverage']:.3f}**",
        "",
        "Non sono precision, recall, sensitivity, specificity o accuracy, e non vanno",
        "chiamate cosi'. Il batch contiene solo positivi scelti dal rilevatore: non",
        "dice nulla su quante fonti abbia mancato in silenzio.",
        "",
        "## Stato",
        "",
        "```",
        f"detector_promotion_ready = {str(metrics['detector_promotion_ready']).lower()}",
        "```",
        "",
        "Il rilevatore resta fuori produzione. Tre casi, uno sbagliato, e il modo in cui",
        "sbaglia e' strutturale: promuoverlo adesso metterebbe in produzione un",
        "componente che non sa distinguere una citazione da un esperimento.",
        "",
        "La direzione della correzione e' pero' chiara, ed e' piu' utile del verdetto:",
        "servono segnali che leggano il **contesto** dell'occorrenza — vicinanza a un",
        "marcatore di citazione, sezione del documento, presenza di metodi propri — e",
        "un segnale che conti i modelli distinti invece di limitarsi a rilevarne uno.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    signals = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.audit_dir / "detector_signals.jsonl")
    }

    rows: list[dict[str, Any]] = []
    for finding in FINDINGS:
        signal = signals.get(finding.parent_unit_id, {})
        review = SIGNAL_REVIEW[finding.parent_unit_id]
        found = signal.get("signals") or []
        rows.append(
            {
                "profile_unit_id": finding.parent_unit_id,
                "canonical_source_id": finding.canonical_source_id,
                "detector_verdict": signal.get("split_likelihood", ""),
                "detector_score": signal.get("score", 0),
                "detector_categories": list(signal.get("categories") or ()),
                "signal_count": len(found),
                "signal_id_counts": dict(
                    sorted(Counter(item["signal_id"] for item in found).items())
                ),
                "structural_review_verdict": finding.decision,
                "concordance": CONCORDANCE_BY_DECISION.get(finding.decision, INSUFFICIENT),
                "audit_unit_count": finding.audit_unit_count,
                "reviewed_unit_count": finding.reviewed_unit_count,
                "unit_count_correct": finding.audit_unit_count == finding.reviewed_unit_count,
                "correct_signals": list(review["correct_signals"]),
                "wrong_signals": list(review["wrong_signals"]),
                "missing_signals": list(review["missing_signals"]),
                "rationale": review["rationale"],
                "created_at": created_at,
                "review_version": REVIEW_VERSION,
            }
        )

    rows.sort(key=lambda row: row["profile_unit_id"])
    from benchmarks.mtb_evidence.pilot.audit_lib.serialize import write_jsonl

    write_jsonl(args.output / "detector_case_review.jsonl", rows)

    concordance = Counter(row["concordance"] for row in rows)
    # Le componenti che la lettura ha trovato sono quelle che i segnali dovevano
    # vedere; quelle segnalate senza esistere si contano a parte invece di
    # diluirle nella stessa frazione.
    components_found = sum(
        1 + (1 if finding.decision != AUDIT_SPLIT_NOT_SUPPORTED else 0) for finding in FINDINGS
    )
    spurious = sum(len(row["wrong_signals"]) for row in rows)
    metrics = {
        "created_at": created_at,
        "review_version": REVIEW_VERSION,
        "metric_kind": "descriptive_small_batch",
        "metric_kind_note": (
            "Conteggi su tre positivi scelti dal rilevatore stesso. Non sono metriche "
            "di qualita' e non sono generalizzabili: il batch non contiene negativi."
        ),
        "cases_reviewed": len(rows),
        "confirmed_positives": concordance[CONFIRMED],
        "partially_confirmed": concordance[PARTIAL],
        "rejected_positives": concordance[REJECTED],
        "insufficient_evidence": concordance[INSUFFICIENT],
        "components_found_by_reading": components_found,
        "components_signalled": components_found,
        "component_signal_coverage": 1.0,
        "spurious_components": spurious,
        "unit_count_correct": sum(1 for row in rows if row["unit_count_correct"]),
        "unit_count_coverage": round(
            sum(1 for row in rows if row["unit_count_correct"]) / len(rows), 3
        ),
        "detector_promotion_ready": False,
        "not_calculated": {
            "precision": "not_calculated",
            "recall": "not_calculated",
            "sensitivity": "not_calculated",
            "specificity": "not_calculated",
            "accuracy": "not_calculated",
        },
        "not_calculated_reason": (
            "il batch contiene soltanto positivi selezionati dal rilevatore: senza "
            "negativi nessuna di queste quantita' e' definibile"
        ),
    }
    write_json(args.output / "detector_small_batch_metrics.json", metrics)
    write_text(args.output / "DETECTOR_SMALL_BATCH_REPORT.md", build_report(rows, metrics))

    for row in rows:
        print(
            f"{row['profile_unit_id']}: {row['detector_verdict']} -> "
            f"{row['structural_review_verdict']} = {row['concordance']}"
        )
    print(f"promozione: {metrics['detector_promotion_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
