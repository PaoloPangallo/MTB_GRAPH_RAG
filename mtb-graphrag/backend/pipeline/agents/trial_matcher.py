"""
Trial Matcher — ClinicalTrial → ASSOCIATED_GENE + DIAGNOSES_GENE → Disease.
Attivo solo per complessità High.
"""

from __future__ import annotations

from backend.pipeline.state import MTBState
from backend.pipeline.helpers import run_cypher, get_disease_keywords
from backend.pipeline.cypher import CYPHER_TRIALS


def trial_matcher(state: MTBState) -> MTBState:
    gene       = state.get("gene") or ""
    drug_names = list({r["drug_name"] for r in state.get("drug_candidates", [])})
    disease_kws = get_disease_keywords(state["tumor_type"])
    records    = run_cypher(CYPHER_TRIALS, {
        "gene":       gene,
        "disease_keywords": disease_kws,
        "drug_names": drug_names,
    })
    return {**state, "trial_candidates": records}
