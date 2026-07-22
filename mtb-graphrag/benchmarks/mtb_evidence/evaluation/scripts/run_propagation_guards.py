"""Esegue le guardie di propagazione su tutte le unita' e decisioni note."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.propagation_guards import (  # noqa: E402
    ALL_RULE_IDS,
    GUARD_VERSION,
    run_guards,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")
DEFAULT_REVIEW = Path("benchmarks/mtb_evidence/v3/first_review")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    units: list[dict[str, Any]] = []
    for path in (
        args.review_dir / "reviewed_profile_units.jsonl",
        args.audit_dir / "proposed_profile_units.jsonl",
        args.curation_dir / "resolved_profile_units.jsonl",
        args.curation_dir / "unresolved_profile_units.jsonl",
    ):
        if path.is_file():
            units.extend(read_jsonl(path))

    decisions: list[dict[str, Any]] = []
    for path in (
        args.review_dir / "statement_first_review_decisions.jsonl",
        args.audit_dir / "statement_unit_mapping_proposals.jsonl",
    ):
        if path.is_file():
            decisions.extend(read_jsonl(path))

    mappings = list(read_jsonl(args.review_dir / "intervention_mappings.jsonl"))

    violations = run_guards(units=units, decisions=decisions, mappings=mappings)
    rows = [item.as_dict() for item in violations]
    rows.sort(key=lambda item: (item["rule_id"], item["subject"]))
    write_jsonl(args.audit_dir / "propagation_guard_results.jsonl", rows)

    by_rule = {rule: 0 for rule in ALL_RULE_IDS}
    for row in rows:
        by_rule[row["rule_id"]] = by_rule.get(row["rule_id"], 0) + 1

    write_json(
        args.audit_dir / "propagation_guard_summary.json",
        {
            "created_at": created_at,
            "guard_version": GUARD_VERSION,
            "rules_available": list(ALL_RULE_IDS),
            "units_checked": len(units),
            "decisions_checked": len(decisions),
            "mappings_checked": len(mappings),
            "violations_total": len(rows),
            "violations_by_rule": by_rule,
            "note": (
                "Zero violazioni non significa che le regole siano inerti: sono provate "
                "su casi deliberatamente scorretti nella suite di test. Qui misurano lo "
                "stato reale degli artefatti."
            ),
        },
    )

    print(f"unita' controllate: {len(units)} | decisioni: {len(decisions)} | mapping: {len(mappings)}")
    print(f"violazioni: {len(rows)}")
    for row in rows:
        print(f"  [{row['rule_id']}] {row['subject']}: {row['message']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
