"""Deterministic, read-only reconciliation of the research pipeline stages."""

from __future__ import annotations

from typing import Any
from copy import deepcopy

from .builder import evidence_id, is_aggregation_eligible


def apply_publication_integrity(report: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with publication completeness separate from execution.

    Reconciliation failure preserves every claim and evidence record; it only
    closes publication and exposes the original diagnostic. Safe for replayed
    reports and repeated projections, without repairing or inventing evidence.
    """
    from .observations import migrate_public_projection
    projected = deepcopy(migrate_public_projection(report))
    if projected.get("documentary_contract_version"):
        from .observations import project_documentary_findings

        expected = project_documentary_findings(projected)
        aligned = expected.get("documentary_summary") == projected.get("documentary_summary") and all(
            actual.get("documentary_findings") == reference.get("documentary_findings")
            and actual.get("documentary_target") == reference.get("documentary_target")
            and actual.get("documentary_attempts") == reference.get("documentary_attempts")
            for actual, reference in zip(projected.get("paper_evidence") or [], expected.get("paper_evidence") or [])
        )
        if not aligned:
            pipeline = projected.setdefault("pipeline_accounting", {})
            original = deepcopy(pipeline.get("bidirectional_reconciliation") or {})
            pipeline["bidirectional_reconciliation"] = {
                **original, "status": "FAIL",
                "reason_codes": list(dict.fromkeys([*(original.get("reason_codes") or []), "DOCUMENTARY_PROJECTION_MISMATCH"])),
            }
    reconciliation = ((projected.get("pipeline_accounting") or {})
                      .get("bidirectional_reconciliation") or {})
    technical = projected.get("technical_run_status", projected.get("run_status"))
    projected["technical_run_status"] = technical
    reconciliation_passed = reconciliation.get("status") == "PASS"
    projected["publication_status"] = (
        "COMPLETE" if reconciliation_passed and technical == "COMPLETED" else "INCOMPLETE")
    projected["publication_integrity"] = {
        "reconciliation_status": reconciliation.get("status", "NOT_AVAILABLE"),
        "reason_codes": list(reconciliation.get("reason_codes") or []),
        "diagnostic": deepcopy(reconciliation),
    }
    if not reconciliation_passed and projected.get("run_status") == "COMPLETED":
        projected["run_status"] = "PARTIAL"
    return projected


def build_pipeline_accounting(
    *, mention_accounting: dict[str, Any], retrieval_result: dict[str, Any],
    selections: list[dict[str, Any]], paper_results: dict[str, dict[str, Any]],
    trial_results: dict[str, dict[str, Any]], report: dict[str, Any],
    pending_reader_requests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Account for each transition without promoting trial metadata to efficacy."""
    used_candidates = sorted({
        str(candidate_id)
        for association in retrieval_result.get("associations") or []
        for candidate_id in association.get("candidate_group_candidate_ids")
        or [association.get("candidate_id")]
        if candidate_id
    })
    excluded_candidates = sorted((
        {"candidate_id": str(item.get("candidate_id")),
         "reason": ",".join(str(reason) for reason in item.get("reason_codes") or []) or "NO_MATCH"}
        for item in retrieval_result.get("excluded_candidates") or []
    ), key=lambda item: (item["candidate_id"], item["reason"]))

    used_documents = sorted((
        {"candidate_id": str(selection.get("candidate_id")),
         "document_id": str(paper.get("document_id"))}
        for selection in selections for paper in selection.get("selected_papers") or []
    ), key=lambda item: (item["candidate_id"], item["document_id"]))
    excluded_documents = sorted((
        {"candidate_id": str(selection.get("candidate_id")),
         "document_id": str(paper.get("document_id")),
         "reason": ",".join(str(reason) for reason in paper.get("reason_codes") or []) or "NOT_SELECTED"}
        for selection in selections for paper in selection.get("excluded_papers") or []
    ), key=lambda item: (item["candidate_id"], item["document_id"], item["reason"]))

    accepted_evidence: list[dict[str, Any]] = []
    rejected_evidence: list[dict[str, Any]] = []
    reader_records: list[dict[str, Any]] = []
    for candidate_id, result in sorted(paper_results.items()):
        for record in result.get("evidence_records") or []:
            allowed, reason = is_aggregation_eligible(record)
            support_result = ((record.get("candidate_support") or {}).get("result")
                              or record.get("support_level"))
            entry = {"candidate_id": candidate_id, "evidence_id": evidence_id(record),
                     "document_id": record.get("document_id") or record.get("paper_id"),
                     "source_unit_id": record.get("source_unit_id"),
                     "support_result": support_result,
                     "reader_attempt_status": record.get("reader_attempt_status"),
                     "validation_outcome": record.get("validation_outcome")}
            verification = record.get("document_verification") or {}
            entry.update({
                "verification_status": verification.get("verification_status"),
                "final_admission": verification.get("final_admission"),
                "semantic_attempted": verification.get("semantic_assessment") is not None,
                "verification_reason_codes": verification.get("admission_reason_codes") or [],
                "verification_disposition": _verification_disposition(
                    verification.get("verification_status"), support_result),
            })
            if allowed:
                disposition = "ADMITTED_TO_DOSSIER"
                accepted_evidence.append(entry)
            else:
                disposition = _failure_disposition(record, reason)
                rejected_evidence.append({**entry, "reason": reason or "NOT_ELIGIBLE",
                                          "disposition": disposition})
            reader_records.append({**entry, "eligible": allowed,
                                   "disposition": disposition,
                                   "reason": None if allowed else reason or "NOT_ELIGIBLE"})
    for candidate_id, result in sorted(trial_results.items()):
        for record in result.get("reader_attempts") or []:
            entry = {
                "candidate_id": candidate_id, "evidence_id": evidence_id(record),
                "document_id": record.get("document_id") or record.get("paper_id"),
                "reason": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
                "reader_attempt_status": record.get("reader_attempt_status"),
                "disposition": "TRIAL_CONTEXT_ONLY",
            }
            rejected_evidence.append(entry)
            reader_records.append({**entry, "eligible": False, "support_result": None,
                                  "source_unit_id": record.get("source_unit_id"),
                                  "validation_outcome": record.get("validation_outcome")})

    summary = retrieval_result.get("retrieval_summary") or {}
    considered = (summary.get("gca4_source_candidate_count") or 0) + (
        summary.get("derived_composite_candidate_count") or 0
    )
    used_ids = set(used_candidates)
    excluded_ids = {item["candidate_id"] for item in excluded_candidates}
    total_attempts = len(accepted_evidence) + len(rejected_evidence)
    accepted_ids = {item["evidence_id"] for item in accepted_evidence}
    reconciliation = _reconcile_claims(paper_results, report, reader_records)
    claimed_ids = {
        str(evidence)
        for claim in report.get("claims") or []
        for key in ("supporting_evidence_ids", "partial_evidence_ids",
                    "contradicting_evidence_ids", "no_support_evidence_ids",
                    "unverifiable_evidence_ids", "insufficient_information_evidence_ids",
                    "structurally_blocked_evidence_ids", "technical_error_evidence_ids")
        for evidence in claim.get(key) or []
    }
    accepted_not_represented = sorted(accepted_ids - claimed_ids)
    claims_without_admitted_record = sorted(claimed_ids - accepted_ids)
    if accepted_not_represented or claims_without_admitted_record:
        reconciliation["status"] = "FAIL"
        reconciliation["reason_codes"] = sorted(set(
            reconciliation["reason_codes"] + ["EVIDENCE_CLAIM_RECONCILIATION_FAILED"]
        ))
    return {
        "parsed_mentions": mention_accounting,
        "retrieved_candidates": {
            "considered": considered, "used": used_candidates,
            "excluded": excluded_candidates,
            "duplicate_accounting_ids": sorted(used_ids & excluded_ids),
            "unaccounted_count": considered - len(used_ids | excluded_ids),
        },
        "selected_documents": {"used": used_documents, "excluded": excluded_documents},
        "pending_reader_requests": [dict(item) for item in pending_reader_requests or []],
        "reader_attempts": {"total": total_attempts, "records": reader_records,
                             "duplicate_evidence_ids": _duplicates(
                                 item["evidence_id"] for item in reader_records)},
        "accepted_evidence": {"count": len(accepted_evidence), "used": accepted_evidence,
                              "unclaimed_ids": sorted(accepted_ids - claimed_ids)},
        "rejected_or_failed_evidence": {"count": len(rejected_evidence), "excluded": rejected_evidence},
        "final_claims": {"count": len(report.get("claims") or []),
                         "used": sorted(str(item.get("claim_id")) for item in report.get("claims") or []),
                         "unknown_evidence_ids": sorted(claimed_ids - accepted_ids)},
        "bidirectional_reconciliation": {
            "accepted_not_represented": accepted_not_represented,
            "claims_without_admitted_record": claims_without_admitted_record,
            "duplicate_reader_evidence_ids": _duplicates(item["evidence_id"] for item in reader_records),
            **reconciliation,
        },
    }


def _reconcile_claims(paper_results: dict[str, dict[str, Any]], report: dict[str, Any],
                      reader_records: list[dict[str, Any]]) -> dict[str, Any]:
    admitted = {item["evidence_id"]: item for item in reader_records if item["eligible"]}
    claim_fields = {
        "FULL_SUPPORT": "supporting_evidence_ids",
        "PARTIAL_SUPPORT": "partial_evidence_ids",
        "CONTRADICTORY": "contradicting_evidence_ids",
        "NO_SUPPORT": "no_support_evidence_ids",
        "UNVERIFIABLE": "unverifiable_evidence_ids",
        "INSUFFICIENT_INFORMATION": "insufficient_information_evidence_ids",
    }
    mismatches: list[dict[str, Any]] = []
    missing_assessment_ids: list[str] = []
    legacy_claims: list[str] = []
    claims = report.get("claims") or []
    for claim in claims:
        candidate_id = str(claim.get("candidate_id") or "")
        group_ids = {str(value) for value in claim.get("candidate_group_candidate_ids") or []}
        claim_candidate_ids = {candidate_id, *group_ids} - {""}
        for status, field in claim_fields.items():
            for evidence_ref in claim.get(field) or []:
                identity = str(evidence_ref)
                record = admitted.get(identity)
                if record and record.get("support_result") != status:
                    mismatches.append({"evidence_id": identity, "field": field,
                                       "expected_status": record.get("support_result"),
                                       "observed_status": status})
                if record and record.get("candidate_id") not in claim_candidate_ids:
                    mismatches.append({"evidence_id": identity, "field": "candidate_id",
                                       "expected": record.get("candidate_id"),
                                       "observed": sorted(claim_candidate_ids)})
        assessments = claim.get("evidence_assessments") or []
        if not assessments:
            if any(claim.get(field) for field in claim_fields.values()):
                legacy_claims.append(str(claim.get("claim_id")))
            continue  # historical reports may predate per-evidence assessments
        for assessment in assessments:
            identity = str(assessment.get("evidence_id") or "")
            record = admitted.get(identity)
            if not record:
                mismatches.append({"evidence_id": identity, "field": "evidence_assessments",
                                   "reason": "ASSESSMENT_WITHOUT_ADMITTED_RECORD"})
                missing_assessment_ids.append(identity)
                continue
            if record.get("candidate_id") != candidate_id:
                mismatches.append({"evidence_id": identity, "field": "candidate_id",
                                   "expected": record.get("candidate_id"), "observed": candidate_id})
            original = next((raw for result in paper_results.values()
                             for raw in result.get("evidence_records") or []
                             if evidence_id(raw) == identity and is_aggregation_eligible(raw)[0]), None)
            if original is None:
                missing_assessment_ids.append(identity)
                continue
            verification = original.get("document_verification") or {}
            expected = {
                "paper_id": original.get("paper_id") or original.get("document_id"),
                "document_id": original.get("document_id") or original.get("paper_id"),
                "source_unit_id": original.get("source_unit_id"),
                "quote_valid": original.get("quote_valid") is True,
                "quote": (original.get("quote") or original.get("author_claim_quote")
                          if original.get("quote_valid") is True else None),
                "support_result": (original.get("candidate_support") or {}).get("result")
                                  or original.get("support_level"),
                "support_limitation": verification.get("support_limitation"),
            }
            for field, value in expected.items():
                if field not in assessment or assessment.get(field) != value:
                    mismatches.append({"evidence_id": identity, "field": field,
                                       "expected": value, "observed": assessment.get(field)})
    duplicates = _duplicates(item["evidence_id"] for item in reader_records)
    errors = bool(mismatches or duplicates or missing_assessment_ids)
    status = "FAIL" if errors else "LEGACY_UNVERIFIED" if legacy_claims else "PASS"
    reason_codes = ((["EVIDENCE_ASSESSMENT_MISMATCH"] if mismatches else [])
                    + (["DUPLICATE_EVIDENCE_ID"] if duplicates else [])
                    + (["ASSESSMENT_SOURCE_RECORD_MISSING"] if missing_assessment_ids else [])
                    + (["LEGACY_ASSESSMENT_FIELDS_ABSENT"] if legacy_claims else []))
    return {
        "status": status,
        "reason_codes": sorted(set(reason_codes)),
        "assessment_mismatches": mismatches,
        "assessments_without_source_record": sorted(set(missing_assessment_ids)),
        "legacy_claims_without_assessment": sorted(set(legacy_claims)),
    }


def _duplicates(values) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _failure_disposition(record: dict[str, Any], reason: str | None) -> str:
    """Separate technical/structural/non-evaluated records from scientific states."""
    status = str(record.get("reader_attempt_status") or "").upper()
    outcome = str(record.get("validation_outcome") or "").upper()
    if any(token in status or token in outcome for token in
           ("TRANSPORT", "PARSE_FAILED", "TECHNICAL_ERROR", "SCHEMA_INVALID", "RATE_LIMIT")):
        return "TECHNICAL_ERROR"
    if any(token in status or token in outcome for token in ("NOT_RUN", "NOT_EVALUATED", "SKIPPED")):
        return "NOT_EVALUATED"
    if reason in {"SOURCE_UNIT_ID_MISSING", "DOCUMENT_ID_MISSING", "DOCUMENT_VERIFICATION_NOT_ADMITTED"}:
        return "STRUCTURAL_OR_PROVENANCE_REJECTION"
    return "REJECTED_FROM_DOSSIER"


def _verification_disposition(verification_status: Any, support_result: Any) -> str:
    """Keep semantic outcome orthogonal to whether the record enters the dossier."""
    status = str(verification_status or "").upper()
    support = str(support_result or "").upper()
    if status == "TECHNICAL_ERROR":
        return "TECHNICAL_ERROR"
    if status.startswith("STRUCTURAL_"):
        return "STRUCTURAL_BLOCK"
    if status in {"NOT_RUN", "SEMANTIC_ASSESSMENT_NOT_RUN"}:
        return "NOT_EVALUATED"
    if support == "UNVERIFIABLE":
        return "UNVERIFIABLE"
    if support in {"FULL_SUPPORT", "PARTIAL_SUPPORT", "CONTRADICTORY", "NO_SUPPORT",
                   "INSUFFICIENT_INFORMATION"}:
        return support
    return "NOT_EVALUATED"
