"""Conservative, non-default claim-level provenance propagation pilot."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

AMBIGUOUS_PARENT_PROVENANCE = "AMBIGUOUS_PARENT_PROVENANCE"
CLAIM_PUBLICATION_IDENTIFIER_ONLY = "CLAIM_PUBLICATION_IDENTIFIER_ONLY"
CLAIM_VERIFIED_LOCATOR = "CLAIM_VERIFIED_LOCATOR"
PARENT_PUBLICATION_AVAILABLE = "PARENT_PUBLICATION_AVAILABLE"
PARENT_RECORD_ONLY = "PARENT_RECORD_ONLY"
PROVENANCE_BROKEN = "PROVENANCE_BROKEN"
SOURCE_UNIT_MAPPING_MISSING = "SOURCE_UNIT_MAPPING_MISSING"


@dataclass(frozen=True)
class PropagationDecision:
    status: str
    rule: str
    reason: str
    confidence: str
    source_unit_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    locators: tuple[dict[str, Any], ...] = ()

    @property
    def can_promote(self) -> bool:
        return self.status in {
            CLAIM_VERIFIED_LOCATOR,
            CLAIM_PUBLICATION_IDENTIFIER_ONLY,
        }


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in (value or ()) if str(item).strip())


def _locators(value: Any) -> tuple[dict[str, Any], ...]:
    return tuple(dict(item) for item in (value or ()) if isinstance(item, Mapping))


def _source_key(value: str) -> str:
    prefix, separator, identifier = value.partition(":")
    if not separator:
        return value.strip().upper()
    prefix = prefix.strip().upper()
    if prefix == "PUBMED":
        prefix = "PMID"
    return f"{prefix}:{identifier.strip()}"


def _locator_sources(locators: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(
        str(item["source_id"])
        for item in locators
        if str(item.get("source_id") or "").strip()
    )


def _make(
    status: str,
    *,
    rule: str,
    reason: str,
    confidence: str,
    source_unit_ids: Sequence[str] = (),
    source_ids: Sequence[str] = (),
    locators: Sequence[Mapping[str, Any]] = (),
) -> PropagationDecision:
    return PropagationDecision(
        status=status,
        rule=rule,
        reason=reason,
        confidence=confidence,
        source_unit_ids=tuple(source_unit_ids),
        source_ids=tuple(source_ids),
        locators=tuple(dict(item) for item in locators),
    )


def decide_propagation(
    claim: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    explicit_mapping: Mapping[str, Any] | None = None,
) -> PropagationDecision:
    """Return a decision without copying parent identifiers as claim data."""
    existing_units = _strings(claim.get("source_unit_ids"))
    existing_locators = _locators(claim.get("locators"))
    existing_sources = _locator_sources(existing_locators)
    if existing_units and existing_locators and existing_sources:
        return _make(
            CLAIM_VERIFIED_LOCATOR,
            rule="EXISTING_CLAIM_MAPPING",
            reason="Claim already contains source unit and locator.",
            confidence="high",
            source_unit_ids=existing_units,
            source_ids=existing_sources,
            locators=existing_locators,
        )

    claim_id = str(claim.get("claim_id") or "")
    parent_sources = _strings(parent.get("source_ids"))

    if explicit_mapping is not None:
        if str(explicit_mapping.get("claim_id") or "") != claim_id:
            return _make(
                PROVENANCE_BROKEN,
                rule="EXPLICIT_MAPPING_ID_MISMATCH",
                reason="Explicit mapping belongs to another claim.",
                confidence="high",
            )
        mapped_units = _strings(explicit_mapping.get("source_unit_ids"))
        mapped_locators = _locators(explicit_mapping.get("locators"))
        mapped_sources = _strings(explicit_mapping.get("source_ids")) or _locator_sources(
            mapped_locators
        )
        if len(mapped_units) != 1:
            return _make(
                AMBIGUOUS_PARENT_PROVENANCE,
                rule="EXPLICIT_MAPPING_NOT_UNIQUE",
                reason="Explicit mapping does not identify one source unit.",
                confidence="high",
            )
        if not mapped_sources:
            return _make(
                SOURCE_UNIT_MAPPING_MISSING,
                rule="MAPPING_HAS_NO_DOCUMENT_IDENTIFIER",
                reason="Source unit exists in mapping but no document identifier is present.",
                confidence="high",
                source_unit_ids=mapped_units,
            )
        parent_keys = {_source_key(item) for item in parent_sources}
        if parent_keys and not all(_source_key(item) in parent_keys for item in mapped_sources):
            return _make(
                PROVENANCE_BROKEN,
                rule="MAPPING_SOURCE_NOT_IN_PARENT",
                reason="Mapped document identifier is not present in the parent.",
                confidence="high",
            )
        status = (
            CLAIM_VERIFIED_LOCATOR
            if mapped_locators
            else CLAIM_PUBLICATION_IDENTIFIER_ONLY
        )
        return _make(
            status,
            rule="EXPLICIT_CLAIM_SOURCE_UNIT_MAPPING",
            reason=(
                "Explicit claim-to-source-unit mapping and locator are present."
                if mapped_locators
                else "Explicit claim-to-source-unit mapping and publication are present; locator is absent."
            ),
            confidence="high",
            source_unit_ids=mapped_units,
            source_ids=mapped_sources,
            locators=mapped_locators,
        )

    parent_units = _strings(parent.get("source_unit_ids"))
    if len(parent_units) == 1 and len(parent_sources) == 1:
        parent_locators = _locators(parent.get("locators"))
        parent_locator_sources = _locator_sources(parent_locators)
        if parent_locator_sources:
            return _make(
                CLAIM_VERIFIED_LOCATOR,
                rule="SINGLE_PARENT_SOURCE_UNIT_AND_PUBLICATION",
                reason="Parent has one source unit, publication, and locator.",
                confidence="medium",
                source_unit_ids=parent_units,
                source_ids=parent_locator_sources,
                locators=parent_locators,
            )
        return _make(
            CLAIM_PUBLICATION_IDENTIFIER_ONLY,
            rule="SINGLE_PARENT_SOURCE_UNIT_AND_PUBLICATION",
            reason="Parent has one source unit and publication but no locator.",
            confidence="medium",
            source_unit_ids=parent_units,
            source_ids=parent_sources,
        )

    if len(parent_sources) > 1:
        return _make(
            AMBIGUOUS_PARENT_PROVENANCE,
            rule="PARENT_HAS_MULTIPLE_PUBLICATIONS",
            reason="Multiple parent publications have no claim-specific mapping.",
            confidence="high",
        )
    if len(parent_sources) == 1:
        aggregate = str(claim.get("claim_type") or "") == "aggregate_intervention_claim"
        reason = "One parent publication is available without claim-specific mapping."
        if aggregate:
            reason += " Aggregate claims require explicit mapping."
        return _make(
            PARENT_PUBLICATION_AVAILABLE,
            rule="PARENT_PUBLICATION_ONLY",
            reason=reason,
            confidence="high",
        )
    return _make(
        PARENT_RECORD_ONLY,
        rule="PARENT_RECORD_ONLY",
        reason="Parent has no document identifier.",
        confidence="high",
    )


def apply_decision(
    claim: Mapping[str, Any],
    decision: PropagationDecision,
    *,
    pilot_version: str = "qualified_claim_repository/1.5-provenance-pilot",
) -> dict[str, Any]:
    """Apply only promotable mapped fields and attach an audit record."""
    result = dict(claim)
    if decision.can_promote:
        result["source_unit_ids"] = list(decision.source_unit_ids)
        result["locators"] = [dict(item) for item in decision.locators]
    result["provenance_repair"] = {
        "pilot_version": pilot_version,
        "status": decision.status,
        "rule": decision.rule,
        "reason": decision.reason,
        "confidence": decision.confidence,
        "claim_source_ids": list(decision.source_ids),
        "source_unit_ids": list(decision.source_unit_ids),
        "locator_count": len(decision.locators),
    }
    return result


__all__ = [
    "AMBIGUOUS_PARENT_PROVENANCE",
    "CLAIM_PUBLICATION_IDENTIFIER_ONLY",
    "CLAIM_VERIFIED_LOCATOR",
    "PARENT_PUBLICATION_AVAILABLE",
    "PARENT_RECORD_ONLY",
    "PROVENANCE_BROKEN",
    "SOURCE_UNIT_MAPPING_MISSING",
    "PropagationDecision",
    "apply_decision",
    "decide_propagation",
]
