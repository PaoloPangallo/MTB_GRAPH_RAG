"""Normalizzazione usata dagli indici del repository.

Si appoggia alle funzioni gia' validate dall'audit del grafo invece di
reimplementarle: due definizioni di "stessa malattia" o "stesso PMID" potrebbero
divergere, e il repository deve indicizzare esattamente come l'audit confronta.

Le forme normalizzate servono **solo** agli indici. Il valore originale resta nello
statement e viene restituito dai lookup: normalizzare il dato conservato sarebbe una
modifica in-place, che il repository non fa mai.
"""

from __future__ import annotations

from typing import Any


def normalize_text(value: Any) -> str:
    """Casefold, trim e collasso degli spazi."""
    from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_text

    return norm_text(value)


def normalize_pmid(value: Any) -> str:
    """PMID in forma testuale canonica, stringa vuota se non valido."""
    from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_pmid

    normalized = norm_pmid(value)
    return normalized.text if normalized.valid else ""


def normalize_nct(value: Any) -> str:
    from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_nct

    normalized = norm_nct(value)
    return normalized.text if normalized.valid else ""


def normalize_drug(value: Any) -> str:
    """Nome di farmaco con gli alias controllati gia' validati dall'audit."""
    from benchmarks.mtb_evidence.pilot.audit_lib.aliases import build_alias_table
    from benchmarks.mtb_evidence.pilot.audit_lib.normalize import norm_drug

    return norm_drug(value, build_alias_table())


def diseases_match(left: Any, right: Any) -> bool:
    """Due denominazioni indicano la stessa entita'?

    Riusa la regola dell'audit: identita' o sola differenza di vocabolario contano come
    match, un sottotipo rispetto al suo genitore no.
    """
    from benchmarks.mtb_evidence.pilot.audit_lib.disease import diseases_match as _match

    return _match(left, right)


def disease_relation(left: Any, right: Any) -> str:
    from benchmarks.mtb_evidence.pilot.audit_lib.disease import disease_relation as _relation

    return _relation(left, right)
