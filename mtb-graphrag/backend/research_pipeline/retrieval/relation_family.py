"""Deterministic relation-family classification for materialized GCA records."""

from __future__ import annotations

from typing import Any


PAPER_EVIDENCE = "PAPER_EVIDENCE"
CLINICAL_TRIAL = "CLINICAL_TRIAL"
KG_ONLY = "KG_ONLY"


def classify_relation_family(candidate: dict[str, Any]) -> str:
    """Classify a candidate from its actual document identifiers.

    Source metadata is deliberately ignored: a source label alone is not
    document provenance. A record carrying both publication and trial
    identifiers is rejected because this slice defines no mixed family.
    """
    identifiers = candidate.get("document_identifiers") or []
    has_pmid = any(item.get("pmid") for item in identifiers if isinstance(item, dict))
    has_nct = any(item.get("nct") for item in identifiers if isinstance(item, dict))
    if has_pmid and has_nct:
        raise ValueError(
            "candidate contains both PMID and NCT; mixed provenance has no relation family"
        )
    if has_pmid:
        return PAPER_EVIDENCE
    if has_nct:
        return CLINICAL_TRIAL
    return KG_ONLY
