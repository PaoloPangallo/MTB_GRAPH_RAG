"""No-LLM integration from contrasting SourceUnits to the deterministic claim."""

from __future__ import annotations

import pytest

from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.experimental.sourceunit_selector import (
    SourceUnitSelectionInput,
    select,
)
from backend.research_pipeline.orchestrator import _assess_v3_quoted_relation


def test_positive_and_contrary_quotes_survive_to_dossier() -> None:
    candidate = {
        "candidate_id": "GCA4-P0-INTEGRATION",
        "predicate": "associated_with_sensitivity_to",
        "direction": "Supports",
        "disease": [{"label": "lung cancer"}],
        "biomarkers": [{"label": "EGFR", "type": "Gene"},
                       {"label": "L858R", "type": "Variant", "linked_gene": "EGFR"}],
        "interventions": [{"label": "erlotinib"}],
        "document_identifiers": [{"pmid": "123"}],
        "source_record_ids": ["row:1"],
        "source_datasets": ["source.csv"],
        "semantic_key": "EVIDENCE_STATEMENT|Evidence:1",
        "node_ids": ["Gene:1", "Evidence:1"],
        "edge_ids": ["edge:1"],
        "graph_path": ["Gene:1", "Evidence:1"],
        "materialization_rule": "gca/4.0/evidence_statement",
    }
    units = [
        {"source_unit_id": "positive", "document_id": "pmid:123",
         "unit_type": "FULLTEXT_SENTENCE", "section": "Results",
         "text": "EGFR L858R was associated with response to erlotinib in lung cancer."},
        {"source_unit_id": "contrary", "document_id": "pmid:123",
         "unit_type": "FULLTEXT_SENTENCE", "section": "Results",
         "text": "EGFR L858R did not support response to erlotinib in lung cancer."},
    ]
    selected = select(SourceUnitSelectionInput.from_candidate(candidate, "pmid:123", units))
    assert set(selected.selected_source_unit_ids) == {"positive", "contrary"}

    records = []
    for unit in units:
        quote = unit["text"]
        enrichment = {
            "decision": "QUOTE", "quote": quote,
            "observed_relation": {
                "subjects": [{"type": "GENE", "surface_value": "EGFR"},
                             {"type": "ALTERATION", "surface_value": "L858R"}],
                "subject_pairings": [{"gene": "EGFR", "alteration": "L858R"}],
                "intervention": "erlotinib", "disease": "lung cancer",
                "effect_direction": "SENSITIVITY_RESPONSE", "observed_stance": "SUPPORTS",
                "relation_scope": "SINGLE", "relation_assertion": "RELATION_ASSERTED",
            },
        }
        records.append({
            **enrichment, "candidate_id": candidate["candidate_id"],
            "document_id": "pmid:123", "source_unit_id": unit["source_unit_id"],
            "validation_outcome": "ENRICHMENT_V3_ACCEPTED", "quote_valid": True,
            "presentation_state": "VALIDATED_QUOTE", "accepted_for_gates": True,
            "candidate_support": _assess_v3_quoted_relation(candidate, enrichment, quote),
        })

    report = build_relation_aware_report(
        {"disease": "lung cancer"}, [candidate],
        {candidate["candidate_id"]: {"evidence_records": records}},
    )
    claim = report["paper_evidence"][0]["claim"]
    assert claim["status"] == "PARTIAL_SUPPORT"
    assert claim["contradiction_present"] is True
    assert len(claim["supporting_evidence_ids"]) == 1
    assert len(claim["contradicting_evidence_ids"]) == 1


@pytest.mark.parametrize("quote,expected", [
    ("EGFR L858R and erlotinib were studied.", "NO_SUPPORT"),
    ("EGFR G719A showed sensitivity to erlotinib.", "NO_SUPPORT"),
    ("EGFR L858R showed sensitivity to gefitinib.", "NO_SUPPORT"),
    ("EGFR L858R predicted response to gefitinib, while erlotinib response was measured.", "NO_SUPPORT"),
    ("EGFR L858R sensitivity to erlotinib was measured.", "NO_SUPPORT"),
    ("Whether EGFR L858R showed sensitivity to erlotinib was investigated.", "NO_SUPPORT"),
    ("The hypothesis that EGFR L858R showed sensitivity to erlotinib was tested.", "NO_SUPPORT"),
    ("No evidence that EGFR L858R showed sensitivity to erlotinib was found.", "NO_SUPPORT"),
    ("Only EGFR G719A, not EGFR L858R, showed sensitivity to erlotinib.", "CONTRADICTORY"),
    ("EGFR L858R showed sensitivity to erlotinib in breast cancer.", "NO_SUPPORT"),
    ("EGFR L858R showed resistance to erlotinib.", "CONTRADICTORY"),
    ("The finding that EGFR L858R showed sensitivity to erlotinib was rejected.", "NO_SUPPORT"),
    ("Smith et al. reported that EGFR L858R showed sensitivity to erlotinib.", "NO_SUPPORT"),
    ("We hypothesized that EGFR L858R might predict sensitivity to erlotinib.", "NO_SUPPORT"),
])
def test_adversarial_quote_reaches_dossier_without_false_support(quote: str, expected: str) -> None:
    candidate = {
        "candidate_id": "P0-ADVERSARIAL", "predicate": "associated_with_sensitivity_to",
        "direction": "Supports", "disease": [{"label": "lung cancer"}],
        "biomarkers": [{"label": "EGFR", "type": "Gene"}, {"label": "L858R", "type": "Variant"}],
        "interventions": [{"label": "erlotinib"}],
        "document_identifiers": [{"pmid": "123"}],
    }
    observation = {
        "decision": "QUOTE", "quote": quote,
        "observed_relation": {
            "subjects": [{"type": "GENE", "surface_value": "EGFR"},
                         {"type": "ALTERATION", "surface_value": "L858R"}],
            "subject_pairings": [{"gene": "EGFR", "alteration": "L858R"}],
            "intervention": "erlotinib", "disease": None,
            "effect_direction": "SENSITIVITY_RESPONSE", "observed_stance": "SUPPORTS",
            "relation_scope": "SINGLE", "relation_assertion": "RELATION_ASSERTED",
        },
    }
    support = _assess_v3_quoted_relation(candidate, observation, quote)
    record = {
        **observation, "candidate_id": candidate["candidate_id"], "document_id": "pmid:123",
        "source_unit_id": "SU-1", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
        "quote_valid": True, "presentation_state": "VALIDATED_QUOTE",
        "accepted_for_gates": True, "candidate_support": support,
    }
    report = build_relation_aware_report(
        {"disease": "lung cancer"}, [candidate],
        {candidate["candidate_id"]: {"evidence_records": [record]}},
    )
    claim = report["paper_evidence"][0]["claim"]
    assert support["result"] == expected
    assert claim["status"] != "FULL_SUPPORT"
