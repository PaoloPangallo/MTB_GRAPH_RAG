"""PaperContextEnrichmentV2Validator -- deterministic, separate from and
never replacing/modifying PaperContextEnricherValidator (v1,
enrichment_validator.py). Applies all semantic checks the v2.0 transport
deliberately defers (section 5 of the protocol)."""
from __future__ import annotations

import re
from typing import Any, Callable

_RECOMMENDATION_PHRASES = ("should be treated", "should receive", "recommend", "is indicated for", "eligible for", "we suggest", "patients should")
_STATUS_GATE_WORDS = ("direct", "partial", "ambiguous", "contradicted", "gate", "bucket", "score", "evidence level")
_ELLIPSIS_MARKERS = ("...", "…")

QUOTE_OUTCOMES = (
    "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY",
    "REJECTED_SOURCE_UNIT", "REJECTED_QUOTE_NOT_FOUND", "REJECTED_QUOTE_NON_CONTIGUOUS",
    "REJECTED_CONTEXT_MISMATCH", "REJECTED_SUMMARY_UNGROUNDED", "REJECTED_CLINICAL_RECOMMENDATION",
)
ABSTAIN_OUTCOMES = ("ENRICHMENT_V2_ABSTAINED", "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS")
ALL_OUTCOMES = QUOTE_OUTCOMES + ABSTAIN_OUTCOMES + ("REJECTED_TRANSPORT",)


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _content_words(text: str) -> set[str]:
    stopwords = {"the", "a", "an", "and", "or", "of", "in", "to", "for", "with", "this", "that", "is", "was", "were", "are", "be", "as", "by", "on", "at", "it", "its", "these", "those"}
    return {w for w in _norm(text).split() if len(w) > 2 and w not in stopwords}


def _validate_quote(args: dict[str, str], *, candidate: dict[str, Any], paper_bundle: dict[str, Any], source_units_by_id: dict[str, dict], requested_drug: str, case_context_text: str, candidate_text: str) -> dict[str, Any]:
    source_unit_id = args["source_unit_id"].strip()
    quote = args["author_claim_quote"].strip()
    summary = args["author_context_summary"].strip()

    if not source_unit_id:
        return _result("REJECTED_SOURCE_UNIT", ["SOURCE_UNIT_ID_EMPTY"])
    if source_unit_id not in source_units_by_id:
        return _result("REJECTED_SOURCE_UNIT", ["SOURCE_UNIT_NOT_FOUND"])
    if source_unit_id not in (paper_bundle.get("resolved_source_unit_ids") or paper_bundle.get("source_unit_ids") or []):
        return _result("REJECTED_SOURCE_UNIT", ["SOURCE_UNIT_NOT_IN_PAPER"])

    if not quote:
        return _result("REJECTED_QUOTE_NOT_FOUND", ["QUOTE_EMPTY"])
    if any(marker in quote for marker in _ELLIPSIS_MARKERS):
        return _result("REJECTED_QUOTE_NON_CONTIGUOUS", ["QUOTE_CONTAINS_ELLIPSIS"])

    unit_text = source_units_by_id[source_unit_id].get("text") or ""
    if quote not in unit_text:
        return _result("REJECTED_QUOTE_NOT_FOUND", ["QUOTE_NOT_LITERAL_IN_SOURCE_UNIT"])

    if case_context_text and quote in case_context_text:
        return _result("REJECTED_CONTEXT_MISMATCH", ["QUOTE_MATCHES_CASE_CONTEXT"])
    if candidate_text and quote in candidate_text:
        return _result("REJECTED_CONTEXT_MISMATCH", ["QUOTE_MATCHES_CANDIDATE"])

    drug_norm = _norm(requested_drug)
    if drug_norm and drug_norm not in _norm(quote) and drug_norm not in _norm(unit_text):
        return _result("REJECTED_CONTEXT_MISMATCH", ["DRUG_NOT_PRESENT_IN_PASSAGE"])

    reasons: list[str] = []
    if not summary:
        return _result("ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY", ["SUMMARY_EMPTY"])

    if any(phrase in summary.lower() for phrase in _RECOMMENDATION_PHRASES):
        return _result("REJECTED_CLINICAL_RECOMMENDATION", ["SUMMARY_CONTAINS_CLINICAL_RECOMMENDATION"])
    if any(word in _norm(summary).split() or word in _norm(summary) for word in _STATUS_GATE_WORDS):
        return _result("REJECTED_SUMMARY_UNGROUNDED", ["SUMMARY_CONTAINS_STATUS_OR_GATE_LANGUAGE"])

    grounding_vocabulary = _content_words(quote) | _content_words(requested_drug)
    summary_words = _content_words(summary)
    overlap_ratio = len(summary_words & grounding_vocabulary) / len(summary_words) if summary_words else 0.0
    if overlap_ratio < 0.25:
        return _result("REJECTED_SUMMARY_UNGROUNDED", [f"SUMMARY_QUOTE_OVERLAP_BELOW_THRESHOLD:{overlap_ratio:.2f}"])
    if overlap_ratio < 0.5:
        reasons.append(f"SUMMARY_QUOTE_OVERLAP_LOW:{overlap_ratio:.2f}")

    return _result("ENRICHMENT_V2_ACCEPTED", reasons)


def _validate_abstain(args: dict[str, str]) -> dict[str, Any]:
    populated = [key for key in ("source_unit_id", "author_claim_quote", "author_context_summary") if args[key].strip()]
    if populated:
        return _result("ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS", [f"FIELDS_POPULATED_DESPITE_ABSTAIN:{populated}"], inconsistent_fields=populated)
    reasons = [] if args["abstention_reason"].strip() else ["ABSTENTION_REASON_EMPTY"]
    return _result("ENRICHMENT_V2_ABSTAINED", reasons)


def identity_semantic_validator(args: dict[str, str], **_: Any) -> dict[str, Any]:
    """D06-only identity seam after transport/schema acceptance."""
    if args["decision"] == "ABSTAIN":
        return _validate_abstain(args)
    return _result("ENRICHMENT_V2_ACCEPTED", ["SEMANTIC_VALIDATION_IDENTITY"])


def validate_enrichment_v2(transport_result: str, args: dict[str, str] | None, *, candidate: dict[str, Any], paper_bundle: dict[str, Any], source_units_by_id: dict[str, dict], requested_drug: str, case_context_text: str = "", candidate_text: str = "", semantic_validator: Callable[..., dict[str, Any]] | None = None) -> dict[str, Any]:
    if transport_result != "V2_TRANSPORT_VALID" or args is None:
        return _result("REJECTED_TRANSPORT", [f"TRANSPORT_RESULT:{transport_result}"])

    if semantic_validator is not None:
        return semantic_validator(
            args, candidate=candidate, paper_bundle=paper_bundle,
            source_units_by_id=source_units_by_id, requested_drug=requested_drug,
            case_context_text=case_context_text, candidate_text=candidate_text,
        )

    if args["decision"] == "ABSTAIN":
        return _validate_abstain(args)
    return _validate_quote(args, candidate=candidate, paper_bundle=paper_bundle, source_units_by_id=source_units_by_id, requested_drug=requested_drug, case_context_text=case_context_text, candidate_text=candidate_text)


def _result(outcome: str, reason_codes: list[str], **extra: Any) -> dict[str, Any]:
    assert outcome in ALL_OUTCOMES, outcome
    return {"outcome": outcome, "reason_codes": reason_codes, **extra}
