"""Metriche strutturali dell'audit e readiness, con il manifest finale.

Le metriche sono **strutturali**, non cliniche: contano unita', stati e segnali.
Nessuna dice quanto bene il sistema funzioni, e il campo `metric_kind` lo rende
esplicito perche' un lettore che apra il solo JSON non possa scambiarle per
metriche di qualita'.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from backend.pipeline.evidence.profile_unit import PROFILE_UNIT_VERSION  # noqa: E402
from backend.pipeline.evidence.propagation_guards import ALL_RULE_IDS, GUARD_VERSION  # noqa: E402
from benchmarks.mtb_evidence.evaluation.cohort_split_audit import (  # noqa: E402
    AUDIT_VERSION,
    DETECTOR_VERSION,
    SOURCE_SIGNALS,
    STRUCTURE_STATES,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_text,
)

DEFAULT_AUDIT = Path("benchmarks/mtb_evidence/v3/cohort_split_audit")
DEFAULT_CORPUS = Path("benchmarks/mtb_evidence/v3/qualification_corpus")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def _branch_and_sha() -> tuple[str, str]:
    def run(*args: str) -> str:
        try:
            return subprocess.run(
                args, capture_output=True, text=True, check=True, cwd=REPO_ROOT
            ).stdout.strip()
        except Exception:
            return ""

    return run("git", "rev-parse", "--abbrev-ref", "HEAD"), run("git", "rev-parse", "HEAD")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    audit = args.audit_dir
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    scope = list(read_jsonl(audit / "audit_scope.jsonl"))
    classifications = list(read_jsonl(audit / "source_structure_classification.jsonl"))
    access = list(read_jsonl(audit / "source_access_audit.jsonl"))
    proposals = list(read_jsonl(audit / "proposed_profile_units.jsonl"))
    split_summaries = list(read_jsonl(audit / "split_proposals.jsonl"))
    mappings = list(read_jsonl(audit / "statement_unit_mapping_proposals.jsonl"))
    guards = list(read_jsonl(audit / "propagation_guard_results.jsonl"))
    screen = list(read_jsonl(audit / "single_statement_split_screen.jsonl"))
    import json

    screen_summary = json.loads(
        (audit / "single_statement_screen_summary.json").read_text(encoding="utf-8")
    )
    blinding = json.loads(
        (audit / "second_review_blinding_check.json").read_text(encoding="utf-8")
    )

    by_state = {state: 0 for state in STRUCTURE_STATES}
    for row in classifications:
        by_state[row["structure_state"]] = by_state.get(row["structure_state"], 0) + 1

    signal_categories: dict[str, int] = {}
    for row in read_jsonl(audit / "detector_signals.jsonl"):
        for category in row.get("categories") or []:
            signal_categories[category] = signal_categories.get(category, 0) + 1

    metrics = {
        "created_at": created_at,
        "metric_kind": "structural_audit_metrics",
        "metric_kind_note": (
            "Queste metriche contano unita', stati e segnali. Nessuna dice quanto bene il "
            "sistema funzioni: non sono metriche cliniche ne' di qualita' del retrieval."
        ),
        "audit_version": AUDIT_VERSION,
        "detector_version": DETECTOR_VERSION,
        "units_audited": len(scope),
        "sources_accessible": sum(1 for row in access if row["availability"] != "unavailable"),
        "sources_with_full_text": sum(1 for row in access if row["availability"] == "full_text"),
        "sources_abstract_only": sum(1 for row in access if row["availability"] == "abstract_only"),
        "sources_not_accessible": sum(1 for row in access if row["availability"] == "unavailable"),
        "by_structure_state": by_state,
        "split_proposals": len(split_summaries),
        "proposed_derived_units": len(proposals),
        "statements_redistributed": len(mappings),
        "statements_ambiguous_after_audit": sum(
            1 for row in mappings if row["candidate_link_status"] == "candidate_ambiguous"
        ),
        "non_propagation_rules_available": len(ALL_RULE_IDS),
        "non_propagation_rules_triggered": len({row["rule_id"] for row in guards}),
        "propagation_violations": len(guards),
        "source_level_signals_available": len(SOURCE_SIGNALS),
        "source_level_signal_categories": signal_categories,
        "single_statement_sources_screened": screen_summary["sources_screened"],
        "single_statement_sources": screen_summary["single_statement_sources"],
        "single_statement_split_candidates": screen_summary["single_statement_split_candidates"],
        "split_candidates_total": screen_summary["split_candidates"],
        "residual_split_risk_rate": screen_summary["residual_split_risk_rate"],
        "weak_negative_verdicts": screen_summary["weak_negative_verdicts"],
        "second_review_packets_unchanged": blinding["byte_identical"],
        "not_calculated": {
            "linking_precision": "not_calculated",
            "linking_recall": "not_calculated",
            "linking_f1": "not_calculated",
            "agreement": "not_calculated",
            "final_accuracy": "not_calculated",
            "clinical_applicability_accuracy": "not_calculated",
        },
        "not_calculated_reason": (
            "questa fase non produce revisioni umane e non tocca il gold: nessuna metrica "
            "di qualita' e' definibile"
        ),
    }
    write_json(audit / "structural_audit_metrics.json", metrics)

    # --- readiness ------------------------------------------------------------
    all_classified = len(classifications) == len(scope)
    all_with_provenance = all(
        all(
            any(item["field_name"] == dimension for item in row.get("provenance") or [])
            for dimension in row.get("known_dimensions") or []
        )
        for row in proposals
    )
    none_propagatable = all(not row["is_propagatable"] for row in proposals)
    packets_ready = len(
        list((audit / "annotation_packets/first_review_split_audit").glob("*.json"))
    ) == len(scope)
    risk_quantified = "residual_split_risk_rate" in screen_summary
    no_undeclared_errors = not guards

    checks = {
        "all_units_classified": all_classified,
        "all_proposals_have_provenance": all_with_provenance,
        "no_proposal_is_propagatable": none_propagatable,
        "updated_packets_ready": packets_ready,
        "second_review_packets_unchanged": bool(blinding["byte_identical"]),
        "single_statement_risk_quantified": risk_quantified,
        "no_undeclared_structural_errors": no_undeclared_errors,
    }

    readiness = {
        "created_at": created_at,
        "source_structure_readiness": "audited" if all_classified else "incomplete",
        "qualifier_extraction_readiness": "blocked_by_review",
        "first_review_readiness": "ready",
        "second_review_readiness": "blocked_by_first_review",
        "final_evaluation_readiness": "not_ready",
        "cohort_structure_audit_complete": all_classified,
        "single_statement_residual_risk": screen_summary["residual_split_risk_rate"],
        "split_proposals_awaiting_review": len(proposals),
        "propagation_guards_ready": bool(ALL_RULE_IDS) and no_undeclared_errors,
        "criteria": [
            {"criterion": key, "satisfied": value} for key, value in checks.items()
        ],
        "ready_to_resume_priority_queue": all(checks.values()),
        "blockers": [key for key, value in checks.items() if not value],
        "note": (
            "La readiness per riprendere la coda non e' readiness per il retrieval "
            "qualificato ne' per la valutazione finale: dice soltanto che l'audit "
            "strutturale non lascia sorprese note a chi riprende le revisioni."
        ),
    }
    write_json(audit / "readiness.json", readiness)

    branch, sha = _branch_and_sha()
    corpus_manifest = json.loads(
        (args.corpus_dir / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
    )
    write_json(
        audit / "audit_manifest.json",
        {
            "branch": branch,
            "source_sha": sha,
            "generated_at": created_at,
            "audit_status": (
                "complete" if readiness["ready_to_resume_priority_queue"] else "blocked"
            ),
            "snapshot_fingerprint": corpus_manifest["snapshot_fingerprint"],
            "input_hashes": {
                "statement_repository": corpus_manifest["statement_repository_hash"],
                "source_inventory": corpus_manifest["source_inventory_hash"],
                "profile_units": corpus_manifest["profile_units_hash"],
            },
            "output_hashes": {
                "audit_scope": content_hash(scope),
                "classification": content_hash(classifications),
                "proposed_units": content_hash(proposals),
                "statement_mappings": content_hash(mappings),
                "screen": content_hash(screen),
            },
            "schema_versions": {
                "source_clinical_profile_unit": PROFILE_UNIT_VERSION,
                "cohort_split_audit": AUDIT_VERSION,
                "propagation_guards": GUARD_VERSION,
            },
            "detector_version": DETECTOR_VERSION,
        },
    )

    print(f"unita' auditate: {len(scope)} | stati: { {k: v for k, v in by_state.items() if v} }")
    print(f"proposte: {len(split_summaries)} | unita' proposte: {len(proposals)}")
    print(f"statement rimappati: {len(mappings)} | violazioni: {len(guards)}")
    print(f"rischio residuo: {screen_summary['residual_split_risk_rate']:.1%}")
    print(f"ready_to_resume_priority_queue = {readiness['ready_to_resume_priority_queue']}")
    for blocker in readiness["blockers"]:
        print(f"  blocker: {blocker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
