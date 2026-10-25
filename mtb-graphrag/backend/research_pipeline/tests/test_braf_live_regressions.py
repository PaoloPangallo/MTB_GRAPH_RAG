"""Regression cases derived from the recorded BRAF execution."""
from copy import deepcopy
from unittest.mock import patch

import pytest

from backend.research_pipeline.narrative import narrator
from backend.research_pipeline.narrative.verifier import _check_branch_semantics, _unlicensed_global_text
from backend.research_pipeline.tests.test_narrator_workload import _input


TRIAL = {'candidate_id': 'T', 'branch': 'TRIAL', 'trial_context': {
    'nct_id': 'NCT02279004', 'conditions': ['NSCLC', 'Melanoma'],
    'eligibility_status': 'NOT_EVALUATED',
    'evidence_interpretation': 'TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE',
    'graph_provenance': {'node_ids': ['Trial:NCT02279004', 'GeneSymbol:BRAF']},
}}


def test_grounded_trial_association_and_negative_efficacy_from_live_response():
    text = ("È stata identificata un'associazione in un registro di studi (NCT02279004) "
            "che include il melanoma e il gene BRAF. Tuttavia, si tratta di un contesto "
            "di associazione di registro e non di evidenza di efficacia. "
            "L'idoneità individuale non è stata valutata.")
    assert _check_branch_semantics(TRIAL, text) == []


@pytest.mark.parametrize('replacement', [
    ('il melanoma', 'il carcinoma renale'), ('BRAF', 'EGFR'),
    ('NCT02279004', 'NCT12345678'),
    ('non di evidenza di efficacia', 'di evidenza di efficacia'),
    ('non di evidenza di efficacia', 'non non di evidenza di efficacia'),
])
def test_trial_paraphrase_stays_grounded_and_negation_preserving(replacement):
    text = ("È stata identificata un'associazione in un registro di studi (NCT02279004) "
            "che include il melanoma e il gene BRAF. Tuttavia, si tratta di un contesto "
            "di associazione di registro e non di evidenza di efficacia.")
    assert _check_branch_semantics(TRIAL, text.replace(*replacement))


def test_global_case_summary_is_not_misclassified_as_a_trial_claim():
    source = {'case': {'disease': 'melanoma metastatico', 'biomarkers': ['BRAF V600K'],
                       'target_intervention': 'dabrafenib e trametinib'},
              'presentation_scope_note': 'L’applicabilità clinica individuale resta da valutare.'}
    text = ('Caso di ricerca: melanoma metastatico; profilo molecolare BRAF V600K. '
            'La domanda riguarda dabrafenib e trametinib. '
            'L’applicabilità clinica individuale resta da valutare.')
    assert _unlicensed_global_text(text, source) == ''
    assert 'efficace' in _unlicensed_global_text(text + ' Il trial è efficace.', source)
    assert _unlicensed_global_text(text.replace('V600K', 'V600E'), source)


def _result(chunk, outcome='FORCED_TOOL_VALID'):
    return {'transport_result': outcome, 'model_call_count': 1, 'retry_count': 0,
            'latency_ms': 1, 'attempts': [{'transport_result': outcome}],
            'narrative': None if outcome != 'FORCED_TOOL_VALID' else {'candidate_narratives': [
                {'candidate_id': row['candidate_id'], 'text': 'Test prose.'} for row in chunk]}}


def test_rich_candidates_are_batched_by_serialized_input_size():
    source = _input(8)
    for row in source['candidates']:
        row['source_cards'] = [{'title': 'Document', 'quotation': 'original text ' * 3000}]
    before = deepcopy(source)
    sizes = []
    def provider(case_id, batch, run_index):
        sizes.append(len(batch['candidates']))
        return _result(batch['candidates'])
    with patch.object(narrator, '_call_narrator_batch', side_effect=provider):
        result = narrator.call_narrator('CASE', source)
    assert len(sizes) > 1
    assert sum(sizes) == 8
    assert source == before
    assert [row['candidate_id'] for row in result['narrative']['candidate_narratives']] == [
        row['candidate_id'] for row in source['candidates']]


@pytest.mark.parametrize('count', [2, 8, 26])
def test_empty_tool_responses_can_recover_as_smaller_independent_requests(count):
    source = _input(count)
    sizes = []
    def provider(case_id, batch, run_index):
        size = len(batch['candidates'])
        sizes.append(size)
        return _result(batch['candidates'], 'FORCED_TOOL_IGNORED' if size > max(1, count // 2) else 'FORCED_TOOL_VALID')
    with patch.object(narrator, '_call_narrator_batch', side_effect=provider):
        result = narrator.call_narrator('CASE', source)
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert len(result['narrative']['candidate_narratives']) == count
    assert sizes[0] == count
    assert result['model_call_count'] == len(sizes)


def test_reader_reports_the_exact_missing_required_field():
    import json
    from backend.research_pipeline.enrichment import enricher_v3, prompt_v3
    response = {'choices': [{'message': {'tool_calls': [{'function': {
        'name': prompt_v3.TOOL_NAME, 'arguments': json.dumps({'notes': 'No decision supplied'})}}]}}]}
    status, observation, reasons = enricher_v3._transport(200, response, None)
    assert status == 'INVALID_TOOL_ARGUMENTS'
    assert observation is None
    assert 'REQUIRED_FIELD_MISSING:decision' in reasons


def test_reader_format_retry_explicitly_names_required_tool_fields():
    from backend.research_pipeline.enrichment import transport
    payload = {'messages': [{'role': 'user', 'content': 'Original source data'}],
               'tools': [{'function': {'parameters': {'required': ['decision']}}}]}
    requests = []
    def provider(request):
        requests.append(deepcopy(request))
        return 200, {'choices': [{'finish_reason': 'tool_calls'}], 'usage': {
            'prompt_tokens': 10, 'completion_tokens': 5}}, None, 0
    with patch.object(transport, 'post_with_infra_retry', side_effect=provider):
        transport.post_with_format_retry(payload, lambda *_: 'INVALID_TOOL_ARGUMENTS')
    assert len(requests) == 2
    assert 'decision' in requests[1]['messages'][-1]['content']
    assert requests[1]['messages'][0] == payload['messages'][0]
    assert len(payload['messages']) == 1


@pytest.mark.parametrize('profile', ['', 'focused-v1'])
def test_physical_budget_is_active_for_each_canonical_profile(monkeypatch, profile):
    from backend.research_pipeline.budget import CallBudget, active_budget, run_budget_context
    monkeypatch.setenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', profile)
    @run_budget_context
    def execute(*, budget):
        assert active_budget() is budget
        budget.before_transport({'messages': []})
    budget = CallBudget(1)
    execute(budget=budget)
    assert len(budget.transport_attempts) == 1
    assert active_budget() is None


def test_workload_plan_starts_after_physical_retries_and_preserves_explicit_caps():
    from backend.research_pipeline.budget import CallBudget
    adaptive = CallBudget(3, workload_sized=True)
    fixed = CallBudget(3)
    for budget in (adaptive, fixed):
        for _ in range(3):
            budget.before_transport({'messages': []})
        budget.plan_remaining_calls(4)
    assert adaptive.maximum == 7
    assert fixed.maximum == 3


def test_narrator_provisions_discovered_requests_within_a_workload_sized_budget():
    from backend.research_pipeline.budget import CallBudget
    budget = CallBudget(1, workload_sized=True)
    def provider(case_id, batch, run_index):
        budget.before_transport({'messages': []})
        return _result(batch['candidates'], 'FORCED_TOOL_IGNORED' if len(batch['candidates']) > 1 else 'FORCED_TOOL_VALID')
    with budget.activate(), patch.object(narrator, '_call_narrator_batch', side_effect=provider):
        result = narrator.call_narrator('CASE', _input(3))
    assert result['transport_result'] == 'FORCED_TOOL_VALID'
    assert len(budget.transport_attempts) == 5


def test_reporting_a_correspondence_check_is_not_a_prescription():
    from backend.research_pipeline.narrative.lexicon import recommendation_hits
    text = 'La corrispondenza con la malattia è indicata come non confermata.'
    assert recommendation_hits(text) == []
    assert recommendation_hits(text + ' La terapia è indicata per il paziente.')


def test_reporting_an_unresolved_disease_check_is_not_a_prescription():
    from backend.research_pipeline.narrative.lexicon import recommendation_hits
    text = 'La corrispondenza con la malattia è indicata come ancora da confermare.'
    assert recommendation_hits(text) == []
    assert recommendation_hits(text + ' La terapia è indicata per il paziente.')


def test_documented_infigratinib_alias_preserves_single_agent_identity():
    from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation
    assert entity_relation('infigratinib', 'BGJ398', domain='INTERVENTION') == 'CANONICAL_ALIAS'
    assert entity_relation('infigratinib', 'BGJ398 plus chemotherapy', domain='INTERVENTION') not in {'IDENTICAL', 'CANONICAL_ALIAS'}


def test_quoted_trial_title_is_bound_to_its_own_registered_metadata():
    from backend.research_pipeline.narrative.verifier import _check_quotes
    trial = deepcopy(TRIAL)
    title = 'A Prospective Study of Plasma Genotyping as a Noninvasive Biomarker for Genotype-directed Cancer Care'
    trial['trial_context']['title'] = title
    source = {'candidates': [trial, {'candidate_id': 'OTHER'}]}
    narrative = {'candidate_narratives': [{'candidate_id': 'T', 'text': 'Studio "' + title + '".'}]}
    assert _check_quotes(narrative, {}, {'quotes': set()}, source) == ([], [])
    narrative['candidate_narratives'][0]['candidate_id'] = 'OTHER'
    assert _check_quotes(narrative, {}, {'quotes': set()}, source)[0]


def test_negated_registry_efficacy_is_not_a_positive_efficacy_claim():
    text = ("È importante sottolineare che l'associazione registrata in questo registro "
            "di studi (trial) non costituisce un'evidenza di efficacia clinica.")
    assert _check_branch_semantics(TRIAL, text) == []
    assert _check_branch_semantics(TRIAL, text.replace('non costituisce', 'costituisce'))
    assert _check_branch_semantics(TRIAL, text.replace('non costituisce', 'non non costituisce'))


def test_italian_decimal_comma_preserves_the_recorded_scientific_quantity():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.tests.test_narrative_multistudy import multistudy, covered_output, check
    data = multistudy()
    data['paper_evidence'][0]['documentary_findings'][0]['quotation'] += ' P=0.016.'
    source = build_narrator_input(data)
    output = covered_output(source)
    item = output['candidate_narratives'][0]['observation_narratives'][0]
    item['text'] += ' Il valore p riportato è 0,016.'
    assert check(data, source, output)['status'] == 'PASS'
    item['text'] = item['text'].replace('0,016', '0,017')
    assert 'NARRATIVE_OBSERVATION_NUMBER_MISMATCH' in check(data, source, output)['reason_codes']
