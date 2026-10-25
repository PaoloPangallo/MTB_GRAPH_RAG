"""Normalizzazione di testo, PMID, NCT e nomi di farmaco.

Tutte le funzioni sono pure e restituiscono valori nuovi: nessun argomento viene mutato.

Vincolo che attraversa l'intero modulo: la normalizzazione puo' solo ripulire la forma
di un identificatore, mai fondere entita' clinicamente distinte. Le regole che lo
impediscono vivono in `aliases.py`, che rifiuta in costruzione qualunque alias capace
di collassare malattie diverse, mutazione singola e composta, o fusione e alterazione
generica.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")
_PMID_PREFIX = re.compile(r"^pmid\s*:\s*", re.IGNORECASE)
_NCT_PREFIX = re.compile(r"^nct\s*:\s*", re.IGNORECASE)
_PMID_BODY = re.compile(r"^\d{1,12}$")
_NCT_BODY = re.compile(r"^NCT\d{8}$")


def norm_text(value: object) -> str:
    """Casefold, trim e collasso degli spazi interni. `None` diventa stringa vuota."""
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value).strip()).casefold()


@dataclass(frozen=True)
class NormalizedPmid:
    """Un PMID nelle due forme che il grafo usa davvero.

    Lo snapshot memorizza `Publication.pmid` come INTEGER e `Evidence.citation_id`
    come array di stringhe. Legare la forma sbagliata a una query non produce un
    errore: produce zero risultati, che e' molto peggio. Per questo la
    normalizzazione espone entrambe le forme esplicitamente.
    """

    raw: str
    text: str
    numeric: int | None
    valid: bool
    reason: str = ""


def norm_pmid(value: object) -> NormalizedPmid:
    raw = "" if value is None else str(value)
    stripped = _WHITESPACE.sub("", _PMID_PREFIX.sub("", raw.strip()))
    if not stripped:
        return NormalizedPmid(raw=raw, text="", numeric=None, valid=False, reason="empty")
    if not _PMID_BODY.match(stripped):
        return NormalizedPmid(
            raw=raw, text=stripped, numeric=None, valid=False, reason="not_numeric"
        )
    normalized = stripped.lstrip("0") or "0"
    return NormalizedPmid(raw=raw, text=normalized, numeric=int(normalized), valid=True)


@dataclass(frozen=True)
class NormalizedNct:
    raw: str
    text: str
    valid: bool
    reason: str = ""


def norm_nct(value: object) -> NormalizedNct:
    raw = "" if value is None else str(value)
    stripped = _WHITESPACE.sub("", _NCT_PREFIX.sub("", raw.strip())).upper()
    if not stripped:
        return NormalizedNct(raw=raw, text="", valid=False, reason="empty")
    if stripped.isdigit() and len(stripped) == 8:
        stripped = f"NCT{stripped}"
    if not _NCT_BODY.match(stripped):
        return NormalizedNct(raw=raw, text=stripped, valid=False, reason="malformed")
    return NormalizedNct(raw=raw, text=stripped, valid=True)


def norm_drug(value: object, alias_table: dict[str, str] | None = None) -> str:
    """Normalizza un nome di farmaco, risolvendo gli alias registrati.

    `alias_table` va costruita con `aliases.build_alias_table`, che e' l'unico punto
    in cui si valida che un alias non fonda entita' distinte.
    """
    normalized = norm_text(value)
    if not normalized:
        return ""
    if alias_table is None:
        return normalized
    return alias_table.get(normalized, normalized)


def norm_drug_set(values: object, alias_table: dict[str, str] | None = None) -> tuple[str, ...]:
    """Normalizza una lista di farmaci in una tupla ordinata e deduplicata."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        candidates: list[object] = [values]
    else:
        try:
            candidates = list(values)  # type: ignore[arg-type]
        except TypeError:
            candidates = [values]
    normalized = {norm_drug(item, alias_table) for item in candidates}
    return tuple(sorted(name for name in normalized if name))


def norm_pmid_set(values: object) -> tuple[str, ...]:
    """Estrae i PMID validi da un valore scalare o iterabile, in forma testuale."""
    if values is None:
        return ()
    if isinstance(values, (str, bytes, int)):
        candidates: list[object] = [values]
    else:
        try:
            candidates = list(values)  # type: ignore[arg-type]
        except TypeError:
            candidates = [values]
    # Si deduplica sul testo normalizzato, non sull'oggetto: `NormalizedPmid`
    # conserva il valore grezzo, quindi "PMID:2" e 2 sarebbero due oggetti distinti.
    return tuple(sorted({item.text for item in map(norm_pmid, candidates) if item.valid}))


def norm_nct_set(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        candidates: list[object] = [values]
    else:
        try:
            candidates = list(values)  # type: ignore[arg-type]
        except TypeError:
            candidates = [values]
    return tuple(sorted({item.text for item in map(norm_nct, candidates) if item.valid}))
