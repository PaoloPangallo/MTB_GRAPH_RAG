from backend.research_pipeline.enrichment.observation_checks import assess_observation


def test_purpose_is_not_observed_response():
    result = assess_observation('PURPOSE To assess resistance mechanisms of drug X.',
                                {'effect_direction': 'SENSITIVITY_RESPONSE', 'relation_assertion': 'RELATION_ASSERTED'})
    assert result['status'] == 'MISMATCH'
    assert 'OBJECTIVE_NOT_OBSERVED_RESULT' in result['reason_codes']


def test_objective_with_actual_result_is_not_automatically_blocked():
    assert assess_observation('We aimed to assess response. Results showed a 40% response rate.',
                              {'effect_direction': 'SENSITIVITY_RESPONSE'})['status'] == 'PASS'


def test_separate_studies_are_not_combination():
    result = assess_observation('Vemurafenib and dabrafenib prolonged survival and progression-free survival, respectively, in separate trials.',
                                {'intervention_composition': 'COMBINATION'})
    assert 'SEPARATE_INTERVENTIONS_NOT_COMBINATION' in result['reason_codes']


def test_alternative_population_is_not_coalteration():
    assert assess_observation('Patients had BRAF V600E or V600K mutations.',
                              {'molecular_composition': 'COMBINATION'})['status'] == 'MISMATCH'
    assert assess_observation('Cells had BRAF V600E and NF1 loss.',
                              {'molecular_composition': 'COMBINATION'})['status'] == 'PASS'


def test_true_drug_combination_passes():
    assert assess_observation('Dabrafenib plus trametinib improved survival.',
                              {'intervention_composition': 'COMBINATION'})['status'] == 'PASS'


def test_objective_clause_with_observed_regression_is_allowed():
    quote = 'To evaluate dabrafenib efficacy, we treated 20 patients; tumor regression occurred in 12 patients and median survival improved to 18 months.'
    assert assess_observation(quote, {'effect_direction': 'SENSITIVITY_RESPONSE'})['status'] == 'PASS'
