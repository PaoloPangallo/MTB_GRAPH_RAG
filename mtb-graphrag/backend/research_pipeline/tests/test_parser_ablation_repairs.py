"""Regressions for observed text-JSON nulls and incomplete 2048-token output."""
import copy
import json

import pytest

from backend.research_pipeline.casecontext import parser, prompt
from backend.research_pipeline.budget import CallBudget, CallBudgetExceeded


def arguments(alteration=None):
    return {'disease': None, 'biomarkers': [{'gene': {'raw_value': 'BRAF', 'quote': 'BRAF'},
             'alteration': alteration}], 'previous_interventions': [], 'target_intervention': None,
            'query_intent': None, 'clinical_question': None}


def response(args, *, finish='stop', text=True):
    message={'content':'```json\n'+json.dumps({prompt.TOOL_NAME:args})+'\n```'} if text else {
        'tool_calls':[{'function':{'name':prompt.TOOL_NAME,'arguments':json.dumps(args)}}]}
    return {'choices':[{'finish_reason':finish,'message':message}],
            'usage':{'prompt_tokens':10,'completion_tokens':5}}


def install(monkeypatch,bodies):
    payloads=[]
    def post(payload):
        active=parser.tr.active_budget()
        if active is not None:active.before_transport(payload)
        payloads.append(copy.deepcopy(payload))
        body=copy.deepcopy(bodies[min(len(payloads)-1,len(bodies)-1)])
        return 200,body,None,0,{'http_status':200,'raw_response_body':copy.deepcopy(body)}
    monkeypatch.setattr(parser.tr,'post_with_infra_retry_with_diagnostics',post)
    return payloads


@pytest.mark.parametrize('empty',[{'raw_value':None,'quote':None},{'raw_value':'','quote':''}])
def test_text_json_empty_alteration_is_null_without_changing_raw_response(monkeypatch,empty):
    body=response(arguments(empty));original=copy.deepcopy(body)
    install(monkeypatch,[body]);result=parser.call_parser('NULL','BRAF')
    assert result['transport_result']=='FORCED_TOOL_VALID'
    assert result['case_context_v2']['biomarkers'][0]['alteration'] is None
    assert result['case_context_raw']['biomarkers'][0]['alteration'] is None
    assert result['parser_diagnostics']['raw_response_body']==original
    assert result['parser_diagnostics']['response_normalized'] is True


def test_text_normalization_can_be_disabled_for_ablation(monkeypatch):
    install(monkeypatch,[response(arguments({'raw_value':None,'quote':None}))])
    result=parser.call_parser('BASE','BRAF',normalize_text_values=False)
    assert result['transport_result']=='INVALID_TOOL_ARGUMENTS'
    assert result['case_context_raw'] is None


@pytest.mark.parametrize('partial',[{'raw_value':None,'quote':'V600E'},
    {'raw_value':'V600E','quote':None},{'raw_value':None,'quote':None,'extra':'untrusted'}])
def test_partial_or_extra_alteration_is_never_erased(monkeypatch,partial):
    install(monkeypatch,[response(arguments(partial))])
    result=parser.call_parser('PARTIAL','BRAF V600E')
    assert result['transport_result']=='INVALID_TOOL_ARGUMENTS'
    assert result['case_context_raw'] is None


def truncated():
    return {'choices':[{'finish_reason':'length','message':{'content':'{"biomarkers": ['}}],
            'usage':{'prompt_tokens':10,'completion_tokens':2048}}


def test_truncation_gets_one_larger_attempt_and_accounts_for_both(monkeypatch):
    payloads=install(monkeypatch,[truncated(),response(arguments())])
    result=parser.call_parser('LONG','BRAF')
    assert result['transport_result']=='FORCED_TOOL_VALID'
    assert [p['max_tokens'] for p in payloads]==[2048,8192]
    assert payloads[0]['messages']==payloads[1]['messages']
    assert result['retry_result']=='TEXT_RESPONSE_RECOVERED'
    assert result['model_call_count']==2
    assert result['output_tokens']==2053
    assert [a['maximum_output_tokens'] for a in result['parser_attempts']]==[2048,8192]


def test_second_truncation_remains_failure_and_never_infers_json(monkeypatch):
    payloads=install(monkeypatch,[truncated()])
    result=parser.call_parser('LONG-FAIL','BRAF')
    assert len(payloads)==2
    assert result['case_context_raw'] is None
    assert result['transport_result']=='TEXT_RESPONSE'


def test_truncation_recovery_disabled_is_original_policy(monkeypatch):
    payloads=install(monkeypatch,[truncated()])
    result=parser.call_parser('LENGTH-BASE','BRAF',recover_truncation=False)
    assert len(payloads)==1
    assert result['transport_result']=='TEXT_RESPONSE'


def test_retry_obeys_existing_physical_budget(monkeypatch):
    payloads=install(monkeypatch,[truncated(),response(arguments())])
    with CallBudget(1).activate():
        with pytest.raises(CallBudgetExceeded):parser.call_parser('CAP','BRAF')
    assert len(payloads)==1


def test_http_error_is_not_a_truncation_repair(monkeypatch):
    calls=[]
    def post(payload):
        calls.append(payload);return 429,{},None,0,{'http_status':429}
    monkeypatch.setattr(parser.tr,'post_with_infra_retry_with_diagnostics',post)
    result=parser.call_parser('RATE','BRAF')
    assert result['transport_result']=='HTTP_ERROR'
    assert len(calls)==1


def test_malformed_biomarker_collection_is_rejected_without_normalizer_exception(monkeypatch):
    raw=arguments();raw['biomarkers']=5
    install(monkeypatch,[response(raw)])
    result=parser.call_parser('MALFORMED','BRAF')
    assert result['transport_result']=='INVALID_TOOL_ARGUMENTS'
    assert 'BIOMARKERS_NOT_LIST' in result['transport_reason_codes']


def test_text_empty_alteration_fix_does_not_expand_scalar_disease_repair(monkeypatch):
    raw=arguments({'raw_value':None,'quote':None});raw['disease']='lung cancer'
    install(monkeypatch,[response(raw)])
    result=parser.call_parser('ISOLATED','lung cancer BRAF')
    assert result['transport_result']=='INVALID_TOOL_ARGUMENTS'
