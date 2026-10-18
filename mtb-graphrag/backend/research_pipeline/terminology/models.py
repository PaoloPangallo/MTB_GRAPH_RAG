from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Domain = Literal["DISEASE", "GENE", "VARIANT", "PROFILE", "INTERVENTION", "TRIAL"]
DOMAINS = frozenset({"DISEASE", "GENE", "VARIANT", "PROFILE", "INTERVENTION", "TRIAL"})
ResolutionStatus = Literal["RESOLVED", "AMBIGUOUS", "UNMAPPED", "INVALID"]


@dataclass(frozen=True)
class SourceRef:
    asset: str
    version: str
    sha256: str
    locator: str


@dataclass(frozen=True)
class Term:
    domain: Domain
    concept_id: str
    label: str
    alias_scope: str
    source: SourceRef
    gene_id: str | None = None
    reference: str | None = None


@dataclass(frozen=True)
class Resolution:
    domain: Domain
    raw_value: str
    status: ResolutionStatus
    method: str
    concept_ids: tuple[str, ...]
    terms: tuple[Term, ...]
    reasons: tuple[str, ...]
    registry_version: str

    def to_dict(self) -> dict:
        return asdict(self)
