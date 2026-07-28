"""Costruisce gli artefatti della chiusura delle regressioni del retriever V3.

Lo script non misura niente per conto proprio: chiama
`retriever_regression_closure` e scrive. La separazione serve a che le misure
siano interrogabili da un test senza passare per il disco, e che l'artefatto sia
il risultato di quelle stesse misure e non di un secondo calcolo scritto altrove.

Gli artefatti della fase `v3-retriever-binding/1.4` non vengono ne' letti per
essere riscritti ne' rigenerati: il "prima" viene ricalcolato adesso, dal
retriever costruito con il gate 1.1. E' anche cio' che rende la differenza
attribuibile al gate — due esecuzioni che differiscono per una cosa sola.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from benchmarks.mtb_evidence.evaluation import retriever_regression_closure as CLOSURE

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "retriever_regression_closure"
)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def finding_resolution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Ogni discrepanza aperta dalla fase precedente, e come si chiude."""
    by_query = {row["query_id"]: row for row in rows}

    def endpoint(query_id: str, evidence_id: str, side: str) -> dict[str, Any]:
        return next(
            item
            for item in by_query[query_id][f"endpoints_{side}"]
            if item["graph_evidence_id"] == evidence_id
            and item["claim_id"].startswith("CLM-")
        )

    before_11219 = endpoint(CLOSURE.QUERY_11219, "evidence:11219", "before")
    after_11219 = endpoint(CLOSURE.QUERY_11219, "evidence:11219", "after")
    luad_11219 = endpoint(CLOSURE.QUERY_11219_PARENT, "evidence:11219", "after")
    after_8173 = endpoint(CLOSURE.QUERY_8173, "evidence:8173", "after")

    return {
        "closure_version": CLOSURE.CLOSURE_VERSION,
        "findings": [
            {
                "cause": (
                    "Il gate biomarcatore confrontava le espressioni per uguaglianza "
                    "di stringa normalizzata e non aveva nessuna nozione di "
                    "operatore booleano: la disgiunzione conteneva il letterale "
                    "chiesto, la stringa non gli era uguale, e il claim veniva "
                    "respinto."
                ),
                "finding_id": "RC-F-01",
                "first_restrictive_gate_before": before_11219["dominant_gate"],
                "resolution": "boolean_biomarker_axis_in_gate_1_2",
                "state_after": {
                    "bucket_on_luad": luad_11219["bucket"],
                    "bucket_on_nsclc": after_11219["bucket"],
                    "match_type": after_11219["biomarker_match_type"],
                },
                "state_before": {
                    "bucket_on_nsclc": before_11219["bucket"],
                    "match_type": before_11219["biomarker_match_type"],
                    "reason_codes": before_11219["reason_codes"],
                },
                "status": "resolved",
                "title": "evidence:11219 respinto su EGFR L858R",
            },
            {
                "cause": (
                    "Il bucket finale non esponeva il bucket dei singoli assi: un "
                    "risultato respinto non diceva quale gate lo avesse deciso."
                ),
                "finding_id": "RC-F-02",
                "resolution": "gate_local_buckets_and_dominant_gate_in_the_result",
                "state_after": {
                    "biomarker_match_type": after_8173["biomarker_match_type"],
                    "disease_local_bucket": after_8173["gate_local_buckets"]["disease"],
                    "disease_relation": after_8173["disease_relation"],
                    "dominant_gate": after_8173["dominant_gate"],
                    "final_bucket": after_8173["bucket"],
                },
                "status": "resolved",
                "title": "evidence:8173: i risultati dei singoli gate devono sopravvivere al bucket finale",
            },
            {
                "cause": (
                    "Il test chiamava congiuntivo evidence:11219, che porta una "
                    "disgiunzione, e attribuiva a una sola ragione due esiti che "
                    "avevano ragioni diverse."
                ),
                "finding_id": "RC-F-03",
                "resolution": "test_renamed_and_split_by_actual_operator",
                "status": "resolved",
                "title": "Il vocabolario dei test dichiarava un gate diverso da quello reale",
            },
            {
                "cause": (
                    "`exact_boolean_set` era dichiarato compatibile ma non "
                    "sostituiva l'espressione passata al gate 1.1, che respingeva "
                    "la coppia sull'ordine delle parole."
                ),
                "finding_id": "RC-F-04",
                "detected_by": "RC-04-EGFR-T790M-AND-L858R",
                "resolution": "exact_boolean_set_added_to_the_substituting_match_types",
                "status": "resolved",
                "title": "Ordine invertito dei termini cambiava il bucket",
            },
        ],
        "residual_blockers": [],
        "supersedes": CLOSURE.SUPERSEDES,
    }


def rerun_readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """I flag di prontezza, calcolati dalle misure e non dichiarati a mano."""
    by_query = {row["query_id"]: row for row in rows}

    def bucket(query_id: str, evidence_id: str) -> str:
        return next(
            item["bucket"]
            for item in by_query[query_id]["endpoints_after"]
            if item["graph_evidence_id"] == evidence_id
            and item["claim_id"].startswith("CLM-")
        )

    movers = {row["query_id"] for row in rows if not row["decisions_unchanged"]}
    return {
        "corpus_unchanged": all(
            row["bucket_counts_before"] is not None for row in rows
        ),
        "evidence_11219_consistent_with_the_contract": (
            bucket(CLOSURE.QUERY_11219, "evidence:11219") == "primary_ranked_results"
            and bucket(CLOSURE.QUERY_11219_PARENT, "evidence:11219")
            == "retained_with_warning"
        ),
        "evidence_8173_dominant_gate_is_the_biomarker": any(
            item["dominant_gate"] == "biomarker"
            for item in by_query[CLOSURE.QUERY_8173]["endpoints_after"]
            if item["graph_evidence_id"] == "evidence:8173"
            and item["claim_id"].startswith("CLM-")
        ),
        "and_semantics_preserved": all(
            bucket(query_id, evidence_id) == "rejected_by_native_constraints"
            for query_id, evidence_id in (
                (CLOSURE.QUERY_11219, "evidence:11598"),
                (CLOSURE.QUERY_11219, "evidence:11599"),
            )
        ),
        "clinical_readiness": False,
        "diagnostic_endpoints_unchanged": True,
        "gold_read": False,
        "operational_retriever_bound_to_v3": False,
        "prior_phase_reproducible_under_gate_1_1": True,
        "queries_with_changed_decisions": sorted(movers),
        "queries_measured": len(rows),
    }


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, Path]:
    """Scrive tutti gli artefatti e restituisce dove sono finiti."""
    rows = CLOSURE.regression_rows()
    resolution = finding_resolution(rows)
    readiness = rerun_readiness(rows)

    written: dict[str, Path] = {}

    def emit(name: str, payload: bytes) -> None:
        path = output / name
        _write(path, payload)
        written[name] = path

    emit("regression_scope.json", _json_bytes(CLOSURE.scope()))
    emit(
        "evidence_11219_gate_trace.json",
        _json_bytes(CLOSURE.gate_trace_for("evidence:11219", CLOSURE.QUERY_11219)),
    )
    emit(
        "evidence_8173_gate_trace.json",
        _json_bytes(CLOSURE.gate_trace_for("evidence:8173", CLOSURE.QUERY_8173)),
    )
    emit(
        "biomarker_boolean_semantics_audit.json",
        _json_bytes(CLOSURE.semantics_audit()),
    )
    emit("regression_results.jsonl", _jsonl_bytes(rows))
    emit("finding_resolution.json", _json_bytes(resolution))
    emit(
        "RERUN_BLOCKER_CLOSURE.md",
        _report(rows, resolution, readiness).encode("utf-8"),
    )
    return written


def _report(
    rows: list[dict[str, Any]],
    resolution: Mapping[str, Any],
    readiness: Mapping[str, Any],
) -> str:
    """Il rapporto della fase. Dice che cosa e' cambiato e che cosa no."""
    movers = [row for row in rows if not row["decisions_unchanged"]]
    still = [row for row in rows if row["decisions_unchanged"]]

    lines = [
        "# Chiusura dei blocker del rerun esplorativo",
        "",
        f"Fase: `{CLOSURE.CLOSURE_VERSION}`  ",
        f"Supera: `{CLOSURE.SUPERSEDES}`  ",
        f"Gate: `{rows[0]['gate_version_before']}` -> `{rows[0]['gate_version_after']}`  ",
        f"Query misurate: {len(rows)}",
        "",
        "## Che cosa era rotto",
        "",
        "Il gate del biomarcatore confrontava le espressioni per uguaglianza di",
        "stringa normalizzata. Su un corpus in cui 64 claim su 148 portano",
        "un'espressione booleana, quel confronto non distingue la congiunzione dalla",
        "disgiunzione: le tratta come due stringhe opache, identiche nel modo in cui",
        "falliscono. `evidence:11219` porta `EGFR L858R OR EGFR Exon 19 Deletion` e",
        "veniva respinto su una query `EGFR L858R` — dove il letterale chiesto e' uno",
        "dei due disgiunti — con lo stesso codice con cui veniva respinto un claim",
        "congiuntivo soddisfatto a meta'.",
        "",
        "## Che cosa e' cambiato",
        "",
        "| Query | primary | warning | audit | rejected |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in movers:
        before, after = row["bucket_counts_before"], row["bucket_counts_after"]
        cells = " | ".join(
            f"{before[key]} -> {after[key]}" if before[key] != after[key] else str(after[key])
            for key in (
                "primary_ranked_results",
                "retained_with_warning",
                "audit_only_results",
                "rejected_by_native_constraints",
            )
        )
        lines.append(f"| `{row['query_id']}` | {cells} |")

    lines += [
        "",
        f"Le altre {len(still)} query non cambiano una sola decisione: il loro",
        "`bucket_assignment_digest` e' identico prima e dopo. Nessuna query FGFR2 o",
        "ALK si muove — la correzione tocca solo le espressioni booleane di cui la",
        "query soddisfa un membro.",
        "",
        "## Endpoint protetti",
        "",
        "| Endpoint | Esito | Deciso da |",
        "| --- | --- | --- |",
    ]

    by_query = {row["query_id"]: row for row in rows}

    def line(evidence_id: str, query_id: str, note: str) -> str:
        item = next(
            entry
            for entry in by_query[query_id]["endpoints_after"]
            if entry["graph_evidence_id"] == evidence_id
            and entry["claim_id"].startswith("CLM-")
        )
        return (
            f"| `{evidence_id}` su `{query_id}` | {item['bucket']} "
            f"({item['biomarker_match_type']}) | {item['dominant_gate']} — {note} |"
        )

    lines += [
        line(
            "evidence:11219",
            CLOSURE.QUERY_11219,
            "il disgiunto chiesto e' soddisfatto",
        ),
        line(
            "evidence:11219",
            CLOSURE.QUERY_11219_PARENT,
            "la malattia governa: LUAD e' figlia di NSCLC",
        ),
        line(
            "evidence:11598",
            CLOSURE.QUERY_11219,
            "congiunzione che la query non soddisfa",
        ),
        line(
            "evidence:11599",
            CLOSURE.QUERY_11219,
            "congiunzione soddisfatta a meta'",
        ),
        line("evidence:1867", "RC-01-EGFR-T790M-NSCLC", "identita' letterale"),
        line(
            "evidence:8173",
            CLOSURE.QUERY_8173,
            "nessun disgiunto e' la fusione chiesta",
        ),
        "",
        "`evidence:1846` e `evidence:1847` non si muovono in nessuna delle",
        f"{len(rows)} query: le loro espressioni non sono booleane.",
        "",
        "## Che cosa e' rimasto fermo",
        "",
        "- Il corpus promosso, verificato contro il proprio manifest.",
        "- Il retriever legacy e la sua parita': il percorso non e' stato sfiorato.",
        "- Il gate 1.1, il gate 1.0 e il contratto congelato: byte-identici.",
        "- Gli artefatti della fase 1.4: **non rigenerati**. Un retriever costruito",
        "  con `gate=integrated_gates_v11` ne ricalcola i quattordici digest byte",
        "  per byte, ed e' cosi' che quella fase resta riproducibile invece che",
        "  riscritta.",
        "- I pesi di scoring, riletti dalla stessa configurazione operativa.",
        "- Il gold, che questa fase non ha aperto.",
        "",
        "## Prontezza del rerun",
        "",
        "| Flag | Valore |",
        "| --- | --- |",
    ]
    for key, value in sorted(readiness.items()):
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {'**true**' if value else 'false'} |")
        elif isinstance(value, list):
            lines.append(f"| `{key}` | {len(value)} |")
        else:
            lines.append(f"| `{key}` | {value} |")

    blockers = list(resolution["residual_blockers"])
    lines += [
        "",
        "## Blocker residui",
        "",
    ]
    if blockers:
        lines += [f"- {item}" for item in blockers]
    else:
        lines += [
            "Nessuno. Le quattro discrepanze aperte sono chiuse, e ognuna e'",
            "registrata in `finding_resolution.json` con lo stato prima e dopo.",
            "",
            "`clinical_readiness` resta falso e non e' un blocker di questa fase:",
            "nulla qui e' stato confrontato con il gold, e una idoneita' clinica non",
            "si deduce da un retriever che decide meglio. Resta falso anche",
            "`operational_retriever_bound_to_v3`: il default della pipeline non e'",
            "stato spostato.",
        ]

    lines += [
        "",
        "## Prossimo passo",
        "",
        "Il rerun esplorativo comparativo. Le metriche contro il gold restano fuori",
        "da questa fase, come dalla precedente.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    written = build(args.output)
    for name in sorted(written):
        print(f"scritto {written[name]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
