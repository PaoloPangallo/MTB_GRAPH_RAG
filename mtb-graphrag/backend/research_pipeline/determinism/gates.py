"""STAGE 8 — deterministic support mask, status, gate, and warnings. Fully
rule-based: combines the already-structural CaseContext-vs-candidate match
(from retrieval.py) with only VALIDATED Gemma enrichments (ENRICHMENT_ACCEPTED
or ENRICHMENT_ACCEPTED_WITH_WARNING outcomes only -- never a rejected or raw
one). Gemma's evidence_kind is treated as reported testimony to reconcile
against the candidate's own asserted direction; Gemma itself never decides
the status. This is a new, independent decision path -- it does not call or
depend on the frozen `llm_claim_extractor` / `ClaimSupportVerifier`.
"""
from __future__ import annotations

import re
from typing import Any

POSITIVE_EVIDENCE_KINDS = {"RESPONSE", "BENEFIT"}
GATE_BUCKETS = ("PRIMARY_BUCKET", "WARNING_BUCKET", "REJECTED_BUCKET", "DISCOVERY_BUCKET")
STATUS_VALUES = ("DIRECT", "PARTIAL", "AMBIGUOUS", "CONTRADICTED", "DISCOVERED", "NO_MATCH")


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def direction_consistency(candidate_direction: str | None, evidence_kind: str | None) -> str | None:
    if evidence_kind is None:
        return None
    direction = _norm(candidate_direction)
    if "resistance" in direction:
        if evidence_kind == "RESISTANCE":
            return "CONSISTENT"
        if evidence_kind in POSITIVE_EVIDENCE_KINDS:
            return "CONFLICTING"
        return "UNRELATED"
    if "sensitivity" in direction or "response" in direction or "support" in direction:
        if evidence_kind in POSITIVE_EVIDENCE_KINDS:
            return "CONSISTENT"
        if evidence_kind == "RESISTANCE":
            return "CONFLICTING"
        return "UNRELATED"
    return "UNRELATED"


def evaluate_association(query_intent: str, candidate: dict[str, Any], validated_enrichments: list[dict[str, Any]]) -> dict[str, Any]:
    """validated_enrichments: list of {"validation_outcome", "enrichment"} where outcome is
    ENRICHMENT_ACCEPTED or ENRICHMENT_ACCEPTED_WITH_WARNING only -- callers must filter first."""
    accepted = [item for item in validated_enrichments if item["validation_outcome"] in ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING")]
    warnings: list[str] = []
    mask = {"disease": "SUPPORTED", "biomarker": "SUPPORTED"}

    if query_intent == "THERAPY_DISCOVERY":
        mask["intervention"] = "DISCOVERED"
        mask["direction"] = "NOT_APPLICABLE"
        return {"status": "DISCOVERED", "support_mask": mask, "gate_bucket": "DISCOVERY_BUCKET", "warnings": warnings, "direction_consistencies": []}

    mask["intervention"] = "SUPPORTED"
    if not accepted:
        mask["direction"] = "NO_DOCUMENT_SIGNAL"
        warnings.append("NO_VALIDATED_ENRICHMENT_AVAILABLE")
        return {"status": "AMBIGUOUS", "support_mask": mask, "gate_bucket": "WARNING_BUCKET", "warnings": warnings, "direction_consistencies": []}

    consistencies = [direction_consistency(candidate.get("direction"), item["enrichment"].get("evidence_kind")) for item in accepted]
    any_warning = any(item["validation_outcome"] == "ENRICHMENT_ACCEPTED_WITH_WARNING" for item in accepted)
    if any_warning:
        warnings.append("SOME_ENRICHMENTS_ACCEPTED_WITH_WARNING")

    if "CONFLICTING" in consistencies:
        mask["direction"] = "CONTRADICTED"
        return {"status": "CONTRADICTED", "support_mask": mask, "gate_bucket": "REJECTED_BUCKET", "warnings": warnings, "direction_consistencies": consistencies}
    if "CONSISTENT" in consistencies:
        mask["direction"] = "SUPPORTED"
        gate = "WARNING_BUCKET" if any_warning else "PRIMARY_BUCKET"
        status = "PARTIAL" if any_warning else "DIRECT"
        return {"status": status, "support_mask": mask, "gate_bucket": gate, "warnings": warnings, "direction_consistencies": consistencies}
    mask["direction"] = "UNRELATED_EVIDENCE"
    warnings.append("VALIDATED_ENRICHMENT_DOES_NOT_ADDRESS_DIRECTION")
    return {"status": "PARTIAL", "support_mask": mask, "gate_bucket": "WARNING_BUCKET", "warnings": warnings, "direction_consistencies": consistencies}
