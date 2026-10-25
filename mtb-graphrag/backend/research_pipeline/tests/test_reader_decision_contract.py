"""Every demonstrated Reader action carries its mandatory explicit decision."""
import copy
import json
from backend.research_pipeline.enrichment import prompt_v3 as prompt
from backend.research_pipeline.enrichment.enricher_v3 import _transport


def response(arguments):
    return {'choices': [{'message': {'tool_calls': [{'function': {
        'name': prompt.TOOL_NAME, 'arguments': json.dumps(arguments)}}]}}]}


def test_rendered_decision_examples_are_transport_valid_without_inference():
    request = json.loads(prompt.render_request({}, {}, 'doc:fixture', []))
    contract = request['output_decision_contract']
    assert contract['required_fields'] == ['decision']
    for example in contract['examples']:
        assert _transport(200, response(example), None)[0] == 'V3_TRANSPORT_VALID'


def test_missing_decision_is_still_rejected_even_with_a_quote():
    arguments = {'source_unit_id': 'SU-fixture', 'quote': 'Literal example.'}
    original = copy.deepcopy(arguments)
    outcome, _, reasons = _transport(200, response(arguments), None)
    assert outcome == 'INVALID_TOOL_ARGUMENTS'
    assert 'REQUIRED_FIELD_MISSING:decision' in reasons
    assert arguments == original


def test_abstention_example_does_not_hide_present_observation_fields():
    request = json.loads(prompt.render_request({}, {}, 'doc:fixture', []))
    example = next(e for e in request['output_decision_contract']['examples'] if e['decision'] == 'ABSTAIN')
    example['quote'] = 'Must remain rejected.'
    assert _transport(200, response(example), None)[0] == 'INVALID_TOOL_ARGUMENTS'
