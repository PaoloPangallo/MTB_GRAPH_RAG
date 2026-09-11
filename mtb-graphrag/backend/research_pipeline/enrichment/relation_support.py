"""Small deterministic verifier for document-grounded GCA relations."""

from __future__ import annotations

import re
from typing import Any

from backend.research_pipeline.determinism.direction_semantics import (
    compare_relation_axes, derive_expected_effect, derive_source_stance,
)

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
    expected_stance = derive_source_stance(candidate)
    expected_effect = derive_expected_effect(candidate)
    if expected_stance == "UNKNOWN" and expected_effect == "UNKNOWN" and not _norm(candidate.get("direction")):
        return NOT_APPLICABLE
    if not _norm(observed) or _norm(observed) in {"unknown", "not applicable"}:
        return NOT_CONFIRMED
    comparison = compare_relation_axes(
        candidate.get("predicate"), expected_stance, expected_effect, observed,
    )
    if comparison == "CONSISTENT":
        return CONFIRMED
    if comparison == "CONFLICTING":
        return CONTRADICTORY
    return NOT_CONFIRMED


def _composition_state(candidate: dict[str, Any], observed: dict[str, Any]) -> str:
    relation = observed.get("observed_relation")
    if relation is None:
        return "LEGACY"
    scope = str(relation.get("relation_scope") or "UNKNOWN")
    subjects = relation.get("subjects") or []
    expected = [*_labels(candidate, "biomarkers", {"gene", "variant", "alteration"})]
    values = {_norm(item.get("value")) for item in subjects if isinstance(item, dict)}
    expected_values = {_norm(value) for value in expected}
    if scope == "UNKNOWN":
        return "UNKNOWN"
    if not expected_values or not expected_values.issubset(values):
        return "DIFFERENT"
    if scope != "SINGLE" and len(values) > len(expected_values):
        return "COMPOSITE_MISMATCH"
    return "EXACT"


def _evidence_context_state(candidate: dict[str, Any], observed: dict[str, Any]) -> str:
    relation = observed.get("observed_relation") or {}
    context = relation.get("evidence_context")
    if context is None:
        return "LEGACY"
    scope = _norm(candidate.get("evidence_scope") or candidate.get("diagnostic_scope"))
    level = str(context.get("subject_level") or "UNKNOWN")
    claim = str(context.get("claim_type") or "UNKNOWN")
    if level == "UNKNOWN" or claim == "UNKNOWN":
        return "UNKNOWN"
    if scope == "predictive" and (level == "INDIVIDUAL" and claim == "OBSERVED_RESPONSE"):
        return "INSUFFICIENT_GENERALIZATION"
    compatible = {
        "functional": {("CELL_MODEL", "FUNCTIONAL_EFFECT"), ("ANIMAL_MODEL", "FUNCTIONAL_EFFECT")},
        "prognostic": {("COHORT", "PROGNOSTIC_ASSOCIATION"), ("POPULATION", "PROGNOSTIC_ASSOCIATION")},
        "diagnostic": {("COHORT", "DIAGNOSTIC_ASSOCIATION"), ("POPULATION", "DIAGNOSTIC_ASSOCIATION")},
        "predictive": {("COHORT", "PREDICTIVE_ASSOCIATION"), ("POPULATION", "PREDICTIVE_ASSOCIATION"), ("CELL_MODEL", "FUNCTIONAL_EFFECT")},
    }
    return "EXACT" if (level, claim) in compatible.get(scope, set()) else "UNKNOWN"


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
    composition = _composition_state(candidate, observed)
    if composition in {"COMPOSITE_MISMATCH", "DIFFERENT"}:
        return {"fields": fields, "result": PARTIAL_SUPPORT,
                "reason": "OBSERVED_RELATION_COMPOSITION_MISMATCH",
                "relation_composition": composition}
    evidence_context = _evidence_context_state(candidate, observed)
    if evidence_context in {"INSUFFICIENT_GENERALIZATION", "UNKNOWN"} and observed.get("observed_relation") is not None:
        return {"fields": fields, "result": PARTIAL_SUPPORT,
                "reason": "OBSERVED_EVIDENCE_CONTEXT_INSUFFICIENT",
                "evidence_context": evidence_context}
    if composition == "UNKNOWN" and observed.get("observed_relation") is not None:
        return {"fields": fields, "result": PARTIAL_SUPPORT,
                "reason": "OBSERVED_RELATION_COMPOSITION_UNRESOLVED",
                "relation_composition": composition}
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
