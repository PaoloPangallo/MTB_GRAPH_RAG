"""CaseContext Match Verifier: fully deterministic, no LLM. Checks every
field the parser produced against the original clinical text using literal
span matching, normalization, and structural consistency checks -- never a
generic self-confirmation prompt to the same model that produced the
CaseContext (explicitly excluded by the protocol)."""
from __future__ import annotations

import re
from typing import Any

from ..models import MATCH_FIELDS, MatchVerificationRecord

ESSENTIAL_FIELDS = ("disease", "biomarker", "query_intent")


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _find_offsets(text: str, quote: str) -> list[int]:
    if not quote:
        return []
    return [m.start() for m in re.finditer(re.escape(quote), text)]


def _verify_span_field(field_name: str, payload: dict[str, Any] | None, text: str) -> MatchVerificationRecord:
    if payload is None or payload.get("raw_value") is None:
        return MatchVerificationRecord(field_name, None, "MISSING_IN_TEXT", None, None, None, "FIELD_NOT_POPULATED")
    spans = payload.get("source_spans") or []
    if not spans:
        return MatchVerificationRecord(field_name, payload.get("raw_value"), "MISMATCH", None, None, None, "VALUE_WITHOUT_SOURCE_SPAN")
    span = spans[0]
    quote = span.get("quote")
    if not quote or not isinstance(quote, str):
        return MatchVerificationRecord(field_name, payload.get("raw_value"), "MISMATCH", None, None, None, "SPAN_QUOTE_MISSING")
    # The literal quote's presence in the text is authoritative (same "exact quote"
    # philosophy used throughout this research thread's other validators); the model's
    # self-reported start/end offsets only disambiguate which occurrence was meant when
    # the quote appears more than once -- they never override a confirmed single literal
    # match, since LLM-reported offsets are frequently off by a few characters even when
    # the quote text itself was copied correctly.
    occurrences = _find_offsets(text, quote)
    if not occurrences:
        return MatchVerificationRecord(field_name, payload.get("raw_value"), "MISMATCH", None, None, None, "QUOTE_NOT_IN_TEXT")
    start, end = span.get("start_offset"), span.get("end_offset")
    if len(occurrences) == 1:
        chosen_start, chosen_end = occurrences[0], occurrences[0] + len(quote)
    elif isinstance(start, int) and isinstance(end, int) and text[start:end] == quote and start in occurrences:
        chosen_start, chosen_end = start, end
    else:
        return MatchVerificationRecord(field_name, payload.get("raw_value"), "UNCERTAIN", quote, None, None, "AMBIGUOUS_OFFSET_MULTIPLE_OCCURRENCES")
    normalized = payload.get("normalized_value") or ""
    if _norm(normalized) and _norm(normalized) not in _norm(quote) and _norm(quote) not in _norm(normalized):
        return MatchVerificationRecord(field_name, payload.get("raw_value"), "UNCERTAIN", quote, chosen_start, chosen_end, "NORMALIZED_VALUE_DIVERGES_FROM_QUOTE")
    return MatchVerificationRecord(field_name, payload.get("raw_value"), "MATCH", quote, chosen_start, chosen_end, "EXACT_TEXT_MATCH")


def verify_case_context(case_context: dict[str, Any], clinical_text: str) -> list[MatchVerificationRecord]:
    records = [_verify_span_field("disease", case_context.get("disease"), clinical_text)]

    biomarkers = case_context.get("biomarkers") or []
    if not biomarkers:
        records.append(MatchVerificationRecord("biomarker", None, "MISSING_IN_TEXT", None, None, None, "FIELD_NOT_POPULATED"))
        records.append(MatchVerificationRecord("alteration", None, "MISSING_IN_TEXT", None, None, None, "FIELD_NOT_POPULATED"))
    else:
        for index, biomarker in enumerate(biomarkers):
            gene_payload = {"raw_value": biomarker.get("raw_value"), "normalized_value": biomarker.get("normalized_value"), "source_spans": biomarker.get("source_spans")}
            record = _verify_span_field("biomarker", gene_payload, clinical_text)
            records.append(MatchVerificationRecord(f"biomarker[{index}]", record.casecontext_value, record.status, record.supporting_text, record.start_offset, record.end_offset, record.reason_code))
            if biomarker.get("alteration"):
                alteration_payload = {"raw_value": biomarker.get("alteration"), "normalized_value": biomarker.get("alteration"), "source_spans": biomarker.get("source_spans")}
                arecord = _verify_span_field("alteration", alteration_payload, clinical_text)
                records.append(MatchVerificationRecord(f"alteration[{index}]", arecord.casecontext_value, arecord.status, arecord.supporting_text, arecord.start_offset, arecord.end_offset, arecord.reason_code))

    previous = case_context.get("previous_interventions") or []
    if not previous:
        records.append(MatchVerificationRecord("previous_intervention", None, "MISSING_IN_TEXT", None, None, None, "FIELD_NOT_POPULATED"))
    else:
        for index, item in enumerate(previous):
            record = _verify_span_field("previous_intervention", item, clinical_text)
            records.append(MatchVerificationRecord(f"previous_intervention[{index}]", record.casecontext_value, record.status, record.supporting_text, record.start_offset, record.end_offset, record.reason_code))

    records.append(_verify_span_field("target_intervention", case_context.get("target_intervention"), clinical_text))

    query_intent = case_context.get("query_intent")
    target = case_context.get("target_intervention")
    structurally_consistent = (query_intent == "THERAPY_EVALUATION" and target is not None) or (query_intent == "THERAPY_DISCOVERY" and target is None)
    records.append(MatchVerificationRecord(
        "query_intent", query_intent, "MATCH" if structurally_consistent else "MISMATCH", None, None, None,
        "INTENT_TARGET_CONSISTENT" if structurally_consistent else "INTENT_TARGET_INCONSISTENT",
    ))
    return records


def essential_fields_pass(records: list[MatchVerificationRecord]) -> tuple[bool, list[str]]:
    """Section 7: pipeline may continue only if essential fields are MATCH, or UNCERTAIN
    with an explicit warning. Any essential MISMATCH stops the case before retrieval."""
    warnings: list[str] = []
    by_field: dict[str, list[MatchVerificationRecord]] = {}
    for record in records:
        base_field = record.field.split("[")[0]
        by_field.setdefault(base_field, []).append(record)

    for essential in ESSENTIAL_FIELDS:
        field_records = by_field.get(essential, [])
        if not field_records:
            return False, warnings
        statuses = {record.status for record in field_records}
        if "MISMATCH" in statuses:
            return False, warnings
        if "UNCERTAIN" in statuses:
            warnings.append(f"UNCERTAIN_ESSENTIAL_FIELD:{essential}")
    return True, warnings
