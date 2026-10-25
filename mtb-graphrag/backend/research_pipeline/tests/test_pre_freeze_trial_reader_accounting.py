"""Trial Reader observations are audit metadata, never efficacy support."""

from backend.research_pipeline.dossier.builder import build_relation_aware_report


def test_trial_reader_attempt_is_visible_without_efficacy_escalation() -> None:
    candidate = {
        "candidate_id": "T1", "predicate": "investigated_in",
        "document_identifiers": [{"nct": "NCT12345678"}],
        "source_record_ids": ["trial-row:1"],
        "source_datasets": ["edge_trial.csv"],
    }
    attempt = {
        "candidate_id": "T1", "document_id": "nct:NCT12345678",
        "reader_attempt_status": "READER_ABSTAINED",
        "validation_outcome": "ENRICHMENT_V3_ABSTAINED",
    }
    report = build_relation_aware_report({}, [candidate], trial_results={
        "T1": {"trial_resolution_status": "AVAILABLE", "resolved_nct_id": "NCT12345678",
               "provenance_status": "TRIAL_RECORD_RESOLVED", "reader_attempts": [attempt]}
    })
    entry = report["clinical_trials"][0]
    assert entry["reader_attempts"] == [attempt]
    assert entry["claim"]["status"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    assert entry["claim"]["supporting_evidence_ids"] == []


def test_raw_failed_trial_result_cannot_be_labeled_available_by_dossier() -> None:
    candidate = {"candidate_id": "T", "predicate": "investigated_in",
                 "document_identifiers": [{"nct": "NCT12345678"}]}
    entry = build_relation_aware_report({}, [candidate], trial_results={
        "T": {"document_id": "nct:NCT12345678", "availability": "RESOLUTION_FAILED"}
    })["clinical_trials"][0]
    assert entry["trial_resolution_status"] == "RESOLUTION_FAILED"
    assert entry["provenance_status"] != "TRIAL_RECORD_RESOLVED"
