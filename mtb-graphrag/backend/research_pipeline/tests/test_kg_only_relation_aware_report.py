from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates, retrieve


GENE_DRUG_ID = "GCA-6cb3e69e2badaaf63cdb75bd"
COMPANION_ID = "GCA-7891d9f9f7fd9b803ce6e792"


def _case(gene, *, drug=None, intent="BIOMARKER_INTERPRETATION"):
    value = {
        "case_id": f"CASE-{gene}",
        "disease": {"raw_value": "unspecified cancer"},
        "biomarkers": [{"gene": gene}],
        "query_intent": intent,
    }
    if drug:
        value["target_intervention"] = {"raw_value": drug}
    return value


def test_real_gene_drug_kg_only_survives_retrieval_and_reaches_report():
    candidates = load_candidates()
    result = retrieve(_case("CYP2D6", drug="RACLOPRIDE", intent="THERAPY_EVALUATION"))
    association = next(item for item in result["associations"] if item["candidate_id"] == GENE_DRUG_ID)
    entry = build_relation_aware_report({}, [association["candidate"]])["kg_only_relations"][0]

    assert association["relation_family"] == "KG_ONLY"
    assert entry["candidate_id"] == GENE_DRUG_ID
    assert entry["source_database"] == "DTC"
    assert entry["graph_provenance"]["node_ids"] == candidates[GENE_DRUG_ID]["node_ids"]
    assert entry["graph_provenance"]["edge_ids"] == candidates[GENE_DRUG_ID]["edge_ids"]
    assert entry["document_id"] is None
    assert entry["document_provenance"] == "NOT_AVAILABLE"
    assert entry["verification_status"] == "KG_ONLY"
    assert "quote" not in entry
    assert "support_level" not in entry
    assert COMPANION_ID not in {item["candidate_id"] for item in result["associations"]}


def test_real_companion_diagnostic_is_admitted_to_retrieval_without_enrichment(monkeypatch):
    candidates = load_candidates()
    def match_only_target(case_context, candidate):
        if candidate["candidate_id"] == COMPANION_ID:
            return True, ["BIOMARKER_COMPATIBLE"]
        return False, ["UNRELATED_TO_TEST_CASE"]

    monkeypatch.setattr(kg_retrieval, "_match_candidate", match_only_target)
    result = retrieve(_case("IDH1"))
    association = next(item for item in result["associations"] if item["candidate_id"] == COMPANION_ID)
    report = build_relation_aware_report({}, [association["candidate"]])
    entry = report["kg_only_relations"][0]

    assert association["relation_family"] == "KG_ONLY"
    assert entry["relation"] == "has_companion_diagnostic"
    assert entry["object"]["type"] == "CompanionDiagnostic"
    assert entry["source_database"] == "KG"
    assert entry["graph_provenance"]["graph_path"] == candidates[COMPANION_ID]["graph_path"]
    assert entry["document_id"] is None
    assert entry["verification_status"] == "KG_ONLY"
    assert entry["document_provenance"] == "NOT_AVAILABLE"
    assert report["limitations"] == ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"]


def test_unrelated_kg_only_candidate_remains_filtered_and_report_is_not_evidence():
    result = retrieve(_case("CYP2D6", drug="RACLOPRIDE", intent="THERAPY_EVALUATION"))
    returned_ids = {item["candidate_id"] for item in result["associations"]}

    assert GENE_DRUG_ID in returned_ids
    assert COMPANION_ID not in returned_ids
