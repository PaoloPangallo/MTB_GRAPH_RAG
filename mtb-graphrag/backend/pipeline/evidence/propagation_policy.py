"""Quando un qualificatore source-derived puo' essere usato, e per farci cosa.

Il repository conteneva due domande diverse sotto una sola bandiera. `is_propagatable`
rispondeva a «la coorte e' risolta?», e veniva letto come se rispondesse a «la
revisione autorizza a usare questo valore?». Finche' le due domande hanno la
stessa risposta l'ambiguita' non si vede; smette di non vedersi appena una fonte
a coorte unica non e' ancora stata revisionata da nessuno — e in quel momento un
valore estratto automaticamente diventa indistinguibile da uno confermato da una
persona.

La politica separa **tre** livelli, perche' due non bastano:

- `none` — il valore esiste ma nessuno lo ha confermato: non si mostra come
  qualificatore e non si usa per niente;
- `prototype_only` — una persona lo ha confermato, ma da sola: si puo' mostrare,
  ispezionare e usare in esperimenti dichiarati provvisori, e non si puo' usare
  per escludere evidenza o per una metrica finale;
- `final` — due revisioni concordi, una adjudication o un dossier congelato: si
  puo' usare per filtrare.

La differenza fra `prototype_only` e `final` non e' di grado. Un qualificatore
mostrato che sia sbagliato viene letto da chi puo' accorgersene; un qualificatore
che filtra e sia sbagliato **rimuove** un'evidenza, e nessuno vede cio' che non
compare piu'.

I campi nativi degli EvidenceStatement non sono soggetti a questa politica:
vengono dal grafo congelato, non da una revisione, e bloccarli renderebbe il
sistema meno capace senza renderlo piu' prudente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .profile_unit import (
    ADJUDICATED,
    AWAITING_FIRST_REVIEW,
    AWAITING_SECOND_REVIEW,
    AWAITING_SOURCE_REVIEW,
    COHORT_RESOLVED,
    COHORT_SINGLE,
    DISAGREEMENT,
    FIRST_REVIEW_COMPLETE,
    FROZEN,
    HUMAN_REVIEWED,
    NOT_APPLICABLE,
    REJECTED,
    SECOND_REVIEW_COMPLETE,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
    UNKNOWN,
    UNREVIEWED,
)

POLICY_VERSION = "propagation_policy/1.0"

# --- livelli ------------------------------------------------------------------
NONE = "none"
PROTOTYPE_ONLY = "prototype_only"
FINAL = "final"

ELIGIBILITY_LEVELS = (NONE, PROTOTYPE_ONLY, FINAL)

# Stato di accordo fra prima e seconda revisione. Una seconda revisione che non
# dichiara accordo non promuove: «due revisioni esistono» non e' «due revisioni
# dicono la stessa cosa».
AGREEMENT_AGREED = "agreed"
AGREEMENT_DISAGREED = "disagreed"
AGREEMENT_UNKNOWN = ""


# --- errori tipizzati ---------------------------------------------------------


class PropagationPolicyError(RuntimeError):
    """Violazione della politica di propagazione."""

    rule_id = "propagation_policy"


class UnreviewedPropagationError(PropagationPolicyError):
    """Un valore mai revisionato dichiarato propagabile."""

    rule_id = "unreviewed_is_not_propagatable"


class NonIndependentPropagationError(PropagationPolicyError):
    """Una prima revisione non indipendente dichiarata definitiva."""

    rule_id = "non_independent_is_not_final"


class UnresolvedDisagreementError(PropagationPolicyError):
    """Un disaccordo non adjudicato dichiarato propagabile."""

    rule_id = "disagreement_is_not_propagatable"


class PrototypeHardFilterError(PropagationPolicyError):
    """Un qualificatore prototype-only usato per escludere evidenza."""

    rule_id = "prototype_cannot_hard_filter"


class EvaluabilityError(PropagationPolicyError):
    """Dichiarato valutabile senza un gold che lo copra."""

    rule_id = "not_evaluable_without_gold"


# --- decisione ----------------------------------------------------------------

# Stati che non hanno mai visto una revisione umana.
_UNREVIEWED_STATUSES = frozenset(
    {UNREVIEWED, AWAITING_SOURCE_REVIEW, AWAITING_FIRST_REVIEW, SOURCE_CHECKED_REVIEW_PROPOSAL}
)

# Stati in cui una persona ha deciso una volta sola.
_SINGLE_REVIEW_STATUSES = frozenset({FIRST_REVIEW_COMPLETE, HUMAN_REVIEWED, AWAITING_SECOND_REVIEW})

# Sentinella: non sono valori e non contano come qualificatori propagati.
NON_VALUES = frozenset({"", UNKNOWN, NOT_APPLICABLE, "not_separable"})


@dataclass(frozen=True)
class EligibilityDecision:
    """Il livello assegnato a una unita', con la ragione che lo giustifica."""

    eligibility: str
    reason: str
    is_propagatable: bool
    is_evaluable: bool
    requires_second_independent_review: bool

    @property
    def may_display_qualifiers(self) -> bool:
        """Il qualificatore puo' comparire nella QualifiedEvidenceView?"""
        return self.eligibility in (PROTOTYPE_ONLY, FINAL)

    @property
    def may_hard_filter(self) -> bool:
        """Il qualificatore puo' escludere una evidenza da un risultato?"""
        return self.eligibility == FINAL

    @property
    def may_enter_final_metrics(self) -> bool:
        return self.eligibility == FINAL

    def as_dict(self) -> dict[str, Any]:
        return {
            "propagation_eligibility": self.eligibility,
            "reason": self.reason,
            "is_propagatable": self.is_propagatable,
            "is_evaluable": self.is_evaluable,
            "requires_second_independent_review": self.requires_second_independent_review,
            "may_display_qualifiers": self.may_display_qualifiers,
            "may_hard_filter": self.may_hard_filter,
            "may_enter_final_metrics": self.may_enter_final_metrics,
            "policy_version": POLICY_VERSION,
        }


def decide(
    *,
    review_status: str,
    cohort_state: str = COHORT_SINGLE,
    independent_review: bool = False,
    agreement: str = AGREEMENT_UNKNOWN,
    gold_covered: bool = False,
) -> EligibilityDecision:
    """Il livello di una unita', dai soli fatti della sua revisione.

    La risoluzione della coorte resta necessaria ma non e' piu' sufficiente: una
    coorte irrisolta non propaga nemmeno dopo una adjudication, perche' non si
    saprebbe a quale braccio il valore appartenga.
    """
    status = str(review_status or "")
    cohort_resolved = cohort_state in (COHORT_SINGLE, COHORT_RESOLVED)

    if status == REJECTED:
        return EligibilityDecision(
            NONE, "revisione respinta", False, False, requires_second_independent_review=False
        )

    if status in _UNREVIEWED_STATUSES:
        return EligibilityDecision(
            NONE,
            "nessuna revisione umana: il valore e' estratto o proposto, non confermato",
            False,
            False,
            requires_second_independent_review=True,
        )

    if status == DISAGREEMENT:
        return EligibilityDecision(
            PROTOTYPE_ONLY,
            "disaccordo non adjudicato: visibile, mai usato per filtrare",
            False,
            False,
            requires_second_independent_review=True,
        )

    if status in (ADJUDICATED, FROZEN):
        return EligibilityDecision(
            FINAL if cohort_resolved else PROTOTYPE_ONLY,
            (
                "adjudicato o congelato"
                if cohort_resolved
                else "adjudicato ma la coorte non e' risolta: non si sa a chi si applichi"
            ),
            cohort_resolved,
            cohort_resolved and (gold_covered or status == FROZEN),
            requires_second_independent_review=False,
        )

    if status == SECOND_REVIEW_COMPLETE:
        if agreement != AGREEMENT_AGREED:
            return EligibilityDecision(
                PROTOTYPE_ONLY,
                "seconda revisione senza accordo esplicito: due revisioni non sono due accordi",
                False,
                False,
                requires_second_independent_review=False,
            )
        return EligibilityDecision(
            FINAL if cohort_resolved else PROTOTYPE_ONLY,
            (
                "seconda revisione concordante"
                if cohort_resolved
                else "seconda revisione concordante ma coorte non risolta"
            ),
            cohort_resolved,
            cohort_resolved and gold_covered,
            requires_second_independent_review=False,
        )

    if status in _SINGLE_REVIEW_STATUSES:
        if independent_review and cohort_resolved:
            return EligibilityDecision(
                PROTOTYPE_ONLY,
                (
                    "prima revisione indipendente: resta prototype finche' una seconda "
                    "non la conferma"
                ),
                False,
                False,
                requires_second_independent_review=True,
            )
        return EligibilityDecision(
            PROTOTYPE_ONLY,
            (
                "prima revisione non indipendente: una sola persona, con materiale "
                "preparato da una macchina"
            ),
            False,
            False,
            requires_second_independent_review=True,
        )

    return EligibilityDecision(
        NONE,
        f"stato di revisione non riconosciuto: {status!r}",
        False,
        False,
        requires_second_independent_review=True,
    )


def eligibility_for(unit: Mapping[str, Any]) -> EligibilityDecision:
    """Il livello di un record serializzato."""
    return decide(
        review_status=str(unit.get("review_status") or ""),
        cohort_state=str(unit.get("cohort_state") or COHORT_SINGLE),
        independent_review=bool(unit.get("independent_review")),
        agreement=str(unit.get("agreement_state") or unit.get("agreement") or ""),
        gold_covered=bool(unit.get("gold_covered")),
    )


def propagated_dimensions(unit: Mapping[str, Any], dimensions: Sequence[str]) -> list[str]:
    """Le dimensioni che contano come qualificatori propagati.

    I sentinella non contano. `unknown` non e' un qualificatore: e' l'assenza di
    un qualificatore, e contarlo gonfierebbe la copertura con dei buchi.
    """
    found: list[str] = []
    for dimension in dimensions:
        value = unit.get(dimension)
        if isinstance(value, (list, tuple)):
            if value:
                found.append(dimension)
        elif str(value or "").strip().casefold() not in NON_VALUES:
            found.append(dimension)
    return found


# --- validazione --------------------------------------------------------------


@dataclass(frozen=True)
class PolicyViolation:
    """Una unita' che dichiara piu' di quanto la sua revisione permetta."""

    rule_id: str
    error_type: type[PropagationPolicyError]
    profile_unit_id: str
    declared: str
    expected: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "error_type": self.error_type.__name__,
            "profile_unit_id": self.profile_unit_id,
            "declared": self.declared,
            "expected": self.expected,
            "message": self.message,
        }

    def raise_it(self) -> None:
        raise self.error_type(self.message)


def validate_unit(unit: Mapping[str, Any]) -> list[PolicyViolation]:
    """Confronta cio' che l'unita' dichiara con cio' che la politica permette."""
    decision = eligibility_for(unit)
    unit_id = str(unit.get("profile_unit_id") or unit.get("proposed_profile_unit_id") or "")
    status = str(unit.get("review_status") or "")
    violations: list[PolicyViolation] = []

    declared_propagatable = bool(unit.get("is_propagatable"))
    if declared_propagatable and not decision.is_propagatable:
        if status in _UNREVIEWED_STATUSES:
            error: type[PropagationPolicyError] = UnreviewedPropagationError
        elif status == DISAGREEMENT:
            error = UnresolvedDisagreementError
        else:
            error = NonIndependentPropagationError
        violations.append(
            PolicyViolation(
                error.rule_id,
                error,
                unit_id,
                "is_propagatable=true",
                f"propagation_eligibility={decision.eligibility}",
                (
                    f"{unit_id} dichiara di poter propagare, ma {decision.reason}. "
                    "Propagare significherebbe far filtrare un valore che nessuno ha "
                    "confermato in modo indipendente"
                ),
            )
        )

    declared_eligibility = str(unit.get("propagation_eligibility") or "")
    if declared_eligibility and declared_eligibility != decision.eligibility:
        violations.append(
            PolicyViolation(
                "declared_eligibility_mismatch",
                PropagationPolicyError,
                unit_id,
                f"propagation_eligibility={declared_eligibility}",
                f"propagation_eligibility={decision.eligibility}",
                f"{unit_id} dichiara {declared_eligibility!r} ma la politica assegna "
                f"{decision.eligibility!r}: {decision.reason}",
            )
        )

    if bool(unit.get("is_evaluable")) and not decision.is_evaluable:
        violations.append(
            PolicyViolation(
                EvaluabilityError.rule_id,
                EvaluabilityError,
                unit_id,
                "is_evaluable=true",
                "is_evaluable=false",
                f"{unit_id} e' dichiarata valutabile ma {decision.reason}",
            )
        )

    if bool(unit.get("used_as_hard_filter")) and not decision.may_hard_filter:
        violations.append(
            PolicyViolation(
                PrototypeHardFilterError.rule_id,
                PrototypeHardFilterError,
                unit_id,
                "used_as_hard_filter=true",
                f"propagation_eligibility={decision.eligibility}",
                (
                    f"{unit_id} e' usata per escludere evidenza con eligibility "
                    f"{decision.eligibility}: un filtro sbagliato rimuove cio' che "
                    "nessuno potra' piu' vedere"
                ),
            )
        )

    return violations


def validate_units(units: Sequence[Mapping[str, Any]]) -> list[PolicyViolation]:
    return [violation for unit in units for violation in validate_unit(unit)]


__all__ = [
    "POLICY_VERSION",
    "NONE",
    "PROTOTYPE_ONLY",
    "FINAL",
    "ELIGIBILITY_LEVELS",
    "AGREEMENT_AGREED",
    "AGREEMENT_DISAGREED",
    "PropagationPolicyError",
    "UnreviewedPropagationError",
    "NonIndependentPropagationError",
    "UnresolvedDisagreementError",
    "PrototypeHardFilterError",
    "EvaluabilityError",
    "EligibilityDecision",
    "PolicyViolation",
    "decide",
    "eligibility_for",
    "propagated_dimensions",
    "validate_unit",
    "validate_units",
]
