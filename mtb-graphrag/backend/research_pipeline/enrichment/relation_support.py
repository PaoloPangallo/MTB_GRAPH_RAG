"""Small deterministic verifier for document-grounded GCA relations."""

from __future__ import annotations

import re
from typing import Any

from backend.research_pipeline.determinism.direction_semantics import (
    compare_relation_axes, derive_expected_effect, derive_source_stance,
)
from .canonical_normalizer import entity_relation

VERIFIER_POLICY_VERSION = "paper-relation-verifier/4.0"

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


def _matches(expected: list[str], observed: Any, *, allow_hierarchy: bool = False) -> str:
    if not expected:
        return NOT_APPLICABLE
    values = observed if isinstance(observed, list) else [observed]
    if not any(_norm(value) for value in values):
        return NOT_CONFIRMED
    allowed = {"IDENTICAL", "CANONICAL_ALIAS"}
    if allow_hierarchy:
        allowed.update({"SOURCE_BROADER", "SOURCE_NARROWER"})
    return CONFIRMED if any(entity_relation(value, actual) in allowed
                            for value in expected for actual in values) else NOT_CONFIRMED


def _relation_values(observed: dict[str, Any], kind: str) -> list[str]:
    has_canonical_relation = "observed_relation" in observed and observed.get("observed_relation") is not None
    relation = observed.get("observed_relation") or {}
    if kind == "disease":
        return [relation.get("disease")] if has_canonical_relation else [observed.get("observed_disease")]
    if kind == "drug":
        return [relation.get("intervention")] if has_canonical_relation else [observed.get("observed_drug")]
    types = {"gene": {"GENE"}, "alteration": {"ALTERATION"}, "biomarker": {"GENE", "ALTERATION", "BIOMARKER"}}[kind]
    values = [item.get("canonical_value") or item.get("surface_value") or item.get("value")
              for item in relation.get("subjects") or []
              if isinstance(item, dict) and str(item.get("type") or "").upper() in types]
    if has_canonical_relation:
        return values
    return [observed.get({"gene": "observed_gene", "alteration": "observed_alteration"}.get(kind, ""))]


def _direction(candidate: dict[str, Any], observed: Any, observed_stance: Any = None) -> str:
    expected_stance = derive_source_stance(candidate)
    expected_effect = derive_expected_effect(candidate)
    if expected_stance == "UNKNOWN" and expected_effect == "UNKNOWN" and not _norm(candidate.get("direction")):
        return NOT_APPLICABLE
    comparison = compare_relation_axes(
        candidate.get("predicate"), expected_stance, expected_effect, observed, observed_stance,
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
    values = {_norm(item.get("canonical_value") or item.get("surface_value") or item.get("value"))
              for item in subjects if isinstance(item, dict)}
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

    fields = {
        "disease": _matches(_labels(candidate, "disease"), _relation_values(observed, "disease"), allow_hierarchy=True),
        "gene": _matches(_labels(candidate, "biomarkers", {"gene"}), _relation_values(observed, "gene")),
        "alteration": _matches(
            _labels(candidate, "biomarkers", {"variant", "alteration"}),
            _relation_values(observed, "alteration"),
        ),
        "drug": _matches(_labels(candidate, "interventions"), _relation_values(observed, "drug")),
        "direction": _direction(
            candidate,
            ((observed.get("observed_relation") or {}).get("effect_direction")
             if observed.get("observed_relation") is not None else observed.get("observed_direction")),
            (observed.get("observed_relation") or {}).get("observed_stance"),
        ),
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
    if evidence_context == "EXACT":
        fields["evidence_context"] = CONFIRMED
    applicable = [value for value in fields.values() if value != NOT_APPLICABLE]
    core_names = ("gene", "alteration", "drug", "direction", "evidence_context")
    core = [fields[name] for name in core_names if fields.get(name, NOT_APPLICABLE) != NOT_APPLICABLE]
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
    if observed.get("observed_relation") is None and overall == FULL_SUPPORT:
        overall, reason = PARTIAL_SUPPORT, "LEGACY_OBSERVATION_CANNOT_ESTABLISH_FULL_SUPPORT"
    return {"fields": fields, "result": overall, "reason": reason}
