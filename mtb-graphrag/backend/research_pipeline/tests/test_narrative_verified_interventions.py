"""The dossier introduction must preserve every verified research intervention."""
from copy import deepcopy

from backend.research_pipeline.dossier.builder import _case_summary
from backend.research_pipeline.narrative.input_projection import build_narrator_input


def test_all_verified_interventions_reach_the_narrator_overview():
    context = {'case_id': 'BRAF', 'disease': {'raw_value': 'melanoma metastatico'},
               'biomarkers': [{'gene': 'BRAF', 'alteration': 'V600K'}],
               'target_intervention': {'raw_value': 'dabrafenib'},
               'entity_resolution': {'interventions': [
                   {'raw_value': 'dabrafenib', 'status': 'RESOLVED'},
                   {'raw_value': 'trametinib', 'status': 'RESOLVED'}]}}
    before = deepcopy(context)
    summary = _case_summary(context)
    source = build_narrator_input({'case_summary': summary, 'paper_evidence': [],
                                  'clinical_trials': [], 'kg_only_relations': []})
    assert summary['intervention'] == 'dabrafenib e trametinib'
    assert 'dabrafenib e trametinib' in source['case_overview']
    assert context == before


def test_unverified_parser_interventions_do_not_expand_the_case_summary():
    context = {'target_intervention': {'raw_value': 'dabrafenib'},
               'interventions': [{'name': 'unverified agent', 'role': 'TARGET'}]}
    assert _case_summary(context)['intervention'] == 'dabrafenib'


def test_verified_plural_contract_preserves_unmapped_targets_and_deduplicates():
    context = {'target_intervention': {'raw_value': 'dabrafenib'},
               'target_interventions': [{'raw_value': 'dabrafenib'},
                                        {'raw_value': 'DABRAFENIB'},
                                        {'raw_value': 'unmapped agent'}]}
    assert _case_summary(context)['intervention'] == 'dabrafenib e unmapped agent'
