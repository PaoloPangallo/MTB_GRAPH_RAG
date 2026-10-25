"""Immutable branch context is copied exactly, with bounded transport recovery."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from backend.research_pipeline.narrative import narrator, prompt
from backend.research_pipeline.narrative.model_view import model_view


def source():
    return {'documentary_contract_version': 'test', 'candidates': [{
        'candidate_id': 'GCA4-07d53e2d316aec3c3a1081ce', 'branch': 'KG_ONLY',
        'kg_context': {'subject': {'label': 'PANITUMUMAB'},
                       'object': {'label': 'KRAS G12D'}},
        'narration_observations': []}]}


def body(data):
    return {'narrative_summary': 'Caso KRAS G12D.', 'limitations_summary': '',
            'closing_note': '', 'candidate_narratives': [
                {'candidate_id': row['candidate_id'], 'text': row['branch_scope_text'],
                 'observation_narratives': []} for row in model_view(data)['candidates']]}


def response(answer):
    return 200, {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
        {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(answer)}}]}}],
        'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, None, 0


@pytest.mark.parametrize('change', [
    lambda text: text.replace('PANITUMUMAB', 'PANITUMUMUMAB'),
    lambda text: text + ' Introduzione aggiunta.',
    lambda text: ' ' + text,
])
def test_documentary_branch_context_requires_exact_copy(change):
    data = source()
    answer = body(data)
    assert narrator._bound_argument_errors(answer, data) == []
    answer['candidate_narratives'][0]['text'] = change(answer['candidate_narratives'][0]['text'])
    assert narrator._bound_argument_errors(answer, data) == ['BRANCH_SCOPE_TEXT_MISMATCH:0']
    data.pop('documentary_contract_version')
    data['candidates'][0]['branch_scope_text'] = 'Historical field is not a copy contract.'
    assert narrator._bound_argument_errors(answer, data) == []


def test_trial_scope_uses_same_copy_contract_but_free_observation_prose_is_not_scored():
    data = source()
    candidate = data['candidates'][0]
    candidate.update(branch='TRIAL', trial_context={
        'nct_id': 'NCT12345678', 'eligibility_status': 'NOT_EVALUATED',
        'evidence_interpretation': 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE'})
    candidate['narration_observations'] = [{'observation_id': 'OBS-1', 'study_id': 'STUDY-1'}]
    answer = body(data)
    answer['candidate_narratives'][0]['observation_narratives'] = [
        {'observation_id': 'OBS-1', 'text': 'An unsupported scientific claim.'}]
    assert narrator._bound_argument_errors(answer, data) == []
    answer['candidate_narratives'][0]['text'] += ' Extra.'
    assert narrator._bound_argument_errors(answer, data) == ['BRANCH_SCOPE_TEXT_MISMATCH:0']


@pytest.mark.parametrize('recovers', [True, False])
def test_malformed_drug_identity_retries_once_and_never_rewrites(recovers):
    data = source()
    before = deepcopy(data)
    valid = body(data)
    invalid = deepcopy(valid)
    invalid['candidate_narratives'][0]['text'] = invalid['candidate_narratives'][0]['text'].replace(
        'PANITUMUMAB', 'PANITUMUMUMAB')
    with patch.object(narrator.tr, 'post_with_infra_retry', side_effect=[
            response(invalid), response(valid if recovers else invalid)]) as provider:
        result = narrator.call_narrator('CASE', data)
    assert provider.call_count == result['model_call_count'] == 2
    assert result['attempts'][0]['reason_codes'] == ['BRANCH_SCOPE_TEXT_MISMATCH:0']
    assert 'PANITUMUMUMAB' not in str(provider.call_args.args[0]['messages'])
    if recovers:
        assert result['transport_result'] == 'FORCED_TOOL_VALID'
        assert result['narrative']['candidate_narratives'] == valid['candidate_narratives']
    else:
        assert result['transport_result'] == 'INVALID_TOOL_ARGUMENTS'
        assert result['narrative'] is None
    assert data == before


def test_batch_copy_mismatch_splits_without_losing_candidate_order():
    data = source()
    second = deepcopy(data['candidates'][0])
    second['candidate_id'] = 'GCA4-second'
    data['candidates'].append(second)
    before = deepcopy(data)

    def provider(payload):
        content = payload['messages'][1]['content']
        received = json.loads(content[content.index('{'):])
        answer = {'narrative_summary': 'Caso KRAS G12D.', 'limitations_summary': '',
                  'closing_note': '', 'candidate_narratives': [
                      {'candidate_id': row['candidate_id'], 'text': row['branch_scope_text'],
                       'observation_narratives': []} for row in received['candidates']]}
        if len(received['candidates']) > 1:
            answer['candidate_narratives'][0]['text'] += ' Extra.'
        return response(answer)

    with patch.object(narrator.tr, 'post_with_infra_retry', side_effect=provider):
        result = narrator.call_narrator('CASE', data)
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert result['model_call_count'] == 3
    assert result['structural_recovery_count'] == 1
    assert result['attempts'][0]['reason_codes'] == ['BRANCH_SCOPE_TEXT_MISMATCH:0']
    assert result['narrative']['candidate_narratives'] == body(data)['candidate_narratives']
    assert data == before
