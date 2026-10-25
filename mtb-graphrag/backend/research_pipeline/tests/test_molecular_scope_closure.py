"""Offline characterization of the bounded registry-backed molecular scope.

These are software contracts, not clinical gold labels or parser accuracy tests.
"""
from copy import deepcopy

import pytest

from backend.research_pipeline.terminology.case_resolution import resolve_case
from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.terminology.molecular import evaluate_profile, parse_profile


@pytest.mark.parametrize("gene", ["BCR::ABL1", "BCR-ABL1", "EGFR::RAD51"])
def test_unlinked_fusion_preserves_literal_and_exposes_unknown_identity(gene):
    case = {"biomarkers": [{"gene": gene, "alteration": "Fusion", "assertion_status": "PRESENT"}]}
    before = deepcopy(case)
    resolved = resolve_case(case, get_registry())
    assert case == before
    assert resolved["biomarkers"] == before["biomarkers"]
    record = resolved["entity_resolution"]["biomarkers"][0]
    assert record["gene"]["status"] == "UNMAPPED"
    assert record["variant"]["reasons"] == ("GENE_UNRESOLVED",)
    assert not record["variant"]["concept_ids"]


def test_resolved_component_does_not_resolve_unlinked_compound():
    registry = get_registry()
    assert parse_profile("ABL1 T315I", registry)["status"] == "RESOLVED"
    expression = "UNLINKED::ABL1 Fusion AND ABL1 T315I"
    profile = parse_profile(expression, registry)
    assert profile["status"] == "UNMAPPED"
    assert profile["unresolved_tokens"] == [expression]
    assert profile["component_ids"] == []
    assert evaluate_profile(profile["ast"], []) == "UNKNOWN"


def test_missing_conflicting_and_uncertain_observations_are_not_negative():
    profile = parse_profile("ABL1 T315I", get_registry())
    cid = profile["component_ids"][0]
    def observation(status):
        return {"concept_ids": [cid], "assertion_status": status}
    assert evaluate_profile(profile["ast"], []) == "UNKNOWN"
    assert evaluate_profile(profile["ast"], [observation("UNCERTAIN")]) == "UNKNOWN"
    assert evaluate_profile(profile["ast"], [observation("PRESENT"), observation("NEGATED")]) == "UNKNOWN"
    assert evaluate_profile(profile["ast"], [observation("NEGATED")]) == "FALSE"


def test_wild_type_is_not_specific_allele_absence():
    case = {"biomarkers": [], "negated_biomarkers": [{"gene": "KRAS", "alteration": "wild-type"}]}
    resolved = resolve_case(case, get_registry())
    record = resolved["entity_resolution"]["negated_biomarkers"][0]
    assert record["gene"]["status"] == "RESOLVED"
    assert record["variant"]["status"] == "UNMAPPED"
    profile = parse_profile("NOT KRAS G12D", get_registry())
    assert evaluate_profile(profile["ast"], [{**record["variant"], "assertion_status": "NEGATED"}]) == "UNKNOWN"
