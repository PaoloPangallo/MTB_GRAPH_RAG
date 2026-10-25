from backend.research_pipeline.documents.trial_resolution import resolve_trial_record
from backend.research_pipeline.dossier.builder import build_relation_aware_report


def paper_candidate():
    return {
        "candidate_id": "GCA-P", "subject": "BRAF", "predicate": "has_evidence_statement",
        "object": "vemurafenib", "document_identifiers": [{"pmid": "123"}],
        "biomarkers": [], "interventions": [], "disease": [],
    }


def trial_candidate():
    return {
        "candidate_id": "GCA-T", "subject": "ERBB2", "predicate": "investigated_in",
        "object": "trastuzumab", "document_identifiers": [{"nct": "NCT00000001"}],
        "biomarkers": [], "interventions": [], "disease": [],
    }


def test_trial_resolver_accepts_matching_identity_with_verified_payload_without_disease():
    result = resolve_trial_record("NCT00000001", {
        "document_id": "nct:NCT00000001", "nct_id": "NCT00000001",
        "availability": "METADATA_ONLY",
        "conditions": [], "interventions": ["trastuzumab"], "source": "ClinicalTrials.gov",
    }, resolved_payload=True)
    assert result["trial_resolution_status"] == "AVAILABLE"
    assert result["resolved_nct_id"] == "NCT00000001"


def test_matching_trial_identity_without_payload_is_not_available():
    result = resolve_trial_record("NCT00000001", {
        "document_id": "nct:NCT00000001", "nct_id": "NCT00000001",
    })
    assert result["trial_resolution_status"] != "AVAILABLE"


def test_trial_resolver_rejects_mismatched_identity():
    result = resolve_trial_record("NCT00000001", {
        "document_id": "nct:NCT99999999", "nct_id": "NCT99999999",
    })
    assert result["trial_resolution_status"] == "INVALID_IDENTITY"


def test_trial_resolver_marks_missing_record_unavailable():
    assert resolve_trial_record("NCT00000001", None)["trial_resolution_status"] == "UNAVAILABLE"


def test_paper_dossier_separates_declared_from_unresolved_identity():
    report = build_relation_aware_report({}, [paper_candidate()], paper_results={})
    entry = report["paper_evidence"][0]
    assert entry["declared_source_identity"] == "pmid:123"
    assert entry["resolved_source_identity"] is None
    assert entry["document_resolution_status"] == "UNAVAILABLE"


def test_paper_dossier_exposes_resolved_identity_only_when_confirmed():
    report = build_relation_aware_report({}, [paper_candidate()], paper_results={
        "GCA-P": {"document_id": "pmid:123", "document_resolution_status": "RESOLVED"}
    })
    entry = report["paper_evidence"][0]
    assert entry["declared_source_identity"] == "pmid:123"
    assert entry["resolved_source_identity"] == "pmid:123"
