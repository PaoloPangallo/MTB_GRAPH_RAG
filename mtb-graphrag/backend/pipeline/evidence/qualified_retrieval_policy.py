"""Che cosa un qualificatore puo' fare, in funzione di chi lo ha confermato.

Il modulo esiste per rendere impossibile una cosa sola:

    qualifier eligibility != final
    → qualifier cannot exclude an EvidenceStatement

Scriverla come commento la lascerebbe vera finche' qualcuno se la ricorda.
`assert_may_hard_filter` la rende un errore nel punto d'uso, e
`hard_filter_allowed` la rende una domanda che si puo' fare prima.

Tre livelli, e la distinzione fra il secondo e il terzo non e' di grado. Un
qualificatore mostrato che sia sbagliato viene letto da chi puo' accorgersene; un
qualificatore che filtri e sia sbagliato **rimuove** una evidenza, e nessuno vede
cio' che non compare piu'.

I campi nativi degli EvidenceStatement non passano di qui. Vengono dal grafo
congelato e non da una revisione: sottoporli a questa politica renderebbe il
sistema meno capace senza renderlo piu' prudente.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .profile_unit import NOT_APPLICABLE, UNKNOWN
from .propagation_policy import FINAL, NONE, PROTOTYPE_ONLY
from .qualified_retrieval_errors import PrototypeQualifierAsHardFilterError

POLICY_VERSION = "qualified_retrieval_policy/1.0"

NOT_SEPARABLE = "not_separable"

# Le tre assenze. Non sono sinonimi, e il retriever le tratta diversamente:
# `unknown` non sappiamo, `not_applicable` la domanda non si pone,
# `not_separable` la fonte conferma i componenti e non la loro relazione.
SENTINELS = (UNKNOWN, NOT_APPLICABLE, NOT_SEPARABLE)

# --- che cosa un livello permette ---------------------------------------------
CONTRIBUTION_NONE = "none"
CONTRIBUTION_NEUTRAL = "neutral"
CONTRIBUTION_CAPPED = "capped"
CONTRIBUTION_FULL = "full"

# --- codici di trattamento ----------------------------------------------------
TREAT_SCORE = "score"
TREAT_WARN = "warn"
TREAT_EXCLUDE_FROM_SCORE = "exclude_from_score"
TREAT_SHOW_AS_UNREVIEWED = "show_as_unreviewed"


@dataclass(frozen=True)
class QualifierPermission:
    """Che cosa e' lecito fare con un qualificatore, e perche'."""

    eligibility: str
    may_display: bool
    may_score: bool
    may_hard_filter: bool
    contribution: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "propagation_eligibility": self.eligibility,
            "may_display": self.may_display,
            "may_score": self.may_score,
            "may_hard_filter": self.may_hard_filter,
            "contribution": self.contribution,
            "reason": self.reason,
        }


_PERMISSIONS: Mapping[str, QualifierPermission] = {
    NONE: QualifierPermission(
        eligibility=NONE,
        may_display=True,
        may_score=False,
        may_hard_filter=False,
        contribution=CONTRIBUTION_NONE,
        reason=(
            "nessuna revisione umana: il valore e' estratto o proposto, non "
            "confermato. Si puo' mostrare come non revisionato, non puo' dare un "
            "bonus clinico e non puo' escludere nulla"
        ),
    ),
    PROTOTYPE_ONLY: QualifierPermission(
        eligibility=PROTOTYPE_ONLY,
        may_display=True,
        may_score=True,
        may_hard_filter=False,
        contribution=CONTRIBUTION_CAPPED,
        reason=(
            "una sola revisione, non indipendente: il valore puo' spostare un "
            "punteggio entro un tetto dichiarato e accendere un warning, e non "
            "puo' eliminare un candidato"
        ),
    ),
    FINAL: QualifierPermission(
        eligibility=FINAL,
        may_display=True,
        may_score=True,
        may_hard_filter=True,
        contribution=CONTRIBUTION_FULL,
        reason="due revisioni concordi, una adjudication o un dossier congelato",
    ),
}

_UNKNOWN_PERMISSION = QualifierPermission(
    eligibility="",
    may_display=False,
    may_score=False,
    may_hard_filter=False,
    contribution=CONTRIBUTION_NONE,
    reason=(
        "livello di propagazione non riconosciuto: il caso prudente e' non "
        "usarlo per niente"
    ),
)


def permission_for(eligibility: Any) -> QualifierPermission:
    """I permessi di un livello. Un livello ignoto non ne ha nessuno."""
    return _PERMISSIONS.get(str(eligibility or "").strip(), _UNKNOWN_PERMISSION)


def may_display(eligibility: Any) -> bool:
    return permission_for(eligibility).may_display


def may_score(eligibility: Any) -> bool:
    return permission_for(eligibility).may_score


def hard_filter_allowed(eligibility: Any) -> bool:
    """La domanda che va fatta prima di escludere qualcosa."""
    return permission_for(eligibility).may_hard_filter


def assert_may_hard_filter(
    eligibility: Any, *, dimension: str, statement_id: str = ""
) -> None:
    """Solleva se qualcuno sta per filtrare con un qualificatore non definitivo.

    Esiste perche' il rifiuto sia esplicito nel punto d'uso. Un chiamante che
    legga i qualificatori e filtri senza chiedere non trova ostacoli: questa e' la
    chiamata che glielo mette davanti.
    """
    permission = permission_for(eligibility)
    if permission.may_hard_filter:
        return
    subject = f" su {statement_id}" if statement_id else ""
    raise PrototypeQualifierAsHardFilterError(
        f"{dimension}{subject} ha eligibility {str(eligibility)!r}: "
        f"{permission.reason}. Un filtro sbagliato rimuove cio' che nessuno "
        "potra' piu' vedere"
    )


def sentinel_treatment(value: Any) -> tuple[str, str]:
    """Come trattare una delle tre assenze, e il codice del trattamento.

    Restituisce `("", "")` per un valore vero: chi chiama distingue cosi'
    l'assenza dal valore senza dover riconoscere i sentinella da solo.
    """
    text = str(value or "").strip().casefold()
    if text == UNKNOWN:
        return (
            TREAT_SCORE,
            "unknown: contributo neutro. Non sapere non e' un difetto della fonte "
            "e non e' una conferma",
        )
    if text == NOT_APPLICABLE:
        return (
            TREAT_EXCLUDE_FROM_SCORE,
            "not_applicable: la domanda non si pone per questa unita', quindi la "
            "dimensione esce dal punteggio invece di valere zero",
        )
    if text == NOT_SEPARABLE:
        return (
            TREAT_WARN,
            "not_separable: la fonte conferma i componenti e non la loro "
            "relazione. Nessun bonus, un warning, mai un rifiuto",
        )
    return ("", "")


def is_sentinel(value: Any) -> bool:
    return str(value or "").strip().casefold() in SENTINELS


def describe_policy() -> dict[str, Any]:
    """La politica in forma serializzabile, per manifest e report."""
    return {
        "policy_version": POLICY_VERSION,
        "rule": "qualifier eligibility != final -> qualifier cannot exclude an EvidenceStatement",
        "levels": {
            name: permission.as_dict() for name, permission in sorted(_PERMISSIONS.items())
        },
        "sentinels": {
            UNKNOWN: TREAT_SCORE,
            NOT_APPLICABLE: TREAT_EXCLUDE_FROM_SCORE,
            NOT_SEPARABLE: TREAT_WARN,
        },
        "native_fields_exempt": True,
        "native_fields_exempt_reason": (
            "i campi nativi vengono dal grafo congelato e non da una revisione: "
            "sottoporli a questa politica renderebbe il sistema meno capace senza "
            "renderlo piu' prudente"
        ),
    }


__all__ = [
    "POLICY_VERSION",
    "NOT_SEPARABLE",
    "SENTINELS",
    "CONTRIBUTION_NONE",
    "CONTRIBUTION_NEUTRAL",
    "CONTRIBUTION_CAPPED",
    "CONTRIBUTION_FULL",
    "TREAT_SCORE",
    "TREAT_WARN",
    "TREAT_EXCLUDE_FROM_SCORE",
    "TREAT_SHOW_AS_UNREVIEWED",
    "QualifierPermission",
    "permission_for",
    "may_display",
    "may_score",
    "hard_filter_allowed",
    "assert_may_hard_filter",
    "sentinel_treatment",
    "is_sentinel",
    "describe_policy",
]
