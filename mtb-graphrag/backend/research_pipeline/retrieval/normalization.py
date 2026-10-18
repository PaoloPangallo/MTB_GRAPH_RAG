"""Versioned, conservative retrieval identities; never rewrite grounded artifacts.

No fuzzy matching, substring disease matching or inferred nucleotide/protein
conversion. Unrecognized expressions retain their complete lexical identity.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

VERSION = "retrieval-normalization/1.0"
_QUALIFIERS = ("locally advanced", "metastatic", "advanced", "recurrent")
_AMINO_ACIDS = dict(zip(
    ("ala", "arg", "asn", "asp", "cys", "gln", "glu", "gly", "his", "ile",
     "leu", "lys", "met", "phe", "pro", "ser", "thr", "trp", "tyr", "val"),
    "ARNDCQEGHILKMFPSTWYV", strict=True))


def lexical(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def disease_identity(value: Any) -> dict[str, Any]:
    identity = lexical(value)
    qualifiers: list[str] = []
    while True:
        qualifier = next((q for q in _QUALIFIERS if identity.startswith(q + " ")), None)
        if qualifier is None:
            break
        qualifiers.append(qualifier)
        identity = identity[len(qualifier):].strip()
    return {"raw": value, "identity": identity, "qualifiers": sorted(set(qualifiers)),
            "rule": "DISEASE_PREFIX_QUALIFIERS" if qualifiers else "LEXICAL_EXACT"}


def disease_matches(query: Any, candidate: Any) -> bool:
    left, right = disease_identity(query), disease_identity(candidate)
    # Unspecified candidate context can cover a qualified case. The inverse
    # cannot invent a stage/recurrence that the patient text did not establish.
    return bool(left["identity"] and left["identity"] == right["identity"]
                and set(right["qualifiers"]).issubset(left["qualifiers"]))


def alteration_identity(value: Any) -> dict[str, Any]:
    raw = unicodedata.normalize("NFKC", str(value or "")).strip()
    # Only a complete, single protein substitution licenses these wrappers.
    # Compound profiles, deletions, fusions and DNA coordinates stay intact.
    expression = re.sub(r"\s+mutation$", "", raw, flags=re.IGNORECASE)
    expression = re.sub(r"^p\.", "", expression, flags=re.IGNORECASE)
    if expression.startswith("(") and expression.endswith(")"):
        expression = expression[1:-1]
    match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]*)([A-Za-z]{1,3})", expression)
    if match:
        before, position, after = match.groups()
        def amino(token: str) -> str | None:
            if len(token) == 1 and token.upper() in _AMINO_ACIDS.values():
                return token.upper()
            return _AMINO_ACIDS.get(token.lower())
        source, target = amino(before), amino(after)
        if source and target:
            return {"raw": value, "identity": f"{source}{position}{target}".lower(),
                    "rule": "PROTEIN_SUBSTITUTION"}
    # Unknown molecular syntax must preserve operators, uncertainty markers
    # and parentheses: DNA substitutions and compound profiles are not words.
    return {"raw": value, "identity": re.sub(r"\s+", " ", raw.casefold()),
            "rule": "LEXICAL_EXACT"}


def alteration_matches(query: Any, candidate: Any) -> bool:
    left, right = alteration_identity(query), alteration_identity(candidate)
    return bool(left["identity"] and left["identity"] == right["identity"])
