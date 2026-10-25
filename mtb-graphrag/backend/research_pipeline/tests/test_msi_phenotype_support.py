import pytest

from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.terminology.molecular import molecular_observation, parse_profile, evaluate_profile
from backend.research_pipeline.retrieval import kg_retrieval as kg


@pytest.mark.parametrize("label", ["MSI-H", "MSI High", "Microsatellite Instability High", "MSI-High", "microsatellite instability-high"])
def test_source_linked_msi_high_is_a_phenotype_without_gene(label):
    obs = molecular_observation({"gene": None, "alteration": label, "alteration_type": "PHENOTYPE", "assertion_status": "PRESENT"}, get_registry()).to_dict()
    assert obs["phenotype_value"] == "HIGH"
    assert obs["phenotype_resolution_status"] == "RESOLVED"
    assert obs["concept_ids"] == ("CIViCVariant:4944",)
    profile = parse_profile("MSI High", get_registry())
    assert profile["ast"]["op"] == "PHENOTYPE"
    assert evaluate_profile(profile["ast"], [obs]) == "TRUE"
    assert evaluate_profile(profile["ast"], [{**obs, "assertion_status": "UNCERTAIN"}]) == "UNKNOWN"
    assert evaluate_profile(profile["ast"], [{**obs, "assertion_status": "NEGATED"}]) == "FALSE"
    assert evaluate_profile(profile["ast"], [{"concept_ids": ("CIViCVariant:4944",), "assertion_status": "PRESENT"}]) == "UNKNOWN"


@pytest.mark.parametrize("label,value", [("MSI", "UNSPECIFIED"), ("MSI-L", "LOW"), ("MSS", "STABLE")])
def test_other_microsatellite_states_never_establish_high(label, value):
    obs = molecular_observation({"alteration": label, "alteration_type": "PHENOTYPE"}, get_registry()).to_dict()
    assert obs["phenotype_value"] == value
    assert obs["phenotype_resolution_status"] == "UNSUPPORTED_DOMAIN"
    assert not obs["concept_ids"]


def test_pinned_corpus_msi_high_candidates_require_source_phenotype():
    registry = get_registry()
    rows = kg._linked_candidates(kg.load_candidates(), registry)
    ids = ["GCA4-39f474079fc195a856324187", "GCA4-a8deb9cbedb09c189c61e295"]
    for cid in ids:
        row = rows[cid]
        assert row["entity_resolution"]["compound"]
        assert row["entity_resolution"]["profile"]["status"] == "RESOLVED"
        case = {"biomarkers": [{"alteration": "MSI-H", "alteration_type": "PHENOTYPE", "assertion_status": "PRESENT"}]}
        # Disease/intervention filters are independent; isolate the molecular constraint here.
        molecular_row = {**row, "disease": [], "interventions": []}
        assert "PROFILE_CONSTRAINT_UNKNOWN_OR_FALSE" not in kg._match_candidate(case, molecular_row)[1]
        case["biomarkers"][0]["alteration"] = "MSI"
        assert "PROFILE_CONSTRAINT_UNKNOWN_OR_FALSE" in kg._match_candidate(case, molecular_row)[1]


@pytest.mark.parametrize('label,eligible,reason', [
    ('MSI-H', True, 'MINIMUM_FIELDS_SATISFIED'),
    ('MSI-L', False, 'MOLECULAR_PHENOTYPE_DOMAIN_UNSUPPORTED'),
    ('MSS', False, 'MOLECULAR_PHENOTYPE_DOMAIN_UNSUPPORTED'),
    ('MSI', False, 'MOLECULAR_PHENOTYPE_SCOPE_UNSPECIFIED'),
])
def test_gate_checks_actual_source_phenotype_coverage(label, eligible, reason):
    from backend.research_pipeline.tests.test_live_case_parser_boundaries import context
    from backend.research_pipeline.casecontext import pipeline
    text = f'Paziente con carcinoma colorettale e {label}. Valutare nivolumab.'
    result = pipeline.run(text, context(text, alteration=label, alteration_type='PHENOTYPE'))
    assert result['eligibility']['eligible'] is eligible
    assert reason in result['eligibility']['reason_codes']
    assert result['eligibility']['verified_fields']['genes'] == []


def test_phenotype_cannot_match_an_unrelated_gene_or_intervention_only_trial():
    case = {'biomarkers': [{'gene': None, 'alteration': 'MSI-H', 'alteration_type': 'PHENOTYPE', 'assertion_status': 'PRESENT'}]}
    assert kg._molecular_compatible(case['biomarkers'], [{'gene': 'MET'}])[0] is False
    assert kg._match_candidate(case, {'biomarkers': [], 'relation_family': 'CLINICAL_TRIAL'})[0] is False
