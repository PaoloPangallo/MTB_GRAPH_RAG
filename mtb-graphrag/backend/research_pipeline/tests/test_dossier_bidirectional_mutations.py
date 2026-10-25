from __future__ import annotations

from copy import deepcopy

import pytest

from backend.research_pipeline.dossier.accounting import build_pipeline_accounting
from backend.research_pipeline.dossier.builder import evidence_id


def _fixture(support="PARTIAL_SUPPORT"):
    record = {
        "candidate_id": "C", "document_id": "PMID:42", "paper_id": "PMID:42",
        "source_unit_id": "SU-42", "quote": "Observed in a preclinical model.",
        "quote_valid": True, "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
        "candidate_support": {"result": support},
        "document_verification": {"support_limitation": {"experimental_scope": {
            "literal_span": "in a preclinical model",
        }}},
    }
    record["evidence_id"] = evidence_id(record)
    field = {"FULL_SUPPORT": "supporting_evidence_ids", "PARTIAL_SUPPORT": "partial_evidence_ids",
             "CONTRADICTORY": "contradicting_evidence_ids"}[support]
    claim = {"claim_id": "CL-C", "candidate_id": "C", field: [record["evidence_id"]],
             "evidence_assessments": [{
                 "evidence_id": record["evidence_id"], "paper_id": record["paper_id"],
                 "document_id": record["document_id"], "source_unit_id": record["source_unit_id"],
                 "quote_valid": True, "quote": record["quote"], "support_result": support,
                 "support_limitation": record["document_verification"]["support_limitation"],
             }]}
    inputs = {
        "mention_accounting": {}, "retrieval_result": {"associations": [], "retrieval_summary": {}},
        "selections": [], "paper_results": {"C": {"evidence_records": [record]}},
        "trial_results": {}, "report": {"claims": [claim]},
    }
    return inputs, record


def _status(inputs):
    result = build_pipeline_accounting(**inputs)
    return result["bidirectional_reconciliation"]


def test_valid_dossier_has_no_false_alarm():
    inputs, _ = _fixture()
    result = _status(inputs)
    assert result["status"] == "PASS"
    assert result["reason_codes"] == []


def test_claim_cannot_attach_an_admitted_id_to_another_candidate():
    inputs, _ = _fixture()
    inputs["report"]["claims"][0]["candidate_id"] = "OTHER"
    result = _status(inputs)
    assert result["status"] == "FAIL"
    assert any(item["field"] == "candidate_id" for item in result["assessment_mismatches"])


def test_legacy_claim_without_assessment_is_not_marked_pass():
    inputs, _ = _fixture()
    inputs["report"]["claims"][0].pop("evidence_assessments")
    result = _status(inputs)
    assert result["status"] == "LEGACY_UNVERIFIED"
    assert "LEGACY_ASSESSMENT_FIELDS_ABSENT" in result["reason_codes"]


def test_missing_canonical_source_record_fails_assessment_reconciliation():
    inputs, _ = _fixture()
    inputs["paper_results"]["C"]["evidence_records"] = []
    result = _status(inputs)
    assert result["status"] == "FAIL"
    assert "ASSESSMENT_SOURCE_RECORD_MISSING" in result["reason_codes"]


@pytest.mark.parametrize("mutation", [
    "citation_replaced", "partial_promoted", "limitation_removed", "contradiction_omitted",
    "wrong_pmid", "duplicate_evidence", "admitted_record_omitted",
])
def test_controlled_dossier_mutations_are_detected(mutation):
    inputs, record = _fixture("CONTRADICTORY" if mutation == "contradiction_omitted" else "PARTIAL_SUPPORT")
    inputs = deepcopy(inputs)
    claim = inputs["report"]["claims"][0]
    assessment = claim["evidence_assessments"][0]
    if mutation == "citation_replaced":
        assessment["quote"] = "A different sentence."
    elif mutation == "partial_promoted":
        claim.pop("partial_evidence_ids")
        claim["supporting_evidence_ids"] = [record["evidence_id"]]
        assessment["support_result"] = "FULL_SUPPORT"
    elif mutation == "limitation_removed":
        assessment.pop("support_limitation")
    elif mutation == "contradiction_omitted":
        claim.pop("contradicting_evidence_ids")
        claim["evidence_assessments"] = []
    elif mutation == "wrong_pmid":
        assessment["paper_id"] = "PMID:999"
        assessment["document_id"] = "PMID:999"
    elif mutation == "duplicate_evidence":
        inputs["paper_results"]["C"]["evidence_records"].append(deepcopy(record))
    elif mutation == "admitted_record_omitted":
        claim["partial_evidence_ids"] = []
        claim["evidence_assessments"] = []
    result = _status(inputs)
    assert result["status"] == "FAIL", result
