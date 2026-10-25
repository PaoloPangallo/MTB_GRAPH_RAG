"""Uncertain molecular subjects constrain retrieval without asserting presence."""
from copy import deepcopy

import pytest

from backend.research_pipeline.retrieval import kg_retrieval as kr
from backend.research_pipeline.terminology import matching as terminology
from backend.research_pipeline.terminology.case_resolution import resolve_case
from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.terminology.molecular import parse_profile, evaluate_profile


def query(gene, alteration=None, status="UNCERTAIN"):
    return {
        "query_intent": "THERAPY_EVALUATION",
        "biomarkers": [{"gene": gene, "alteration": alteration,
                        "assertion_status": status, "clinical_role": "PRIMARY"}],
        "target_intervention": {"raw_value": "panitumumab"},
    }


def candidate(gene):
    return {
        "candidate_id": "GCA-QUERY-SUBJECT",
        "relation_family": "GENE_DRUG",
        "biomarkers": [{"type": "Gene", "label": gene}],
        "interventions": [{"type": "Drug", "label": "panitumumab"}],
        "document_identifiers": [{"pmid": "12345678"}],
        "disease": [],
    }


@pytest.mark.parametrize("gene", ["UNLISTED_RESEARCH_GENE", "ANOTHER_UNLINKED_GENE"])
def test_unknown_uncertain_subject_does_not_broaden_to_shared_drug(monkeypatch, gene):
    row = candidate("KRAS")
    monkeypatch.setattr(kr, "load_candidates", lambda: {row["candidate_id"]: row})
    result = kr.retrieve(query(gene, "P44R"))
    assert result["no_match"] is True
    assert result["associations"] == []
    assert "BIOMARKER_NOT_COMPATIBLE" in result["excluded_candidates"][0]["reason_codes"]


def test_known_uncertain_subject_rejects_unrelated_gene_despite_shared_drug():
    matched, reasons = kr._match_candidate(query("EGFR"), candidate("KRAS"))
    assert matched is False
    assert "BIOMARKER_NOT_COMPATIBLE" in reasons


def test_known_uncertain_subject_can_retrieve_same_gene_without_asserting_presence(monkeypatch):
    case = query("EGFR", "L858R")
    before = deepcopy(case)
    row = candidate("EGFR")
    monkeypatch.setattr(kr, "load_candidates", lambda: {row["candidate_id"]: row})
    result = kr.retrieve(case)
    assert [item["candidate_id"] for item in result["associations"]] == ["GCA-QUERY-SUBJECT"]
    anchor = result["retrieval_summary"]["anchor_trace"][0]
    assert anchor["assertion_status"] == "UNCERTAIN"
    assert anchor["used_by_retrieval"] is True
    assert case == before
    resolved = resolve_case(case, get_registry())
    observation = resolved["entity_resolution"]["biomarkers"][0]
    profile = parse_profile("EGFR L858R", get_registry())
    assert evaluate_profile(profile["ast"], [{**observation["variant"], "assertion_status": observation["assertion_status"]}]) == "UNKNOWN"


def test_uncertain_subject_does_not_satisfy_compound_presence_gate():
    row = candidate("EGFR")
    row["entity_resolution"] = {"compound": True, "profile": parse_profile("EGFR L858R AND ABL1 T315I", get_registry())}
    case = query("EGFR", "L858R")
    case["biomarkers"].append({"gene": "ABL1", "alteration": "T315I", "assertion_status": "PRESENT"})
    matched, reasons = kr._match_candidate(case, row)
    assert matched is False
    assert reasons == ["PROFILE_CONSTRAINT_UNKNOWN_OR_FALSE"]


def test_negated_subject_is_not_promoted_to_retrieval_anchor():
    case = query("KRAS", status="NEGATED")
    case["target_intervention"] = None
    assert kr._match_candidate(case, candidate("KRAS")) == (False, ["NO_POSITIVE_ANCHOR"])


def test_explicit_negative_conflict_still_vetoes_same_gene():
    case = query("KRAS")
    case["negated_biomarkers"] = [{"gene": "KRAS", "alteration": None}]
    matched, reasons = kr._match_candidate(case, candidate("KRAS"))
    assert matched is False
    assert "NEGATED_BIOMARKER_CONFLICT" in reasons


def test_historical_matcher_retains_recorded_uncertain_subject_policy():
    token = terminology.historical_matching.set(True)
    try:
        assert kr._match_candidate(query("EGFR"), candidate("KRAS"))[0] is True
    finally:
        terminology.historical_matching.reset(token)
