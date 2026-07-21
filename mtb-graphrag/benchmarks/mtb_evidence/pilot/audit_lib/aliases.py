"""Alias farmacologici ammessi, con validazione degli invarianti di non-fusione.

Un alias e' ammesso solo se mette in relazione due nomi dello *stesso* farmaco: il
codice di sviluppo e la denominazione comune internazionale. Qualunque voce che possa
collassare entita' clinicamente distinte viene rifiutata in costruzione, non
commentata: `build_alias_table` alza `ValueError`.
"""

from __future__ import annotations

import re

from .normalize import norm_text

# Codice di sviluppo o sinonimo commerciale -> denominazione comune internazionale.
# Limitato ai farmaci dei quattro casi pilota; ampliarlo richiede di superare la
# validazione sotto.
DRUG_ALIASES: dict[str, str] = {
    "incb054828": "pemigatinib",
    "incb 054828": "pemigatinib",
    "pemazyre": "pemigatinib",
    "tas-120": "futibatinib",
    "tas 120": "futibatinib",
    "lytgobi": "futibatinib",
    "pf-06463922": "lorlatinib",
    "pf 06463922": "lorlatinib",
    "lorbrena": "lorlatinib",
    "azd9291": "osimertinib",
    "azd 9291": "osimertinib",
    "tagrisso": "osimertinib",
    "mereletinib": "osimertinib",
}

# Token che segnalano un discriminante clinico. Un alias che ne contiene uno
# starebbe normalizzando qualcosa che non e' il nome di un farmaco.
_DISEASE_TOKENS = frozenset(
    {
        "carcinoma",
        "cancer",
        "tumor",
        "tumour",
        "neoplasm",
        "cholangiocarcinoma",
        "intrahepatic",
        "extrahepatic",
        "nsclc",
        "adenocarcinoma",
        "metastatic",
        "advanced",
        "resected",
        "adjuvant",
    }
)

_VARIANT_TOKENS = frozenset(
    {
        "fusion",
        "rearrangement",
        "compound",
        "mutation",
        "deletion",
        "amplification",
        "alteration",
        "wildtype",
        "wild-type",
    }
)

# Un alias composto (`A/B`, `A+B`, `A and B`) fonderebbe due entita' in una.
_COMPOUND_SEPARATOR = re.compile(r"[/+]|\band\b|\bplus\b")

# Notazione di variante proteica, es. G1202R, L858R, T790M.
_PROTEIN_VARIANT = re.compile(r"\b[A-Z]\d{2,5}[A-Z]\b")


class AliasValidationError(ValueError):
    """Un alias violerebbe un invariante di non-fusione."""


def _reject(alias: str, canonical: str, reason: str) -> AliasValidationError:
    return AliasValidationError(
        f"alias rifiutato {alias!r} -> {canonical!r}: {reason}. "
        "La normalizzazione puo' unificare solo nomi dello stesso farmaco."
    )


def _validate_entry(alias: str, canonical: str) -> None:
    if not alias or not canonical:
        raise _reject(alias, canonical, "chiave o valore vuoti")

    for label, value in (("alias", alias), ("canonico", canonical)):
        if _COMPOUND_SEPARATOR.search(value):
            raise _reject(
                alias, canonical, f"il {label} e' composto e fonderebbe due entita'"
            )
        if _PROTEIN_VARIANT.search(value.upper()):
            raise _reject(
                alias, canonical, f"il {label} contiene una notazione di variante"
            )
        tokens = set(re.split(r"[\s\-_]+", value))
        disease_hit = tokens & _DISEASE_TOKENS
        if disease_hit:
            raise _reject(
                alias, canonical, f"il {label} contiene un termine di malattia {sorted(disease_hit)}"
            )
        variant_hit = tokens & _VARIANT_TOKENS
        if variant_hit:
            raise _reject(
                alias,
                canonical,
                f"il {label} contiene un termine di tipo-alterazione {sorted(variant_hit)}",
            )


def build_alias_table(raw: dict[str, str] | None = None) -> dict[str, str]:
    """Costruisce la tabella alias normalizzata, validando ogni voce.

    Restituisce una mappa nuova; l'input non viene mutato.
    """
    source = DRUG_ALIASES if raw is None else raw
    table: dict[str, str] = {}
    for alias, canonical in source.items():
        normalized_alias = norm_text(alias)
        normalized_canonical = norm_text(canonical)
        _validate_entry(normalized_alias, normalized_canonical)
        if normalized_alias == normalized_canonical:
            continue
        if normalized_alias in table and table[normalized_alias] != normalized_canonical:
            raise _reject(
                normalized_alias,
                normalized_canonical,
                f"gia' mappato su {table[normalized_alias]!r}",
            )
        table[normalized_alias] = normalized_canonical
    return table


def alias_manifest(table: dict[str, str]) -> dict[str, object]:
    """Descrive la tabella alias per `normalization_manifest.json`."""
    by_canonical: dict[str, list[str]] = {}
    for alias, canonical in table.items():
        by_canonical.setdefault(canonical, []).append(alias)
    return {
        "alias_count": len(table),
        "canonical_count": len(by_canonical),
        "aliases": dict(sorted(table.items())),
        "by_canonical": {k: sorted(v) for k, v in sorted(by_canonical.items())},
        "invariants": [
            "casefold, trim e collasso degli spazi su ogni valore",
            "prefissi PMID:/NCT: rimossi; NCT normalizzato in uppercase",
            "un alias puo' unificare solo nomi dello stesso farmaco",
            "rifiutati alias contenenti termini di malattia",
            "rifiutati alias contenenti termini di tipo-alterazione (fusion, compound, ...)",
            "rifiutati alias composti (A/B, A+B) che fonderebbero due entita'",
            "rifiutati alias contenenti notazione di variante proteica",
        ],
        "rejected_by_construction": {
            "malattie_distinte": "intrahepatic cholangiocarcinoma non e' cholangiocarcinoma",
            "mutazione_composta": "G1202R non e' G1202R/L1196M",
            "tipo_alterazione": "FGFR2 fusion non e' FGFR2 mutation",
        },
    }
