"""Historical label-only pairing stays isolated from canonical identity gates."""
from backend.research_pipeline.retrieval.kg_retrieval import _candidate_biomarkers, _match_candidate
from backend.research_pipeline.terminology.matching import historical_matching
import pytest
from copy import deepcopy


def _recorded_context():
    from backend.research_pipeline.replay import _parser_outputs_by_case
    return deepcopy(_parser_outputs_by_case()["CASE-2-therapy-discovery"]["case_context_raw"])


def test_recorded_research_case_replays_recorded_retrieval_not_new_identity_policy():
    from backend.research_pipeline.retrieval.kg_retrieval import retrieve_frozen_bundles
    result = retrieve_frozen_bundles(_recorded_context())
    assert result["replayed"] is True
    assert result["associations"][0]["candidate_id"] == "GCA-0031c17c5ff5ae29ff221b1e"
    assert result["repository_version"] == "2.0"


@pytest.mark.parametrize("field,value", [
    ("disease", {"raw_value": "melanoma", "normalized_value": "melanoma"}),
    ("biomarkers", [{"gene": "EGFR", "alteration": "L858R"}]),
    ("target_intervention", {"raw_value": "agentone"}),
])
def test_recorded_retrieval_rejects_modified_clinical_input(field, value):
    from backend.research_pipeline.retrieval.kg_retrieval import retrieve_frozen_bundles
    context = _recorded_context()
    context[field] = value
    with pytest.raises(ValueError, match="FROZEN_RETRIEVAL_INPUT_MISMATCH"):
        retrieve_frozen_bundles(context)


def test_label_only_pair_can_reproduce_frozen_retrieval_but_not_license_canonical_pair():
    case = {"disease": {"raw_value": "colorectal cancer"},
            "biomarkers": [{"gene": "KRAS", "alteration": "G12D"}]}
    candidate = {"biomarkers": [{"type": "Gene", "label": "KRAS"},
                                {"type": "Variant", "label": "G12D"}],
                 "disease": [{"label": "colorectal cancer"}]}
    assert not _match_candidate(case, candidate)[0]
    token = historical_matching.set(True)
    try:
        assert any(x.get("gene") == "KRAS" and x.get("alteration") == "G12D"
                   for x in _candidate_biomarkers(candidate))
        assert _match_candidate(case, candidate)[0]
    finally:
        historical_matching.reset(token)
    assert not _match_candidate(case, candidate)[0]
