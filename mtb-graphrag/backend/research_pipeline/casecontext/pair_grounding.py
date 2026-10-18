"""Ground a parsed gene–alteration observation in one literal clinical span."""

from __future__ import annotations

import re
from typing import Any
from ..terminology.fusion_syntax import MARKERS, explicit_partners, has_marker


def ground_pair(text: str, gene: Any, alteration: Any) -> dict[str, Any] | None:
    """Return the shared span only for a local, explicit pair expression.

    Conjunctions and punctuation cannot join independent observations. The
    parser's two individually valid quotes are never used as pair evidence.
    """
    gene_text = str(gene or "").strip()
    alteration_text = str(alteration or "").strip()
    if not gene_text or not alteration_text:
        return None
    g = re.escape(gene_text)
    a = re.escape(alteration_text)
    gene_partners = explicit_partners(gene_text, allow_hyphen=True)
    alteration_partners = explicit_partners(alteration_text, allow_hyphen=has_marker(alteration_text))
    if alteration_partners and not (gene_text.upper() in alteration_partners or gene_partners == alteration_partners):
        return None
    patterns = (
        rf"\b{g}\b\s+(?:p\.)?{a}\b",
        rf"\b{g}\b\s+(?:mutation|mutant|variant|alteration)\s+(?:p\.)?{a}\b",
        rf"\b(?:p\.)?{a}\b\s+(?:mutation|variant|alteration)\s+in\s+\b{g}\b",
    )
    if gene_partners and alteration_text.casefold() in MARKERS:
        patterns += (rf'\b{a}\s+{g}\b',)
    matches = [match for pattern in patterns
               for match in re.finditer(pattern, text, flags=re.IGNORECASE)]
    if not matches:
        return None
    match = min(matches, key=lambda item: item.start())
    clause_start = max(
        (boundary.end() for boundary in re.finditer(r"[.;!?\n]|\b(?:and|but|or|ma|oppure)\b",
                                                     text[:match.start()], re.IGNORECASE)),
        default=0,
    )
    prefix = text[clause_start:match.start()]
    suffix = text[match.end():]
    negated = bool(re.search(r"\b(?:no|without|negative\s+for|absence\s+of|assenza\s+di|senza|negativ[oa]\s+per|non)\s*$", prefix,
                             re.IGNORECASE)) or bool(re.match(
        r"\s+(?:was|were|is|are|has\s+been)?\s*(?:not\s+detected|absent|negative|assente|non\s+rilevat[ao])\b",
        suffix, re.IGNORECASE,
    ))
    return {
        "quote": match.group(), "start_offset": match.start(),
        "end_offset": match.end(), "negated": negated,
    }
