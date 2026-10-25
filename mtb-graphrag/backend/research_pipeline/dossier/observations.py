"""Versioned documentary facts, not a replacement clinical/support score.

This pure projection preserves the admission engine's decisions without using its
legacy aggregate verdict to infer authentication, correspondence or clinical truth.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any
from ..enrichment.verification_policy import public_artifact

DOCUMENTARY_VERSION = "documentary-findings/1.1"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def project_record(record: dict[str, Any], entry: dict[str, Any], disposition: str) -> dict[str, Any]:
    # Use the exact public representation before binding source hashes/target.
    # Publication serialization must not subsequently change documentary facts.
    record = public_artifact(record)
    verification = _mapping(record.get("document_verification"))
    support = _mapping(record.get("candidate_support"))
    family = record.get("relation_family") or verification.get("target_snapshot", {}).get("relation_family")
    final = verification.get("final_admission")
    state = verification.get("verification_status")
    if final == "TECHNICAL_ERROR" or state == "TECHNICAL_ERROR":
        semantic_status = "TECHNICAL_ERROR"
    elif final == "NOT_RUN_STRUCTURAL" or state == "SEMANTIC_ASSESSMENT_NOT_RUN":
        semantic_status = "NOT_EXECUTED"
    elif state == "ASSESSED":
        semantic_status = "ASSESSED"
    elif family == "EVIDENCE_STATEMENT":
        semantic_status = "NOT_REQUIRED_BY_POLICY"
    else:
        semantic_status = "NOT_RECORDED"
    valid = record.get("quote_valid")
    validation_reasons = record.get("validation_reason_codes") or record.get("reason_codes") or []
    literal_failed = "QUOTE_NOT_LITERAL_IN_SOURCE_UNIT" in validation_reasons
    literal = record.get("quote") or record.get("author_claim_quote")
    result = {
        "evidence_id": record.get("evidence_id"),
        "candidate_id": entry.get("candidate_id"), "relation_family": family,
        "requested_target": deepcopy(verification.get("target_snapshot") or entry.get("documentary_target") or {}),
        "disposition": disposition,
        "source": {key: deepcopy(record.get(key)) for key in (
            "public_source_identity", "document_id", "paper_id", "source_unit_id",
            "source_unit_sha256", "source_unit_digest_contract", "source_unit_chars")},
        "quotation": literal if valid is True else None,
        "observed": deepcopy(record.get("observed_relation") or {}),
        "observed_origin": "READER_EXTRACTION_NOT_INDEPENDENT_GOLD",
        "checks": {
            "quotation": {"status": "AUTHENTICATED" if valid is True else "REJECTED" if literal_failed else "NOT_ESTABLISHED" if valid is False else "NOT_RECORDED",
                          "validation_outcome": record.get("validation_outcome"),
                          "reason_codes": deepcopy(validation_reasons),
                          "origin": "RECORDED_DOCUMENT_VALIDATOR"},
            "structural": {"status": verification.get("structural_status") or "NOT_RECORDED",
                           "reason_codes": verification.get("structural_reason_codes") or [],
                           "origin": "DETERMINISTIC_GATE"},
            "correspondence": {"fields": deepcopy(support.get("fields") or {}),
                               "origin": "RECORDED_POLICY_FIELDS_NOT_INDEPENDENT_GOLD"},
            "semantic": {"status": semantic_status, "origin": "MODEL_ASSESSMENT_WITH_DETERMINISTIC_CONSTRAINTS",
                         "assessment": deepcopy(verification.get("semantic_assessment")) if semantic_status == "ASSESSED" else None,
                         "model": verification.get("semantic_model"),
                         "prompt_version": verification.get("semantic_prompt_version")},
        },
        "limitations": {"reason_codes": deepcopy(verification.get("admission_reason_codes") or record.get("reason_codes") or record.get("validation_reason_codes") or []),
                        "rejection_reason": record.get("rejection_reason") or record.get("reason"),
                        "scope": deepcopy(verification.get("support_limitation")),
                        "abstain_reason": record.get("abstain_reason") or record.get("abstention_reason")},
        "scientific_correctness": "NOT_INDEPENDENTLY_EVALUATED",
        "clinical_applicability": "NOT_EVALUATED",
        "legacy_classification": {"result": support.get("result") or record.get("support_level"),
                                  "final_admission": final, "role": "COMPATIBILITY_ONLY_NOT_SCIENTIFIC_ENDPOINT"},
    }
    phenotype = support.get('phenotype')
    if isinstance(phenotype, dict):
        result['requested_target']['phenotype'] = deepcopy(phenotype)
        scope = support.get('phenotype_scope')
        if isinstance(scope, dict):
            result['checks']['correspondence']['phenotype_scope'] = deepcopy(scope)
            result['limitations']['phenotype_scope'] = deepcopy(scope)
    return result



def project_documentary_findings(report: dict[str, Any]) -> dict[str, Any]:
    """Fresh projection; historical artifacts and raw decisions are never rewritten."""
    result = deepcopy(report)
    records = []
    for entry in result.get("paper_evidence") or []:
        entry["documentary_target"] = {key: deepcopy(entry.get(key)) for key in (
            "candidate_id", "subject", "relation", "object", "direction", "disease_context", "evidence_type", "graph_provenance")}
        entry["documentary_target"].update({
            "specificity": deepcopy(_mapping(entry.get("claim")).get("specificity") or {}),
            "gene_variant_pairings": deepcopy(_mapping(entry.get("claim")).get("gene_variant_pairings") or []),
        })
        findings = []
        originals: dict[str, list[dict[str, Any]]] = {}
        for raw in entry.get("evidence_records") or []:
            if raw.get("evidence_id"):
                originals.setdefault(raw["evidence_id"], []).append(raw)
        for key, disposition in (("accepted_evidence_records", "RETAINED_RECORD"),
                                 ("rejected_evidence", "EXCLUDED_RECORD")):
            for record in entry.get(key) or []:
                matches = originals.get(record.get("evidence_id"), [])
                # Only one exact evidence identity may supply omitted audit fields.
                # Duplicate/conflicting IDs must be reconciled, never guessed.
                audit = {**matches[0], **record} if len(matches) == 1 else record
                findings.append(project_record(audit, entry, disposition))
        # Include unexecuted/abstained attempts; never infer an extracted record.
        entry["documentary_attempts"] = [
            {key: deepcopy(attempt.get(key)) for key in (
                "evidence_id", "paper_id", "source_unit_id", "decision", "abstain_reason",
                "reader_attempt_status", "transport_result", "validation_outcome")}
            for attempt in entry.get("reader_attempts") or []
        ]
        entry["documentary_attempts"].extend(
            {**deepcopy(attempt), "reader_attempt_status": "NOT_EXECUTED"}
            for attempt in result.get("pending_reader_requests") or []
            if attempt.get("candidate_id") == entry.get("candidate_id")
        )
        entry["documentary_findings"] = findings
        entry["legacy_aggregate"] = {"support_level": entry.get("support_level"),
                                     "role": "COMPATIBILITY_ONLY_NOT_SCIENTIFIC_ENDPOINT"}
        records.extend(findings)
    for entry in result.get("clinical_trials") or []:
        entry["documentary_scope"] = "REGISTRY_INFORMATION_NOT_EFFICACY"
    for entry in result.get("kg_only_relations") or []:
        entry["documentary_scope"] = "GRAPH_PROVENANCE_ONLY"
    result["documentary_contract_version"] = DOCUMENTARY_VERSION
    result["documentary_summary"] = {
        "record_count": len(records),
        "authenticated_record_count": sum(r["checks"]["quotation"]["status"] == "AUTHENTICATED" for r in records),
        "retained_record_count": sum(r["disposition"] == "RETAINED_RECORD" for r in records),
        "excluded_record_count": sum(r["disposition"] == "EXCLUDED_RECORD" for r in records),
        "distinct_source_identifier_count": len({r["source"].get("public_source_identity") or r["source"].get("document_id") or r["source"].get("paper_id") for r in records} - {None, ""}),
        "structural_counts": dict(Counter(r["checks"]["structural"]["status"] for r in records)),
        "semantic_execution_counts": dict(Counter(r["checks"]["semantic"]["status"] for r in records)),
        "scientific_accuracy": "NOT_MEASURED_BY_THIS_SUMMARY",
    }
    return result


def migrate_public_projection(report: dict[str, Any]) -> dict[str, Any]:
    """Read-only 1.0 migration, allowing only the known serialization defects.

    No observation, check, disposition, or nonempty digest may change. Anything
    else remains a reconciliation failure, not a repaired or promoted record.
    """
    if report.get("documentary_contract_version") != "documentary-findings/1.0":
        return report
    expected = project_documentary_findings(report)
    if expected.get("documentary_summary") != report.get("documentary_summary"):
        return report
    for actual, reference in zip(report.get("paper_evidence") or [], expected.get("paper_evidence") or []):
        if actual.get("documentary_target") != reference.get("documentary_target") or actual.get("documentary_attempts") != reference.get("documentary_attempts"):
            return report
        old_findings, new_findings = actual.get("documentary_findings") or [], reference.get("documentary_findings") or []
        if len(old_findings) != len(new_findings):
            return report
        for old, new in zip(old_findings, new_findings):
            normalized = deepcopy(old)
            _mapping(normalized.get("requested_target")).pop("evidence_statement", None)
            source = _mapping(normalized.get("source"))
            for key in ("source_unit_sha256", "source_unit_digest_contract", "source_unit_chars"):
                if source.get(key) is None:
                    source[key] = new["source"].get(key)
            if normalized != new:
                return report
    expected["documentary_projection_migration"] = {
        "from_version": "documentary-findings/1.0", "to_version": DOCUMENTARY_VERSION,
        "reason": "PUBLIC_SERIALIZATION_NORMALIZATION", "observation_content_changed": False,
        "stored_ledger_unchanged": True,
    }
    return expected
