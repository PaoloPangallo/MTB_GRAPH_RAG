"""Small, source-backed identity aliases; no class, variant, or regimen expansion.

Aliases are accepted only when the complete observed entity matches one of the
domain-specific listed names. Composite phrases therefore remain non-identical.
Sources: PubChem, NCI, and NCBI records linked below.
"""

from __future__ import annotations

import re
import unicodedata

VERSION = "approved-identity-aliases/1.3"

# A grammatical form of the same copy-number state. Gene ownership is checked
# separately through the source-linked variant concept, never through this map.
VARIANT_WORD_FORMS = {'amplified': 'Amplification'}
VARIANT_WORD_FORM_SOURCE = 'https://www.cancer.gov/publications/dictionaries/cancer-terms/def/gene-amplification'

_RECORDS = (
    {
        "canonical": "infigratinib",
        "aliases": ("BGJ398",),
        "source": "https://www.cancer.gov/research/participate/clinical-trials-search/v?id=NCT02150967",
    },
    {
        "canonical": "tretinoin",
        "aliases": ("all-trans retinoic acid", "ATRA", "trans-retinoic acid", "vitamin A acid"),
        "source": "https://pubchem.ncbi.nlm.nih.gov/compound/444795",
    },
    {
        "canonical": "sirolimus",
        "aliases": ("rapamycin",),
        "source": "https://pubchem.ncbi.nlm.nih.gov/compound/5284616",
    },
    {
        "canonical": "palbociclib",
        "aliases": ("PD-0332991", "PD0332991"),
        "source": "https://pubchem.ncbi.nlm.nih.gov/compound/5330286",
    },
    {
        "canonical": "dordaviprone",
        "aliases": ("ONC201", "ONC-201", "ONC 201", "ONC201 monotherapy"),
        "source": "https://pubchem.ncbi.nlm.nih.gov/compound/73777259",
    },
    {
        "canonical": "pictilisib",
        "aliases": ("GDC-0941", "GDC0941", "GDC-0941/Pictilisib"),
        "source": "https://pubchem.ncbi.nlm.nih.gov/compound/17755052",
    },
    {
        "canonical": "fexagratinib",
        "aliases": ("AZD4547", "AZD-4547", "KB-74810", "ABSK-091"),
        "source": "https://www.cancer.gov/publications/dictionaries/cancer-drug/def/fexagratinib",
    },
    {
        "canonical": "AZD1480",
        "aliases": ("JAK2 inhibitor AZD1480",),
        "source": "https://pubchem.ncbi.nlm.nih.gov/compound/16659841",
    },
    {
        "canonical": "irinotecan",
        "aliases": ("irinotecan hydrochloride", "CPT-11", "CPT11", "CPT 11"),
        "source": "https://www.cancer.gov/publications/dictionaries/cancer-terms/def/cpt-11",
    },
)

_GENE_RECORDS = (
    {
        "canonical": "ERBB2",
        "aliases": ("human epidermal growth factor receptor 2",),
        "source": "https://www.ncbi.nlm.nih.gov/gene/2064",
    },
)


def _key(value: str) -> str:
    text = unicodedata.normalize("NFC", value.casefold())
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()

_IDENTITY: dict[str, tuple[str, str]] = {}
for _record in _RECORDS:
    _canonical = _key(_record["canonical"])
    _IDENTITY[_canonical] = (_canonical, _record["source"])
    for _alias in _record["aliases"]:
        _IDENTITY[_key(_alias)] = (_canonical, _record["source"])

_GENE_IDENTITY: dict[str, tuple[str, str]] = {}
for _record in _GENE_RECORDS:
    _canonical = _key(_record["canonical"])
    _GENE_IDENTITY[_canonical] = (_canonical, _record["source"])
    for _alias in _record["aliases"]:
        _GENE_IDENTITY[_key(_alias)] = (_canonical, _record["source"])


def compare(expected: str, observed: str, *, domain: str = "INTERVENTION") -> dict[str, str] | None:
    """Return curated identity only for exact entity strings, never substrings."""
    identities = _GENE_IDENTITY if domain == "GENE" else _IDENTITY
    left = identities.get(_key(expected))
    right = identities.get(_key(observed))
    if left and right and left[0] == right[0]:
        if _key(expected) == _key(observed):
            return {"relation": "IDENTICAL", "alias_version": VERSION, "source": left[1]}
        return {"relation": "VERIFIED_ALIAS", "alias_version": VERSION, "source": left[1]}
    return None
