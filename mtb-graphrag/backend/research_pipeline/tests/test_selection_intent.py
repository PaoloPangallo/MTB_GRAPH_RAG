from backend.research_pipeline.retrieval.selection_intent import build_selection_intent
from backend.research_pipeline.experimental.sourceunit_selector import SourceUnitSelectionInput


def test_question_does_not_replace_candidate_target():
    candidate = {'candidate_id': 'x', 'interventions': [], 'biomarkers': []}
    case = {'target_intervention': {'normalized_value': 'dabrafenib and trametinib'}}
    intent = build_selection_intent(candidate, case, [])
    assert intent['candidate_target']['interventions'] == []
    assert intent['case_question']['interventions'] == ['dabrafenib and trametinib']
    assert candidate['interventions'] == []
    selection = SourceUnitSelectionInput.from_candidate(candidate, 'pmid:1', [], selection_intent=intent)
    assert selection.interventions == ()
    assert 'trametinib' in selection.query_terms()


def test_discovery_does_not_invent_drug():
    intent = build_selection_intent({'candidate_id': 'x'}, {}, [])
    assert intent['case_question']['interventions'] == []


def test_negated_intervention_is_not_a_query_target():
    intent = build_selection_intent({}, {'target_interventions': [
        {'normalized_value': 'drug X', 'assertion_status': 'NEGATED'}]}, [])
    assert not intent['case_question']['interventions']
