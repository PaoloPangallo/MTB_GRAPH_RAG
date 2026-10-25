import copy
import json

from jsonschema import Draft7Validator

from backend.research_pipeline.casecontext import parser, prompt
from backend.research_pipeline.casecontext.pipeline import run

TEXT = 'Synthetic test: colorectal cancer with KRAS G12D; evaluating panitumumab.'


def arguments():
    return {
        'disease': None,
        'diseases': [{'value': {'raw_value': 'colorectal cancer', 'quote': 'colorectal cancer'},
                      'assertion_status': 'PRESENT', 'clinical_role': 'PRIMARY'}],
        'biomarkers': [{'gene': {'raw_value': 'KRAS', 'quote': 'KRAS'},
                        'alteration': {'raw_value': 'G12D', 'quote': 'G12D'},
                        'assertion_status': 'PRESENT'}],
        'interventions': [{'name': {'raw_value': 'panitumumab', 'quote': 'panitumumab'},
                           'role': 'TARGET', 'assertion_status': 'UNKNOWN'}],
        'previous_interventions': [], 'target_intervention': None,
        'query_intent': 'THERAPY_EVALUATION', 'clinical_question': 'evaluating panitumumab',
    }


def test_provider_visible_nullable_shape_preserves_target_and_eligibility(monkeypatch):
    # The observed provider drops nested anyOf object fields. Model that boundary
    # while exercising the real parser, adapter and pre-retrieval gate.
    def post(payload):
        schema = payload['tools'][0]['function']['parameters']['properties']
        raw = arguments()
        target_shape = schema['target_intervention']
        raw['target_intervention'] = (
            {'raw_value': 'panitumumab', 'quote': 'panitumumab'}
            if {'raw_value', 'quote'} <= set(target_shape.get('properties', {})) else {}
        )
        role_enum = schema['interventions']['items']['properties']['role'].get('enum', [])
        raw['interventions'][0]['role'] = 'TARGET' if 'TARGET' in role_enum else 'target_intervention'
        response = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(raw)}}
        ]}}]}
        return 200, response, None, 0, {'http_status': 200}

    monkeypatch.setattr(parser.tr, 'post_with_infra_retry_with_diagnostics', post)
    result = parser.call_parser('SCHEMA-COMPATIBILITY', TEXT)
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert result['case_context_raw']['target_intervention']['raw_value'] == 'panitumumab'
    assert run(TEXT, result['case_context_raw'])['eligibility']['eligible'] is True


def test_empty_target_remains_invalid_and_absent_target_remains_null():
    target_schema = prompt.CASECONTEXT_TOOL_SCHEMA['properties']['target_intervention']
    validator = Draft7Validator(target_schema)
    assert validator.is_valid(None)
    assert validator.is_valid({'raw_value': 'panitumumab', 'quote': 'panitumumab'})
    for invalid in [{}, {'raw_value': None, 'quote': None}, {'raw_value': 'panitumumab'}, 'panitumumab']:
        assert not validator.is_valid(invalid)
    raw = arguments()
    raw['target_intervention'] = {}
    assert 'TARGET_INTERVENTION_KEYS_INVALID' in prompt.tool_argument_errors(raw)


def test_noncanonical_intervention_role_is_rejected_not_silently_lost():
    raw = arguments()
    raw['interventions'][0]['role'] = 'target therapy'
    assert 'INTERVENTION_0_ROLE_INVALID' in prompt.tool_argument_errors(raw)


def test_discovery_does_not_acquire_an_invented_target():
    raw = copy.deepcopy(arguments())
    raw.update(interventions=[], target_intervention=None, query_intent='THERAPY_DISCOVERY')
    text = 'Synthetic test: colorectal cancer with KRAS G12D. Which treatment options exist?'
    assert prompt.tool_argument_errors(raw) == []
    context = parser.adapt_case_context('DISCOVERY', raw, text)
    assert context['target_intervention'] is None
    assert run(text, context)['eligibility']['eligible'] is True

def test_invalid_arguments_are_retried_with_feedback_and_still_validated(monkeypatch):
    payloads = []
    def post(payload):
        payloads.append(copy.deepcopy(payload))
        raw = arguments()
        if len(payloads) == 1:
            raw['disease'] = {}
        response = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(raw)}}
        ]}}]}
        response['usage'] = {'prompt_tokens': 10, 'completion_tokens': 4}
        return 200, response, None, 0, {'http_status': 200}
    monkeypatch.setattr(parser.tr, 'post_with_infra_retry_with_diagnostics', post)
    result = parser.call_parser('REPAIR', TEXT)
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert result['retry_result'] == 'INVALID_TOOL_ARGUMENTS_RECOVERED'
    assert len(payloads) == 2
    assert 'DISEASE_KEYS_INVALID' in payloads[1]['messages'][-1]['content']
    assert result['parser_attempts'][0]['reason_codes'] == ['DISEASE_KEYS_INVALID']
    assert result['model_call_count'] == 2
    assert result['input_tokens'] == 20
    assert result['output_tokens'] == 8
    assert result['token_usage_complete'] is True


def test_invalid_arguments_retry_is_bounded_and_never_coerces_empty_objects(monkeypatch):
    calls = []
    def post(payload):
        calls.append(payload)
        raw = arguments()
        raw['disease'] = {}
        response = {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(raw)}}
        ]}}]}
        return 200, response, None, 0, {'http_status': 200}
    monkeypatch.setattr(parser.tr, 'post_with_infra_retry_with_diagnostics', post)
    result = parser.call_parser('REPAIR-FAIL', TEXT)
    assert len(calls) == 2
    assert result['transport_result'] == 'INVALID_TOOL_ARGUMENTS'
    assert result['case_context_raw'] is None
    assert result['retry_result'] == 'INVALID_TOOL_ARGUMENTS_FINAL'
