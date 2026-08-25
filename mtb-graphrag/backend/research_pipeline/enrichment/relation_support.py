"""Small deterministic verifier for document-grounded GCA relations."""

from __future__ import annotations

import re
from typing import Any

CONFIRMED = "CONFIRMED"
NOT_CONFIRMED = "NOT_CONFIRMED"
CONTRADICTORY = "CONTRADICTORY"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNKNOWN = "UNKNOWN"

FULL_SUPPORT = "FULL_SUPPORT"
PARTIAL_SUPPORT = "PARTIAL_SUPPORT"
NO_SUPPORT = "NO_SUPPORT"
UNVERIFIABLE = "UNVERIFIABLE"


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _labels(candidate: dict[str, Any], key: str, types: set[str] | None = None) -> list[str]:
    return [
        str(item["label"])
        for item in candidate.get(key) or []
        if item.get("label") and (types is None or _norm(item.get("type")) in types)
    ]


def _matches(expected: list[str], observed: Any) -> str:
    if not expected:
        return NOT_APPLICABLE
    actual = _norm(observed)
    if not actual or actual in {"unknown", "not applicable"}:
        return NOT_CONFIRMED
    return CONFIRMED if any(_norm(value) in actual or actual in _norm(value) for value in expected) else NOT_CONFIRMED


def _direction(candidate: dict[str, Any], observed: Any) -> str:
    expected = _norm(candidate.get("direction"))
    actual = _norm(observed)
    if not expected:
        return NOT_APPLICABLE
    if not actual or actual in {"unknown", "not applicable"}:
        return NOT_CONFIRMED
    groups = {
        "positive": {"supports", "sensitivity", "sensitivity response", "response"},
        "negative": {"does not support", "resistance", "reduced sensitivity", "adverse response"},
    }
    expected_group = next((name for name, values in groups.items() if expected in values), None)
    actual_group = next((name for name, values in groups.items() if actual in values), None)
    if expected == actual or expected_group == actual_group:
        return CONFIRMED
    if expected_group and actual_group and expected_group != actual_group:
        return CONTRADICTORY
    return NOT_CONFIRMED


def assess_relation_support(candidate: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Compare Reader observations with fields semantically required by a GCA."""
    if observed.get("decision") != "QUOTE":
        return {"fields": {}, "result": UNVERIFIABLE, "reason": "READER_ABSTAINED"}

    evidence_scope = candidate.get("evidence_scope") or candidate.get("diagnostic_scope")
    fields = {
        "disease": _matches(_labels(candidate, "disease"), observed.get("observed_disease")),
        "gene": _matches(_labels(candidate, "biomarkers", {"gene"}), observed.get("observed_gene")),
        "alteration": _matches(
            _labels(candidate, "biomarkers", {"variant", "alteration"}),
            observed.get("observed_alteration"),
        ),
        "drug": _matches(_labels(candidate, "interventions"), observed.get("observed_drug")),
        "direction": _direction(candidate, observed.get("observed_direction")),
        "evidence_type": _matches([str(evidence_scope)] if evidence_scope else [], observed.get("observed_evidence_type")),
    }
    applicable = [value for value in fields.values() if value != NOT_APPLICABLE]
    core_names = ("gene", "alteration", "drug", "direction", "evidence_type")
    core = [fields[name] for name in core_names if fields[name] != NOT_APPLICABLE]
    if CONTRADICTORY in applicable:
        overall, reason = CONTRADICTORY, "SOURCE_CONTRADICTS_REQUIRED_RELATION_FIELD"
    elif not core:
        overall, reason = UNVERIFIABLE, "CANDIDATE_HAS_NO_VERIFIABLE_RELATION_CORE"
    elif applicable and all(value == CONFIRMED for value in applicable):
        overall, reason = FULL_SUPPORT, "ALL_REQUIRED_RELATION_FIELDS_CONFIRMED"
    elif any(value == CONFIRMED for value in core):
        overall, reason = PARTIAL_SUPPORT, "RELATION_CORE_PRESENT_WITH_MISSING_SPECIFICITY"
    else:
        overall, reason = NO_SUPPORT, "RELATION_CORE_NOT_CONFIRMED"
    return {"fields": fields, "result": overall, "reason": reason}
