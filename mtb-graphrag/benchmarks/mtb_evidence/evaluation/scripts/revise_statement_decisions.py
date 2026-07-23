"""Decisioni di prima revisione sugli statement, gold provvisorio, caso del rilevatore.

La correzione principale riguarda `ES-V2-evidence-100003`: la fonte riporta una
frequenza per la **classe** dei TKI ALK di seconda generazione, lo statement la
attribuisce a **brigatinib**. Non e' un dubbio da lasciare aperto — il full text
e' disponibile e la mancata attribuzione specifica e' verificabile — quindi non
e' `not_determinable` ma `candidate_invalid`.

Il link_status vive in `first_review_annotation` e **non** in `final_status`.
Copiarlo nel gold darebbe al linker una precision misurata contro un solo
giudizio, non indipendente e non clinico: il gold resta `provisional_first_review`
e `is_evaluable` resta falso.

Il gold prodotto qui e' una versione completa e nuova, non una modifica del file
della fase precedente: quello resta invariato, e il manifest dice quale supera
quale.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipeline.evidence.corpus_manifest import content_hash  # noqa: E402
from benchmarks.mtb_evidence.evaluation.author_approval import (  # noqa: E402
    APPROVAL_VERSION,
    APPROVED_UNIT_ID,
    CANONICAL_SOURCE_ID,
    DETECTOR_REFERENCE_CASE,
    FORBIDDEN_STATUSES,
    PARENT_UNIT_ID,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    STATEMENT_REVISIONS,
)
from benchmarks.mtb_evidence.pilot.audit_lib.serialize import (  # noqa: E402
    read_jsonl,
    write_json,
    write_jsonl,
)

DEFAULT_OUTPUT = Path("benchmarks/mtb_evidence/v3/author_approval")
DEFAULT_REVIEW = Path("benchmarks/mtb_evidence/v3/first_review")
DEFAULT_BATCH = Path("benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch")


class GoldError(RuntimeError):
    """Il gold provvisorio viola un invariante."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--timestamp", default=None)
    return parser.parse_args(argv)


def build_decisions(created_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for revision in STATEMENT_REVISIONS:
        row = {
            "statement_id": revision.statement_id,
            "canonical_source_id": CANONICAL_SOURCE_ID,
            "profile_unit_ids": [APPROVED_UNIT_ID],
            "parent_profile_unit_id": PARENT_UNIT_ID,
            "previous_candidate_status": revision.previous_candidate_status,
            "first_review_candidate_status": revision.first_review_status,
            "first_review_link_status": revision.link_status,
            "supported_dimensions": list(revision.supported_dimensions),
            "unsupported_or_not_separable_dimensions": list(revision.unsupported_dimensions),
            "invalid_reason": revision.invalid_reason,
            "source_claim_scope": revision.source_claim_scope,
            "statement_claim_scope": revision.statement_claim_scope,
            "intervention_attribution": revision.intervention_attribution,
            "rationale": revision.rationale,
            "reviewer_id": REVIEWER_ID,
            "reviewer_role": REVIEWER_ROLE,
            "review_method": REVIEW_METHOD,
            "independent_review": False,
            "clinical_reviewer": False,
            "is_evaluable_for_final_metrics": False,
            "has_clinical_component": True,
            "has_preclinical_component": False,
            "note": (
                "decisione di prima revisione. Non e' gold e non entra in nessuna "
                "metrica finale di linking o accordo."
            ),
            "created_at": created_at,
            "approval_version": APPROVAL_VERSION,
        }
        if revision.extra:
            row.update(dict(revision.extra))
        rows.append(row)
    return rows


def annotate_gold(
    gold: list[dict[str, Any]], *, created_at: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Annota i soli link fra i due statement e la parent unit di questa fonte."""
    by_statement = {revision.statement_id: revision for revision in STATEMENT_REVISIONS}
    touched: list[str] = []
    rows: list[dict[str, Any]] = []

    for row in gold:
        revision = by_statement.get(str(row.get("statement_id")))
        if revision is None or str(row.get("profile_unit_id")) != PARENT_UNIT_ID:
            rows.append(row)
            continue

        annotated = {
            **row,
            "review_stage": "first_review_complete",
            "final_status": "provisional_first_review",
            "is_evaluable": False,
            "requires_second_review": True,
            "first_annotator": REVIEWER_ID,
            "first_review_annotation": {
                "reviewer_id": REVIEWER_ID,
                "reviewer_role": REVIEWER_ROLE,
                "review_method": REVIEW_METHOD,
                "independent_review": False,
                "clinical_reviewer": False,
                "link_status": revision.link_status,
                "candidate_status": revision.first_review_status,
                "profile_unit_ids": [APPROVED_UNIT_ID],
                "invalid_reason": revision.invalid_reason,
                "supported_dimensions": list(revision.supported_dimensions),
                "unsupported_or_not_separable_dimensions": list(revision.unsupported_dimensions),
                "rationale": revision.rationale,
                "reviewed_at": created_at,
            },
            "second_annotation": None,
            "second_annotator": None,
            "agreement": None,
            "adjudication": None,
            "adjudicator": None,
            "frozen_at": "",
            "profile_review_status": "first_review_complete",
            "note": (
                "prima revisione registrata. Il link_status vive in "
                "first_review_annotation e non in final_status: una prima revisione "
                "non indipendente e non clinica non puo' essere il riferimento contro "
                "cui si misura il linker."
            ),
        }
        touched.append(str(row.get("gold_link_id")))
        rows.append(annotated)

    return rows, touched


def check_gold(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        if row.get("is_evaluable"):
            raise GoldError(f"{row.get('gold_link_id')}: il gold non puo' essere valutabile")
        if row.get("final_status") in ("final", "frozen", "adjudicated"):
            raise GoldError(f"{row.get('gold_link_id')}: final_status non ammesso")
        annotation = row.get("first_review_annotation") or {}
        if annotation.get("candidate_status") and row.get("final_status") == annotation.get(
            "candidate_status"
        ):
            raise GoldError(
                f"{row.get('gold_link_id')}: lo stato del candidato e' stato copiato in "
                "final_status"
            )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    created_at = args.timestamp or datetime.now(timezone.utc).isoformat()

    decisions = build_decisions(created_at)
    write_jsonl(args.output / "statement_first_review_decisions.jsonl", decisions)

    previous_gold = list(read_jsonl(args.review_dir / "provisional_gold.jsonl"))
    gold, touched = annotate_gold(previous_gold, created_at=created_at)
    if len(touched) != len(STATEMENT_REVISIONS):
        raise GoldError(
            f"annotati {len(touched)} link invece di {len(STATEMENT_REVISIONS)}: {touched}"
        )
    check_gold(gold)
    write_jsonl(args.output / "provisional_gold.jsonl", gold)

    reference = {
        "canonical_source_id": CANONICAL_SOURCE_ID,
        "profile_unit_id": PARENT_UNIT_ID,
        "reviewer_id": REVIEWER_ID,
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        **dict(DETECTOR_REFERENCE_CASE),
    }
    write_jsonl(args.output / "detector_reference_cases.jsonl", [reference])

    previous_metrics = json.loads(
        (args.review_dir / "first_review_metrics.json").read_text(encoding="utf-8")
    )
    invalid = sum(
        1 for row in decisions if row["first_review_candidate_status"] == "candidate_invalid"
    )
    partial = sum(
        1 for row in decisions if row["first_review_candidate_status"] == "candidate_partial"
    )
    batch_units = list(read_jsonl(args.batch_dir / "proposed_profile_units.jsonl"))

    metrics = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "metric_kind": "descriptive_first_review_metrics",
        "metric_kind_note": (
            "Contano decisioni e coperture. Nessuna misura la qualita' del sistema: "
            "esiste una sola annotazione per link, non indipendente e non clinica."
        ),
        "author_approval_packets_completed": 1,
        "first_review_sources_completed": 1,
        "first_review_statements_reviewed": len(decisions),
        "first_review_structural_splits_rejected": 1,
        "first_review_candidate_invalid": invalid,
        "first_review_candidate_partial": partial,
        "detector_reference_hard_negatives": 1,
        "cumulative": {
            "first_review_packets_completed": (
                previous_metrics["first_review_packets_completed"] + 1
            ),
            "first_review_statements_reviewed": (
                previous_metrics["first_review_statements_reviewed"] + len(decisions)
            ),
            "first_review_profile_units_created": (
                previous_metrics["first_review_profile_units_created"] + 1
            ),
        },
        # La copertura separa gli stadi perche' confonderli e' il modo piu'
        # rapido di far sembrare revisionato cio' che e' soltanto proposto.
        "coverage_by_review_stage": {
            "source_checked_proposal": len(batch_units),
            "first_review_confirmed": (
                previous_metrics["coverage_by_review_stage"]["first_review_proposed"]
                + len(decisions)
            ),
            "second_review_confirmed": 0,
            "final_adjudicated": 0,
        },
        "qualifier_provenance_completeness": 1.0,
        "second_review_packets_completed": 0,
        "not_calculated": {
            "linking_precision": "not_calculated",
            "linking_recall": "not_calculated",
            "linking_f1": "not_calculated",
            "inter_annotator_agreement": "not_calculated",
            "detector_accuracy": "not_calculated",
            "clinical_applicability_accuracy": "not_calculated",
            "retrieval_quality": "not_calculated",
        },
        "not_calculated_reason": (
            "la prima revisione non e' indipendente e non e' clinica; nessuna seconda "
            "revisione esiste. Un solo caso non stima le prestazioni del rilevatore."
        ),
        "hashes": {
            "statement_decisions": content_hash(decisions),
            "provisional_gold": content_hash(gold),
            "detector_reference_cases": content_hash([reference]),
        },
        "supersedes_gold": "benchmarks/mtb_evidence/v3/first_review/provisional_gold.jsonl",
        "annotated_gold_links": touched,
    }
    write_json(args.output / "review_metrics.json", metrics)

    blinding = json.loads(
        (args.output / "second_review_blinding_check.json").read_text(encoding="utf-8")
    )
    readiness = {
        "created_at": created_at,
        "approval_version": APPROVAL_VERSION,
        "author_approvals_completed": 1,
        "author_approvals_pending": 2,
        "clinical_preclinical_false_positives_confirmed": 1,
        "detector_promotion_ready": False,
        "ready_for_final_evaluation": False,
        "gold_evaluable": False,
        "second_review_required": True,
        "second_review_packets_unchanged": blinding["byte_identical"],
        "standard_queue_resumed": False,
        "note": (
            "La coda standard non riprende in questo branch. Il passo successivo e' "
            "l'approvazione della seconda fonte del batch clinico/preclinico."
        ),
        "next_report_to_approve": "SOURCE_REVIEW_PMID-22235099.md",
        "forbidden_statuses_declared": [],
        "forbidden_statuses_checked": list(FORBIDDEN_STATUSES),
    }
    write_json(args.output / "readiness.json", readiness)

    print(f"decisioni registrate: {len(decisions)}")
    for row in decisions:
        print(
            f"  {row['statement_id']}: {row['previous_candidate_status']} -> "
            f"{row['first_review_candidate_status']}"
        )
    print(f"gold annotato: {touched}")
    print(f"caso di riferimento: {reference['reference_case_type']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
