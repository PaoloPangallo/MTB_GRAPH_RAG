"""Disease identity must not be inferred from generic shared words."""

from __future__ import annotations

import pytest

from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate, _term_matches, _trial_term_matches


@pytest.mark.parametrize(
    ("case_disease", "candidate_disease", "expected"),
    [
        ("breast cancer", "lung cancer", False),
        ("melanoma", "metastatic melanoma", False),
        ("colorectal cancer", "colon cancer", False),
        # The pinned Disease Ontology now supplies an EXACT synonym, replacing
        # the former absence of an approved alias resource.
        ("NSCLC", "non-small cell lung cancer", True),
        ("  LUNG   CANCER ", "lung cancer", True),
    ],
)
def test_disease_term_requires_demonstrated_identity(
    case_disease: str, candidate_disease: str, expected: bool,
) -> None:
    assert _term_matches(case_disease, candidate_disease) is expected


def test_matching_gene_and_drug_do_not_override_wrong_disease() -> None:
    case_context = {
        "query_intent": "THERAPY_EVALUATION",
        "disease": {"normalized_value": "breast cancer"},
        "biomarkers": [{"gene": "EGFR", "assertion_status": "PRESENT"}],
        "target_interventions": [
            {"normalized_value": "erlotinib", "assertion_status": "PRESENT"},
        ],
    }
    candidate = {
        "candidate_id": "disease-probe",
        "disease": [{"label": "lung cancer"}],
        "biomarkers": [{"label": "EGFR", "type": "Gene"}],
        "interventions": [{"label": "erlotinib", "type": "Drug"}],
    }
    matched, reasons = _match_candidate(case_context, candidate)
    assert matched is False
    assert "DISEASE_NOT_COMPATIBLE" in reasons


def test_trial_condition_small_cell_does_not_match_non_small_cell() -> None:
    assert not _trial_term_matches("small cell lung cancer", "non small cell lung cancer")


def _paper_candidate(*, disease_required: bool = False) -> dict:
    return {
        "candidate_id": "disease-verifier-probe",
        "disease": [{"label": "lung cancer", "type": "Disease"}],
        "biomarkers": [
            {"label": "EGFR", "type": "Gene"},
            {"label": "L858R", "type": "Variant"},
        ],
        "interventions": [{"label": "erlotinib", "type": "Drug"}],
        "direction": "Supports",
        "predicate": "associated_with_sensitivity_to",
        "disease_required": disease_required,
    }


def _reader_observation(disease: str | None) -> dict:
    return {
        "decision": "QUOTE",
        "observed_relation": {
            "subjects": [
                {"type": "GENE", "surface_value": "EGFR"},
                {"type": "ALTERATION", "surface_value": "L858R"},
            ],
            "subject_pairings": [{"gene": "EGFR", "alteration": "L858R"}],
            "intervention": "erlotinib",
            "disease": disease,
            "effect_direction": "SENSITIVITY_RESPONSE",
            "observed_stance": "SUPPORTS",
            "relation_scope": "SINGLE",
            "relation_assertion": "RELATION_ASSERTED",
        },
    }


def test_explicit_wrong_disease_cannot_produce_full_support() -> None:
    result = assess_relation_support(
        _paper_candidate(),
        _reader_observation("breast cancer"),
        source_unit_text="EGFR L858R tumors showed sensitivity to erlotinib in breast cancer.",
    )
    assert result["result"] == "NO_SUPPORT"
    assert result["disease_policy"] == "OPTIONAL"


def test_optional_disease_can_be_unmentioned_but_is_visible() -> None:
    result = assess_relation_support(
        _paper_candidate(),
        _reader_observation(None),
        source_unit_text="EGFR L858R tumors showed sensitivity to erlotinib.",
    )
    assert result["disease_policy"] == "OPTIONAL"
    assert result["fields"]["disease"] == "NOT_CONFIRMED"
    assert result["result"] == "FULL_SUPPORT"


def test_required_disease_missing_cannot_produce_full_support() -> None:
    result = assess_relation_support(
        _paper_candidate(disease_required=True),
        _reader_observation(None),
        source_unit_text="EGFR L858R tumors showed sensitivity to erlotinib.",
    )
    assert result["disease_policy"] == "REQUIRED"
    assert result["result"] != "FULL_SUPPORT"
