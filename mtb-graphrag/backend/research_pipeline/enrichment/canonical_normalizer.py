"""Versioned, semantics-preserving normalization for PAPER observations."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

NORMALIZER_VERSION = "paper-canonical-normalizer/1.0"
ALIAS_TABLE_VERSION = "paper-alias-table/1.0"
# Deliberately empty at v1.0.  New aliases require a reviewed, versioned resource;
# representation normalization must not turn a broader biomedical concept into a target.
APPROVED_ALIASES: dict[str, str] = {}
ANCHOR_TYPES = frozenset({"GENE", "ALTERATION", "BIOMARKER", "OTHER"})


def normalize_surface(value: Any) -> str:
    """Normalize representation only; never infer an entity or relation."""
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def entity_relation(expected: Any, observed: Any) -> str:
    """Compare candidate expected vs source observed identity, conservatively."""
    left, right = normalize_surface(expected), normalize_surface(observed)
    if not left or not right:
        return "UNKNOWN"
    if left == right:
        return "IDENTICAL"
    if APPROVED_ALIASES.get(left) == right or APPROVED_ALIASES.get(right) == left:
        return "CANONICAL_ALIAS"
    left_tokens, right_tokens = set(left.split()), set(right.split())
    if left_tokens < right_tokens:
        return "SOURCE_BROADER"
    if right_tokens < left_tokens:
        return "SOURCE_NARROWER"
    return "DIFFERENT"


def normalize_anchor(anchor: dict[str, Any]) -> dict[str, Any]:
    """Attach audit-friendly canonical text without changing the extracted surface."""
    surface = str(anchor.get("surface_value") or anchor.get("value") or "")
    normalized = {
        "type": str(anchor.get("type") or "OTHER").upper(),
        "surface_value": surface,
        "canonical_value": normalize_surface(surface),
    }
    if anchor.get("linked_gene"):
        normalized["linked_gene"] = str(anchor["linked_gene"])
    return normalized


def normalize_observed_relation(relation: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a normalized copy; raw Reader fields remain present for provenance."""
    if relation is None:
        return None
    normalized = dict(relation)
    normalized["subjects"] = [normalize_anchor(item) for item in relation.get("subjects") or []
                              if isinstance(item, dict)]
    for field in ("disease", "intervention"):
        value = relation.get(field)
        normalized[f"{field}_canonical"] = normalize_surface(value) if value else ""
    return normalized


def normalized_phrase_in(value: Any, text: Any) -> bool:
    """Representation-safe phrase grounding, not clinical equivalence."""
    phrase, context = normalize_surface(value), normalize_surface(text)
    return bool(phrase and phrase in context)


def subject_level_consistency(level: Any, quote: Any) -> str:
    """Detect only gross contradictions; absence of cues is unresolved."""
    value, text = str(level or "UNKNOWN"), normalize_surface(quote)
    cell = any(token in text for token in ("cell line", "cells", "in vitro", "cultured"))
    animal = any(token in text for token in ("mouse", "mice", "xenograft", "animal model"))
    human_collective = any(token in text for token in ("patient", "participant", "subject", "population", "cohort", "series", "trial"))
    if value == "COHORT" and (cell or animal) and not human_collective:
        return "INCONSISTENT"
    if value == "INDIVIDUAL" and (cell or animal) and not human_collective:
        return "INCONSISTENT"
    if value == "CELL_MODEL" and cell:
        return "CONSISTENT"
    if value == "ANIMAL_MODEL" and animal:
        return "CONSISTENT"
    if value == "COHORT" and human_collective:
        return "CONSISTENT"
    if value == "INDIVIDUAL" and "patient" in text:
        return "CONSISTENT"
    return "UNRESOLVED"
