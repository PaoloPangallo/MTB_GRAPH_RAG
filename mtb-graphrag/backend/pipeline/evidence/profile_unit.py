"""Unita' di annotazione di una fonte clinica.

`SourceClinicalProfile` assume implicitamente **una pubblicazione = un profilo**.
L'assunzione regge finche' la fonte descrive un solo braccio; smette di reggere
appena descrive due coorti con linee di terapia diverse, che e' il caso normale
in oncologia. Con un profilo solo, i qualificatori delle due coorti si fondono e
lo statement di una eredita' il setting dell'altra — un errore invisibile, perche'
il risultato resta un profilo sintatticamente valido.

`SourceClinicalProfileUnit` scioglie l'assunzione: l'unita' e' la coorte, non la
pubblicazione. Una fonte a braccio unico ha esattamente una unita', quindi il
caso semplice non paga il costo del caso complesso.

Quando le coorti esistono ma i dati disponibili non permettono di separarle,
l'unita' resta **irrisolta**: non si sceglie una coorte a caso e non si fondono i
qualificatori. Un qualificatore mancante blocca un filtro; un qualificatore
sbagliato produce una raccomandazione applicata al paziente sbagliato.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..evidence.source_identity import SourceIdentity

PROFILE_UNIT_VERSION = "source_clinical_profile_unit/1.0"

# --- stati di estrazione ------------------------------------------------------
UNREVIEWED = "unreviewed"
MACHINE_EXTRACTED = "machine_extracted"
SOURCE_CHECKED = "source_checked"
EXTRACTION_STATUSES = (UNREVIEWED, MACHINE_EXTRACTED, SOURCE_CHECKED)

# --- stati di revisione -------------------------------------------------------
AWAITING_FIRST_REVIEW = "awaiting_first_review"
FIRST_REVIEW_COMPLETE = "first_review_complete"
AWAITING_SECOND_REVIEW = "awaiting_second_review"
SECOND_REVIEW_COMPLETE = "second_review_complete"
DISAGREEMENT = "disagreement"
ADJUDICATED = "adjudicated"
FROZEN = "frozen"
REJECTED = "rejected"
AWAITING_SOURCE_REVIEW = "awaiting_source_review"
HUMAN_REVIEWED = "human_reviewed"

REVIEW_STATUSES = (
    UNREVIEWED,
    AWAITING_SOURCE_REVIEW,
    AWAITING_FIRST_REVIEW,
    FIRST_REVIEW_COMPLETE,
    AWAITING_SECOND_REVIEW,
    SECOND_REVIEW_COMPLETE,
    DISAGREEMENT,
    ADJUDICATED,
    FROZEN,
    REJECTED,
    HUMAN_REVIEWED,
)

# Stati che soltanto una decisione umana tracciabile puo' assegnare. Un processo
# automatico che li scrivesse trasformerebbe la propria estrazione in gold, che e'
# esattamente la circolarita' che il corpus esiste per evitare.
HUMAN_ONLY_STATUSES = (
    FIRST_REVIEW_COMPLETE,
    SECOND_REVIEW_COMPLETE,
    ADJUDICATED,
    FROZEN,
    HUMAN_REVIEWED,
)

# --- risoluzione della coorte -------------------------------------------------
COHORT_SINGLE = "single_cohort"
COHORT_RESOLVED = "resolved_cohort"
COHORT_UNRESOLVED = "unresolved_cohort"
COHORT_CANDIDATE = "candidate_cohort"
# Una unita' che una revisione ha sostituito con piu' unita' derivate. Resta nel
# repository come record storico — i link e le metriche prodotti prima della
# revisione la citano, e cancellarla renderebbe illeggibile la loro storia — ma
# non puo' piu' propagare nulla.
COHORT_SUPERSEDED = "superseded_by_reviewed_split"
COHORT_STATES = (
    COHORT_SINGLE,
    COHORT_RESOLVED,
    COHORT_UNRESOLVED,
    COHORT_CANDIDATE,
    COHORT_SUPERSEDED,
)

# Che cosa descrive l'unita'. La distinzione clinico/preclinico non e' una
# etichetta descrittiva: e' cio' che impedisce a una popolazione di pazienti di
# qualificare un esperimento su linee cellulari, e viceversa.
UNIT_TYPE_CLINICAL_COHORT = "clinical_observational_cohort"
UNIT_TYPE_CLINICAL_TRIAL_ARM = "clinical_trial_arm"
UNIT_TYPE_PRECLINICAL = "preclinical_in_vitro"
UNIT_TYPE_PRECLINICAL_COMPARATIVE = "preclinical_in_vitro_comparative_pharmacology"
UNIT_TYPE_UNSPECIFIED = "unspecified"
UNIT_TYPES = (
    UNIT_TYPE_CLINICAL_COHORT,
    UNIT_TYPE_CLINICAL_TRIAL_ARM,
    UNIT_TYPE_PRECLINICAL,
    UNIT_TYPE_PRECLINICAL_COMPARATIVE,
    UNIT_TYPE_UNSPECIFIED,
)

CLINICAL_UNIT_TYPES = (UNIT_TYPE_CLINICAL_COHORT, UNIT_TYPE_CLINICAL_TRIAL_ARM)
PRECLINICAL_UNIT_TYPES = (UNIT_TYPE_PRECLINICAL, UNIT_TYPE_PRECLINICAL_COMPARATIVE)

# Dimensioni cliniche che l'unita' puo' portare. Coincidono con quelle che il
# grafo congelato non modella: e' il motivo per cui il corpus esiste.
UNIT_DIMENSIONS = (
    "disease",
    "biomarker_requirements",
    "intervention",
    "regimen",
    "comparator",
    "population",
    "stage",
    "setting",
    "therapy_line",
    "prior_therapies",
    "resection_status",
    "inclusion_criteria",
    "exclusion_criteria",
    "evidence_design",
)

UNKNOWN = "unknown"

# Distinto da `unknown`, e la distinzione porta informazione. `unknown` dice che
# non sappiamo il valore; `not_applicable` dice che la domanda non si pone —
# chiedere la linea di terapia di un esperimento su linee cellulari non ha
# risposta, e registrarlo come `unknown` suggerirebbe che qualcuno debba ancora
# cercarla. Nessuno dei due conta come dimensione nota.
NOT_APPLICABLE = "not_applicable"
NON_VALUES = (UNKNOWN, NOT_APPLICABLE, "")


class ProfileUnitError(ValueError):
    """Unita' di profilo non valida."""


@dataclass(frozen=True)
class FieldProvenance:
    """Da dove viene un singolo valore, e chi lo ha asserito.

    La provenienza e' per campo e non per unita': in una stessa unita' il disegno
    dello studio puo' venire dal registro e la linea di terapia da un revisore.
    Attribuirle alla stessa fonte renderebbe impossibile sapere che cosa e' stato
    davvero verificato.
    """

    field_name: str
    value_origin: str
    source_locator: str = ""
    access_date: str = ""
    asserted_by: str = ""
    span_hash: str = ""
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "value_origin": self.value_origin,
            "source_locator": self.source_locator,
            "access_date": self.access_date,
            "asserted_by": self.asserted_by,
            "span_hash": self.span_hash,
            "note": self.note,
        }


@dataclass
class SourceClinicalProfileUnit:
    """Una coorte, o il braccio unico di una fonte a braccio unico."""

    profile_unit_id: str
    canonical_source_id: str
    source_profile_id: str = ""
    pmids: tuple[str, ...] = ()
    dois: tuple[str, ...] = ()
    ncts: tuple[str, ...] = ()
    title: str = ""
    cohort_id: str = "cohort-1"
    cohort_label: str = ""
    cohort_state: str = COHORT_SINGLE
    cohort_note: str = ""

    disease: str = UNKNOWN
    biomarker_requirements: tuple[str, ...] = ()
    intervention: tuple[str, ...] = ()
    regimen: str = UNKNOWN
    comparator: str = UNKNOWN
    population: str = UNKNOWN
    stage: str = UNKNOWN
    setting: str = UNKNOWN
    therapy_line: str = UNKNOWN
    prior_therapies: tuple[str, ...] = ()
    resection_status: str = UNKNOWN
    inclusion_criteria: str = UNKNOWN
    exclusion_criteria: str = UNKNOWN
    evidence_design: str = UNKNOWN

    unit_type: str = UNIT_TYPE_UNSPECIFIED
    superseded_by: tuple[str, ...] = ()
    supersedes: str = ""
    field_decisions: Mapping[str, str] = field(default_factory=dict)

    statement_ids: tuple[str, ...] = ()
    source_spans: tuple[str, ...] = ()
    extraction_status: str = UNREVIEWED
    review_status: str = AWAITING_SOURCE_REVIEW
    reviewer: str = ""
    requires_human_review: bool = True
    human_review_reasons: tuple[str, ...] = ()
    provenance: tuple[FieldProvenance, ...] = ()
    blind_annotation_id: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.extraction_status not in EXTRACTION_STATUSES:
            raise ProfileUnitError(
                f"extraction_status non ammesso: {self.extraction_status!r}. "
                f"Ammessi: {list(EXTRACTION_STATUSES)}"
            )
        if self.review_status not in REVIEW_STATUSES:
            raise ProfileUnitError(
                f"review_status non ammesso: {self.review_status!r}. "
                f"Ammessi: {list(REVIEW_STATUSES)}"
            )
        if self.cohort_state not in COHORT_STATES:
            raise ProfileUnitError(
                f"cohort_state non ammesso: {self.cohort_state!r}. Ammessi: {list(COHORT_STATES)}"
            )
        if self.unit_type not in UNIT_TYPES:
            raise ProfileUnitError(
                f"unit_type non ammesso: {self.unit_type!r}. Ammessi: {list(UNIT_TYPES)}"
            )
        if not self.profile_unit_id:
            raise ProfileUnitError("profile_unit_id obbligatorio")

    # -- interrogazione --------------------------------------------------------

    def known_dimensions(self) -> tuple[str, ...]:
        """Dimensioni con un valore diverso da `unknown` o vuoto."""
        found: list[str] = []
        for dimension in UNIT_DIMENSIONS:
            value = getattr(self, dimension, None)
            if isinstance(value, (tuple, list)):
                if value:
                    found.append(dimension)
            elif value not in NON_VALUES:
                found.append(dimension)
        return tuple(found)

    def provenance_for(self, dimension: str) -> FieldProvenance | None:
        for item in self.provenance:
            if item.field_name == dimension:
                return item
        return None

    def provenance_complete(self) -> bool:
        """Ogni dimensione nota ha una provenienza dichiarata?

        E' l'invariante che rende il corpus verificabile: un valore senza
        provenienza non e' distinguibile da un valore inventato.
        """
        return all(self.provenance_for(dimension) is not None for dimension in self.known_dimensions())

    def missing_provenance(self) -> tuple[str, ...]:
        return tuple(
            dimension
            for dimension in self.known_dimensions()
            if self.provenance_for(dimension) is None
        )

    @property
    def is_propagatable(self) -> bool:
        """L'unita' puo' propagare qualificatori su uno statement?

        No, se la coorte non e' risolta. Una fonte con due coorti indistinguibili
        non sa a quale dei due bracci lo statement appartenga, e propagare
        significherebbe scegliere a caso.
        """
        return self.cohort_state in (COHORT_SINGLE, COHORT_RESOLVED)

    @property
    def is_clinical(self) -> bool:
        return self.unit_type in CLINICAL_UNIT_TYPES

    @property
    def is_preclinical(self) -> bool:
        return self.unit_type in PRECLINICAL_UNIT_TYPES

    def not_applicable_dimensions(self) -> tuple[str, ...]:
        return tuple(
            dimension
            for dimension in UNIT_DIMENSIONS
            if getattr(self, dimension, None) == NOT_APPLICABLE
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_unit_id": self.profile_unit_id,
            "canonical_source_id": self.canonical_source_id,
            "source_profile_id": self.source_profile_id,
            "pmids": list(self.pmids),
            "dois": list(self.dois),
            "ncts": list(self.ncts),
            "title": self.title,
            "cohort_id": self.cohort_id,
            "cohort_label": self.cohort_label,
            "cohort_state": self.cohort_state,
            "cohort_note": self.cohort_note,
            "unit_type": self.unit_type,
            "superseded_by": list(self.superseded_by),
            "supersedes": self.supersedes,
            "field_decisions": dict(self.field_decisions),
            "disease": self.disease,
            "biomarker_requirements": list(self.biomarker_requirements),
            "intervention": list(self.intervention),
            "regimen": self.regimen,
            "comparator": self.comparator,
            "population": self.population,
            "stage": self.stage,
            "setting": self.setting,
            "therapy_line": self.therapy_line,
            "prior_therapies": list(self.prior_therapies),
            "resection_status": self.resection_status,
            "inclusion_criteria": self.inclusion_criteria,
            "exclusion_criteria": self.exclusion_criteria,
            "evidence_design": self.evidence_design,
            "statement_ids": list(self.statement_ids),
            "source_spans": list(self.source_spans),
            "extraction_status": self.extraction_status,
            "review_status": self.review_status,
            "reviewer": self.reviewer,
            "requires_human_review": self.requires_human_review,
            "human_review_reasons": list(self.human_review_reasons),
            "provenance": [item.as_dict() for item in self.provenance],
            "known_dimensions": list(self.known_dimensions()),
            "not_applicable_dimensions": list(self.not_applicable_dimensions()),
            "is_propagatable": self.is_propagatable,
            "is_clinical": self.is_clinical,
            "is_preclinical": self.is_preclinical,
            "blind_annotation_id": self.blind_annotation_id,
            "created_at": self.created_at,
            "schema_version": PROFILE_UNIT_VERSION,
        }


def unit_id(canonical_source_id: str, cohort_id: str) -> str:
    """Identita' deterministica dell'unita': fonte piu' coorte."""
    return f"PU-{canonical_source_id.replace(':', '-')}-{cohort_id}"


def blind_id(canonical_source_id: str, cohort_id: str) -> str:
    """Identificatore cieco per l'annotazione.

    L'annotatore non deve poter risalire dalla stringa a quanto quella fonte
    conta per il sistema: un id che contenesse il PMID o lo strato renderebbe
    visibile proprio cio' che va nascosto.
    """
    digest = hashlib.sha256(f"{canonical_source_id}|{cohort_id}".encode("utf-8")).hexdigest()
    return f"BA-{digest[:16]}"


def from_reviewed_profile(
    profile: Any,
    *,
    canonical_source_id: str,
    statement_ids: Sequence[str] = (),
) -> SourceClinicalProfileUnit:
    """Converte un `SourceClinicalProfile` gia' revisionato in una unita'.

    Lo stato di revisione umano viene **conservato**, non ricalcolato: quei
    profili sono stati letti da una persona e declassarli a `machine_extracted`
    perderebbe l'unica revisione reale che il corpus possiede.
    """
    cohort_id = "cohort-1"
    provenance = tuple(
        FieldProvenance(
            field_name=dimension,
            value_origin="reviewed_source_profile",
            source_locator=f"profile:{getattr(profile, 'source_id', '')}",
            asserted_by=getattr(profile, "reviewer", "") or "human_annotator",
            note="valore dell'annotazione umana preesistente",
        )
        for dimension in _reviewed_known_dimensions(profile)
    )
    return SourceClinicalProfileUnit(
        profile_unit_id=unit_id(canonical_source_id, cohort_id),
        canonical_source_id=canonical_source_id,
        source_profile_id=getattr(profile, "source_id", ""),
        pmids=tuple(x for x in (getattr(profile, "pmid", ""),) if x),
        ncts=tuple(getattr(profile, "nct_ids", ()) or ()),
        title=getattr(profile, "title", "") or "",
        cohort_id=cohort_id,
        cohort_state=COHORT_SINGLE,
        disease=getattr(profile, "disease", "") or UNKNOWN,
        biomarker_requirements=tuple(getattr(profile, "biomarker_requirements", ()) or ()),
        intervention=tuple(getattr(profile, "interventions", ()) or ()),
        regimen=getattr(profile, "regimen", "") or UNKNOWN,
        population=getattr(profile, "population", "") or UNKNOWN,
        stage=getattr(profile, "stage", "") or UNKNOWN,
        setting=getattr(profile, "setting", "") or UNKNOWN,
        therapy_line=getattr(profile, "therapy_line", "") or UNKNOWN,
        prior_therapies=tuple(getattr(profile, "prior_therapies", ()) or ()),
        inclusion_criteria=getattr(profile, "inclusion_criteria_summary", "") or UNKNOWN,
        exclusion_criteria=getattr(profile, "exclusion_criteria_summary", "") or UNKNOWN,
        statement_ids=tuple(sorted(statement_ids)),
        source_spans=tuple(getattr(profile, "source_spans", ()) or ()),
        extraction_status=SOURCE_CHECKED,
        review_status=HUMAN_REVIEWED,
        reviewer=getattr(profile, "reviewer", "") or "",
        requires_human_review=False,
        provenance=provenance,
        blind_annotation_id=blind_id(canonical_source_id, cohort_id),
        created_at=getattr(profile, "created_at", "") or "",
    )


def _reviewed_known_dimensions(profile: Any) -> tuple[str, ...]:
    mapping = {
        "disease": "disease",
        "biomarker_requirements": "biomarker_requirements",
        "intervention": "interventions",
        "regimen": "regimen",
        "population": "population",
        "stage": "stage",
        "setting": "setting",
        "therapy_line": "therapy_line",
        "prior_therapies": "prior_therapies",
        "inclusion_criteria": "inclusion_criteria_summary",
        "exclusion_criteria": "exclusion_criteria_summary",
    }
    found: list[str] = []
    for dimension, attribute in mapping.items():
        value = getattr(profile, attribute, None)
        if isinstance(value, (tuple, list)):
            if value:
                found.append(dimension)
        elif value:
            found.append(dimension)
    return tuple(found)


def validate_units(units: Iterable[SourceClinicalProfileUnit]) -> list[str]:
    """Invarianti che nessuna unita' puo' violare."""
    problems: list[str] = []
    seen: set[str] = set()
    for unit in units:
        if unit.profile_unit_id in seen:
            problems.append(f"profile_unit_id duplicato: {unit.profile_unit_id}")
        seen.add(unit.profile_unit_id)

        missing = unit.missing_provenance()
        if missing:
            problems.append(
                f"{unit.profile_unit_id}: dimensioni note senza provenance: {list(missing)}"
            )
        if unit.review_status in HUMAN_ONLY_STATUSES and unit.extraction_status == MACHINE_EXTRACTED:
            problems.append(
                f"{unit.profile_unit_id}: stato umano {unit.review_status!r} su una unita' "
                "solo machine_extracted"
            )
        if unit.cohort_state == COHORT_UNRESOLVED and not unit.requires_human_review:
            problems.append(
                f"{unit.profile_unit_id}: coorte irrisolta ma non marcata requires_human_review"
            )
    return problems


__all__ = [
    "PROFILE_UNIT_VERSION",
    "UNKNOWN",
    "UNIT_DIMENSIONS",
    "EXTRACTION_STATUSES",
    "REVIEW_STATUSES",
    "HUMAN_ONLY_STATUSES",
    "COHORT_STATES",
    "COHORT_SINGLE",
    "COHORT_RESOLVED",
    "COHORT_UNRESOLVED",
    "COHORT_CANDIDATE",
    "COHORT_SUPERSEDED",
    "NOT_APPLICABLE",
    "NON_VALUES",
    "UNIT_TYPES",
    "UNIT_TYPE_CLINICAL_COHORT",
    "UNIT_TYPE_CLINICAL_TRIAL_ARM",
    "UNIT_TYPE_PRECLINICAL",
    "UNIT_TYPE_PRECLINICAL_COMPARATIVE",
    "UNIT_TYPE_UNSPECIFIED",
    "CLINICAL_UNIT_TYPES",
    "PRECLINICAL_UNIT_TYPES",
    "UNREVIEWED",
    "MACHINE_EXTRACTED",
    "SOURCE_CHECKED",
    "AWAITING_SOURCE_REVIEW",
    "AWAITING_FIRST_REVIEW",
    "FIRST_REVIEW_COMPLETE",
    "AWAITING_SECOND_REVIEW",
    "SECOND_REVIEW_COMPLETE",
    "DISAGREEMENT",
    "ADJUDICATED",
    "FROZEN",
    "REJECTED",
    "HUMAN_REVIEWED",
    "ProfileUnitError",
    "FieldProvenance",
    "SourceClinicalProfileUnit",
    "unit_id",
    "blind_id",
    "from_reviewed_profile",
    "validate_units",
]
