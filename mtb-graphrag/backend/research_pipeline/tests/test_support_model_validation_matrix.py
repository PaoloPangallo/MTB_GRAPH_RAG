"""Scenario matrix for the support contract; assessments are controlled, not model output."""

from __future__ import annotations

import pytest

from backend.research_pipeline.enrichment.document_verification import admit
from backend.research_pipeline.tests.test_document_verification import _structural
from backend.research_pipeline.tests.test_semantic_admission_contract import assessment


@pytest.mark.parametrize("phrase,claim,changes,expected,verification_status", [
    (
        "EGFR L858R showed sensitivity to erlotinib in lung cancer.",
        "EGFR L858R is sensitive to erlotinib in lung cancer.",
        {}, "FULL_SUPPORT", "ASSESSED",
    ),
    (
        "In a subgroup of patients with EGFR L858R lung cancer, response to erlotinib was observed.",
        "Patients with EGFR L858R lung cancer respond to erlotinib.",
        {"population_scope": "NARROWER", "population_span": "a subgroup of patients"},
        "PARTIAL_SUPPORT", "ASSESSED",
    ),
    (
        "EGFR L858R did not show sensitivity to erlotinib in lung cancer.",
        "EGFR L858R is sensitive to erlotinib in lung cancer.",
        {"relation_alignment": "OPPOSITE"}, "CONTRADICTORY", "ASSESSED",
    ),
    (
        "No response association was observed for EGFR L858R with erlotinib in lung cancer.",
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        {"relation_alignment": "NO_SUPPORT", "reason": "No association was observed."},
        "NO_SUPPORT", "ASSESSED",
    ),
    (
        "EGFR L858R and erlotinib were studied in lung cancer.",
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        {"relation_alignment": "INSUFFICIENT", "evidence_role": "UNKNOWN",
         "molecular_scope": "UNKNOWN", "population_scope": "UNKNOWN",
         "intervention_scope": "UNKNOWN", "inference": "UNKNOWN", "certainty": "UNKNOWN"},
        "INSUFFICIENT_INFORMATION", "ASSESSED",
    ),
    (
        "In cell lines, EGFR L858R showed sensitivity to erlotinib in lung cancer.",
        "A patient with EGFR L858R lung cancer will benefit from erlotinib.",
        {}, "FULL_SUPPORT", "ASSESSED",
    ),
    (
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        {"population_scope": "DIFFERENT"}, "UNVERIFIABLE", "ASSESSED",
    ),
    (
        "EGFR L858R and erlotinib were discussed; EGFR L858R was associated with longer survival in lung cancer.",
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        {"relation_alignment": "INSUFFICIENT", "evidence_role": "UNKNOWN",
         "inference": "UNKNOWN", "certainty": "UNKNOWN"},
        "INSUFFICIENT_INFORMATION", "ASSESSED",
    ),
    (
        "Patients with EGFR L858R lung cancer were eligible for an erlotinib trial.",
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        {"evidence_role": "ELIGIBILITY"}, "UNVERIFIABLE", "ASSESSED",
    ),
    (
        "EGFR L858R and erlotinib were mentioned in a lung cancer methods section.",
        "EGFR L858R predicts response to erlotinib in lung cancer.",
        {"relation_alignment": "INSUFFICIENT", "evidence_role": "UNKNOWN",
         "molecular_scope": "UNKNOWN", "population_scope": "UNKNOWN",
         "intervention_scope": "UNKNOWN", "inference": "UNKNOWN", "certainty": "UNKNOWN"},
        "INSUFFICIENT_INFORMATION", "ASSESSED",
    ),
])
def test_support_validation_scenarios(phrase, claim, changes, expected, verification_status):
    context = {"disease": "lung cancer", "biomarkers": [
        {"gene": "EGFR", "alteration": "L858R"},
    ]}
    structural = _structural(phrase, case_context=context)
    result = admit(structural, assessment(phrase, **changes))

    assert result["support_result"] == expected, {"claim": claim, "result": result}
    assert result["verification_status"] == verification_status
    if expected == "PARTIAL_SUPPORT":
        assert result["support_limitation"]["population_scope"]["literal_span"] == "a subgroup of patients"
        assert result["final_admission"] == "PARTIALLY_SUPPORTED"
    if phrase.startswith("In cell lines"):
        assert result["study_context"] == "PRECLINICAL_CELL"
        assert result["applicability_to_case"] == "LIMITED_PRECLINICAL"


@pytest.mark.parametrize("structural_status,reason,expected_status", [
    ("UNRESOLVED", "POSSIBLE_MULTI_AGENT_INTERVENTION", "STRUCTURAL_AMBIGUITY"),
    ("MISMATCH", "VARIANT_IDENTITY_MISMATCH", "STRUCTURAL_INCOMPATIBILITY"),
])
def test_structural_gate_does_not_create_a_scientific_judgment(
    structural_status, reason, expected_status,
):
    structural = _structural("EGFR L858R showed sensitivity to erlotinib in lung cancer.")
    structural["structural_status"] = structural_status
    structural["structural_reason_codes"] = [reason]
    result = admit(structural, None)
    assert result["support_result"] == "UNVERIFIABLE"
    assert result["verification_status"] == expected_status
    assert result["final_admission"] == "NOT_RUN_STRUCTURAL"


@pytest.mark.parametrize("semantic,expected,status", [
    ({"relation_alignment": "AMBIGUOUS", "assertion_scope": "UNKNOWN",
      "reason": "SEMANTIC_PROVIDER_FAILURE:TimeoutError", "decisive_text": ""},
     "UNVERIFIABLE", "TECHNICAL_ERROR"),
])
def test_technical_failure_is_not_a_scientific_absence(semantic, expected, status):
    result = admit(_structural("EGFR L858R showed sensitivity to erlotinib in lung cancer."), semantic)
    assert result["support_result"] == expected
    assert result["verification_status"] == status


def test_missing_semantic_assessment_is_not_reported_as_assessed():
    result = admit(_structural("EGFR L858R showed sensitivity to erlotinib in lung cancer."), None)
    assert result["support_result"] == "UNVERIFIABLE"
    assert result["verification_status"] == "SEMANTIC_ASSESSMENT_NOT_RUN"
    assert "SEMANTIC_ASSESSMENT_MISSING" in result["admission_reason_codes"]


def test_dossier_preserves_support_scope_conflict_and_failure_provenance():
    from backend.research_pipeline.dossier.builder import aggregate_evidence_records

    text = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
    partial_text = "In a subgroup of patients with EGFR L858R lung cancer, response to erlotinib was observed."
    assessments = [
        admit(_structural(text), assessment(text)),
        admit(_structural(partial_text), assessment(
            partial_text, population_scope="NARROWER", population_span="a subgroup of patients")),
        admit(_structural(text), assessment(text, relation_alignment="OPPOSITE")),
        admit(_structural(text), None),
        admit({**_structural(text), "structural_status": "MISMATCH",
               "structural_reason_codes": ["VARIANT_IDENTITY_MISMATCH"]}, None),
        admit(_structural(text), {"relation_alignment": "AMBIGUOUS", "assertion_scope": "UNKNOWN",
                                  "reason": "SEMANTIC_PROVIDER_FAILURE:TimeoutError",
                                  "decisive_text": ""}),
    ]
    records = [{
        "evidence_id": f"EV-{i}", "relation_family": "EVIDENCE_DRUG",
        "validation_outcome": "ENRICHMENT_V3_ACCEPTED", "quote_valid": True,
        "source_unit_id": f"SU-{i}", "document_id": "pmid:12345678",
        "candidate_support": {"result": item["support_result"]},
        "document_verification": item,
    } for i, item in enumerate(assessments)]

    dossier = aggregate_evidence_records(records)
    assert dossier["full_evidence_ids"] == ["EV-0"]
    assert dossier["partial_evidence_ids"] == ["EV-1"]
    assert dossier["contradicting_evidence_ids"] == ["EV-2"]
    assert dossier["unverifiable_evidence_ids"] == ["EV-3", "EV-4", "EV-5"]
    assert dossier["structurally_blocked_evidence_ids"] == ["EV-4"]
    assert dossier["technical_error_evidence_ids"] == ["EV-5"]
    partial = next(item for item in dossier["evidence_records"] if item["evidence_id"] == "EV-1")
    assert partial["document_verification"]["support_limitation"]["population_scope"]["literal_span"] == "a subgroup of patients"
