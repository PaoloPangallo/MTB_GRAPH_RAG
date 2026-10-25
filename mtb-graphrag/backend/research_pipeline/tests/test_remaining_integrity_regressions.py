"""Campaign regressions: alternatives, real caller metadata, trial arm fidelity."""
import hashlib
import json
from copy import deepcopy

import pytest

from backend.research_pipeline.enrichment.observation_checks import assess_observation
from backend.research_pipeline.enrichment.document_verification import admit
from backend.research_pipeline.enrichment import transport
from backend.research_pipeline.tests.test_semantic_admission_contract import assessment, structural
from backend.research_pipeline.documents import trial_resolution
from backend.research_pipeline.dossier.builder import _trial_result_fields
from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown


@pytest.mark.parametrize('quote', [
    'Patients had BRAF V600E versus V600K mutations.',
    'The population comprised both V600E and V600K mutation-positive patients.',
    'The study included two cohorts, comprising both V600E and V600K.',
    'Pazienti con BRAF V600E oppure V600K.',
    'Patients had BRAF V600E vs. V600K.',
])
def test_alternative_cohorts_are_not_a_molecular_combination(quote):
    result = assess_observation(quote, {'molecular_composition': 'COMBINATION'})
    assert 'ALTERNATIVE_VARIANTS_NOT_COALTERATION' in result['reason_codes']


def test_coexisting_mutations_are_not_rejected_as_separate_populations():
    assert assess_observation('Both V600E and V600K co-occurred in the same tumor.',
                              {'molecular_composition': 'COMBINATION'})['status'] == 'PASS'


def test_actual_semantic_caller_metadata_does_not_invalidate_assessment():
    output = {**assessment(), 'model': 'test', 'prompt_version': 'test',
              'operational_metrics': {'model_call_count': 1, 'input_tokens': 10}}
    assert admit(structural(), output)['final_admission'] == 'DOCUMENT_SUPPORTED'
    assert admit(structural(), {**output, 'invented_scientific_field': True})['final_admission'] == 'UNVERIFIABLE'


def test_trial_arms_are_bound_to_the_exact_cached_snapshot(tmp_path):
    payload = {'protocolSection': {'identificationModule': {'nctId': 'NCT02465060'},
        'armsInterventionsModule': {'armGroups': [
            {'label': 'NRAS cohort', 'description': 'NRAS mutation-positive melanoma', 'interventionNames': ['Drug: Binimetinib']},
            {'label': 'Other cohort', 'description': 'Other molecular cohort', 'interventionNames': ['Drug: Trametinib']}]}}}
    data = json.dumps(payload).encode()
    (tmp_path / 'trial.json').write_bytes(data)
    record = {'document_id': 'nct:NCT02465060', 'local_cache_path': 'trial.json',
              'content_hash': hashlib.sha256(data).hexdigest()}
    result = trial_resolution.read_trial_structure(tmp_path, record)
    assert result['arm_groups'] == payload['protocolSection']['armsInterventionsModule']['armGroups']
    assert result['trial_structure_provenance']['snapshot_digest'] == record['content_hash']
    assert _trial_result_fields(result)['arm_groups'] == result['arm_groups']
    with pytest.raises(ValueError):
        trial_resolution.read_trial_structure(tmp_path, {**record, 'content_hash': 'wrong'})
    with pytest.raises(ValueError):
        trial_resolution.read_trial_structure(tmp_path, {**record, 'document_id': 'nct:NCT00000001'})


def test_markdown_documentary_observations_are_readable_before_technical_json():
    finding = {'evidence_id': 'E', 'disposition': 'RETAINED_RECORD',
        'source': {'document_id': 'pmid:1', 'source_unit_id': 'SU1'},
        'quotation': 'Drug X reduced growth in mice.',
        'observed': {'intervention': 'Drug X', 'disease': 'Melanoma', 'effect_direction': 'SENSITIVITY_RESPONSE'},
        'checks': {'quotation': {'status': 'AUTHENTICATED'}, 'semantic': {'status': 'NOT_REQUIRED_BY_POLICY'}}}
    dossier = {'documentary_contract_version': 'documentary-findings/1.1',
        'paper_evidence': [{'candidate_id': 'C', 'documentary_target': {'subject': {'label': 'BRAF V600E'}},
                            'documentary_findings': [finding]}]}
    before = deepcopy(dossier)
    output = render_dossier_markdown(dossier)
    assert 'Intervento osservato' in output
    assert 'Drug X reduced growth in mice.' in output
    assert output.index('Drug X reduced growth in mice.') < output.index('<details><summary>Schema originale')
    assert '<details>' in output
    assert dossier == before


def test_one_format_retry_preserves_failures_and_counts_all_usage(monkeypatch):
    responses = iter([(200, {'valid': False, 'usage': {'prompt_tokens': 4, 'completion_tokens': 1}}, None, 0),
                      (200, {'valid': True, 'usage': {'prompt_tokens': 6, 'completion_tokens': 2}}, None, 0)])
    payloads = []
    def post(payload):
        payloads.append(deepcopy(payload))
        return next(responses)
    monkeypatch.setattr(transport, 'post_with_infra_retry', post)
    payload = {'messages': [{'role': 'user', 'content': 'source data'}]}
    before = deepcopy(payload)
    result, metrics = transport.post_with_format_retry(payload,
        lambda status, body, error: 'VALID' if body['valid'] else 'INVALID_TOOL_ARGUMENTS')
    assert result[1]['valid']
    assert metrics['model_call_count'] == 2
    assert metrics['input_tokens'] == 10 and metrics['output_tokens'] == 3
    assert [x['outcome'] for x in metrics['format_attempts']] == ['INVALID_TOOL_ARGUMENTS', 'VALID']
    assert payload == before
    assert payloads[1]['messages'][0] == before['messages'][0]


@pytest.mark.parametrize('outcome,status', [('VALID', 200), ('HTTP_ERROR', 429), ('HTTP_ERROR', 500)])
def test_format_retry_never_retries_valid_or_infrastructure_outcomes(monkeypatch, outcome, status):
    calls = []
    def post(payload):
        calls.append(payload)
        return status, {}, None, 0
    monkeypatch.setattr(transport, 'post_with_infra_retry', post)
    transport.post_with_format_retry({'messages': []}, lambda *_: outcome)
    assert len(calls) == 1


def test_format_retry_stops_after_two_invalid_responses(monkeypatch):
    calls = []
    def post(payload):
        calls.append(payload)
        return 200, {}, None, 0
    monkeypatch.setattr(transport, 'post_with_infra_retry', post)
    _, metrics = transport.post_with_format_retry({'messages': []}, lambda *_: 'INVALID_TOOL_ARGUMENTS')
    assert len(calls) == 2
    assert metrics['model_call_count'] == 2
    assert metrics['input_tokens'] is None and not metrics['token_usage_complete']


def test_format_retry_obeys_physical_budget_and_keeps_original_failure(monkeypatch):
    from backend.research_pipeline.budget import CallBudget
    budget = CallBudget(1)
    calls = []
    def post(payload):
        budget.before_transport(payload)
        calls.append(payload)
        return 200, {'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, None, 0
    monkeypatch.setattr(transport, 'post_with_infra_retry', post)
    result, metrics = transport.post_with_format_retry({'messages': []}, lambda *_: 'INVALID_TOOL_ARGUMENTS')
    assert len(calls) == 1
    assert metrics['format_retry_budget_blocked']
    assert metrics['model_call_count'] == 1
    assert result[1]['usage']['prompt_tokens'] == 1


def test_reader_reports_shape_failure_without_inventing_decision():
    from backend.research_pipeline.enrichment.enricher_v3 import _transport
    from backend.research_pipeline.enrichment.prompt_v3 import TOOL_NAME
    for value, reason in [([], 'ARGUMENTS_NOT_OBJECT'), ({}, 'REQUIRED_FIELDS_MISSING'),
                          ({'decision': 3}, 'REQUIRED_FIELD_TYPE_INVALID')]:
        outcome, args, reasons = _transport(200, {'choices': [{'message': {'tool_calls': [
            {'function': {'name': TOOL_NAME, 'arguments': json.dumps(value)}}]}}]}, None)
        assert outcome == 'INVALID_TOOL_ARGUMENTS' and args is None
        assert reason in reasons


def test_partial_infra_retry_is_counted_when_format_budget_runs_out(monkeypatch):
    from backend.research_pipeline.budget import CallBudget
    budget = CallBudget(2)
    calls = []
    def post(payload):
        budget.before_transport(payload)
        calls.append(payload)
        if len(calls) == 1:
            return 200, {'usage': {'prompt_tokens': 4, 'completion_tokens': 1}}, None, 0
        # A 5xx response followed by an infrastructure retry that cannot start.
        budget.before_transport(payload)
        raise AssertionError('budget should have blocked the third transport')
    monkeypatch.setattr(transport, 'post_with_infra_retry', post)
    with budget.activate():
        _, metrics = transport.post_with_format_retry({'messages': []}, lambda *_: 'INVALID_TOOL_ARGUMENTS')
    assert len(calls) == 2
    assert metrics['model_call_count'] == 2
    assert metrics['format_retry_budget_blocked']
    assert not metrics['token_usage_complete'] and metrics['input_tokens'] is None
    assert metrics['format_attempts'][-1]['outcome'] == 'FORMAT_RETRY_BUDGET_EXCEEDED'


def test_alternative_scope_is_valid_wire_data_but_not_single_variant_support():
    from backend.research_pipeline.enrichment.enricher_v3 import _transport
    from backend.research_pipeline.enrichment.prompt_v3 import TOOL_NAME
    from backend.research_pipeline.enrichment.relation_support import _composition_state
    args = {'decision': 'QUOTE', 'quote': 'Patients had BRAF V600E or V600K.', 'source_unit_id': 'SU',
            'relation_scope': 'ALTERNATIVES', 'molecular_composition': 'ALTERNATIVES'}
    outcome, observed, _ = _transport(200, {'choices': [{'message': {'tool_calls': [
        {'function': {'name': TOOL_NAME, 'arguments': json.dumps(args)}}]}}]}, None)
    assert outcome == 'V3_TRANSPORT_VALID'
    assert _composition_state({}, observed) != 'EXACT'


def test_fusion_resolution_reaches_case_summary_without_rewriting_raw_values():
    from backend.research_pipeline.terminology.case_resolution import resolve_case
    from backend.research_pipeline.terminology.loader import get_registry
    from backend.research_pipeline.dossier.builder import _case_summary
    context = resolve_case({'biomarkers': [{'gene': 'ROS1', 'alteration': 'fusione CD74-ROS1'}]}, get_registry())
    result = _case_summary(context)
    assert result['gene'] == 'ROS1' and result['variant'] == 'fusione CD74-ROS1'
    assert result['molecular_resolution'][0]['fusion_partners'] == ['CD74', 'ROS1']
    assert result['molecular_resolution'][0]['fusion_status'] == 'UNMAPPED'
