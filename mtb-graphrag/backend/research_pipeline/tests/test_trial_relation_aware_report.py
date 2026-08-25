import json

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache
from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates


GCA_ID = "GCA-bd12d81e3b8b2f67728ca364"
NCT_ID = "NCT05176665"


def test_real_nct_resolver_record_reaches_relation_aware_report(tmp_path, monkeypatch):
    candidate = load_candidates()[GCA_ID]
    payload = {
        "protocolSection": {
            "identificationModule": {
                "briefTitle": "EMB-01 in Patients With Advanced/Metastatic Gastrointestinal Cancers"
            },
            "statusModule": {"overallStatus": "RECRUITING"},
            "designModule": {"phases": ["PHASE1", "PHASE2"]},
            "conditionsModule": {"conditions": ["Advanced Gastrointestinal Cancer"]},
            "armsInterventionsModule": {"interventions": [{"name": "EMB-01", "type": "DRUG"}]},
        }
    }
    cache = AuthorizedDocumentCache(tmp_path, network=False)
    monkeypatch.setattr(
        cache,
        "_request",
        lambda url: (json.dumps(payload).encode("utf-8"), {"attempt": 1, "status": 200, "url": url}),
    )

    record = cache.resolve_nct(NCT_ID)
    assert record["availability"] == "METADATA_ONLY"
    assert record["document_id"] == f"nct:{NCT_ID}"
    assert (tmp_path / record["local_cache_path"]).is_file()
    assert record["title"]
    assert record["conditions"]
    assert record["interventions"]

    report = build_relation_aware_report(
        {"case_id": "CASE-TRIAL", "disease": {"raw_value": "gastrointestinal cancer"}},
        [candidate],
        trial_results={candidate["candidate_id"]: record},
    )
    entry = report["clinical_trials"][0]

    assert entry["nct_id"] == NCT_ID
    assert entry["title"] == record["title"]
    assert entry["status"] == "RECRUITING"
    assert entry["phase"] == ["PHASE1", "PHASE2"]
    assert entry["conditions"] == record["conditions"]
    assert entry["interventions"] == record["interventions"]
    assert entry["source"] == "ClinicalTrials.gov API v2"
    assert entry["provenance_status"] == "TRIAL_RECORD_RESOLVED"
    assert entry["eligibility_status"] == "NOT_EVALUATED"
    assert entry["evidence_interpretation"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    serialized = json.dumps(report, sort_keys=True).lower()
    assert "therapy supported" not in serialized
    assert "therapy effective" not in serialized
    assert "patient eligible" not in serialized
    assert "recommended therapy" not in serialized
