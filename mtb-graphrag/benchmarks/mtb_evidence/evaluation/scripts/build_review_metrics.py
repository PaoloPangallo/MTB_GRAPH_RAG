"""Metriche descrittive, readiness e manifest finale del batch.

Le metriche contano fonti, unita', statement e campi. Nessuna dice quanto bene
il sistema funzioni, e il campo `metric_kind` lo dichiara dentro il file perche'
nessuno le scambi per metriche di qualita': in questa fase non esistono
revisioni umane, quindi non esiste nulla contro cui misurarsi.

`ready_to_resume_standard_queue` non e' un giudizio sul corpus. Dice una cosa
sola: il batch non lascia sorprese note a chi riprende la coda, e il passo
successivo e' una decisione umana.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import PROFILE_UNIT_VERSION  # noqa: E402
from backend.pipeline.evidence.propagation_guards import GUARD_VERSION  # noqa: E402
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (  # noqa: E402
    AUDIT_SPLIT_CONFIRMED,
    AUDIT_SPLIT_CONFIRMED_FEWER,
    AUDIT_SPLIT_CONFIRMED_MORE,
    AUDIT_SPLIT_CORRECTED,
    AUDIT_SPLIT_NOT_SUPPORTED,
    CANDIDATE_LINK_STATES,
    REVIEW_VERSION,
    validate_proposal_states,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")
DETECTOR_VERSION = "source_level_split_detector/2.0"

CONFIRMED_STATES = (AUDIT_SPLIT_CONFIRMED, AUDIT_SPLIT_CONFIRMED_MORE, AUDIT_SPLIT_CONFIRMED_FEWER)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--source-sha", default=None)
    return parser.parse_args(argv)


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return ""


def _field_counts(units: list[dict[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for unit in units:
        for decision in (unit.get("field_decisions") or {}).values():
            counts[decision] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    scope = list(read_jsonl(output / "review_batch_scope.jsonl"))
    decisions = list(read_jsonl(output / "structural_review_decisions.jsonl"))
    units = list(read_jsonl(output / "proposed_profile_units.jsonl"))
    statements = list(read_jsonl(output / "statement_unit_review_proposals.jsonl"))
    terminology = list(read_jsonl(output / "terminology_mappings.jsonl"))
    guards = list(read_jsonl(output / "propagation_guard_results.jsonl"))
    access = list(read_jsonl(output / "source_access_verification.jsonl"))
    detector = json.loads((output / "detector_small_batch_metrics.json").read_text(encoding="utf-8"))
    blinding = json.loads(
        (output / "second_review_blinding_check.json").read_text(encoding="utf-8")
    )

    field_counts = _field_counts(units)
    candidate_counts = Counter(row["candidate_link_status"] for row in statements)
    violations = sum(row["violation_count"] for row in guards)

    # Ogni proposta deve rispettare il tetto della fase. Il controllo sta qui e
    # non solo nei test perche' un artefatto che violasse l'invariante non deve
    # poter essere scritto.
    state_problems = [
        f"{row['proposed_profile_unit_id']}: {problem}"
        for row in units
        for problem in validate_proposal_states(row)
    ]
    if state_problems:
        raise RuntimeError("proposte non conformi:\n  " + "\n  ".join(state_problems))

    provenance_complete = all(
        len(row.get("provenance") or ()) >= len(row.get("known_dimensions") or ())
        for row in units
    )

    metrics = {
        "created_at": created_at,
        "review_version": REVIEW_VERSION,
        "metric_kind": "descriptive_review_batch_metrics",
        "metric_kind_note": (
            "Contano fonti, unita', statement e campi. Nessuna dice quanto bene il "
            "sistema funzioni: questa fase non produce revisioni umane e non tocca il "
            "gold, quindi non esiste un riferimento contro cui misurare."
        ),
        "sources_in_batch": len(scope),
        "sources_verified": len(access),
        "sources_with_full_text": sum(1 for row in access if row["availability"] == "full_text"),
        "sources_abstract_only": sum(
            1 for row in access if row["availability"] == "abstract_only"
        ),
        "locators_total": sum(row["locator_count"] for row in access),
        "locators_verified": sum(row["locators_verified"] for row in access),
        "locators_not_verified": sum(row["locators_not_verified"] for row in access),
        "splits_confirmed": sum(
            1 for row in decisions if row["structural_decision"] in CONFIRMED_STATES
        ),
        "splits_corrected": sum(
            1 for row in decisions if row["structural_decision"] == AUDIT_SPLIT_CORRECTED
        ),
        "splits_rejected": sum(
            1 for row in decisions if row["structural_decision"] == AUDIT_SPLIT_NOT_SUPPORTED
        ),
        "by_structural_decision": dict(
            sorted(Counter(row["structural_decision"] for row in decisions).items())
        ),
        "audit_units_total": sum(row["audit_unit_count"] for row in decisions),
        "reviewed_units_total": sum(row["reviewed_unit_count"] for row in decisions),
        "clinical_units_proposed": sum(1 for row in units if row["is_clinical"]),
        "preclinical_units_proposed": sum(1 for row in units if row["is_preclinical"]),
        "in_vitro_units": sum(1 for row in units if row["is_in_vitro"]),
        "in_vivo_units": sum(1 for row in units if row["is_in_vivo"]),
        "statements_mapped": len(statements),
        "candidate_link_status": {
            state: candidate_counts.get(state, 0) for state in CANDIDATE_LINK_STATES
        },
        "fields_confirmed": field_counts.get("confirmed", 0),
        "fields_unknown": field_counts.get("unknown", 0),
        "fields_not_applicable": field_counts.get("not_applicable", 0),
        "fields_not_separable": field_counts.get("not_separable", 0),
        "terminology_mappings": len(terminology),
        "terminology_requiring_verification": sum(
            1 for row in terminology if row["review_required"]
        ),
        "propagation_violations": violations,
        "provenance_completeness": 1.0 if provenance_complete else 0.0,
        "proposals_propagatable": sum(1 for row in units if row["is_propagatable"]),
        "proposals_human_reviewed": sum(1 for row in units if row["human_reviewed"]),
        "second_review_packets_unchanged": blinding["byte_identical"],
        "detector_cases_reviewed": detector["cases_reviewed"],
        "detector_rejected_positives": detector["rejected_positives"],
        "detector_promotion_ready": detector["detector_promotion_ready"],
        "not_calculated": {
            "linking_precision": "not_calculated",
            "linking_recall": "not_calculated",
            "linking_f1": "not_calculated",
            "agreement": "not_calculated",
            "clinical_applicability_accuracy": "not_calculated",
            "retrieval_quality": "not_calculated",
        },
        "not_calculated_reason": (
            "nessuna revisione umana e' stata prodotta e il gold non e' stato toccato"
        ),
    }
    write_json(output / "review_batch_metrics.json", metrics)

    criteria = [
        ("all_sources_verified", len(access) == len(scope) == 3),
        ("all_sources_have_a_decision", len(decisions) == len(scope)),
        ("all_proposals_have_provenance", provenance_complete),
        ("no_proposal_is_propagatable", metrics["proposals_propagatable"] == 0),
        ("author_packets_ready", (output / "annotation_packets/author_approval").is_dir()),
        ("second_review_packets_unchanged", blinding["byte_identical"]),
        ("all_violations_explicit", violations == metrics["propagation_violations"]),
        ("next_step_is_human_approval", metrics["proposals_human_reviewed"] == 0),
    ]
    blockers = [name for name, satisfied in criteria if not satisfied]

    readiness = {
        "created_at": created_at,
        "review_version": REVIEW_VERSION,
        "clinical_preclinical_sources_reviewed": len(decisions),
        "clinical_preclinical_splits_confirmed": metrics["splits_confirmed"],
        "clinical_preclinical_splits_corrected": metrics["splits_corrected"],
        "clinical_preclinical_splits_rejected": metrics["splits_rejected"],
        "clinical_preclinical_units_proposed": len(units),
        "author_approvals_pending": len(decisions),
        "detector_positive_cases_reviewed": detector["cases_reviewed"],
        "detector_promotion_ready": False,
        "ready_to_resume_standard_queue": not blockers,
        "criteria": [
            {"criterion": name, "satisfied": satisfied} for name, satisfied in criteria
        ],
        "blockers": blockers,
        "note": (
            "Riprendere la coda non significa che il corpus sia pronto per il "
            "retrieval qualificato ne' per la valutazione finale. Significa che il "
            "batch non lascia sorprese note, e che il passo successivo e' una "
            "decisione umana."
        ),
    }
    write_json(output / "readiness.json", readiness)

    manifest_path = output / "review_batch_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "generated_at": created_at,
            "branch": "feat/v3-clinical-preclinical-review-batch",
            "source_sha": args.source_sha or _git_sha(),
            "schema_versions": {
                "clinical_preclinical_review": REVIEW_VERSION,
                "source_clinical_profile_unit": PROFILE_UNIT_VERSION,
                "propagation_guards": GUARD_VERSION,
            },
            "detector_version": DETECTOR_VERSION,
            "output_hashes": {
                "review_batch_scope": content_hash(scope),
                "source_access_verification": content_hash(access),
                "structural_review_decisions": content_hash(decisions),
                "proposed_profile_units": content_hash(units),
                "statement_unit_review_proposals": content_hash(statements),
                "terminology_mappings": content_hash(terminology),
                "propagation_guard_results": content_hash(guards),
            },
            "second_review_hashes_after": blinding["hashes_after"],
            "second_review_byte_identical": blinding["byte_identical"],
            "batch_status": "complete" if not blockers else "blocked",
        }
    )
    write_json(manifest_path, manifest)

    print(f"fonti: {metrics['sources_verified']} | unita' proposte: {len(units)}")
    print(
        f"confermati {metrics['splits_confirmed']} | corretti {metrics['splits_corrected']} | "
        f"respinti {metrics['splits_rejected']}"
    )
    print(f"provenance completeness: {metrics['provenance_completeness']:.3f}")
    print(f"ready_to_resume_standard_queue: {readiness['ready_to_resume_standard_queue']}")
    if blockers:
        print(f"blocker: {blockers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
