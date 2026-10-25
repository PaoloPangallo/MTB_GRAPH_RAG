"""Registra l'approvazione dell'autore e la traccia di audit.

L'approvazione e' un fatto: qualcuno ha letto un report e ha deciso. Il record
conserva chi, quando, con quale metodo e con quali correzioni, e conserva anche
cio' che la decisione **non** e' — non e' una revisione clinica, non e'
indipendente, non rende il gold valutabile.

Gli hash dei packet ciechi della seconda revisione sono presi prima e dopo. Se
uno solo cambia, lo script esce con errore.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.mtb_evidence.evaluation.author_approval import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_ID,
    AUTHOR_DECISION,
    AUTHOR_DECISIONS,
    CANONICAL_SOURCE_ID,
    CLINICAL_PRECLINICAL_SPLIT,
    DECISION_RATIONALE,
    FINAL_NUMBER_OF_PROFILE_UNITS,
    LIMITATIONS,
    PARENT_UNIT_ID,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_PMC,
    SOURCE_PMID,
    STATEMENT_REVISIONS,
    STRUCTURAL_DECISION,
    SUBGROUP_STRUCTURE,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DEFAULT_CURATION = Path("benchmarks/mtb_evidence/v3/priority_curation")
SECOND_REVIEW = Path("annotation_packets/second_review")


class BlindingViolation(RuntimeError):
    """Un packet cieco della seconda revisione e' cambiato."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--curation-dir", type=Path, default=DEFAULT_CURATION)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def hash_directory(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        return {}
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.iterdir())
        if path.is_file()
    }


def build_record(created_at: str) -> dict[str, Any]:
    if AUTHOR_DECISION not in AUTHOR_DECISIONS:
        raise RuntimeError(f"decisione non ammessa: {AUTHOR_DECISION!r}")
    return {
        "approval_id": f"AP-PMID-{SOURCE_PMID}",
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "pmid": SOURCE_PMID,
        "pmc_id": SOURCE_PMC,
        "parent_profile_unit_id": PARENT_UNIT_ID,
        "approved_profile_unit_ids": [APPROVED_UNIT_ID],
        "source_packet_id": f"AA-PMID-{SOURCE_PMID}",
        "source_report": f"SOURCE_REVIEW_PMID-{SOURCE_PMID}.md",
        # --- chi ha deciso, e con quale autorita' ---------------------------
        "reviewer_id": REVIEWER_ID,
        "reviewer_role": REVIEWER_ROLE,
        "review_method": REVIEW_METHOD,
        "independent_review": False,
        "clinical_reviewer": False,
        "clinical_reviewed": False,
        "review_status": "first_review_complete",
        "human_reviewed": True,
        "requires_second_independent_review": True,
        "is_evaluable_for_final_metrics": False,
        # --- che cosa e' stato deciso ---------------------------------------
        "author_decision": AUTHOR_DECISION,
        "structural_decision": STRUCTURAL_DECISION,
        "clinical_preclinical_split": CLINICAL_PRECLINICAL_SPLIT,
        "final_number_of_profile_units": FINAL_NUMBER_OF_PROFILE_UNITS,
        "decision_rationale": DECISION_RATIONALE,
        "corrections": [
            {
                "target": revision.statement_id,
                "from": revision.previous_candidate_status,
                "to": revision.first_review_status,
            }
            for revision in STATEMENT_REVISIONS
            if revision.previous_candidate_status != revision.first_review_status
        ],
        "subgroup_structure": dict(SUBGROUP_STRUCTURE),
        "limitations": list(LIMITATIONS),
        "reviewed_at": created_at,
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
    }


def build_audit_trail(created_at: str) -> list[dict[str, Any]]:
    """La sequenza degli stati attraversati dalla fonte, con chi li ha decisi."""
    steps = (
        (
            "priority_curation",
            "cohort_partially_resolved",
            "automatic",
            "la coorte non era risolvibile con i soli statement",
        ),
        (
            "cohort_split_audit",
            "clinical_preclinical_split_required",
            "automatic",
            "segnali source-level indicavano una componente preclinica",
        ),
        (
            "clinical_preclinical_review_batch",
            "audit_split_not_supported",
            "source_checked_documentary_review",
            "il full text non contiene esperimenti preclinici propri",
        ),
        (
            "author_approval",
            "first_review_complete",
            REVIEWER_ID,
            "approvazione con correzioni: la fonte e' interamente clinica",
        ),
    )
    return [
        {
            "sequence": index,
            "phase": phase,
            "state": state,
            "decided_by": decided_by,
            "is_human_decision": decided_by == REVIEWER_ID,
            "rationale": rationale,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
        for index, (phase, state, decided_by, rationale) in enumerate(steps, start=1)
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    second_review_dir = args.curation_dir / SECOND_REVIEW
    before = hash_directory(second_review_dir)

    write_jsonl(args.output / "author_approval_records.jsonl", [build_record(created_at)])
    write_jsonl(args.output / "audit_trail.jsonl", build_audit_trail(created_at))

    after = hash_directory(second_review_dir)
    changed = sorted(
        name for name in set(before) | set(after) if before.get(name) != after.get(name)
    )
    write_json(
        args.output / "second_review_blinding_check.json",
        {
            "created_at": created_at,
            "directory": str(SECOND_REVIEW).replace("\\", "/"),
            "file_count_before": len(before),
            "file_count_after": len(after),
            "byte_identical": not changed,
            "changed_files": changed,
            "hashes_before": before,
            "hashes_after": after,
            "approval_version": APPROVAL_VERSION,
        },
    )
    if changed:
        raise BlindingViolation(f"packet ciechi modificati: {changed}")

    print(f"approvazione registrata: {AUTHOR_DECISION} su {CANONICAL_SOURCE_ID}")
    print(f"revisore: {REVIEWER_ID} ({REVIEWER_ROLE}) · metodo: {REVIEW_METHOD}")
    print(f"unita' finali: {FINAL_NUMBER_OF_PROFILE_UNITS} · split: {CLINICAL_PRECLINICAL_SPLIT}")
    print(f"packet ciechi invariati: {not changed} ({len(after)} file)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
