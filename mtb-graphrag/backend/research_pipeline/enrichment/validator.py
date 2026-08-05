"""Deterministic validator for PaperContextEnrichment. Never used as primary
evidence -- primary evidence remains GraphCandidateAssertion + document +
SourceUnit + the deterministic pipeline's own compatibility checks."""
from __future__ import annotations

import re
from typing import Any

from ..models import ENRICHMENT_OUTCOMES

_RECOMMENDATION_PHRASES = ("should be treated", "should receive", "recommend", "is indicated for", "eligible for", "we suggest", "patients should")
_ELLIPSIS_MARKERS = ("...", "…")


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _content_words(text: str) -> set[str]:
    stopwords = {"the", "a", "an", "and", "or", "of", "in", "to", "for", "with", "this", "that", "is", "was", "were", "are", "be", "as", "by", "on", "at", "it", "its", "that", "these", "those"}
    return {w for w in _norm(text).split() if len(w) > 2 and w not in stopwords}


def validate_enrichment(transport_result: str, enrichment: dict[str, Any] | None, *, candidate: dict[str, Any], paper_bundle: dict[str, Any], source_units_by_id: dict[str, dict], requested_drug: str) -> dict[str, Any]:
    if transport_result != "FORCED_TOOL_VALID":
        return _result("REJECTED_TRANSPORT", [f"TRANSPORT_RESULT:{transport_result}"])
    if enrichment is None:
        return _result("REJECTED_SCHEMA", ["ENRICHMENT_MISSING"])

    if enrichment.get("abstain"):
        if any(enrichment.get(key) for key in ("source_unit_id", "drug", "author_claim_quote", "author_context_summary", "evidence_kind")):
            return _result("REJECTED_SCHEMA", ["ABSTAIN_TRUE_BUT_FIELDS_POPULATED"])
        return _result("ENRICHMENT_ABSTAINED", [enrichment.get("abstention_reason") or "MODEL_ABSTENTION"])

    reasons: list[str] = []

    if enrichment.get("candidate_id") != candidate.get("candidate_id"):
        return _result("REJECTED_DOCUMENT", ["CANDIDATE_ID_MISMATCH"])
    if enrichment.get("paper_id") != paper_bundle.get("bundle_id"):
        return _result("REJECTED_DOCUMENT", ["PAPER_ID_MISMATCH"])

    source_unit_id = enrichment.get("source_unit_id")
    if not source_unit_id or source_unit_id not in source_units_by_id:
        return _result("REJECTED_SOURCE_UNIT", ["SOURCE_UNIT_NOT_FOUND"])
    if source_unit_id not in (paper_bundle.get("resolved_source_unit_ids") or paper_bundle.get("source_unit_ids") or []):
        return _result("REJECTED_SOURCE_UNIT", ["SOURCE_UNIT_NOT_IN_PAPER"])

    unit_text = source_units_by_id[source_unit_id].get("text") or ""
    quote = enrichment.get("author_claim_quote") or ""
    if not quote:
        return _result("REJECTED_QUOTE", ["QUOTE_EMPTY"])
    if any(marker in quote for marker in _ELLIPSIS_MARKERS):
        return _result("REJECTED_QUOTE", ["QUOTE_CONTAINS_ELLIPSIS"])
    occurrences = [m.start() for m in re.finditer(re.escape(quote), unit_text)]
    if not occurrences:
        return _result("REJECTED_QUOTE", ["QUOTE_NOT_LITERAL_IN_SOURCE_UNIT"])

    drug_reported = _norm(enrichment.get("drug"))
    drug_requested = _norm(requested_drug)
    if not drug_reported or (drug_requested not in drug_reported and drug_reported not in drug_requested):
        return _result("REJECTED_CONTEXT_MISMATCH", ["DRUG_DOES_NOT_MATCH_REQUESTED_DRUG"])
    if drug_reported not in _norm(unit_text) and drug_reported not in _norm(quote):
        return _result("REJECTED_CONTEXT_MISMATCH", ["DRUG_NOT_PRESENT_IN_SOURCE_UNIT"])

    disease_labels = [_norm(d.get("label")) for d in candidate.get("disease") or [] if d.get("label")]
    biomarker_labels = [_norm(b.get("label")) for b in candidate.get("biomarkers") or [] if b.get("label")]
    disease_compatible = not disease_labels or any(label in _norm(unit_text) for label in disease_labels)
    biomarker_compatible = not biomarker_labels or any(label in _norm(unit_text) for label in biomarker_labels)
    if not (disease_compatible and biomarker_compatible):
        reasons.append("MINIMAL_DISEASE_BIOMARKER_COMPATIBILITY_WEAK")

    # An empty summary is accepted (with a warning, not a rejection): prompt v1.1
    # explicitly allows "zero, one, or two short sentences" and instructs the model not
    # to abstain solely because a safe summary cannot be produced. Rejecting an empty
    # summary outright would penalize exactly the behavior that prompt asks for. A
    # non-empty summary is still checked for recommendations and quote-grounding.
    summary = enrichment.get("author_context_summary") or ""
    if not summary:
        reasons.append("SUMMARY_EMPTY")
    else:
        if any(phrase in summary.lower() for phrase in _RECOMMENDATION_PHRASES):
            return _result("REJECTED_SUMMARY_UNGROUNDED", ["SUMMARY_CONTAINS_CLINICAL_RECOMMENDATION"])
        grounding_vocabulary = _content_words(quote) | _content_words(drug_requested)
        summary_words = _content_words(summary)
        overlap = summary_words & grounding_vocabulary
        overlap_ratio = len(overlap) / len(summary_words) if summary_words else 0.0
        if overlap_ratio < 0.25:
            return _result("REJECTED_SUMMARY_UNGROUNDED", [f"SUMMARY_QUOTE_OVERLAP_BELOW_THRESHOLD:{overlap_ratio:.2f}"])
        if overlap_ratio < 0.5:
            reasons.append(f"SUMMARY_QUOTE_OVERLAP_LOW:{overlap_ratio:.2f}")

    outcome = "ENRICHMENT_ACCEPTED_WITH_WARNING" if reasons else "ENRICHMENT_ACCEPTED"
    return _result(outcome, reasons, quote_offset=occurrences[0], quote_ambiguous=len(occurrences) > 1)


def _result(outcome: str, reason_codes: list[str], **extra: Any) -> dict[str, Any]:
    assert outcome in ENRICHMENT_OUTCOMES
    return {"outcome": outcome, "reason_codes": reason_codes, **extra}
