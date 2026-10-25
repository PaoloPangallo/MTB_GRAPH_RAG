"""Regressions reproduced from the additional Italian clinical requests."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from backend.research_pipeline.casecontext import parser, pipeline, prompt
from backend.research_pipeline.casecontext.pair_grounding import ground_pair
from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import orchestrator
from backend.research_pipeline.budget import CallBudget


def val(text):
    return {'raw_value': text, 'quote': text}


def context(text, *, gene=None, alteration=None, alteration_type=None):
    return parser.adapt_case_context('LIVE-REGRESSION', {
        'disease': val('carcinoma colorettale'),
        'biomarkers': [{'gene': val(gene) if gene else None, 'alteration': val(alteration) if alteration else None,
                        'alteration_type': alteration_type, 'assertion_status': 'PRESENT', 'clinical_role': 'PRIMARY'}],
        'previous_interventions': [], 'target_intervention': val('nivolumab'),
        'query_intent': 'THERAPY_EVALUATION', 'clinical_question': None,
    }, text)


@pytest.mark.parametrize('expression', ['amplificazione di FGFR1', 'amplification of FGFR1', 'amplificazione del gene FGFR1'])
def test_category_before_gene_is_one_explicit_local_pair(expression):
    alteration = 'amplificazione' if expression.startswith('amplificazione') else 'amplification'
    pair = ground_pair(expression, 'FGFR1', alteration)
    assert pair and pair['quote'] == expression and pair['negated'] is False


def test_reversed_category_does_not_join_independent_genes():
    assert ground_pair('amplificazione di FGFR2 e FGFR1', 'FGFR1', 'amplificazione') is None
    pair = ground_pair('assenza di amplificazione di FGFR1', 'FGFR1', 'amplificazione')
    assert pair and pair['negated']


def test_amplification_survives_the_accepted_projection():
    text = 'Paziente con carcinoma colorettale e amplificazione di FGFR1. Valutare nivolumab.'
    raw = context(text, gene='FGFR1', alteration='amplificazione', alteration_type='AMPLIFICATION')
    working = deepcopy(raw)
    checked = pipeline.run(text, working)
    projected = pipeline.build_retrieval_case_context(working, checked['mentions'])
    assert projected['biomarkers'][0]['alteration'] == 'amplificazione'
    assert projected['biomarkers'][0]['pair_source_span']['quote'] == 'amplificazione di FGFR1'


def test_msi_without_degree_requests_clarification_before_retrieval():
    text = 'Paziente con carcinoma colorettale e MSI, grado non riportato. Valutare nivolumab.'
    raw = context(text, alteration='MSI', alteration_type='PHENOTYPE')
    result = pipeline.run(text, raw)
    assert result['eligibility']['eligible'] is False
    assert 'MOLECULAR_PHENOTYPE_SCOPE_UNSPECIFIED' in result['eligibility']['reason_codes']
    assert 'microsatellite_status' in result['eligibility']['missing_required_fields']
    assert result['eligibility']['verified_fields']['genes'] == []


def test_a_phenotype_name_cannot_be_accepted_as_a_gene_field():
    arguments = {'disease': val('carcinoma colorettale'),
        'biomarkers': [{'gene': val('microsatelliti (MSI)'), 'alteration': None}],
        'previous_interventions': [], 'target_intervention': val('nivolumab'),
        'query_intent': 'THERAPY_EVALUATION', 'clinical_question': None}
    assert 'BIOMARKER_0_GENE_IS_PHENOTYPE' in prompt.tool_argument_errors(arguments)


def test_canonical_orchestrator_honors_the_phenotype_clarification_gate(tmp_path):
    text = 'Paziente con carcinoma colorettale e MSI, grado non riportato. Valutare nivolumab.'
    raw = context(text, alteration='MSI', alteration_type='PHENOTYPE')
    with patch.object(orchestrator.retrieval_mod, 'retrieve', return_value={
            'associations': [], 'excluded_candidates': [], 'no_match': True}) as retrieval:
        run = orchestrator.run_case(case_id='MSI-GATE-INTEGRATION', clinical_text=text,
            call_parser_fn=lambda *args: {'transport_result': 'FORCED_TOOL_VALID', 'case_context_raw': raw},
            call_enricher_fn=lambda *args: pytest.fail('Reader must not be called'),
            source_units_by_id={}, budget=CallBudget(3), ledger=EventLedger(tmp_path / 'events.sqlite3'))
    retrieval.assert_not_called()
    assert run.status == 'STOPPED'
    assert run.stopped_at == 'MISSING_REQUIRED_FIELDS'


def test_real_similar_gene_symbols_are_not_rejected_as_phenotypes():
    arguments = {'disease': val('carcinoma colorettale'),
        'biomarkers': [{'gene': val('MSI1'), 'alteration': None}],
        'previous_interventions': [], 'target_intervention': None,
        'query_intent': 'THERAPY_DISCOVERY', 'clinical_question': None}
    assert not prompt.tool_argument_errors(arguments)


@pytest.mark.parametrize('recovered', [False, True])
def test_phenotype_misclassification_has_one_bounded_reextraction(recovered):
    text = 'Paziente con carcinoma colorettale e MSI. Valutare nivolumab.'
    bad = {'disease': val('carcinoma colorettale'),
        'biomarkers': [{'gene': val('MSI'), 'alteration': None}],
        'previous_interventions': [], 'target_intervention': val('nivolumab'),
        'query_intent': 'THERAPY_EVALUATION', 'clinical_question': None}
    good = deepcopy(bad)
    good['biomarkers'] = [{'gene': None, 'alteration': val('MSI'), 'alteration_type': 'PHENOTYPE'}]
    def response(arguments):
        return (200, {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [{
            'function': {'name': prompt.TOOL_NAME, 'arguments': json.dumps(arguments)}}]}}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1}}, None, 0, {})
    with patch.object(parser.tr, 'post_with_infra_retry_with_diagnostics', side_effect=[
            response(bad), response(good if recovered else bad)]) as network:
        result = parser.call_parser('PHENOTYPE-REGRESSION', text)
    assert network.call_count == 2
    assert result['parser_attempts'][0]['reason_codes'] == ['BIOMARKER_0_GENE_IS_PHENOTYPE']
    if recovered:
        assert result['transport_result'] == 'FORCED_TOOL_VALID'
        assert result['case_context_raw']['biomarkers'][0]['gene'] is None
        assert result['case_context_raw']['biomarkers'][0]['alteration'] == 'MSI'
    else:
        assert result['transport_result'] == 'INVALID_TOOL_ARGUMENTS'
        assert result['case_context_raw'] is None
