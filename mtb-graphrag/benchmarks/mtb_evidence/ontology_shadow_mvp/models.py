"""Small immutable data model for the research-only ontology shadow."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


ENTITY_TYPES = {"disease", "gene", "variant", "intervention", "diagnostic"}
MATCH_TYPES = {
    "EXACT",
    "SYNONYM",
    "DESCENDANT",
    "ANCESTOR",
    "CLASS_MATCH",
    "RELATED",
    "INCOMPATIBLE",
    "UNKNOWN",
}


@dataclass
class OntologyConcept:
    registry_key: str
    canonical_id: str | None
    label: str
    entity_type: str
    synonyms: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    source: str = ""
    version: str | None = None
    relation_kinds: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"unsupported entity_type: {self.entity_type}")


@dataclass
class OntologyMatch:
    query_value: str
    claim_value: str
    query_concept_id: str | None
    claim_concept_id: str | None
    match_type: str
    distance: int | None
    path: list[str]
    compatible_candidate: bool
    explanation: str
    confidence: str
    query_registry_key: str | None = None
    claim_registry_key: str | None = None

    def __post_init__(self) -> None:
        if self.match_type not in MATCH_TYPES:
            raise ValueError(f"unsupported match_type: {self.match_type}")
        if self.confidence not in {"high", "medium", "low"}:
            raise ValueError(f"unsupported confidence: {self.confidence}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
