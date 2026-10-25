"""Gold dei collegamenti statement-profilo, indipendente dal linker.

Il linker automatico propone candidati. Se quei candidati diventassero il gold,
la valutazione misurerebbe la coerenza del linker con se stesso e restituirebbe
precision 1.000 qualunque cosa il linker faccia. Per questo il gold vive in un
tipo separato, con annotatori dichiarati, e `from_candidate` rifiuta di produrre
uno stato finale.

Il workflow e' quello classico a due annotatori ciechi piu' adjudication.
L'accordo si calcola **solo** dove esistono due annotazioni reali: un accordo
calcolato su un annotatore duplicato e' un numero che descrive una copia.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from ..evidence.profile_unit import UNIT_DIMENSIONS

GOLD_VERSION = "statement_qualification_gold/1.0"

# --- esiti del collegamento ---------------------------------------------------
VALID_LINK = "valid_link"
PARTIAL_LINK = "partial_link"
AMBIGUOUS_LINK = "ambiguous_link"
CONFLICTING_LINK = "conflicting_link"
INVALID_LINK = "invalid_link"
NO_PROFILE_AVAILABLE = "no_profile_available"
SOURCE_MISSING = "source_missing"
INSUFFICIENT_SOURCE_INFORMATION = "insufficient_source_information"

LINK_STATUSES = (
    VALID_LINK,
    PARTIAL_LINK,
    AMBIGUOUS_LINK,
    CONFLICTING_LINK,
    INVALID_LINK,
    NO_PROFILE_AVAILABLE,
    SOURCE_MISSING,
    INSUFFICIENT_SOURCE_INFORMATION,
)

# Stati in cui il collegamento **non** puo' propagare qualificatori.
NON_PROPAGATING_STATUSES = (
    AMBIGUOUS_LINK,
    CONFLICTING_LINK,
    INVALID_LINK,
    NO_PROFILE_AVAILABLE,
    SOURCE_MISSING,
    INSUFFICIENT_SOURCE_INFORMATION,
)

# --- stato del gold -----------------------------------------------------------
GOLD_CANDIDATE = "candidate"
GOLD_FIRST_REVIEW = "first_review_complete"
GOLD_AWAITING_SECOND = "awaiting_second_review"
GOLD_DISAGREEMENT = "disagreement"
GOLD_ADJUDICATED = "adjudicated"
GOLD_FROZEN = "frozen"

GOLD_STATES = (
    GOLD_CANDIDATE,
    GOLD_FIRST_REVIEW,
    GOLD_AWAITING_SECOND,
    GOLD_DISAGREEMENT,
    GOLD_ADJUDICATED,
    GOLD_FROZEN,
)

# Stati in cui il gold e' utilizzabile come riferimento per precision e recall.
EVALUABLE_STATES = (GOLD_ADJUDICATED, GOLD_FROZEN)

# Codici di motivazione ammessi, per rendere confrontabili due annotatori.
RATIONALE_CODES = (
    "same_study_same_cohort",
    "same_study_other_cohort",
    "disease_more_specific_in_statement",
    "disease_more_specific_in_profile",
    "disease_incompatible",
    "intervention_absent_from_study",
    "intervention_partially_overlapping",
    "cohort_not_separable",
    "source_absent_from_snapshot",
    "source_information_insufficient",
    "identifier_only_coincidence",
)


class QualificationGoldError(ValueError):
    """Record di gold non valido."""


@dataclass(frozen=True)
class AnnotationDecision:
    """La decisione di un singolo annotatore, presa in cieco."""

    annotator_id: str
    link_status: str
    applicable_dimensions: tuple[str, ...] = ()
    excluded_dimensions: tuple[str, ...] = ()
    conflict_dimensions: tuple[str, ...] = ()
    ambiguity_dimensions: tuple[str, ...] = ()
    rationale_codes: tuple[str, ...] = ()
    evidence_locators: tuple[str, ...] = ()
    annotated_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.link_status not in LINK_STATUSES:
            raise QualificationGoldError(
                f"link_status non ammesso: {self.link_status!r}. Ammessi: {list(LINK_STATUSES)}"
            )
        if not self.annotator_id:
            raise QualificationGoldError("annotator_id obbligatorio: un gold anonimo non e' verificabile")
        for dimension in self.applicable_dimensions:
            if dimension not in UNIT_DIMENSIONS:
                raise QualificationGoldError(f"dimensione sconosciuta: {dimension!r}")
        for code in self.rationale_codes:
            if code not in RATIONALE_CODES:
                raise QualificationGoldError(f"rationale_code non ammesso: {code!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "annotator_id": self.annotator_id,
            "link_status": self.link_status,
            "applicable_dimensions": list(self.applicable_dimensions),
            "excluded_dimensions": list(self.excluded_dimensions),
            "conflict_dimensions": list(self.conflict_dimensions),
            "ambiguity_dimensions": list(self.ambiguity_dimensions),
            "rationale_codes": list(self.rationale_codes),
            "evidence_locators": list(self.evidence_locators),
            "annotated_at": self.annotated_at,
            "note": self.note,
        }


@dataclass
class StatementQualificationGold:
    """Il verdetto di riferimento su una coppia statement-unita'."""

    gold_link_id: str
    statement_id: str
    profile_unit_id: str
    first_annotation: AnnotationDecision | None = None
    second_annotation: AnnotationDecision | None = None
    adjudicator: str = ""
    adjudication: AnnotationDecision | None = None
    gold_version: str = GOLD_VERSION
    created_at: str = ""
    frozen_at: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not self.gold_link_id:
            raise QualificationGoldError("gold_link_id obbligatorio")
        if self.adjudication is not None and not self.adjudicator:
            raise QualificationGoldError(
                "una adjudication senza adjudicator non e' attribuibile a nessuno"
            )

    # -- derivazioni -----------------------------------------------------------

    @property
    def first_annotator(self) -> str:
        return self.first_annotation.annotator_id if self.first_annotation else ""

    @property
    def second_annotator(self) -> str:
        return self.second_annotation.annotator_id if self.second_annotation else ""

    @property
    def has_two_real_reviews(self) -> bool:
        """Due annotazioni, di due annotatori **diversi**.

        Il controllo sull'identita' non e' pedanteria: e' cio' che impedisce di
        far passare per doppia revisione la stessa annotazione ripetuta, che
        produrrebbe un accordo perfetto privo di significato.
        """
        return (
            self.first_annotation is not None
            and self.second_annotation is not None
            and self.first_annotation.annotator_id != self.second_annotation.annotator_id
        )

    @property
    def agreement(self) -> bool | None:
        """`None` quando l'accordo non e' definito, mai `False` per default."""
        if not self.has_two_real_reviews:
            return None
        assert self.first_annotation and self.second_annotation
        return self.first_annotation.link_status == self.second_annotation.link_status

    @property
    def state(self) -> str:
        if self.adjudication is not None:
            return GOLD_FROZEN if self.frozen_at else GOLD_ADJUDICATED
        if self.has_two_real_reviews:
            return GOLD_ADJUDICATED if self.agreement else GOLD_DISAGREEMENT
        if self.first_annotation is not None:
            return GOLD_AWAITING_SECOND
        return GOLD_CANDIDATE

    @property
    def final_status(self) -> str:
        """Lo stato definitivo, o stringa vuota se non c'e' ancora.

        Deliberatamente vuoto invece che «probabilmente valid_link»: un gold
        provvisorio che espone un verdetto verrebbe usato come se fosse definitivo.
        """
        if self.adjudication is not None:
            return self.adjudication.link_status
        if self.has_two_real_reviews and self.agreement:
            assert self.first_annotation
            return self.first_annotation.link_status
        return ""

    @property
    def is_evaluable(self) -> bool:
        return self.state in EVALUABLE_STATES and bool(self.final_status)

    def final_dimensions(self) -> tuple[str, ...]:
        decision = self.adjudication or (self.first_annotation if self.is_evaluable else None)
        return decision.applicable_dimensions if decision else ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "gold_link_id": self.gold_link_id,
            "statement_id": self.statement_id,
            "profile_unit_id": self.profile_unit_id,
            "link_status": self.final_status,
            "applicable_dimensions": list(self.final_dimensions()),
            "excluded_dimensions": list(
                (self.adjudication or self.first_annotation).excluded_dimensions
                if (self.adjudication or self.first_annotation)
                else ()
            ),
            "conflict_dimensions": list(
                (self.adjudication or self.first_annotation).conflict_dimensions
                if (self.adjudication or self.first_annotation)
                else ()
            ),
            "ambiguity_dimensions": list(
                (self.adjudication or self.first_annotation).ambiguity_dimensions
                if (self.adjudication or self.first_annotation)
                else ()
            ),
            "rationale_codes": list(
                (self.adjudication or self.first_annotation).rationale_codes
                if (self.adjudication or self.first_annotation)
                else ()
            ),
            "evidence_locators": list(
                (self.adjudication or self.first_annotation).evidence_locators
                if (self.adjudication or self.first_annotation)
                else ()
            ),
            "first_annotator": self.first_annotator,
            "first_annotation": self.first_annotation.as_dict() if self.first_annotation else None,
            "second_annotator": self.second_annotator,
            "second_annotation": (
                self.second_annotation.as_dict() if self.second_annotation else None
            ),
            "agreement": self.agreement,
            "adjudicator": self.adjudicator,
            "adjudication": self.adjudication.as_dict() if self.adjudication else None,
            "final_status": self.final_status,
            "state": self.state,
            "is_evaluable": self.is_evaluable,
            "gold_version": self.gold_version,
            "created_at": self.created_at,
            "frozen_at": self.frozen_at,
            "note": self.note,
        }


def gold_link_id(statement_id: str, profile_unit_id: str) -> str:
    digest = hashlib.sha256(f"{statement_id}|{profile_unit_id}".encode("utf-8")).hexdigest()
    return f"GL-{digest[:20]}"


def candidate_from_link(
    statement_id: str,
    profile_unit_id: str,
    *,
    predicted_status: str,
    note: str = "",
) -> StatementQualificationGold:
    """Crea la **traccia** di un candidato, non un gold.

    La prediction del linker viene conservata nella nota, dove e' leggibile ma
    inerte: non popola nessuna annotazione, quindi non puo' diventare per errore
    il riferimento contro cui il linker viene misurato.
    """
    if predicted_status not in LINK_STATUSES:
        raise QualificationGoldError(f"stato predetto non ammesso: {predicted_status!r}")
    return StatementQualificationGold(
        gold_link_id=gold_link_id(statement_id, profile_unit_id),
        statement_id=statement_id,
        profile_unit_id=profile_unit_id,
        note=note or f"candidato proposto dal linker con stato {predicted_status}; nessuna revisione umana",
    )


def agreement_rate(records: Sequence[StatementQualificationGold]) -> tuple[float | None, int]:
    """Accordo grezzo sui soli record con due revisioni reali.

    Restituisce `(None, 0)` quando non ce ne sono: la scelta e' voluta, perche'
    uno 0.0 verrebbe letto come «gli annotatori non sono mai d'accordo» invece
    che «non esistono due annotatori».
    """
    evaluable = [record for record in records if record.has_two_real_reviews]
    if not evaluable:
        return None, 0
    agreed = sum(1 for record in evaluable if record.agreement)
    return agreed / len(evaluable), len(evaluable)


def validate_gold(records: Iterable[StatementQualificationGold]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for record in records:
        if record.gold_link_id in seen:
            problems.append(f"gold_link_id duplicato: {record.gold_link_id}")
        seen.add(record.gold_link_id)
        if record.frozen_at and record.adjudication is None and not record.agreement:
            problems.append(
                f"{record.gold_link_id}: congelato senza adjudication e senza accordo"
            )
        if record.has_two_real_reviews is False and record.second_annotation is not None:
            problems.append(
                f"{record.gold_link_id}: seconda annotazione dello stesso annotatore della prima"
            )
    return problems


__all__ = [
    "GOLD_VERSION",
    "LINK_STATUSES",
    "NON_PROPAGATING_STATUSES",
    "VALID_LINK",
    "PARTIAL_LINK",
    "AMBIGUOUS_LINK",
    "CONFLICTING_LINK",
    "INVALID_LINK",
    "NO_PROFILE_AVAILABLE",
    "SOURCE_MISSING",
    "INSUFFICIENT_SOURCE_INFORMATION",
    "GOLD_STATES",
    "EVALUABLE_STATES",
    "GOLD_CANDIDATE",
    "GOLD_FIRST_REVIEW",
    "GOLD_AWAITING_SECOND",
    "GOLD_DISAGREEMENT",
    "GOLD_ADJUDICATED",
    "GOLD_FROZEN",
    "RATIONALE_CODES",
    "QualificationGoldError",
    "AnnotationDecision",
    "StatementQualificationGold",
    "gold_link_id",
    "candidate_from_link",
    "agreement_rate",
    "validate_gold",
]
