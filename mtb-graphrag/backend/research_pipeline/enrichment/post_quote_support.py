"""Deterministic assessment after literal quote validation.

This module does not validate transport or quote authenticity and does not
change gate outcomes.  It only compares an already validated quote with the
candidate and the supplied SourceUnit context.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

STRONG_SUPPORT = "STRONG_SUPPORT"
PARTIAL_SUPPORT = "PARTIAL_SUPPORT"
CONTEXT_ONLY = "CONTEXT_ONLY"
CONTRADICTORY = "CONTRADICTORY"
UNVERIFIABLE = "UNVERIFIABLE"

CONFIRMED = "CONFIRMED"
NOT_CONFIRMED = "NOT_CONFIRMED"
OPPOSITE = "OPPOSITE"
UNKNOWN = "UNKNOWN"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _norm(value)))


def _contains_phrase(context: str, value: Any) -> bool:
    wanted = _norm(value)
    return bool(wanted) and wanted in _norm(context)


def _field_labels(candidate: dict[str, Any], key: str) -> list[str]:
    return [str(item.get("label") or "") for item in candidate.get(key) or () if item.get("label")]


def _gene_status(candidate: dict[str, Any], context: str) -> str:
    labels = [
        item.get("label") for item in candidate.get("biomarkers") or ()
        if str(item.get("type") or "").casefold() == "gene" and item.get("label")
    ]
    if not labels:
        return UNKNOWN
    context_tokens = _tokens(context)
    return CONFIRMED if any(_tokens(label) <= context_tokens for label in labels) else NOT_CONFIRMED


def _alteration_status(candidate: dict[str, Any], context: str) -> str:
    labels = [
        item.get("label") for item in candidate.get("biomarkers") or ()
        if str(item.get("type") or "").casefold() in {"variant", "alteration"}
        and item.get("label")
    ]
    if not labels:
        return "NOT_APPLICABLE"
    context_tokens = _tokens(context)
    return CONFIRMED if any(_tokens(label) <= context_tokens for label in labels) else NOT_CONFIRMED


def _drug_status(candidate: dict[str, Any], context: str) -> str:
    labels = _field_labels(candidate, "interventions")
    if not labels:
        return UNKNOWN
    return CONFIRMED if any(_contains_phrase(context, label) for label in labels) else UNKNOWN


def _textual_resistance_direction(candidate: dict[str, Any], context: str) -> str:
    """Recognize only an explicit, drug-bound resistance construction."""
    if _norm(candidate.get("direction")) != "resistance":
        return UNKNOWN

    context_norm = _norm(context)
    for label in _field_labels(candidate, "interventions"):
        drug = _norm(label)
        if not drug:
            continue
        pattern = re.compile(
            rf"\b(?:clinically\s+)?resistant\s+to\s+(?:therapy\s+with\s+)?{re.escape(drug)}\b"
        )
        for match in pattern.finditer(context_norm):
            prefix = context_norm[:match.start()].rstrip()
            if re.search(r"(?:\bnot|\bno\s+evidence\s+of)$", prefix):
                continue
            return CONFIRMED
    return UNKNOWN


def _direction_status(candidate: dict[str, Any], enrichment: dict[str, Any], context: str) -> str:
    candidate_direction = _norm(candidate.get("direction"))
    evidence_kind = _norm(enrichment.get("evidence_kind"))
    if not candidate_direction:
        return UNKNOWN

    # A structured value remains authoritative. Text is consulted only when it
    # is absent, never when it is merely unrecognized.
    if not evidence_kind:
        return _textual_resistance_direction(candidate, context)

    candidate_positive = candidate_direction in {"sensitivity response", "sensitivity", "response"}
    candidate_resistance = candidate_direction in {"resistance", "reduced sensitivity", "adverse response"}
    evidence_positive = evidence_kind in {"response", "benefit"}
    evidence_resistance = evidence_kind == "resistance"

    if candidate_positive and evidence_positive or candidate_resistance and evidence_resistance:
        return CONFIRMED
    if candidate_positive and evidence_resistance or candidate_resistance and evidence_positive:
        return OPPOSITE
    return UNKNOWN


def _final_result(fields: dict[str, str]) -> str:
    if fields["direction"] == OPPOSITE and fields["gene"] == CONFIRMED \
            and fields["drug"] == CONFIRMED \
            and fields["alteration"] in {CONFIRMED, "NOT_APPLICABLE"}:
        return CONTRADICTORY
    if fields["drug"] == UNKNOWN:
        return UNVERIFIABLE
    if fields["gene"] == CONFIRMED and fields["direction"] == CONFIRMED:
        if fields["alteration"] in {CONFIRMED, "NOT_APPLICABLE"}:
            return STRONG_SUPPORT
        return PARTIAL_SUPPORT
    return CONTEXT_ONLY


def assess_candidate_support(
    candidate: dict[str, Any],
    enrichment: dict[str, Any],
    *,
    source_unit_text: str,
    paper_id: str | None = None,
) -> dict[str, Any]:
    """Assess candidate alignment after quote validation.

    Callers must invoke this only after the existing Quote Validator accepts
    the quote. The result is deterministic provenance data used at the gate
    boundary: only ``STRONG_SUPPORT`` may promote the enrichment as exact
    candidate evidence; other support levels remain visible but cannot be
    promoted as exact support.
    """
    quote = str(enrichment.get("author_claim_quote") or "")
    context = f"{quote}\n{source_unit_text}"
    fields = {
        "disease": CONFIRMED if any(
            _contains_phrase(context, label) for label in _field_labels(candidate, "disease")
        ) else UNKNOWN,
        "gene": _gene_status(candidate, context),
        "alteration": _alteration_status(candidate, context),
        "drug": _drug_status(candidate, context),
        "direction": _direction_status(candidate, enrichment, context),
    }
    return {
        "candidate_id": candidate.get("candidate_id"),
        "paper_id": paper_id,
        "source_unit_id": enrichment.get("source_unit_id"),
        "quote": quote,
        "fields": fields,
        "result": _final_result(fields),
        "validator_boundary": "QUOTE_VALIDATOR_MUST_PASS_FIRST",
    }
