"""Representation handling; biological equivalences come from registry records."""
from __future__ import annotations

import re
import unicodedata

_AMINO = dict(zip(
    ("ala", "arg", "asn", "asp", "cys", "gln", "glu", "gly", "his", "ile",
     "leu", "lys", "met", "phe", "pro", "ser", "thr", "trp", "tyr", "val"),
    "ARNDCQEGHILKMFPSTWYV", strict=True))


def surface(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\u2010-\u2015]", "-", value)
    return re.sub(r"\s+", " ", value.casefold()).strip()


def molecular_surface(value: str) -> dict:
    raw = unicodedata.normalize("NFKC", value).strip()
    reference = None
    accession = re.match(r"^([A-Za-z][A-Za-z0-9_]*\.\d+):(.+)$", raw)
    expression = raw
    if accession:
        reference, expression = accession.groups()
    # Strip only a trailing grammatical marker; the remaining expression must
    # still fully match a single substitution. Extra scope/alleles stay intact.
    core = re.sub(r"(?:\s+|[-\u2010-\u2015])(?:mutation|mutated|mutant)$", "", expression, flags=re.IGNORECASE)
    core = re.sub(r"^p\.", "", core, flags=re.IGNORECASE)
    predicted = core.startswith("(") and core.endswith(")")
    if predicted:
        core = core[1:-1]
    match = re.fullmatch(r"([A-Za-z]{1,3})([1-9][0-9]*)([A-Za-z]{1,3}|\*)", core)
    if match:
        before, pos, after = match.groups()
        def amino(token: str) -> str | None:
            if token.lower() == "ter" or token == "*":
                return "*"
            if len(token) == 1 and token.upper() in _AMINO.values():
                return token.upper()
            return _AMINO.get(token.lower())
        left, right = amino(before), amino(after)
        if left and left != "*" and right:
            return {"key": f"p.{left}{pos}{right}".casefold(), "reference": reference,
                    "predicted": predicted, "kind": "PROTEIN_SUBSTITUTION"}
    return {"key": surface(expression), "reference": reference,
            "predicted": False, "kind": "EXACT_SURFACE"}


def lookup_key(domain: str, value: str) -> str:
    return molecular_surface(value)["key"] if domain == "VARIANT" else surface(value)


def protein_keys(text: str) -> set[str]:
    """Extract supported substitution representations for quote scope checks.

    These are syntax keys, not linked concepts or allele identities.
    """
    keys = set()
    for match in re.finditer(r"\b(?:p\.)?\(?[A-Za-z]{1,3}[1-9][0-9]*(?:[A-Za-z]{1,3}|\*)\)?(?=\W|$)", text):
        result = molecular_surface(match[0])
        if result["kind"] == "PROTEIN_SUBSTITUTION":
            keys.add(result["key"])
    return keys
