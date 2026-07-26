"""Associazioni non sostenute e non risolte.

Sono conservate sul parent, mai promosse a claim, mai esposte al retrieval
primario, sempre auditabili. La distinzione fra le due va conservata perche' e'
una distinzione di stato epistemico, non di gravita': `unsupported` e' una
conclusione — la fonte non sostiene l'associazione — mentre `unresolved` e' una
sospensione — il supporto non e' determinabile con quello che si ha.

Fonderle in un unico stato "scartato" perderebbe l'informazione che serve dopo:
un'associazione non sostenuta e' chiusa, una non risolta si riapre quando arriva
il full text o viene approvato un mapping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION


@dataclass(frozen=True)
class _AssociationBase:
    association_id: str
    parent_id: str
    graph_evidence_id: str
    intervention_literal: str
    biomarker: str
    source_unit_ids: tuple[str, ...] = ()
    locators: tuple[dict[str, Any], ...] = ()
    review_status: str = "not_reviewed"
    provenance: dict[str, Any] = field(default_factory=dict)
    schema_version: str = MODEL_SCHEMA_VERSION

    # Invarianti condivisi: non sono claim, non ricevono punteggio positivo, non
    # escono mai dal bucket di audit.
    audit_only: bool = True
    positive_score_allowed: bool = False

    @property
    def is_claim(self) -> bool:
        return False

    def _base_dict(self) -> dict[str, Any]:
        return {
            "association_id": self.association_id,
            "parent_id": self.parent_id,
            "graph_evidence_id": self.graph_evidence_id,
            "kind": self.kind,
            "is_claim": False,
            "intervention_literal": self.intervention_literal,
            "biomarker": self.biomarker,
            "source_unit_ids": list(self.source_unit_ids),
            "locators": [dict(item) for item in self.locators],
            "review_status": self.review_status,
            "provenance": dict(self.provenance),
            "audit_only": True,
            "positive_score_allowed": False,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class UnsupportedAssociation(_AssociationBase):
    """La fonte non sostiene l'associazione. E' una conclusione."""

    kind: str = "unsupported_association"
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload["reason_codes"] = list(self.reason_codes)
        return payload


@dataclass(frozen=True)
class UnresolvedAssociation(_AssociationBase):
    """Il supporto non e' determinabile. E' una sospensione, non un rifiuto."""

    kind: str = "unresolved_association"
    unresolved_reason_codes: tuple[str, ...] = ()
    terminology_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload["unresolved_reason_codes"] = list(self.unresolved_reason_codes)
        payload["terminology_status"] = self.terminology_status
        return payload
