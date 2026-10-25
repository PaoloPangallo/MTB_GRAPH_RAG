"""A shape-valid answer cannot silently omit requested dossier entries."""
from copy import deepcopy
import json
from unittest.mock import patch

from backend.research_pipeline.narrative import narrator, prompt
from backend.research_pipeline.tests.test_narrator_workload import _input


def body(rows):
    return {'narrative_summary': 'Summary.', 'limitations_summary': '', 'closing_note': '',
            'candidate_narratives': [{'candidate_id': row['candidate_id'], 'text': 'Prose.'} for row in rows]}


def test_structural_validation_checks_exact_requested_identity_and_order():
    source = _input(2)
    assert narrator._bound_argument_errors(body(source['candidates']), source) == []
    assert narrator._bound_argument_errors(body(source['candidates'][:1]), source)
    assert narrator._bound_argument_errors(body(source['candidates'][::-1]), source)
    complete = body(source['candidates'])
    complete['candidate_narratives'][0]['text'] = 'An unsupported scientific claim.'
    assert narrator._bound_argument_errors(complete, source) == []  # scientific fidelity stays downstream


def test_missing_entry_triggers_bounded_smaller_requests():
    source = _input(2); original = deepcopy(source)
    def provider(payload):
        content = payload['messages'][-1]['content']
        received = json.loads(content[content.index('{'):])['candidates']
        answer = body(received[:1] if len(received) > 1 else received)
        return 200, {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(answer)}}]}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, None, 0
    with patch.object(narrator.tr, 'post_with_infra_retry', side_effect=provider):
        result = narrator.call_narrator('CASE', source)
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert [entry['candidate_id'] for entry in result['narrative']['candidate_narratives']] == [row['candidate_id'] for row in source['candidates']]
    assert result['model_call_count'] == 3
    assert result['structural_recovery_count'] == 1
    assert source == original


def test_single_candidate_invalid_shape_has_one_bounded_retry():
    source = _input(1)
    original = deepcopy(source)
    valid = body(source['candidates'])
    invalid = deepcopy(valid)
    invalid['candidate_narratives'][0]['observation_narratives'] = 'invalid nested structure'
    responses = []
    for answer in [invalid, valid]:
        responses.append((200, {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(answer)}}]}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, None, 0))
    with patch.object(narrator.tr, 'post_with_infra_retry', side_effect=responses) as provider:
        result = narrator.call_narrator('CASE', source)
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert provider.call_count == 2
    assert result['model_call_count'] == 2
    assert result['narrative']['candidate_narratives'] == valid['candidate_narratives']
    assert result['attempts'][0]['transport_result'] == 'INVALID_TOOL_ARGUMENTS'
    assert source == original


def test_single_candidate_repeated_invalid_shape_still_fails_closed():
    source = _input(1)
    invalid = body(source['candidates'])
    invalid['candidate_narratives'][0]['observation_narratives'] = 'invalid nested structure'
    response = (200, {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
        {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(invalid)}}]}}],
        'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, None, 0)
    with patch.object(narrator.tr, 'post_with_infra_retry', return_value=response) as provider:
        result = narrator.call_narrator('CASE', source)
    assert provider.call_count == 2
    assert result['transport_result'] == 'INVALID_TOOL_ARGUMENTS'
    assert result['narrative'] is None


def test_nested_schema_errors_identify_the_field_without_echoing_its_value():
    invalid = body(_input(1)['candidates'])
    invalid['candidate_narratives'][0]['observation_narratives'] = 'PRIVATE_BAD_FIELD_VALUE'
    errors = narrator._argument_errors(invalid)
    assert 'INVALID_NESTED_NARRATIVE_SHAPE' in errors
    assert any('candidate_narratives/0/observation_narratives' in error and 'type' in error for error in errors)
    assert 'PRIVATE_BAD_FIELD_VALUE' not in str(errors)
