"""Conservative null repair: a repeated gene quote conveys no variant value."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

from backend.research_pipeline.casecontext import parser


def raw(gene='EGFR',quote=None,value=None,alteration_type=None):
    return {'disease':None,'biomarkers':[{'gene':{'raw_value':gene,'quote':gene},
      'alteration':{'raw_value':value,'quote':gene if quote is None else quote},
      'alteration_type':alteration_type}], 'previous_interventions':[],
      'target_intervention':None,'query_intent':None,'clinical_question':None}


def evaluate(monkeypatch,args,*,text=True,enabled=True):
    message={'content':json.dumps(args)} if text else {'tool_calls':[{
       'function':{'name':'submit_case_context','arguments':json.dumps(args)}}]}
    response={'choices':[{'finish_reason':'stop','message':message}]}
    original=copy.deepcopy(response)
    def post(payload):return 200,copy.deepcopy(response),None,0,{'http_status':200,'raw_response_body':copy.deepcopy(response)}
    monkeypatch.setattr(parser.tr,'post_with_infra_retry_with_diagnostics',post)
    result=parser.call_parser('REDUNDANT','EGFR BRAF NRAS BRCA1 L858R',normalize_text_values=enabled)
    assert result['parser_diagnostics']['raw_response_body']==original
    return result


def test_redundant_gene_quote_nulls_generic_gene_symbols_on_both_channels(monkeypatch):
    for gene in ('EGFR','BRAF','NRAS','BRCA1'):
        for text in (True,False):
            result=evaluate(monkeypatch,raw(gene),text=text)
            assert result['transport_result']=='FORCED_TOOL_VALID'
            assert result['case_context_v2']['biomarkers'][0]['alteration'] is None
            assert result['case_context_raw']['biomarkers'][0]['gene']==gene


def test_variant_quote_with_missing_value_remains_rejected(monkeypatch):
    result=evaluate(monkeypatch,raw(quote='L858R'))
    assert result['transport_result']=='INVALID_TOOL_ARGUMENTS'


def test_missing_quote_with_variant_value_remains_rejected(monkeypatch):
    args=raw(value='L858R');args['biomarkers'][0]['alteration']['quote']=None
    assert evaluate(monkeypatch,args)['transport_result']=='INVALID_TOOL_ARGUMENTS'


def test_declared_alteration_type_prevents_gene_only_quote_erasure(monkeypatch):
    assert evaluate(monkeypatch,raw(alteration_type='AMPLIFICATION'))['transport_result']=='INVALID_TOOL_ARGUMENTS'


def test_extra_keys_prevent_redundant_quote_repair(monkeypatch):
    args=raw();args['biomarkers'][0]['alteration']['extra']='untrusted'
    assert evaluate(monkeypatch,args)['transport_result']=='INVALID_TOOL_ARGUMENTS'


def test_policy_off_preserves_old_rejection_for_both_channels(monkeypatch):
    for text in (True,False):
        assert evaluate(monkeypatch,raw(),text=text,enabled=False)['transport_result']=='INVALID_TOOL_ARGUMENTS'


def test_variant_in_gene_field_never_authorizes_quote_erasure(monkeypatch):
    for gene in ('EGFR L858R', 'L858R', 'EGFRL858R', 'NOTAREALGENE'):
        for text in (True, False):
            assert evaluate(monkeypatch,raw(gene),text=text)['transport_result']=='INVALID_TOOL_ARGUMENTS'


def test_unavailable_identity_asset_fails_closed(monkeypatch):
    from backend.research_pipeline.terminology import loader
    def unavailable():raise loader.TerminologyAssetError('fixture')
    monkeypatch.setattr(loader,'get_registry',unavailable)
    assert evaluate(monkeypatch,raw())['transport_result']=='INVALID_TOOL_ARGUMENTS'
