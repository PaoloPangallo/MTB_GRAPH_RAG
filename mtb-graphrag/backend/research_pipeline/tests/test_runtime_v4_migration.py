"""Runtime v4 admission and compatibility contract."""

from __future__ import annotations

from backend.research_pipeline import data_access as da
from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.relation_family import classify_relation_family


def test_runtime_loads_the_complete_v4_repository() -> None:
    candidates = kg_retrieval.load_candidates()
    assert da.GRAPH_CANDIDATE_REPOSITORY_VERSION == "4.0"
    assert len(candidates) == 46974
    assert len(set(candidates)) == 46974
    assert {row["relation_family"] for row in candidates.values()} == {
        "EVIDENCE_STATEMENT", "EVIDENCE_DRUG", "GENE_DRUG", "TRIAL_DRUG",
        "TRIAL_GENE", "DRUG_COMPANION_DIAGNOSTIC", "COMPANION_DIAGNOSTIC_GENE",
    }


def test_runtime_projection_preserves_v4_provenance_and_consumed_aliases() -> None:
    candidate = next(iter(kg_retrieval.load_candidates().values()))
    assert candidate["materializer_version"] == "gca-materializer/4.0"
    assert candidate["edge_ids"]
    assert "materialization_rule_id" in candidate
    assert "biomarkers" in candidate
    assert "interventions" in candidate


def test_companion_diagnostic_is_a_searchable_kg_only_relation() -> None:
    candidate = next(
        row for row in kg_retrieval.load_candidates().values()
        if row["relation_family"] == "DRUG_COMPANION_DIAGNOSTIC"
    )
    assert classify_relation_family(candidate) == "KG_ONLY"
    assert candidate["biomarkers"]
    assert candidate["interventions"]
    case = {
        "disease": {},
        "biomarkers": [{"gene": candidate["biomarkers"][0]["label"]}],
        "target_intervention": {"normalized_value": candidate["interventions"][0]["label"]},
        "query_intent": "THERAPY_EVALUATION",
    }
    matched, _ = kg_retrieval._match_candidate(case, candidate)
    assert matched


def test_malformed_doi_like_values_are_not_numeric_pmids() -> None:
    malformed = {
        item["pmid"]
        for row in kg_retrieval.load_candidates().values()
        for item in row.get("document_identifiers", [])
        if item.get("pmid") and not str(item["pmid"]).isdigit()
    }
    assert malformed == {
        "10.1182/blood-2021-148205",
        "10.1182/blood-2022-163099",
    }
