"""I tre tipi di claim.

Sono tipi separati e non varianti di un unico record con un campo `kind`, perche'
le tre cose si comportano diversamente al momento del match e la differenza deve
sopravvivere fino all'output. Un aggregato appiattito sul primo membro e un
regime reso come farmaco singolo sono lo stesso errore che il modello esiste per
eliminare, ricreato nel formato di uscita.

`AtomicInterventionClaim` attribuisce un risultato a un intervento.
`AggregateInterventionClaim` lo attribuisce a una classe o a un insieme non
separabile: i membri letterali restano leggibili, ma non diventano claim atomici.
`RegimenClaim` lo attribuisce a una combinazione: l'ordine dei componenti non
conta per l'identita', e il risultato non si propaga ai componenti.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

from backend.pipeline.evidence.shadow.identity import canonical_regimen
from backend.pipeline.evidence.shadow.schema import (
    AGGREGATE_TYPES,
    MODEL_SCHEMA_VERSION,
)


class ClaimModelError(ValueError):
    """Un claim viola un invariante del proprio tipo."""


@dataclass(frozen=True)
class _ClaimBase:
    claim_id: str
    parent_id: str
    graph_evidence_id: str
    biomarker: str
    disease_scope: str
    direction: str
    polarity: str
    source_unit_ids: tuple[str, ...] = ()
    locators: tuple[dict[str, Any], ...] = ()
    review_status: str = "not_reviewed"
    provenance: dict[str, Any] = field(default_factory=dict)
    evidence_setting: str | None = None
    deprecated: bool = False
    schema_version: str = MODEL_SCHEMA_VERSION

    @property
    def is_claim(self) -> bool:
        return True

    def _base_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "parent_id": self.parent_id,
            "graph_evidence_id": self.graph_evidence_id,
            "claim_type": self.claim_type,
            "biomarker": self.biomarker,
            "disease_scope": self.disease_scope,
            "direction": self.direction,
            "polarity": self.polarity,
            "source_unit_ids": list(self.source_unit_ids),
            "locators": [dict(item) for item in self.locators],
            "review_status": self.review_status,
            "provenance": dict(self.provenance),
            "evidence_setting": self.evidence_setting,
            "deprecated": self.deprecated,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class AtomicInterventionClaim(_ClaimBase):
    """Un risultato attribuito a un singolo intervento."""

    claim_type: str = "atomic_intervention_claim"
    intervention: str = ""
    qualification_link_ids: tuple[str, ...] = ()
    propagation_policy: str = "prototype_only"
    legacy_statement_ids: tuple[str, ...] = ()
    migration_origin: str | None = None
    documentary_revalidation_completed: bool = False
    warnings: tuple[str, ...] = ()
    mapping_pending: bool = False

    def __post_init__(self) -> None:
        if not self.intervention.strip():
            raise ClaimModelError(f"{self.claim_id}: claim atomico senza intervento")

    @property
    def canonical_intervention(self) -> str:
        return " ".join(self.intervention.split())

    @property
    def intervention_members(self) -> tuple[str, ...]:
        return (self.canonical_intervention,)

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload.update(
            {
                "intervention": self.intervention,
                "canonical_intervention": self.canonical_intervention,
                "qualification_link_ids": list(self.qualification_link_ids),
                "propagation_policy": self.propagation_policy,
                "legacy_statement_ids": list(self.legacy_statement_ids),
                "migration_origin": self.migration_origin,
                "documentary_revalidation_completed": self.documentary_revalidation_completed,
                "warnings": list(self.warnings),
                "mapping_pending": self.mapping_pending,
            }
        )
        return payload


@dataclass(frozen=True)
class AggregateInterventionClaim(_ClaimBase):
    """Un risultato attribuito a una classe o a un insieme non separabile.

    `aggregate_members_literal` conserva i termini come la fonte li nomina. Non
    e' una lista di candidati da atomizzare: `permits_member_specific_claims`
    resta falso, e generare claim atomici dai membri rifarebbe l'inferenza
    rifiutata in evidence:275.
    """

    claim_type: str = "aggregate_intervention_claim"
    aggregate_type: str = "other"
    aggregate_label: str = ""
    aggregate_members_literal: tuple[str, ...] = ()
    permits_member_specific_claims: bool = False
    migration_origin: str | None = None

    def __post_init__(self) -> None:
        if self.aggregate_type not in AGGREGATE_TYPES:
            raise ClaimModelError(
                f"{self.claim_id}: aggregate_type sconosciuto {self.aggregate_type!r}"
            )
        if not self.aggregate_label.strip():
            raise ClaimModelError(f"{self.claim_id}: aggregato senza etichetta")
        if self.permits_member_specific_claims:
            raise ClaimModelError(
                f"{self.claim_id}: un aggregato non autorizza claim per membro"
            )

    @property
    def canonical_intervention(self) -> str:
        return " ".join(self.aggregate_label.split()).lower()

    @property
    def intervention_members(self) -> tuple[str, ...]:
        """Cosa il match strutturale confronta, e dipende dal tipo di aggregato.

        Per una classe il confronto e' con l'etichetta della classe: la query
        chiede `EGFR tyrosine kinase inhibitor`, non i suoi membri, e la
        relazione farmaco-classe resta non verificata. Per un insieme non
        separabile il confronto e' con i membri letterali, perche' un farmaco
        nominato dentro l'insieme *e'* raggiungibile — solo che il risultato non
        gli e' attribuibile, ed e' per questo che finisce in warning e non in
        primario.
        """
        if self.aggregate_type == "intervention_class":
            return (self.aggregate_label,)
        return self.aggregate_members_literal or (self.aggregate_label,)

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload.update(
            {
                "aggregate_type": self.aggregate_type,
                "aggregate_label": self.aggregate_label,
                "aggregate_members_literal": list(self.aggregate_members_literal),
                "permits_member_specific_claims": False,
                "canonical_intervention": self.canonical_intervention,
                "migration_origin": self.migration_origin,
            }
        )
        return payload


@dataclass(frozen=True)
class RegimenClaim(_ClaimBase):
    """Un risultato attribuito a una combinazione di interventi."""

    claim_type: str = "regimen_claim"
    regimen_components: tuple[str, ...] = ()
    migration_origin: str | None = None

    def __post_init__(self) -> None:
        if len(self.regimen_components) < 2:
            raise ClaimModelError(
                f"{self.claim_id}: un regime richiede almeno due componenti"
            )

    @property
    def canonical_component_set(self) -> tuple[str, ...]:
        """Insieme canonico: ordinato, quindi indipendente dall'ordine di scrittura."""
        return tuple(sorted(" ".join(c.split()) for c in self.regimen_components))

    @property
    def canonical_intervention(self) -> str:
        return canonical_regimen(self.regimen_components)

    @property
    def intervention_members(self) -> tuple[str, ...]:
        return self.canonical_component_set

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload.update(
            {
                "regimen_components": list(self.regimen_components),
                "canonical_component_set": list(self.canonical_component_set),
                "canonical_intervention": self.canonical_intervention,
                "propagates_to_components": False,
                "migration_origin": self.migration_origin,
            }
        )
        return payload


TypedClaim = Union[AtomicInterventionClaim, AggregateInterventionClaim, RegimenClaim]
