"""Shared semantics for evidence stance and clinical effect direction."""

from __future__ import annotations

import re
from typing import Any

SUPPORTS = "SUPPORTS"
DOES_NOT_SUPPORT = "DOES_NOT_SUPPORT"
CONTRADICTS = "CONTRADICTS"
UNKNOWN = "UNKNOWN"
NOT_APPLICABLE = "NOT_APPLICABLE"

SENSITIVITY_RESPONSE = "SENSITIVITY_RESPONSE"
RESISTANCE = "RESISTANCE"
REDUCED_SENSITIVITY = "REDUCED_SENSITIVITY"
ADVERSE_RESPONSE = "ADVERSE_RESPONSE"

CLINICAL_EFFECTS = frozenset({SENSITIVITY_RESPONSE, RESISTANCE,
                               REDUCED_SENSITIVITY, ADVERSE_RESPONSE})


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def normalize_observed_effect(value: Any) -> str:
    key = _norm(value)
    aliases = {
        "sensitivity": SENSITIVITY_RESPONSE,
        "sensitivity response": SENSITIVITY_RESPONSE,
        "response": SENSITIVITY_RESPONSE,
        "resistance": RESISTANCE,
        "reduced sensitivity": REDUCED_SENSITIVITY,
        "adverse response": ADVERSE_RESPONSE,
    }
    return aliases.get(key, UNKNOWN if key not in {"", "not applicable"} else NOT_APPLICABLE)


def normalize_observed_stance(value: Any) -> str:
    """Normalize only the evidence-stance axis; never map it to an effect."""
    key = _norm(value)
    aliases = {
        "supports": SUPPORTS,
        "does not support": DOES_NOT_SUPPORT,
        "contradicts": CONTRADICTS,
        "contradicts assertion": CONTRADICTS,
    }
    return aliases.get(key, UNKNOWN if key not in {"", "not applicable"} else NOT_APPLICABLE)


def derive_source_stance(candidate: dict[str, Any]) -> str:
    evidence = (candidate.get("source_properties") or {}).get("evidence") or {}
    key = _norm(evidence.get("evidence_direction"))
    if key == "supports":
        return SUPPORTS
    if key in {"does not support", "contradicts", "contradicts assertion"}:
        return DOES_NOT_SUPPORT if key == "does not support" else CONTRADICTS
    # Legacy candidates sometimes duplicate stance in direction.
    key = _norm(candidate.get("direction"))
    if key == "supports":
        return SUPPORTS
    if key == "does not support":
        return DOES_NOT_SUPPORT
    return UNKNOWN


def derive_expected_effect(candidate: dict[str, Any]) -> str:
    predicate = _norm(candidate.get("predicate"))
    if predicate == "associated with resistance to":
        return RESISTANCE
    if predicate == "associated with sensitivity to":
        return SENSITIVITY_RESPONSE
    if predicate == "has evidence statement":
        significance = _norm(((candidate.get("source_properties") or {}).get("evidence") or {}).get("significance"))
        aliases = {
            "resistance": RESISTANCE,
            "sensitivity response": SENSITIVITY_RESPONSE,
            "sensitivity": SENSITIVITY_RESPONSE,
            "reduced sensitivity": REDUCED_SENSITIVITY,
            "adverse response": ADVERSE_RESPONSE,
        }
        return aliases.get(significance, UNKNOWN)
    return UNKNOWN


def compare_relation_axes(predicate: Any, expected_stance: str,
                          expected_effect: str, observed_direction: Any,
                          observed_stance: Any = None) -> str:
    """Return CONSISTENT, CONFLICTING, or UNRELATED for the relevant axes."""
    raw = _norm(observed_direction)
    observed = normalize_observed_effect(observed_direction)
    stance = normalize_observed_stance(observed_stance)
    # Legacy payloads put stance labels in the overloaded direction field.
    if stance in {UNKNOWN, NOT_APPLICABLE}:
        stance = normalize_observed_stance(observed_direction)
    pred = _norm(predicate)
    if not pred and stance not in {UNKNOWN, NOT_APPLICABLE}:
        return "CONSISTENT" if expected_stance == stance else "CONFLICTING"
    if pred == "has evidence statement":
        if stance not in {UNKNOWN, NOT_APPLICABLE} and expected_stance not in {UNKNOWN, NOT_APPLICABLE}:
            if stance != expected_stance:
                return "CONFLICTING"
            # A stance-only evidence statement can confirm stance, but a clinical
            # effect is never inferred from that stance alone.
            if expected_effect == UNKNOWN:
                return "CONSISTENT"
    if observed in {UNKNOWN, NOT_APPLICABLE}:
        return "UNRELATED"
    if pred == "has evidence statement":
        if expected_effect == UNKNOWN:
            return "UNRELATED"
        return "CONSISTENT" if observed == expected_effect else "CONFLICTING"
    if expected_effect == UNKNOWN:
        return "UNRELATED"
    return "CONSISTENT" if observed == expected_effect else "CONFLICTING"
