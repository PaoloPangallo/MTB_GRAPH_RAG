"""Pipeline reconciliation distinguishes accepted evidence from audit-only attempts."""

from backend.research_pipeline.dossier.accounting import build_pipeline_accounting
from backend.research_pipeline.dossier.builder import _paper_result_fields, evidence_id
from backend.research_pipeline.retrieval import kg_retrieval


def test_reconciliation_accounts_for_candidates_documents_reader_and_claims() -> None:
    retrieval = {
        "associations": [
            {"candidate_id": "P", "candidate_group_candidate_ids": ["P", "P2"]},
            {"candidate_id": "T", "candidate_group_candidate_ids": ["T"]},
        ],
        "excluded_candidates": [{"candidate_id": "X", "reason_codes": ["DISEASE_NOT_COMPATIBLE"]}],
        "retrieval_summary": {"gca4_source_candidate_count": 3,
                              "derived_composite_candidate_count": 1},
    }
    selections = [
        {"candidate_id": "P", "selected_papers": [{"document_id": "pmid:1"}],
         "excluded_papers": [{"document_id": "pmid:2", "reason_codes": ["TEXT_NOT_AVAILABLE_IN_CACHE"]}]},
        {"candidate_id": "T", "selected_papers": [{"document_id": "nct:NCT12345678"}],
         "excluded_papers": []},
    ]
    paper = {"P": {"evidence_records": [
        {"evidence_id": "E1", "reader_attempt_status": "READER_QUOTE_VALIDATED", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
         "quote_valid": True, "source_unit_id": "SU-1", "document_id": "pmid:1",
         "candidate_support": {"result": "FULL_SUPPORT"}},
        {"reader_attempt_status": "READER_PARSE_FAILED", "validation_outcome": "REJECTED_TRANSPORT",
         "quote_valid": False, "document_id": "pmid:2"},
    ]}}
    trial = {"T": {"reader_attempts": [{"reader_attempt_status": "READER_ABSTAINED"}]}}
    report = {"claims": [{"claim_id": "CP", "supporting_evidence_ids": ["E1"]}, {"claim_id": "CT"}]}
    accounting = build_pipeline_accounting(
        mention_accounting={"trial": {"parsed": 1, "accepted": 1, "rejected": 0}},
        retrieval_result=retrieval, selections=selections,
        paper_results=paper, trial_results=trial, report=report,
    )
    assert accounting["parsed_mentions"]["trial"]["parsed"] == 1
    assert len(accounting["retrieved_candidates"]["used"]) == 3
    assert accounting["retrieved_candidates"]["excluded"][0]["reason"] == "DISEASE_NOT_COMPATIBLE"
    assert accounting["retrieved_candidates"]["duplicate_accounting_ids"] == []
    assert len(accounting["selected_documents"]["used"]) == 2
    assert accounting["selected_documents"]["excluded"][0]["reason"] == "TEXT_NOT_AVAILABLE_IN_CACHE"
    assert accounting["reader_attempts"]["total"] == 3
    assert accounting["accepted_evidence"]["count"] == 1
    assert accounting["rejected_or_failed_evidence"]["count"] == 2
    assert accounting["reader_attempts"]["total"] == (
        accounting["accepted_evidence"]["count"]
        + accounting["rejected_or_failed_evidence"]["count"]
    )
    assert accounting["final_claims"]["count"] == 2
    assert accounting["accepted_evidence"]["unclaimed_ids"] == []


def test_invalid_provenance_candidate_is_explicitly_excluded(monkeypatch) -> None:
    candidate = {"candidate_id": "MIXED", "document_identifiers": [
        {"pmid": "123"}, {"nct": "NCT12345678"},
    ]}
    monkeypatch.setattr(kg_retrieval, "load_candidates", lambda: {"MIXED": candidate})
    result = kg_retrieval.retrieve({"biomarkers": [{"gene": "EGFR"}]})
    accounting = build_pipeline_accounting(
        mention_accounting={}, retrieval_result=result, selections=[],
        paper_results={}, trial_results={}, report={"claims": []},
    )
    assert accounting["retrieved_candidates"]["considered"] == 1
    assert accounting["retrieved_candidates"]["unaccounted_count"] == 0
    assert accounting["retrieved_candidates"]["excluded"][0]["reason"] == "INVALID_PROVENANCE"


def test_no_match_still_has_complete_zero_downstream_accounting() -> None:
    accounting = build_pipeline_accounting(
        mention_accounting={},
        retrieval_result={"associations": [], "excluded_candidates": [
            {"candidate_id": "C", "reason_codes": ["NO_MATCH"]}],
            "retrieval_summary": {"gca4_source_candidate_count": 1,
                                  "derived_composite_candidate_count": 0}},
        selections=[], paper_results={}, trial_results={}, report={"claims": []},
    )
    assert accounting["retrieved_candidates"]["unaccounted_count"] == 0
    assert accounting["selected_documents"]["used"] == []
    assert accounting["reader_attempts"]["total"] == 0
    assert accounting["final_claims"]["count"] == 0


def test_rejected_attempt_keeps_same_id_after_quote_redaction() -> None:
    attempt = {
        "candidate_id": "P", "document_id": "pmid:1", "source_unit_id": "SU-1",
        "quote": "Unvalidated proposed quote", "quote_valid": False,
        "validation_outcome": "REJECTED_QUOTE", "reader_attempt_status": "VALIDATOR_REJECTED",
    }
    projected = _paper_result_fields({"evidence_records": [attempt]})
    rejected = projected["rejected_evidence"][0]
    assert rejected["evidence_id"] == evidence_id(attempt)
    assert "quote" not in rejected


def test_insufficient_information_is_claimed_and_reader_records_get_dispositions() -> None:
    record = {
        "candidate_id": "P", "document_id": "pmid:10", "source_unit_id": "SU-10",
        "quote": "Study reports an association.", "quote_valid": True,
        "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
        "candidate_support": {"result": "INSUFFICIENT_INFORMATION"},
    }
    projected = _paper_result_fields({"evidence_records": [record]})
    report = {"claims": [{
        "claim_id": "CP", "insufficient_information_evidence_ids": [evidence_id(record)],
    }]}
    result = build_pipeline_accounting(
        mention_accounting={}, retrieval_result={"associations": [], "retrieval_summary": {}},
        selections=[], paper_results={"P": projected}, trial_results={}, report=report,
    )
    assert result["accepted_evidence"]["unclaimed_ids"] == []
    assert result["final_claims"]["unknown_evidence_ids"] == []
    assert result["reader_attempts"]["records"][0]["support_result"] == "INSUFFICIENT_INFORMATION"
    assert result["reader_attempts"]["records"][0]["disposition"] == "ADMITTED_TO_DOSSIER"


def test_accounting_distinguishes_technical_rejection_from_not_evaluated() -> None:
    technical = {"candidate_id": "P", "document_id": "pmid:1", "validation_outcome": "REJECTED_TRANSPORT",
                 "reader_attempt_status": "READER_PARSE_FAILED"}
    not_evaluated = {"candidate_id": "P", "document_id": "pmid:2", "validation_outcome": "NOT_EVALUATED",
                     "reader_attempt_status": "NOT_RUN"}
    result = build_pipeline_accounting(
        mention_accounting={}, retrieval_result={"associations": [], "retrieval_summary": {}}, selections=[],
        paper_results={"P": {"evidence_records": [technical, not_evaluated]}}, trial_results={}, report={"claims": []},
    )
    dispositions = {item["reader_attempt_status"]: item["disposition"]
                    for item in result["reader_attempts"]["records"]}
    assert dispositions["READER_PARSE_FAILED"] == "TECHNICAL_ERROR"
    assert dispositions["NOT_RUN"] == "NOT_EVALUATED"


def test_admitted_unverifiable_record_keeps_verification_failure_distinct() -> None:
    records = []
    for document_id, verification_status, final_admission in (
        ("pmid:technical", "TECHNICAL_ERROR", "TECHNICAL_ERROR"),
        ("pmid:not-run", "SEMANTIC_ASSESSMENT_NOT_RUN", "UNVERIFIABLE"),
    ):
        record = {
            "candidate_id": "P", "document_id": document_id,
            "paper_id": document_id, "source_unit_id": f"SU-{document_id}",
            "quote": "A validated source sentence.", "quote_valid": True,
            "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
            "candidate_support": {"result": "UNVERIFIABLE"},
            "document_verification": {
                "verification_status": verification_status,
                "final_admission": final_admission,
                "admission_reason_codes": [verification_status],
            },
        }
        records.append(record)
    result = build_pipeline_accounting(
        mention_accounting={}, retrieval_result={"associations": [], "retrieval_summary": {}},
        selections=[], paper_results={"P": {"evidence_records": records}},
        trial_results={}, report={"claims": []},
    )
    by_doc = {item["document_id"]: item for item in result["reader_attempts"]["records"]}
    assert by_doc["pmid:technical"]["disposition"] == "ADMITTED_TO_DOSSIER"
    assert by_doc["pmid:technical"]["verification_disposition"] == "TECHNICAL_ERROR"
    assert by_doc["pmid:not-run"]["disposition"] == "ADMITTED_TO_DOSSIER"
    assert by_doc["pmid:not-run"]["verification_disposition"] == "NOT_EVALUATED"
    assert all(item["support_result"] == "UNVERIFIABLE" for item in by_doc.values())
