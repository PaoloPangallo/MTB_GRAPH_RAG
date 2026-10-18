"""Controlled contract tests, not independently annotated semantic accuracy."""

from copy import deepcopy

import pytest

from backend.research_pipeline.enrichment.document_verification import admit
from backend.research_pipeline.enrichment.semantic_alignment import validate_output
from backend.research_pipeline.dossier.builder import is_aggregation_eligible


TEXT = "AXR1 mutation showed sensitivity to agent-x in lung cancer."


def assessment(text=TEXT, **changes):
    """Explicit current-contract fixture; never upgrades recorded model output."""
    return {
        "relation_alignment": "SAME", "assertion_scope": "DIRECT_ASSERTION",
        "reason": "controlled assessment", "decisive_text": text,
        "evidence_role": "OBSERVED_RESULT", "molecular_scope": "SAME",
        "population_scope": "SAME", "intervention_scope": "SAME",
        "inference": "DIRECT", "certainty": "ESTABLISHED",
        "result_span": text, "molecular_span": text,
        "population_span": text, "intervention_span": text,
        **changes,
    }


def structural(text=TEXT):
    return {"structural_status": "PASS", "target_snapshot": {},
            "GEP_snapshot": {"required_context": text, "proposition": text}}


@pytest.mark.parametrize("alignment", ["SAME", "OPPOSITE"])
@pytest.mark.parametrize("dimension,value", [
    ("evidence_role", "STUDY_DESIGN"), ("evidence_role", "ELIGIBILITY"),
    ("evidence_role", "BACKGROUND"),
    ("molecular_scope", "BROADER"),
    ("population_scope", "DIFFERENT"), ("intervention_scope", "COMBINATION"),
    ("inference", "INVERSE"), ("inference", "INDIRECT"),
    ("certainty", "UNCERTAIN"), ("certainty", "UNKNOWN"),
])
def test_same_or_opposite_cannot_override_a_failed_dimension(alignment, dimension, value):
    result = admit(structural(), assessment(relation_alignment=alignment, **{dimension: value}))
    assert result["final_admission"] == "UNVERIFIABLE"
    assert result["admission_reason_codes"]


@pytest.mark.parametrize("dimension,span", [
    ("molecular_scope", "AXR1 mutation"),
    ("population_scope", "lung cancer"),
])
def test_direct_observed_relation_with_literal_narrower_scope_is_partial(dimension, span):
    result = admit(structural(), assessment(**{dimension: "NARROWER",
                                               dimension.replace("scope", "span"): span}))
    assert result["final_admission"] == "PARTIALLY_SUPPORTED"
    assert result["support_result"] == "PARTIAL_SUPPORT"


@pytest.mark.parametrize("alignment,scope", [
    ("SAME", "DIRECT_ASSERTION"), ("OPPOSITE", "DIRECT_ASSERTION"),
])
def test_legacy_output_cannot_be_promoted(alignment, scope):
    old = {"relation_alignment": alignment, "assertion_scope": scope,
           "reason": "legacy", "decisive_text": TEXT}
    with pytest.raises(ValueError):
        validate_output(old, structural()["GEP_snapshot"])
    assert admit(structural(), old)["final_admission"] == "UNVERIFIABLE"


@pytest.mark.parametrize("field", [
    "decisive_text", "result_span", "molecular_span", "population_span", "intervention_span",
])
@pytest.mark.parametrize("value", ["invented", "", "   "])
def test_required_spans_are_literal_and_nonempty(field, value):
    output = assessment(**{field: value})
    assert admit(structural(), output)["final_admission"] == "UNVERIFIABLE"


def test_current_assessment_roundtrips_without_model_metadata_in_schema():
    output = assessment()
    assert validate_output(output, structural()["GEP_snapshot"]) == output
    assert admit(structural(), {**output, "model": "controlled", "prompt_version": "2.0"})[
        "final_admission"] == "DOCUMENT_SUPPORTED"


@pytest.mark.parametrize("output", [assessment(unexpected="invalid"), ["SAME"], "SAME", 1])
def test_unknown_fields_or_malformed_assessment_fail_closed(output):
    assert admit(structural(), output)["final_admission"] == "UNVERIFIABLE"


@pytest.mark.parametrize("field", ["assertion_scope", "relation_alignment"])
def test_malformed_label_types_do_not_crash_the_trace(field):
    assert admit(structural(), assessment(**{field: []}))["final_admission"] == "UNVERIFIABLE"


def test_imported_malformed_assessment_is_rejected_without_crashing():
    verification = admit(structural(), assessment())
    verification["semantic_assessment"] = ["SAME"]
    record = {"relation_family": "EVIDENCE_DRUG", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
              "quote_valid": True, "source_unit_id": "SU-controlled", "document_id": "pmid:1",
              "candidate_support": {"result": "FULL_SUPPORT"}, "document_verification": verification}
    assert is_aggregation_eligible(record) == (False, "DOCUMENT_VERIFICATION_NOT_ADMITTED")


@pytest.mark.parametrize("alignment,expected", [("SAME", "DOCUMENT_SUPPORTED"), ("OPPOSITE", "REJECTED")])
def test_direct_negative_results_remain_comparable(alignment, expected):
    text = "AXR1 mutation did not predict response to agent-x in lung cancer."
    assert admit(structural(text), assessment(text, relation_alignment=alignment))[
        "final_admission"] == expected


def test_explicit_null_result_is_no_support_not_contradiction_or_abstention():
    result = admit(structural(), assessment(relation_alignment="NO_SUPPORT",
                                            reason="No association was observed."))
    assert result["final_admission"] == "NO_SUPPORT"
    assert result["support_result"] == "NO_SUPPORT"
    assert result["verification_status"] == "ASSESSED"


def test_insufficient_information_stays_distinct_when_scope_cannot_be_resolved():
    result = admit(structural(), assessment(
        relation_alignment="INSUFFICIENT", evidence_role="UNKNOWN",
        molecular_scope="UNKNOWN", population_scope="UNKNOWN",
        intervention_scope="UNKNOWN", inference="UNKNOWN", certainty="UNKNOWN",
        decisive_text="", result_span="", molecular_span="", population_span="",
        intervention_span="",
    ))
    assert result["support_result"] == "INSUFFICIENT_INFORMATION"
    assert result["verification_status"] == "ASSESSED"


@pytest.mark.parametrize("scope", ["REPORTED_PRIOR_WORK", "HYPOTHETICAL", "REJECTED_ASSERTION",
                                     "UNCERTAIN_ASSERTION", "QUESTIONED_ASSERTION", "UNKNOWN"])
def test_non_direct_scope_cannot_create_a_contradiction(scope):
    assert admit(structural(), assessment(relation_alignment="OPPOSITE", assertion_scope=scope))[
        "final_admission"] == "UNVERIFIABLE"


def test_aggregation_rechecks_assessment_not_just_final_label():
    verification = admit(structural(), assessment())
    record = {"relation_family": "EVIDENCE_DRUG", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
              "quote_valid": True, "source_unit_id": "SU-controlled", "document_id": "pmid:1",
              "candidate_support": {"result": "FULL_SUPPORT"}, "document_verification": verification}
    assert is_aggregation_eligible(record) == (True, None)
    forged = deepcopy(record)
    forged["document_verification"]["semantic_assessment"]["inference"] = "INVERSE"
    assert is_aggregation_eligible(forged) == (False, "DOCUMENT_VERIFICATION_NOT_ADMITTED")


def test_aggregation_cannot_use_an_inverse_or_legacy_contradiction():
    verification = admit(structural(), assessment(relation_alignment="OPPOSITE"))
    record = {"relation_family": "EVIDENCE_DRUG", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
              "quote_valid": True, "source_unit_id": "SU-controlled", "document_id": "pmid:1",
              "candidate_support": {"result": "CONTRADICTORY"}, "document_verification": verification}
    assert is_aggregation_eligible(record) == (True, None)
    record["document_verification"]["semantic_assessment"]["inference"] = "INVERSE"
    assert is_aggregation_eligible(record) == (False, "DOCUMENT_VERIFICATION_NOT_ADMITTED")
    record["document_verification"].pop("admission_policy_version")
    assert is_aggregation_eligible(record) == (False, "DOCUMENT_VERIFICATION_NOT_ADMITTED")
