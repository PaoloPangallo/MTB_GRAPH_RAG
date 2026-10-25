"""Su quanto documento poggia una revisione, e che cosa questo permette di dire.

Una revisione fatta sull'abstract e una fatta sul full text producono record
della stessa forma. La differenza non si vede nei campi: si vede in cio' che i
campi **non** contengono, ed e' invisibile per costruzione. Un abstract non
nomina il fondo cellulare di un clone; il record che ne risulta ha `cell_line`
vuoto, esattamente come lo avrebbe un record scritto male su un full text.

`source_basis` rende la differenza leggibile. Non e' una misura di qualita' —
un abstract ben letto vale piu' di un full text letto male — ma dice **quanta
fonte** ha visto chi ha deciso, e da quella quantita' discende cosa la decisione
puo' affermare.

La distinzione che il modulo esiste per tenere aperta e' fra due assenze:

- `unknown` — la fonte potrebbe dirlo e non lo dice, oppure non lo sappiamo;
- `not_separable` — la fonte conferma che i componenti esistono ma non la loro
  relazione. Non e' un buco da riempire cercando meglio: e' una struttura che il
  documento disponibile non risolve.

Scrivere `unknown` dove servirebbe `not_separable` suggerisce che qualcuno debba
ancora cercare il valore. Scrivere `not_separable` dove servirebbe `unknown`
suggerisce che la fonte abbia detto qualcosa che non ha detto.
"""

from __future__ import annotations

from typing import Any

SOURCE_BASIS_VERSION = "source_basis/1.0"

# --- quanta fonte ha visto la revisione ---------------------------------------
ABSTRACT_ONLY = "abstract_only"
FULL_TEXT = "full_text"
FULL_TEXT_PARTIAL = "full_text_partial"
BASIS_UNKNOWN = "unknown"

SOURCE_BASES = (ABSTRACT_ONLY, FULL_TEXT, FULL_TEXT_PARTIAL, BASIS_UNKNOWN)

# Basi che non permettono di affermare una struttura completa. Il full text puo'
# comunque lasciare aperte delle domande, ma non le lascia aperte *per non essere
# stato letto*.
PARTIAL_BASES = (ABSTRACT_ONLY, FULL_TEXT_PARTIAL, BASIS_UNKNOWN)

# --- quanto la struttura e' ricostruibile -------------------------------------
CONFIDENCE_FULL = "full"
CONFIDENCE_PARTIAL = "partial"
CONFIDENCE_NONE = "none"

STRUCTURAL_CONFIDENCES = (CONFIDENCE_FULL, CONFIDENCE_PARTIAL, CONFIDENCE_NONE)

# --- sentinelle dell'assenza ---------------------------------------------------
# `not_separable` e' gia' usato dal repository nei `field_decisions`; qui e' il
# nome canonico, perche' un secondo letterale sparso nel codice divergerebbe dal
# primo senza che nulla lo segnali.
NOT_SEPARABLE = "not_separable"
UNKNOWN = "unknown"


class SourceBasisError(RuntimeError):
    """Una revisione afferma piu' di quanto la sua base documentale permetta."""

    rule_id = "source_basis"


class AbstractOnlyOverclaimError(SourceBasisError):
    """Una revisione su abstract dichiara di aver verificato il full text."""

    rule_id = "abstract_only_is_not_full_text_verified"


def is_partial(basis: Any) -> bool:
    """La base documentale lascia la struttura ricostruibile solo in parte?"""
    return str(basis or "").strip().casefold() in PARTIAL_BASES


def confidence_for(basis: str) -> str:
    """La confidenza strutturale massima che una base documentale consente.

    Massima, non effettiva: un full text puo' comunque non risolvere una
    struttura. La funzione dice il tetto, non il valore.
    """
    return CONFIDENCE_PARTIAL if is_partial(basis) else CONFIDENCE_FULL


def constraints_for_basis(basis: str) -> dict[str, Any]:
    """Cosa una base documentale permette di dichiarare, in forma serializzabile.

    Derivarli invece di lasciarli scrivere a mano su ogni record e' cio' che
    impedisce a un artefatto di dichiararsi `abstract_only` e `full_text_verified`
    insieme.
    """
    partial = is_partial(basis)
    return {
        "source_basis": basis,
        "structural_confidence": confidence_for(basis),
        "full_text_verified": not partial,
        "full_text_stored": False,
        "requires_full_text_or_independent_review": partial,
        "source_basis_version": SOURCE_BASIS_VERSION,
    }


__all__ = [
    "SOURCE_BASIS_VERSION",
    "ABSTRACT_ONLY",
    "FULL_TEXT",
    "FULL_TEXT_PARTIAL",
    "BASIS_UNKNOWN",
    "SOURCE_BASES",
    "PARTIAL_BASES",
    "CONFIDENCE_FULL",
    "CONFIDENCE_PARTIAL",
    "CONFIDENCE_NONE",
    "STRUCTURAL_CONFIDENCES",
    "NOT_SEPARABLE",
    "UNKNOWN",
    "SourceBasisError",
    "AbstractOnlyOverclaimError",
    "is_partial",
    "confidence_for",
    "constraints_for_basis",
]
