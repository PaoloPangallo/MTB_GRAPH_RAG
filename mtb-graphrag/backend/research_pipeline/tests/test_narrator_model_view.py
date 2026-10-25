"""The model sees retained observations once and keeps search targets separate."""
from copy import deepcopy
import json

from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.tests.test_narrative_multistudy import multistudy


def test_model_view_preserves_every_observation_and_source_without_mutation():
    from backend.research_pipeline.narrative.model_view import model_view
    source = build_narrator_input(multistudy())
    before = deepcopy(source)
    view = model_view(source)
    assert source == before
    assert [row['candidate_id'] for row in view['candidates']] == [row['candidate_id'] for row in source['candidates']]
    for original, shown in zip(source['candidates'], view['candidates']):
        assert shown['narration_observations'] == original['narration_observations']
        assert shown['source_cards'] == original['source_cards']
        assert 'documentary_findings' not in shown
    assert view['narrator_input_hash'] == source['narrator_input_hash']


def test_graph_evidence_paragraph_is_not_a_narratable_source_observation():
    from backend.research_pipeline.narrative.model_view import model_view
    source = build_narrator_input(multistudy())
    row = source['candidates'][0]
    row['documentary_target'] = {'subject': {'label': 'BRAF V600K'},
        'relation': 'has_evidence_statement', 'object': {'type': 'Evidence', 'id': 'E:1',
        'label': 'UNVERIFIED GRAPH SUMMARY: 56 patients and NCT01689519'},
        'graph_provenance': {'edge_ids': ['internal-edge']}}
    row['documentary_attempts'] = [{'source': {'document_id': 'pmid:1'},
        'reason_codes': ['READER_ABSTAINED'], 'observed': {'finding': 'DISCARDED RESULT'}}]
    shown = model_view(source)['candidates'][0]
    assert 'UNVERIFIED GRAPH SUMMARY' not in json.dumps(shown)
    assert 'DISCARDED RESULT' not in json.dumps(shown)
    assert shown['documentary_target']['subject']['label'] == 'BRAF V600K'
    assert shown['documentary_attempts'][0]['reason_codes'] == ['READER_ABSTAINED']


def test_registry_scope_is_grounded_and_does_not_license_a_suffix():
    from backend.research_pipeline.narrative.model_view import branch_scope_text
    from backend.research_pipeline.narrative.verifier import _check_branch_semantics
    candidate = {'candidate_id': 'T', 'branch': 'TRIAL', 'trial_context': {
        'nct_id': 'NCT02279004', 'conditions': ['NSCLC', 'Melanoma'],
        'eligibility_status': 'NOT_EVALUATED',
        'evidence_interpretation': 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE'}}
    text = branch_scope_text(candidate)
    assert 'NCT02279004' in text and 'Melanoma' in text
    assert _check_branch_semantics(candidate, text) == []
    assert _check_branch_semantics(candidate, text + '\nIl trial è efficace.')
    assert _check_branch_semantics(candidate, text.replace('Melanoma', 'Renal Cancer'))


def test_graph_hypothesis_does_not_authorize_a_scientific_quantity_in_the_prose():
    from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check
    data = multistudy()
    data['paper_evidence'][0]['documentary_target'] = {'object': {
        'type': 'Evidence', 'label': 'The graph target claims 98765 patients.'}}
    source = build_narrator_input(data)
    output = covered_output(source)
    output['candidate_narratives'][0]['text'] += ' La fonte riporta 98765 pazienti.'
    assert 'NARRATIVE_UNAUTHORIZED_NUMBER' in check(data, source, output)['reason_codes']
