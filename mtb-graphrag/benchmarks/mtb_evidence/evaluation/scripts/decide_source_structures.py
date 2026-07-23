"""Decisione strutturale per ciascuna fonte, dopo la verifica documentale.

Uno stato solo per fonte, e deve dire che cosa la lettura ha cambiato rispetto
alla proposta dell'audit: confermata, confermata con piu' unita', con meno,
corretta, sostenuta in parte, oppure non sostenuta.

La decisione non tocca le unita' originali. Le parent unit restano dove sono,
con lo stato che avevano: finche' una persona non approva, sostituirle
significherebbe far decidere alla macchina che cosa il corpus contiene.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import FINDINGS  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    CONFIRMING_DECISIONS,
    REVIEW_VERSION,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
    STRUCTURAL_DECISIONS,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")


class DecisionError(RuntimeError):
    """Una decisione strutturale non ammessa, o priva di locator."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    verification = {
        str(row["profile_unit_id"]): row
        for row in read_jsonl(args.output / "source_access_verification.jsonl")
    }

    rows: list[dict[str, Any]] = []
    for finding in FINDINGS:
        if finding.decision not in STRUCTURAL_DECISIONS:
            raise DecisionError(f"stato non ammesso: {finding.decision!r}")

        access = verification.get(finding.parent_unit_id, {})
        verified_ids = {
            row["locator_id"] for row in access.get("locators", ()) if row.get("verified")
        }
        supporting = sorted(
            {
                locator_id
                for unit in finding.units
                for locator_id in unit.locator_ids
                if locator_id in verified_ids
            }
        )
        if not supporting:
            raise DecisionError(
                f"{finding.parent_unit_id}: nessun locator verificato sostiene le unita' "
                "proposte. Una decisione strutturale senza locator non e' verificabile"
            )

        specific = sorted(
            {
                dimension
                for unit in finding.units
                for dimension in ("model_type", "cell_line", "assay", "population", "n_subjects")
                if getattr(unit, dimension) not in ("unknown", "not_applicable", (), "")
            }
        )
        rows.append(
            {
                "profile_unit_id": finding.parent_unit_id,
                "canonical_source_id": finding.canonical_source_id,
                "structural_decision": finding.decision,
                "confirms_audit_split": finding.decision in CONFIRMING_DECISIONS,
                "audit_unit_count": finding.audit_unit_count,
                "reviewed_unit_count": finding.reviewed_unit_count,
                "unit_count_delta": finding.reviewed_unit_count - finding.audit_unit_count,
                "clinical_unit_count": sum(
                    1 for unit in finding.units if unit.unit_type.startswith("clinical")
                ),
                "preclinical_unit_count": sum(
                    1 for unit in finding.units if unit.unit_type.startswith("preclinical")
                ),
                "rationale": finding.decision_rationale,
                "supporting_locator_ids": supporting,
                "shared_dimensions": list(finding.shared_dimensions),
                "specific_dimensions": specific,
                "not_separable_dimensions": list(finding.not_separable_dimensions),
                "residual_risk": finding.residual_risk,
                "availability": finding.availability,
                "limitations": list(finding.limitations),
                # Le unita' originali non vengono toccate: nessuno stato
                # `superseded` viene assegnato prima dell'approvazione.
                "parent_unit_preserved": True,
                "parent_unit_new_state": None,
                "review_status": SOURCE_CHECKED_REVIEW_PROPOSAL,
                "human_reviewed": False,
                "requires_author_approval": True,
                "created_at": created_at,
                "review_version": REVIEW_VERSION,
            }
        )

    rows.sort(key=lambda row: row["profile_unit_id"])
    write_jsonl(args.output / "structural_review_decisions.jsonl", rows)

    counts: dict[str, int] = {state: 0 for state in STRUCTURAL_DECISIONS}
    for row in rows:
        counts[row["structural_decision"]] += 1
    write_json(
        args.output / "structural_decision_summary.json",
        {
            "created_at": created_at,
            "review_version": REVIEW_VERSION,
            "sources_reviewed": len(rows),
            "by_decision": counts,
            "audit_units_total": sum(row["audit_unit_count"] for row in rows),
            "reviewed_units_total": sum(row["reviewed_unit_count"] for row in rows),
        },
    )

    for row in rows:
        print(
            f"{row['profile_unit_id']}: {row['structural_decision']} "
            f"({row['audit_unit_count']} -> {row['reviewed_unit_count']} unita')"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
