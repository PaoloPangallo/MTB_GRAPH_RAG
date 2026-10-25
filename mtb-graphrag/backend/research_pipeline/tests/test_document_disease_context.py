"""A shared disease concept does not erase the source's clinical scope."""
import pytest

from backend.research_pipeline.terminology.case_resolution import compare_disease_context
from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.tests.test_relation_support_contract_v5 import candidate, observation
from backend.research_pipeline.tests.test_document_verification import (
    _candidate, _structural, structural_verify,
)
from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _reader_observation, _source_unit
from backend.research_pipeline.tests.test_terminology_registry import term
from backend.research_pipeline.terminology.registry import Registry
from backend.research_pipeline.terminology.matching import active_registry
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation


@pytest.mark.parametrize("base,source", [
    ("colorectal cancer", "metastatic colorectal cancer"),
    ("lung cancer", "recurrent lung cancer"),
])
def test_segmented_source_context_is_unresolved_scope_not_different_disease(base, source):
    comparison = compare_disease_context(base, source, get_registry())
    assert comparison["relation"] == "SAME_CONCEPT_CONTEXT_UNRESOLVED"
    assert comparison["observed"]["residual_context"]
    quote = f"BRAF V600E showed sensitivity to vemurafenib in {source}."
    result = assess_relation_support(candidate(disease=base), observation(disease=source), source_unit_text=quote)
    assert result["result"] == "PARTIAL_SUPPORT", result
    assert result["reason"] == "DISEASE_CONTEXT_SCOPE_UNRESOLVED"
    assert result["predicates"]["relation_full_specificity"] is False
    assert result["disease_resolution"][0] == comparison


def test_specific_disease_is_not_reduced_to_a_shared_suffix():
    comparison = compare_disease_context("lung cancer", "small cell lung cancer", get_registry())
    assert comparison["relation"] not in {"VERIFIED_ALIAS", "LITERAL_IDENTITY"}
    assert comparison["observed"]["residual_context"] == "small cell"


def test_document_structural_gate_abstains_for_unresolved_clinical_scope():
    target = _candidate()
    quote = "EGFR L858R showed sensitivity to erlotinib in recurrent lung cancer."
    observed = _reader_observation(target, [_source_unit(quote)])["enrichment"]
    observed["observed_relation"]["disease"] = "recurrent lung cancer"
    result = _structural(quote, candidate=target, observed=observed)
    assert result["structural_status"] == "UNRESOLVED", result
    assert "DISEASE_CONTEXT_SCOPE_UNRESOLVED" in result["structural_reason_codes"]


def test_source_edge_gene_pair_is_not_a_compound_subject():
    target = candidate(disease="colorectal cancer")
    target["biomarkers"] = [{"type": "Variant", "label": "V600E", "gene": "BRAF"}]
    quote = "BRAF V600E showed sensitivity to vemurafenib in colorectal cancer."
    result = assess_relation_support(target, observation(disease="colorectal cancer"), source_unit_text=quote)
    assert result["relation_composition"] == "EXACT", result
    assert result["result"] == "FULL_SUPPORT", result


def test_exact_disease_alias_preserves_identical_residual_context():
    registry = Registry([term("DOID:9256", "colorectal cancer", "DISEASE"),
                         term("DOID:9256", "CRC", "DISEASE")], "context/test")
    token = active_registry.set(registry)
    try:
        assert entity_relation("metastatic CRC", "metastatic colorectal cancer", domain="DISEASE") == "CANONICAL_ALIAS"
        assert entity_relation("CRC", "metastatic colorectal cancer", domain="DISEASE") not in {"IDENTICAL", "CANONICAL_ALIAS"}
        target = _candidate(disease=[{"label": "metastatic CRC", "type": "Disease"}], context={"disease": "metastatic CRC"})
        quote = "EGFR L858R showed sensitivity to erlotinib in metastatic colorectal cancer."
        observed = _reader_observation(target, [_source_unit(quote)])["enrichment"]
        observed["observed_relation"]["disease"] = "metastatic colorectal cancer"
        assert _structural(quote, candidate=target, observed=observed)["structural_status"] == "PASS"
    finally:
        active_registry.reset(token)


def test_mcrc_is_resolved_as_colorectal_cancer_with_metastatic_context():
    registry = get_registry()
    comparison = compare_disease_context("colorectal cancer", "mCRC", registry)

    assert comparison["relation"] == "SAME_CONCEPT_CONTEXT_UNRESOLVED"
    assert comparison["classification"] == "MATCH_CONTEXTUAL"
    assert tuple(comparison["observed"]["concept_ids"]) == ("DOID:9256",)
    assert comparison["observed"]["residual_context"] == "metastatic"


def test_mcrc_contextual_match_preserves_qualifier_for_semantic_review():
    target = _candidate(
        relation_family="EVIDENCE_DRUG",
        disease=[{"type": "Disease", "label": "Colorectal Cancer"}],
        biomarkers=[{"type": "Gene", "label": "KRAS"},
                    {"type": "Variant", "label": "G13V", "gene": "KRAS"}],
        interventions=[{"type": "Drug", "label": "Panitumumab"}],
        predicate="associated_with_resistance_to",
        direction="Supports",
        document_identifiers=[{"pmid": "12345678"}],
    )
    quote = "KRAS G13V showed resistance to panitumumab in mCRC."
    unit = _source_unit(quote, document_id="pmid:12345678", unit_id="SU-mcrc-context")
    observed = _reader_observation(target, [unit])["enrichment"]
    observed["observed_relation"]["disease"] = "mCRC"
    result = structural_verify(
        target, {"document_id": "pmid:12345678",
                 "resolved_source_unit_ids": [unit["source_unit_id"]]},
        unit, observed,
    )

    assert result["structural_status"] == "PASS", result["structural_reason_codes"]
    assert "DISEASE_CONTEXT_REQUIRES_SEMANTIC_REVIEW" in result["structural_reason_codes"]
    assert result["disease_resolution"]["classification"] == "MATCH_CONTEXTUAL"
    assert result["disease_resolution"]["observed"]["residual_context"] == "metastatic"


def test_disease_comparison_distinguishes_mismatch_from_unknown():
    registry = get_registry()
    mismatch = compare_disease_context("colorectal cancer", "lung cancer", registry)
    # The pinned registry only resolves the lung-cancer substring; unknown
    # histology must not become a proven disease mismatch.
    partial = compare_disease_context("colorectal cancer", "small cell lung cancer", registry)
    unknown = compare_disease_context("colorectal cancer", "unmapped oncology label", registry)

    assert mismatch["classification"] == "MISMATCH"
    assert partial["classification"] == "UNKNOWN"
    assert unknown["relation"] == "UNKNOWN"
    assert unknown["classification"] == "UNKNOWN"


def test_unknown_disease_context_is_not_reported_as_proven_incompatibility():
    quote = "KRAS mutations showed resistance to panitumumab in QXZ-7."
    result = assess_relation_support(
        candidate(disease="colorectal cancer", gene="KRAS", alteration="G13V",
                  drug="panitumumab", predicate="associated_with_resistance_to"),
        observation(gene="KRAS", alteration=None, drug="panitumumab",
                    direction="RESISTANCE", disease="QXZ-7"),
        source_unit_text=quote,
    )

    assert result["reason"] != "DISEASE_CONTEXT_INCOMPATIBLE"
