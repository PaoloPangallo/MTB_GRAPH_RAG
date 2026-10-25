"""DiagnosticClaim e PrognosticClaim.

Sono i due tipi che il modello 1.0 non aveva. Non discendono dai tipi
terapeutici: quelli portano l'intervento, e metterli sotto un nodo che lo
richiede lascerebbe il campo vuoto in una posizione obbligatoria — un invito a
riempirlo col primo farmaco nominato nella fonte, che e' il modo in cui
`evidence:275` era finito ad affermare erlotinib.

`PrognosticClaim` viene implementato e testato ma non istanziato in questa fase:
nessun record del corpus lo sostiene. Una classe senza istanze non e' codice
morto qui — e' il posto dove il prossimo record prognostico andra' a finire, ed
esiste perche' quel record non venga di nuovo costretto in un tipo che non lo
descrive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.pipeline.evidence.shadow.domain import (
    DOMAIN_DIAGNOSTIC,
    DOMAIN_PROGNOSTIC,
)
from backend.pipeline.evidence.shadow.schema import MODEL_SCHEMA_VERSION_V11


class NonTherapeuticClaimError(ValueError):
    """Un claim non terapeutico viola un invariante del proprio tipo."""


DIAGNOSTIC_INTERPRETATIONS = (
    "subtype_defining_alteration",
    "disease_associated_marker",
    "differential_diagnosis_support",
    "diagnostic_exclusion",
    "unknown",
)

PROGNOSTIC_DIRECTIONS = (
    "better_outcome",
    "poor_outcome",
    "no_association",
    "unknown",
)

# Limitazioni che viaggiano col claim invece di restare nel report di revisione.
# Se restassero fuori, il claim uscirebbe piu' forte di quello che la fonte dice.
LIMITATION_CODES = (
    "PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC",
    "CLINICAL_UTILITY_NOT_ASSERTED",
    "ABSTRACT_ONLY_NO_FULL_TEXT",
    "SOURCE_UNIT_AWAITING_HUMAN_REVIEW",
    "OUTCOME_NOT_SEPARATED_BY_TREATMENT",
)


@dataclass(frozen=True)
class _NonTherapeuticClaimBase:
    claim_id: str
    parent_id: str
    graph_evidence_id: str
    biomarker: str
    disease_scope: str
    direction: str
    polarity: str
    source_unit_ids: tuple[str, ...] = ()
    locators: tuple[dict[str, Any], ...] = ()
    qualification_link_ids: tuple[str, ...] = ()
    review_status: str = "not_reviewed"
    propagation_policy: str = "prototype_only"
    provenance: dict[str, Any] = field(default_factory=dict)
    legacy_statement_ids: tuple[str, ...] = ()
    deprecated: bool = False
    schema_version: str = MODEL_SCHEMA_VERSION_V11
    limitation_codes: tuple[str, ...] = ()
    hard_filterable: bool = False
    final_evaluable: bool = False

    @property
    def is_claim(self) -> bool:
        return True

    @property
    def receives_therapy_score(self) -> bool:
        """Mai. Non c'e' terapia a cui attribuire un punteggio."""
        return False

    @property
    def intervention_members(self) -> tuple[str, ...]:
        """Nessun intervento. Non e' un valore mancante: non ce n'e' uno."""
        return ()

    def _base_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "parent_id": self.parent_id,
            "graph_evidence_id": self.graph_evidence_id,
            "claim_domain": self.claim_domain,
            "claim_type": self.claim_type,
            "biomarker": self.biomarker,
            "disease_scope": self.disease_scope,
            "direction": self.direction,
            "polarity": self.polarity,
            "source_unit_ids": list(self.source_unit_ids),
            "locators": [dict(item) for item in self.locators],
            "qualification_link_ids": list(self.qualification_link_ids),
            "review_status": self.review_status,
            "propagation_policy": self.propagation_policy,
            "provenance": dict(self.provenance),
            "legacy_statement_ids": list(self.legacy_statement_ids),
            "deprecated": self.deprecated,
            "schema_version": self.schema_version,
            "limitation_codes": list(self.limitation_codes),
            "hard_filterable": self.hard_filterable,
            "final_evaluable": self.final_evaluable,
            "receives_therapy_score": False,
            "intervention_present": False,
        }


@dataclass(frozen=True)
class DiagnosticClaim(_NonTherapeuticClaimBase):
    """Cosa un biomarcatore identifica, non cosa una terapia ottiene."""

    claim_domain: str = DOMAIN_DIAGNOSTIC
    claim_type: str = "diagnostic_claim"
    diagnostic_subject: str = ""
    diagnostic_interpretation: str = "unknown"
    assay_or_method: str | None = None
    population_or_sample_scope: str | None = None
    # La fonte propone una classificazione: dire che esiste un test validato
    # sarebbe un'affermazione sulla performance, che la fonte non fa.
    clinical_validation_asserted: bool = False
    prevalence_attributable_to_subject: bool = False

    def __post_init__(self) -> None:
        if not self.diagnostic_subject.strip():
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: claim diagnostico senza soggetto"
            )
        if self.diagnostic_interpretation not in DIAGNOSTIC_INTERPRETATIONS:
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: interpretazione diagnostica sconosciuta "
                f"{self.diagnostic_interpretation!r}"
            )
        if self.clinical_validation_asserted:
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: l'utilita' clinica non si deduce dalla presenza "
                "del biomarcatore; va affermata dalla fonte"
            )

    @property
    def canonical_subject(self) -> str:
        return " ".join(self.diagnostic_subject.split()).lower()

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload.update(
            {
                "diagnostic_subject": self.diagnostic_subject,
                "canonical_subject": self.canonical_subject,
                "diagnostic_interpretation": self.diagnostic_interpretation,
                "assay_or_method": self.assay_or_method,
                "population_or_sample_scope": self.population_or_sample_scope,
                "clinical_validation_asserted": False,
                "prevalence_attributable_to_subject": self.prevalence_attributable_to_subject,
            }
        )
        return payload


@dataclass(frozen=True)
class PrognosticClaim(_NonTherapeuticClaimBase):
    """Come va il paziente, non come risponde alla terapia."""

    claim_domain: str = DOMAIN_PROGNOSTIC
    claim_type: str = "prognostic_claim"
    prognostic_subject: str = ""
    outcome: str = ""
    population_scope: str | None = None
    # Le due conversioni che il contratto vieta, rese impossibili invece che
    # sconsigliate.
    predictive_effect_asserted: bool = False
    causality_asserted: bool = False

    def __post_init__(self) -> None:
        if not self.prognostic_subject.strip():
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: claim prognostico senza soggetto"
            )
        if not self.outcome.strip():
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: claim prognostico senza esito; un esito generico "
                "non e' un beneficio di sopravvivenza e va conservato come la fonte "
                "lo nomina"
            )
        if self.direction not in PROGNOSTIC_DIRECTIONS:
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: direzione prognostica sconosciuta {self.direction!r}"
            )
        if self.predictive_effect_asserted:
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: un'associazione prognostica non e' un effetto "
                "predittivo del trattamento"
            )
        if self.causality_asserted:
            raise NonTherapeuticClaimError(
                f"{self.claim_id}: un'associazione osservazionale non stabilisce "
                "una relazione causale"
            )

    @property
    def canonical_subject(self) -> str:
        return " ".join(self.prognostic_subject.split()).lower()

    def to_dict(self) -> dict[str, Any]:
        payload = self._base_dict()
        payload.update(
            {
                "prognostic_subject": self.prognostic_subject,
                "canonical_subject": self.canonical_subject,
                "outcome": self.outcome,
                "population_scope": self.population_scope,
                "predictive_effect_asserted": False,
                "causality_asserted": False,
            }
        )
        return payload


NonTherapeuticClaim = DiagnosticClaim | PrognosticClaim
