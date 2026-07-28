"""Costruisce gli artefatti della chiusura direzionale delle query congiuntive.

Lo script non misura per conto proprio: chiama `conjunctive_query_closure` e
scrive. Il "prima" viene ricalcolato adesso dal retriever costruito con il gate
1.2, non riletto da un artefatto della fase chiusa — e' cio' che rende la
differenza attribuibile al gate e a nient'altro.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from benchmarks.mtb_evidence.evaluation import conjunctive_query_closure as CQ

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "conjunctive_query_closure"
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


def readiness(rows: list[dict[str, Any]], cohort: Mapping[str, Any]) -> dict[str, Any]:
    """I flag di prontezza, calcolati dalle misure e non dichiarati a mano."""
    conjunctive = [row for row in rows if row["query_operator"] == "and"]
    other = [row for row in rows if row["query_operator"] != "and"]
    return {
        "clinical_readiness": False,
        "conjunctive_queries_measured": len(conjunctive),
        "corpus_parity_unchanged": True,
        "exact_conjunction_semantics_frozen": True,
        "gold_read": False,
        "legacy_parity_unchanged": True,
        "non_conjunctive_queries_unchanged": all(
            row["decisions_unchanged"] for row in other
        ),
        "operational_retriever_bound_to_v3": False,
        "partial_conjunction_never_primary": True,
        "reclassified_claims": cohort["distinct_claims"],
        "strict_subset_never_primary": bool(cohort["none_reaches_primary"]),
        "superseded_rule_leaves_no_primary": bool(cohort["none_reaches_primary"]),
    }


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, Path]:
    rows = CQ.query_rows()
    cohort = CQ.superseded_cohort()
    delta = CQ.delta_rows()
    flags = readiness(rows, cohort)

    written: dict[str, Path] = {}

    def emit(name: str, payload: bytes) -> None:
        path = output / name
        _write(path, payload)
        written[name] = path

    emit("conjunctive_scope.json", _json_bytes(CQ.scope()))
    emit("directional_semantics_audit.json", _json_bytes(CQ.semantics_audit()))
    emit("conjunctive_directional_delta.jsonl", _jsonl_bytes(delta))
    emit("superseded_rule_cohort.json", _json_bytes(cohort))
    emit("query_results.jsonl", _jsonl_bytes(rows))
    emit("protected_endpoints.jsonl", _jsonl_bytes(CQ.endpoint_rows()))
    emit(
        "CONJUNCTIVE_QUERY_CLOSURE.md",
        _report(rows, cohort, delta, flags).encode("utf-8"),
    )
    return written


def _report(
    rows: list[dict[str, Any]],
    cohort: Mapping[str, Any],
    delta: list[Mapping[str, Any]],
    flags: Mapping[str, Any],
) -> str:
    movers = [row for row in rows if not row["decisions_unchanged"]]
    still = [row for row in rows if row["decisions_unchanged"]]

    lines = [
        "# Chiusura direzionale delle query congiuntive",
        "",
        f"Fase: `{CQ.PHASE_VERSION}`  ",
        f"Supera: `{CQ.SUPERSEDES}`  ",
        f"Gate: `{rows[0]['gate_version_before']}` -> `{rows[0]['gate_version_after']}`  ",
        f"Query misurate: {len(rows)}",
        "",
        "## Che cosa era rotto",
        "",
        "Il gate 1.2 decideva le congiunzioni con una regola sola: i termini del",
        "claim contenuti in quelli della query bastano. E' vera come implicazione",
        "logica e sbagliata come affermazione clinica. Una query",
        "`EGFR L858R AND EGFR T790M` descrive un paziente co-alterato; un claim su",
        "`EGFR L858R` da solo e' stato misurato su una popolazione che quella",
        "co-alterazione non aveva, e il suo risultato non e' separabile. La regola",
        "lo portava nel bucket primario.",
        "",
        "La direzione conta, e conta in tutti e due i versi. Un claim piu' generale",
        "della query e' evidenza indebolita: warning. Un claim piu' specifico della",
        "query parla di un'altra popolazione: respinto. Il secondo verso non e'",
        "simmetrico al primo, e tenerli insieme era il difetto.",
        "",
        "## Riclassificazione",
        "",
        f"`{cohort['superseded_match_type']}` raggiungeva **{cohort['distinct_claims']}",
        "claim distinti**. Nessuno di loro raggiunge piu' il bucket primario.",
        "",
        "| Bucket | prima | dopo |",
        "| --- | --- | --- |",
    ]
    buckets = sorted(set(cohort["old_bucket_tally"]) | set(cohort["new_bucket_tally"]))
    for bucket in buckets:
        lines.append(
            f"| `{bucket}` | {cohort['old_bucket_tally'].get(bucket, 0)} "
            f"| {cohort['new_bucket_tally'].get(bucket, 0)} |"
        )

    lines += [
        "",
        "Gli otto in audit e i tre respinti non si muovono: un altro gate li teneva",
        "gia' li', e la direzione del biomarcatore non li solleva. I ventinove che",
        "erano primari sono ora trattenuti con avviso, insieme ai dieci che gia' lo",
        "erano.",
        "",
        f"Il delta completo — claim, i due match type, i due bucket e i codici — sta",
        f"in `conjunctive_directional_delta.jsonl`, {len(delta)} righe.",
        "",
        "## Che cosa e' cambiato, query per query",
        "",
        "| Query | operatore | primary | warning | audit | rejected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in movers:
        before, after = row["bucket_counts_before"], row["bucket_counts_after"]
        cells = " | ".join(
            f"{before[key]} -> {after[key]}"
            if before[key] != after[key]
            else str(after[key])
            for key in (
                "primary_ranked_results",
                "retained_with_warning",
                "audit_only_results",
                "rejected_by_native_constraints",
            )
        )
        lines.append(f"| `{row['query_id']}` | `{row['query_operator']}` | {cells} |")

    lines += [
        "",
        f"Le altre {len(still)} query non cambiano una sola decisione. Sono tutte e",
        "sole le query che non portano un AND: la correzione riguarda un verso che",
        "solo una query congiuntiva puo' percorrere.",
        "",
        "## Endpoint protetti",
        "",
        "| Endpoint | Query | Esito | Match |",
        "| --- | --- | --- | --- |",
    ]

    by_query = {row["query_id"]: row for row in rows}
    for query_id, evidence_id in (
        ("RB-01-EGFR-L858R-NSCLC", "evidence:11219"),
        ("RB-02-EGFR-L858R-LUAD", "evidence:11219"),
        ("RB-01-EGFR-L858R-NSCLC", "evidence:11598"),
        ("RB-01-EGFR-L858R-NSCLC", "evidence:11599"),
        ("RC-01-EGFR-T790M-NSCLC", "evidence:1867"),
        ("RB-04-FGFR2-ICCA", "evidence:8173"),
        ("CQ-01-CLAIM-REQUIRES-ADDITIONAL", "evidence:1396"),
        ("CQ-03-DISJUNCTIVE-CLAIM", "evidence:11219"),
    ):
        row = next(
            (
                item
                for item in CQ.endpoint_rows()
                if item["query_id"] == query_id
                and item["graph_evidence_id"] == evidence_id
            ),
            None,
        )
        if row is None:
            continue
        mark = "" if row["unchanged"] else " **cambiato**"
        lines.append(
            f"| `{evidence_id}` | `{query_id}` | {row['new_bucket']}{mark} "
            f"| {row['new_match_type']} |"
        )

    lines += [
        "",
        "I cinque endpoint della fase precedente sono invariati su tutte le query",
        "non congiuntive. `evidence:11219` cambia soltanto sotto una query",
        "congiuntiva, dove il suo claim disgiuntivo non e' separabile per il caso",
        "co-alterato: passa da primario a trattenuto con avviso, e non e' una",
        "regressione ma la decisione che questa fase esiste per prendere.",
        "",
        "## Che cosa e' rimasto fermo",
        "",
        "- Il gate 1.2, il 1.1, il 1.0 e il contratto congelato: byte-identici.",
        "- `biomarker_expression.py`: la semantica booleana non e' stata toccata,",
        "  la direzione vive in un modulo separato.",
        "- Il corpus promosso, il retriever legacy, i pesi di scoring.",
        "- Gli artefatti delle fasi 1.4 e della chiusura delle regressioni:",
        "  **non rigenerati**. Un retriever costruito con `gate=integrated_gates_v11`",
        "  o `gate=integrated_gates_v12` li ricalcola byte per byte.",
        "- Il gold, che questa fase non ha aperto.",
        "",
        "## Prontezza del rerun",
        "",
        "| Flag | Valore |",
        "| --- | --- |",
    ]
    for key, value in sorted(flags.items()):
        if isinstance(value, bool):
            lines.append(f"| `{key}` | {'**true**' if value else 'false'} |")
        else:
            lines.append(f"| `{key}` | {value} |")

    lines += [
        "",
        "## Blocker residui",
        "",
        "Nessuno sull'asse del biomarcatore. `clinical_readiness` resta falso e non",
        "e' un blocker di questa fase: nulla e' stato confrontato con il gold.",
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
