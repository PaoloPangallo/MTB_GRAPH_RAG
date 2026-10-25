from pathlib import Path

import pytest

from backend.research_pipeline.documents.trial_context import (
    TrialContextIndex,
    TrialContextRecord,
    load_trial_context_index,
)
from backend.research_pipeline.retrieval import kg_retrieval


def test_index_preserves_raw_and_normalized_interventions(tmp_path: Path):
    (tmp_path / "edges_trial_gene.csv").write_text(
        "nct_id,gene_symbol,source\nNCT00000001,ERBB2,kg\n", encoding="utf-8"
    )
    (tmp_path / "edges_trial_drug.csv").write_text(
        "nct_id,drug_name_raw,drug_name_normalized\n"
        "NCT00000001,Trastuzumab deruxtecan (DS-8201a),TRASTUZUMAB\n",
        encoding="utf-8",
    )
    (tmp_path / "nodes_clinical_trials.csv").write_text(
        "nct_id,title,status,phase,conditions,keywords,interventions\n"
        "NCT00000001,T,RECRUITING,PHASE2,Breast Cancer,,Trastuzumab deruxtecan (DS-8201a)\n",
        encoding="utf-8",
    )
    index = TrialContextIndex.from_directory(tmp_path)
    record = index.lookup("NCT00000001")
    assert record is not None
    assert record.interventions_raw == ("Trastuzumab deruxtecan (DS-8201a)",)
    assert record.interventions_normalized == ("TRASTUZUMAB",)
    assert record.conditions == ("Breast Cancer",)
    assert record.provenance["nct_id"] == "NCT00000001"


def test_identity_mismatch_is_not_returned(tmp_path: Path):
    (tmp_path / "edges_trial_gene.csv").write_text(
        "nct_id,gene_symbol,source\nNCT00000001,ERBB2,kg\n", encoding="utf-8"
    )
    (tmp_path / "edges_trial_drug.csv").write_text(
        "nct_id,drug_name_raw,drug_name_normalized\n", encoding="utf-8"
    )
    (tmp_path / "nodes_clinical_trials.csv").write_text(
        "nct_id,title,status,phase,conditions,keywords,interventions\n",
        encoding="utf-8",
    )
    index = TrialContextIndex.from_directory(tmp_path)
    assert index.lookup("NCT99999999") is None


def test_missing_nct_is_safe(tmp_path: Path):
    index = TrialContextIndex.from_directory(tmp_path)
    assert index.lookup(None) is None


def test_trial_context_is_used_for_matching_but_not_evidence(tmp_path: Path, monkeypatch):
    (tmp_path / "edges_trial_gene.csv").write_text(
        "nct_id,gene_symbol,source\nNCT00000001,ERBB2,kg\n", encoding="utf-8"
    )
    (tmp_path / "edges_trial_drug.csv").write_text(
        "nct_id,drug_name_raw,drug_name_normalized\n"
        "NCT00000001,Trastuzumab deruxtecan (DS-8201a),TRASTUZUMAB\n",
        encoding="utf-8",
    )
    (tmp_path / "nodes_clinical_trials.csv").write_text(
        "nct_id,title,status,phase,conditions,keywords,interventions\n"
        "NCT00000001,T,RECRUITING,PHASE2,Breast Cancer,,Trastuzumab deruxtecan (DS-8201a)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RESEARCH_PIPELINE_TRIAL_CONTEXT_ROOT", str(tmp_path))
    load_trial_context_index.cache_clear()
    candidate = {
        "candidate_id": "gca",
        "biomarkers": [{"label": "ERBB2", "type": "Gene"}],
        "disease": [],
        "interventions": [],
        "document_identifiers": [{"nct": "NCT00000001", "scope": "clinical_trial"}],
        "graph_path": ["ClinicalTrial:NCT00000001", "Gene:ERBB2"],
        "source_properties": {},
        "predicate": "has_trial_association",
    }
    case = {
        "disease": {"normalized_value": "Breast Cancer"},
        "biomarkers": [{"gene": "ERBB2"}],
        "target_intervention": {"normalized_value": "Trastuzumab deruxtecan (DS-8201a)"},
        "query_intent": "THERAPY_EVALUATION",
    }
    ok, reasons = kg_retrieval._match_candidate(case, candidate)
    assert ok is True
    assert "INTERVENTION_COMPATIBLE" in reasons
    enriched, status = kg_retrieval.enrich_trial_candidate(candidate)
    assert status == "TRIAL_CONTEXT_AVAILABLE"
    assert enriched["trial_context"]["retrieval_only"] is True
    assert "efficacy" not in enriched["trial_context"]
    normalized_case = dict(case)
    normalized_case["target_intervention"] = {"normalized_value": "TRASTUZUMAB"}
    # A legacy lossy normalized drug field cannot equate a conjugate/regimen
    # with its different unconjugated ingredient.
    assert kg_retrieval._match_candidate(normalized_case, candidate)[0] is False


def test_trial_context_requires_conservative_disease_matching(tmp_path: Path, monkeypatch):
    (tmp_path / "edges_trial_gene.csv").write_text("nct_id,gene_symbol,source\nNCT00000001,ERBB2,kg\n", encoding="utf-8")
    (tmp_path / "edges_trial_drug.csv").write_text("nct_id,drug_name_raw,drug_name_normalized\n", encoding="utf-8")
    (tmp_path / "nodes_clinical_trials.csv").write_text("nct_id,title,status,phase,conditions,keywords,interventions\nNCT00000001,T,R,,Breast Cancer,,\n", encoding="utf-8")
    monkeypatch.setenv("RESEARCH_PIPELINE_TRIAL_CONTEXT_ROOT", str(tmp_path))
    load_trial_context_index.cache_clear()
    candidate = {"candidate_id":"gca", "source_properties":{}, "biomarkers":[{"label":"ERBB2","type":"Gene"}], "interventions":[], "disease":[], "document_identifiers":[{"nct":"NCT00000001"}]}
    case = {"disease":{"normalized_value":"Lung Cancer"}, "biomarkers":[{"gene":"ERBB2"}], "target_intervention":None, "query_intent":None}
    assert kg_retrieval._match_candidate(case, candidate)[0] is False


def test_structured_specificity_orders_exact_over_normalized_and_missing():
    exact = {
        "intervention_raw_exact": True, "intervention_normalized_match": False,
        "gene_exact": True, "disease_exact": True, "matched_anchor_count": 3,
        "populated_dimension_count": 3,
    }
    normalized = {
        "intervention_raw_exact": False, "intervention_normalized_match": True,
        "gene_exact": True, "disease_exact": True, "matched_anchor_count": 3,
        "populated_dimension_count": 3,
    }
    missing = {
        "intervention_raw_exact": False, "intervention_normalized_match": False,
        "gene_exact": True, "disease_exact": True, "matched_anchor_count": 2,
        "populated_dimension_count": 2,
    }
    assert kg_retrieval._specificity_order_key("exact", exact) < kg_retrieval._specificity_order_key("normalized", normalized)
    assert kg_retrieval._specificity_order_key("normalized", normalized) < kg_retrieval._specificity_order_key("missing", missing)


def test_nct03650894_target_is_before_family_cap(monkeypatch):
    monkeypatch.delenv("RESEARCH_PIPELINE_TRIAL_CONTEXT_ROOT", raising=False)
    load_trial_context_index.cache_clear()
    case = {
        "disease": {"normalized_value": "Breast Neoplasm Female"},
        "biomarkers": [{"gene": "ERBB2"}],
        "target_intervention": {"normalized_value": "Nivolumab"},
        "query_intent": "THERAPY_EVALUATION",
    }
    result = kg_retrieval.retrieve(case)
    ids = [row["candidate_id"] for row in result["associations"] if row["relation_family"] == "CLINICAL_TRIAL"]
    assert "GCA4-1ee5df252514f76a2a9cd3ef" in ids[:3]
