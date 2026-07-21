"""Audit dei quattro casi del gold pilota contro lo snapshot Neo4j.

    cd mtb-graphrag
    PYTHONPATH=. python benchmarks/mtb_evidence/pilot/scripts/audit_pilot_gold.py \\
        --gold benchmarks/mtb_evidence/pilot/input/mtb_evidence_gold_pilot_v1.jsonl \\
        --output benchmarks/mtb_evidence/pilot/audit

Lo script legge il gold, interroga il grafo, salva tutti i record grezzi e produce il
confronto. Non modifica mai il gold: le divergenze diventano proposte in
`proposed_gold_amendments.jsonl`, tutte da revisionare a mano.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from benchmarks.mtb_evidence.pilot.audit_lib import report, second_review  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import (  # noqa: E402
    alias_manifest,
    build_alias_table,
)
from benchmarks.mtb_evidence.pilot.audit_lib.compare import compare_case  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.gold import GoldParseError, load_gold  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import (  # noqa: E402
    GraphUnavailable,
    Neo4jGraphClient,
)
from benchmarks.mtb_evidence.pilot.audit_lib.queries import (  # noqa: E402
    a2_alk,
    c1_egfr,
    k1_fgfr2,
    n1_rmi2,
)
from benchmarks.mtb_evidence.pilot.audit_lib.schema import build_schema_inventory  # noqa: E402
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    write_json,
    write_jsonl,
    write_text,
)
from benchmarks.mtb_evidence.pilot.audit_lib.snapshot import (  # noqa: E402
    build_snapshot_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[5]

CASE_RUNNERS = {
    k1_fgfr2.CASE_ID: k1_fgfr2.run,
    a2_alk.CASE_ID: a2_alk.run,
    c1_egfr.CASE_ID: c1_egfr.run,
    n1_rmi2.CASE_ID: n1_rmi2.run,
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True, type=Path, help="percorso del gold JSONL")
    parser.add_argument("--output", required=True, type=Path, help="directory di output")
    parser.add_argument(
        "--second-review",
        type=Path,
        default=None,
        help="directory del pacchetto per il secondo revisore "
        "(default: <output>/../second_review)",
    )
    parser.add_argument(
        "--timestamp",
        default=None,
        help="timestamp UTC fisso, per confrontare due esecuzioni byte per byte",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    timestamp = args.timestamp or datetime.now(timezone.utc).isoformat()
    output_dir: Path = args.output
    review_dir: Path = args.second_review or output_dir.parent / "second_review"

    try:
        cases = load_gold(args.gold)
    except GoldParseError as error:
        print(f"ERRORE: gold non leggibile: {error}", file=sys.stderr)
        return 2

    alias_table = build_alias_table()
    client = Neo4jGraphClient()

    try:
        print(f"Ispezione dello schema su {len(cases)} casi...")
        inventory = build_schema_inventory(client)
        manifest = build_snapshot_manifest(client, repo_root=REPO_ROOT, timestamp=timestamp)
    except GraphUnavailable as error:
        print(f"ERRORE: {error}", file=sys.stderr)
        return 3

    write_json(output_dir / "schema_inventory.json", inventory)
    write_json(output_dir / "graph_snapshot_manifest.json", manifest)
    write_json(output_dir / "normalization_manifest.json", alias_manifest(alias_table))

    snapshot_fingerprint = manifest["snapshot_fingerprint"]["value"]
    print(f"Fingerprint snapshot: {snapshot_fingerprint}")

    entries = []
    amendments = []
    try:
        for case in cases:
            runner = CASE_RUNNERS.get(case.case_id)
            if runner is None:
                print(f"ATTENZIONE: nessun runner per {case.case_id}, caso saltato")
                continue
            print(f"  {case.case_id} ...", end=" ", flush=True)
            outcome = runner(client, case, alias_table)
            comparison = compare_case(
                case,
                outcome.graph_claims,
                alias_table=alias_table,
                found_pmids=outcome.found_pmids,
                found_nct_ids=outcome.found_nct_ids,
                found_therapies=outcome.found_therapies,
                audit_warnings=outcome.warnings,
                extra_blockers=outcome.blockers,
            )
            decision = report.decide(case, comparison, outcome)
            entry = {
                "case_id": case.case_id,
                "case": case,
                "outcome": outcome,
                "comparison": comparison,
                "decision": decision,
            }
            entries.append(entry)
            amendments.extend(report.build_amendments(case, comparison, outcome))
            _write_case(output_dir / case.case_id, entry, snapshot_fingerprint, timestamp)
            print(f"{len(outcome.graph_claims)} record, decisione {decision['decision']}")
    except GraphUnavailable as error:
        print(f"ERRORE: {error}", file=sys.stderr)
        return 3

    write_jsonl(output_dir / "proposed_gold_amendments.jsonl", amendments)
    write_text(
        output_dir / "PILOT_GOLD_AUDIT_REPORT.md",
        report.build_audit_report_md(entries, manifest),
    )
    second_review.write_package(review_dir, entries)

    _print_summary(entries, snapshot_fingerprint, review_dir)
    return 0


def _write_case(case_dir: Path, entry: dict, fingerprint: str, timestamp: str) -> None:
    outcome = entry["outcome"]
    case = entry["case"]
    comparison = entry["comparison"]

    write_json(case_dir / "query_manifest.json", {
        "case_id": case.case_id,
        "audit_timestamp_utc": timestamp,
        "snapshot_fingerprint": fingerprint,
        "queries": outcome.query_manifest(),
    })
    write_jsonl(case_dir / "raw_records.jsonl", outcome.raw_records())
    write_jsonl(
        case_dir / "normalized_records.jsonl",
        [claim.as_dict() for claim in outcome.graph_claims],
    )
    write_json(case_dir / "graph_entities.json", {
        "case_id": case.case_id,
        "entities": outcome.entities,
        "buckets": outcome.buckets,
    })
    write_json(case_dir / "graph_sources.json", {
        "case_id": case.case_id,
        **outcome.sources,
    })
    write_json(case_dir / "comparison_with_gold.json", comparison)
    write_text(
        case_dir / "discrepancies.md",
        report.build_case_discrepancies_md(case, comparison, outcome, entry["decision"]),
    )

    if case.case_id == n1_rmi2.CASE_ID:
        write_json(
            case_dir / "negative_path_proof.json",
            n1_rmi2.build_negative_path_proof(
                outcome, snapshot_fingerprint=fingerprint, timestamp=timestamp
            ),
        )


def _print_summary(entries: list[dict], fingerprint: str, review_dir: Path) -> None:
    print("\n" + "=" * 70)
    print(f"Fingerprint snapshot: {fingerprint}")
    print("=" * 70)
    for entry in entries:
        comparison = entry["comparison"]
        print(f"\n{entry['case_id']}  ->  {entry['decision']['decision']}")
        print(f"  record di evidenza  : {len(entry['outcome'].graph_claims)}")
        print(f"  terapie mancanti    : {comparison['missing_therapies'] or '-'}")
        print(f"  PMID mancanti       : {comparison['missing_pmids'] or '-'}")
        print(f"  NCT mancanti        : {comparison['missing_nct_ids'] or '-'}")
        print(f"  freeze blockers     : {len(comparison['freeze_blockers'])}")
    print(f"\nPacchetto secondo revisore: {review_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
