"""Every Reader invocation remains attributable after validation and aggregation."""

from backend.research_pipeline.dossier.builder import aggregate_evidence_records
from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.orchestrator import _reader_attempt_record


def test_failed_reader_before_success_does_not_steal_next_validation() -> None:
    failed = _reader_attempt_record(
        {"transport_result": "INVALID_TOOL_ARGUMENTS", "enrichment": None,
         "transport_reason_codes": ["ARGUMENTS_NOT_JSON"]},
        {"candidate_id": "C1", "paper_id": "pmid:1",
         "outcome": "REJECTED_TRANSPORT", "reason_codes": ["INVALID_TOOL_ARGUMENTS"]},
        document_id="pmid:1", gate_accepted=False,
    )
    accepted = _reader_attempt_record(
        {"transport_result": "V3_TRANSPORT_VALID",
         "enrichment": {"decision": "QUOTE", "quote": "EGFR supports erlotinib.",
                        "source_unit_id": "SU-2"}},
        {"candidate_id": "C1", "paper_id": "pmid:2",
         "outcome": "ENRICHMENT_V3_ACCEPTED", "reason_codes": [],
         "candidate_support": {"result": "FULL_SUPPORT"}},
        document_id="pmid:2", gate_accepted=True,
    )
    records = [failed, accepted]
    aggregate = aggregate_evidence_records(records)
    assert failed["reader_attempt_status"] == "READER_PARSE_FAILED"
    assert failed["candidate_support"] is None
    assert failed["document_id"] == "pmid:1"
    assert accepted["candidate_support"]["result"] == "FULL_SUPPORT"
    assert accepted["document_id"] == "pmid:2"
    assert aggregate["support_level"] == "FULL_SUPPORT"
    assert len(aggregate["evidence_records"]) == 1
    assert len(aggregate["rejected_evidence"]) == 1
    assert aggregate["rejected_evidence"][0]["reader_attempt_status"] == "READER_PARSE_FAILED"
    assert len(records) == len(aggregate["evidence_records"]) + len(aggregate["rejected_evidence"])


def test_abstention_and_transport_failure_are_accounted_but_not_support() -> None:
    attempts = [
        _reader_attempt_record(
            {"transport_result": "V3_TRANSPORT_VALID", "enrichment": {"decision": "ABSTAIN"}},
            {"candidate_id": "C", "paper_id": "pmid:1", "outcome": "ENRICHMENT_V3_ABSTAINED"},
            document_id="pmid:1", gate_accepted=False,
        ),
        _reader_attempt_record(
            {"transport_result": "HTTP_ERROR", "enrichment": None},
            {"candidate_id": "C", "paper_id": "pmid:2", "outcome": "REJECTED_TRANSPORT"},
            document_id="pmid:2", gate_accepted=False,
        ),
    ]
    assert [item["reader_attempt_status"] for item in attempts] == [
        "READER_ABSTAINED", "READER_TRANSPORT_FAILED",
    ]
    aggregate = aggregate_evidence_records(attempts)
    assert aggregate["support_level"] == "UNVERIFIABLE"
    assert len(aggregate["rejected_evidence"]) == 2


def test_failed_first_attempt_cannot_hide_later_validated_quote_in_dossier() -> None:
    candidate = {"candidate_id": "C", "predicate": "has_evidence_statement",
                 "document_identifiers": [{"pmid": "123"}]}
    failed = _reader_attempt_record(
        {"transport_result": "INVALID_TOOL_ARGUMENTS", "enrichment": None},
        {"candidate_id": "C", "paper_id": "pmid:1", "outcome": "REJECTED_TRANSPORT"},
        document_id="pmid:1", gate_accepted=False,
    )
    accepted = _reader_attempt_record(
        {"transport_result": "V3_TRANSPORT_VALID", "enrichment": {
            "decision": "QUOTE", "quote": "EGFR supports erlotinib.", "source_unit_id": "SU-2",
        }},
        {"candidate_id": "C", "paper_id": "pmid:2", "outcome": "ENRICHMENT_V3_ACCEPTED",
         "candidate_support": {"result": "FULL_SUPPORT"}},
        document_id="pmid:2", gate_accepted=True,
        source_unit_text="EGFR supports erlotinib.",
    )
    report = build_relation_aware_report({}, [candidate], paper_results={
        "C": {"evidence_records": [failed, accepted], "quote_valid": False,
              "validation": {"outcome": "REJECTED_TRANSPORT"}}
    })
    entry = report["paper_evidence"][0]
    assert entry["claim"]["status"] == "FULL_SUPPORT"
    assert entry["quote_valid"] is True
    assert entry["quote"] == "EGFR supports erlotinib."
    assert entry["document_id"] == "pmid:2"
    assert entry["quote_source_unit_id"] == "SU-2"
