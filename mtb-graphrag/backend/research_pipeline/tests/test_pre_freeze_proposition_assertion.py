"""Reader-positive mutations must not turn embedded propositions into support."""

from __future__ import annotations

import pytest

from backend.research_pipeline.enrichment.relation_support import assess_relation_support


def candidate() -> dict:
    return {
        "candidate_id": "proposition-scope-probe",
        "relation_family": "COMPOSITE_EVIDENCE_RELATION",
        "disease": [{"label": "lung cancer", "type": "Disease"}],
        "biomarkers": [{"label": "EGFR", "type": "Gene"},
                       {"label": "L858R", "type": "Variant"}],
        "interventions": [{"label": "erlotinib", "type": "Drug"}],
        "predicate": "associated_with_sensitivity_to",
        "direction": "Supports",
    }


def forced_positive_reader() -> dict:
    return {
        "decision": "QUOTE",
        "observed_relation": {
            "subjects": [{"type": "GENE", "surface_value": "EGFR"},
                         {"type": "ALTERATION", "surface_value": "L858R"}],
            "subject_pairings": [{"gene": "EGFR", "alteration": "L858R"}],
            "intervention": "erlotinib",
            "disease": None,
            "effect_direction": "SENSITIVITY_RESPONSE",
            "observed_stance": "SUPPORTS",
            "relation_scope": "SINGLE",
            "relation_assertion": "RELATION_ASSERTED",
        },
    }


@pytest.mark.parametrize("quote,state,full", [
    ("EGFR L858R was associated with sensitivity to erlotinib.", "DIRECT_ASSERTION", True),
    ("Patients with EGFR L858R responded to erlotinib.", "DIRECT_ASSERTION", True),
    ("In our cohort, patients with EGFR L858R responded to erlotinib.", "DIRECT_ASSERTION", True),
    ("The proposition that EGFR L858R showed sensitivity to erlotinib was rejected.", "REJECTED_ASSERTION", False),
    ("The hypothesis that EGFR L858R predicts response to erlotinib was not supported.", "REJECTED_ASSERTION", False),
    ("The proposed association between EGFR L858R and erlotinib sensitivity was disproved.", "REJECTED_ASSERTION", False),
    ("The proposed association was disproved.", "NO_RELATION", False),
    ("We hypothesized that EGFR L858R might predict sensitivity to erlotinib.", "HYPOTHETICAL_ASSERTION", False),
    ("If EGFR L858R were associated with erlotinib response, treatment would follow.", "HYPOTHETICAL_ASSERTION", False),
    ("EGFR L858R could potentially confer sensitivity to erlotinib.", "HYPOTHETICAL_ASSERTION", False),
    ("Whether EGFR L858R predicts response to erlotinib remains unclear.", "QUESTIONED_ASSERTION", False),
    ("It is unknown whether EGFR L858R confers sensitivity to erlotinib.", "QUESTIONED_ASSERTION", False),
    ("Does EGFR L858R predict response to erlotinib?", "QUESTIONED_ASSERTION", False),
    ("Evidence for an association is inconclusive.", "NO_RELATION", False),
    ("Previous studies suggested that EGFR L858R predicts response to erlotinib.", "REPORTED_ASSERTION", False),
    ("It has been claimed that EGFR L858R confers sensitivity to erlotinib.", "REPORTED_ASSERTION", False),
    ("The authors proposed that EGFR L858R predicts response to erlotinib.", "REPORTED_ASSERTION", False),
    ("Our results show that EGFR L858R predicts response to erlotinib.", "DIRECT_ASSERTION", True),
    ("EGFR L858R and erlotinib were studied.", "ENTITY_CO_OCCURRENCE", False),
    ("EGFR L858R was measured and erlotinib was included in the panel.", "ENTITY_CO_OCCURRENCE", False),
    ("EGFR L858R did not predict response to erlotinib.", "DIRECT_NEGATIVE_ASSERTION", False),
    ("Although previously questioned, our results showed that EGFR L858R predicted response to erlotinib.", "DIRECT_ASSERTION", True),
    ("Although initially reported as sensitive, our results did not confirm an association between EGFR L858R and erlotinib response.", "REJECTED_ASSERTION", False),
    ("The association between EGFR L858R and erlotinib response was not rejected.", "UNCERTAIN_ASSERTION", False),
    ("No evidence contradicted the association between EGFR L858R and erlotinib response.", "UNCERTAIN_ASSERTION", False),
    ("The finding that EGFR L858R showed sensitivity to erlotinib was rejected.", "REJECTED_ASSERTION", False),
    ("The proposition that EGFR L858R showed sensitivity to erlotinib was dismissed.", "REJECTED_ASSERTION", False),
    ("EGFR L858R showed sensitivity to erlotinib, but the finding was rejected.", "REJECTED_ASSERTION", False),
    ("EGFR L858R predicted response to erlotinib, but this was not confirmed.", "REJECTED_ASSERTION", False),
    ("EGFR L858R predicted response to erlotinib, but our findings did not confirm it.", "REJECTED_ASSERTION", False),
    ("EGFR L858R predicted response to erlotinib, but this was disproved.", "REJECTED_ASSERTION", False),
    ("Smith et al. reported that EGFR L858R predicted response to erlotinib.", "REPORTED_ASSERTION", False),
    ("A previous report found that EGFR L858R predicted response to erlotinib.", "REPORTED_ASSERTION", False),
    ("Previous studies suggested that EGFR L858R predicts response to erlotinib, but our results demonstrated response to erlotinib in EGFR L858R patients.", "DIRECT_ASSERTION", True),
    ("EGFR L858R showed sensitivity to erlotinib. This finding was rejected.", "REJECTED_ASSERTION", False),
    ("The claim that EGFR L858R showed sensitivity to erlotinib was rejected. However, our experiments showed EGFR L858R sensitivity to erlotinib.", "DIRECT_ASSERTION", True),
    ("The theory that EGFR L858R showed sensitivity to erlotinib was rejected.", "REJECTED_ASSERTION", False),
    ("It was asserted that EGFR L858R showed sensitivity to erlotinib.", "UNCERTAIN_ASSERTION", False),
    ("We found that EGFR L858R showed sensitivity to erlotinib.", "DIRECT_ASSERTION", True),
    ("EGFR L858R showed sensitivity to erlotinib according to previous studies.", "REPORTED_ASSERTION", False),
    ("Previous studies: EGFR L858R showed sensitivity to erlotinib.", "REPORTED_ASSERTION", False),
    ("EGFR L858R showed sensitivity to erlotinib in a hypothetical model.", "HYPOTHETICAL_ASSERTION", False),
    ("No evidence of response to erlotinib was observed in EGFR L858R tumors.", "UNCERTAIN_ASSERTION", False),
    ("An earlier study reported EGFR L858R predicted response to erlotinib.", "REPORTED_ASSERTION", False),
    ("A prior trial reported EGFR L858R predicted response to erlotinib.", "REPORTED_ASSERTION", False),
    ("One study suggested EGFR L858R predicted response to erlotinib.", "REPORTED_ASSERTION", False),
    ("According to previous studies, EGFR L858R predicted response to erlotinib.", "REPORTED_ASSERTION", False),
    ("EGFR L858R was reported to predict response to erlotinib.", "REPORTED_ASSERTION", False),
    ("Previous studies suggested that EGFR L858R predicts response to erlotinib. Our results demonstrated response to erlotinib in EGFR L858R patients.", "DIRECT_ASSERTION", True),
    ("No evidence of an association between EGFR L858R and erlotinib response was found.", "UNCERTAIN_ASSERTION", False),
    ("No evidence for an association between EGFR L858R and erlotinib response was available.", "UNCERTAIN_ASSERTION", False),
    ("Prior reports indicate EGFR L858R showed sensitivity to erlotinib.", "REPORTED_ASSERTION", False),
    ("EGFR L858R showed sensitivity to erlotinib, as reported previously.", "REPORTED_ASSERTION", False),
    ("Smith observed EGFR L858R sensitivity to erlotinib.", "ENTITY_CO_OCCURRENCE", False),
    ("A prior experiment showed EGFR L858R sensitivity to erlotinib.", "UNCERTAIN_ASSERTION", False),
    ("Earlier investigators showed EGFR L858R sensitivity to erlotinib.", "UNCERTAIN_ASSERTION", False),
    ("EGFR L858R showed sensitivity to erlotinib, or so they speculated.", "HYPOTHETICAL_ASSERTION", False),
    ("EGFR L858R showed sensitivity to erlotinib, the authors merely speculated.", "HYPOTHETICAL_ASSERTION", False),
])
def test_forced_positive_reader_cannot_override_quote_scope(
    quote: str, state: str, full: bool,
) -> None:
    result = assess_relation_support(candidate(), forced_positive_reader(), source_unit_text=quote)
    assert result["text_assertion"] == state
    assert bool(result["result"] == "FULL_SUPPORT") is full
    assert result["text_assertion_reason"]


def test_negative_quote_is_not_positive_even_with_reader_forced_positive() -> None:
    result = assess_relation_support(
        candidate(), forced_positive_reader(),
        source_unit_text="EGFR L858R did not predict response to erlotinib.",
    )
    assert result["result"] == "CONTRADICTORY"


def test_absence_of_evidence_is_not_opposite_biological_effect() -> None:
    result = assess_relation_support(
        candidate(), forced_positive_reader(),
        source_unit_text="No evidence of response to erlotinib was observed in EGFR L858R tumors.",
    )
    assert result["result"] == "NO_SUPPORT"


def test_composite_join_is_not_document_support_for_rejected_quote() -> None:
    composite = {
        **candidate(),
        "candidate_id": "COMPOSITE-1",
        "relation_origin": "DERIVED_COMPOSITE",
        "composite_lineage": {
            "profile_candidate_id": "PROFILE-1",
            "evidence_drug_candidate_id": "DRUG-1",
            "shared_evidence_id": "Evidence:1",
        },
    }
    result = assess_relation_support(
        composite, forced_positive_reader(),
        source_unit_text="The proposition that EGFR L858R showed sensitivity to erlotinib was rejected.",
    )
    assert result["result"] != "FULL_SUPPORT"
    assert result["text_assertion"] == "REJECTED_ASSERTION"


def test_absent_authorized_quote_cannot_establish_direct_assertion() -> None:
    result = assess_relation_support(candidate(), forced_positive_reader())
    assert result["text_assertion"] == "NO_RELATION"
    assert result["text_assertion_reason"] == "NO_AUTHORIZED_QUOTE"
    assert result["result"] != "FULL_SUPPORT"


def test_document_scope_contract_does_not_require_drug_for_molecular_family() -> None:
    molecular = {
        **candidate(), "relation_family": "EVIDENCE_STATEMENT",
        "interventions": [], "predicate": "has_evidence_statement",
    }
    observed = forced_positive_reader()
    observed["observed_relation"]["intervention"] = None
    result = assess_relation_support(
        molecular, observed,
        source_unit_text="EGFR L858R was associated with increased survival.",
    )
    assert result["text_assertion"] == "DIRECT_ASSERTION"
    assert result["text_assertion_reason"] == "DIRECT_CANDIDATE_ANCHORED_PREDICATE"
