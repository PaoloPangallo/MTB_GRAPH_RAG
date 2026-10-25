import pytest
from backend.research_pipeline.retrieval.reader_budget import pack_reader_units


def test_budget_preserves_whole_quotes_and_records_deferred():
    units = {'a': {'text': '123456'}, 'b': {'text': '123'}, 'c': {'text': '12'}}
    selected, deferred = pack_reader_units(('a', 'b', 'c'), units, 5)
    assert selected == ('b', 'c')
    assert deferred == ('a',)
    assert units['a']['text'] == '123456'


def test_invalid_text_limit_rejected():
    with pytest.raises(ValueError):
        pack_reader_units((), {}, 0)


def test_adjacent_context_cannot_overrun_reader_limit(monkeypatch):
    from backend.research_pipeline.enrichment.context_reader import read_with_context_policy, ContextPolicy
    from backend.research_pipeline.budget import CallBudget
    monkeypatch.setenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', 'focused-v1')
    text = 'Such tumors showed resistance to drug X.'
    monkeypatch.setenv('RESEARCH_PIPELINE_MAX_READER_SOURCE_CHARACTERS', str(len(text)))
    unit = {'source_unit_id': 'e', 'document_id': 'pmid:1', 'unit_type': 'FULLTEXT_SENTENCE',
            'paragraph_index': 0, 'sentence_index': 1, 'text': text}
    neighbor = dict(unit, source_unit_id='c', sentence_index=0, text='A long neighboring context sentence about the cohort.')
    seen = []
    def reader(*args):
        seen.extend(args[-1])
        return {'transport_result': 'V3_TRANSPORT_VALID', 'enrichment': {'decision': 'ABSTAIN', 'abstain_reason': 'NO_RELEVANT_EVIDENCE'}}
    result = read_with_context_policy(reader, CallBudget(1), 'case', {}, {'candidate_id': 'x'}, '',
        {'document_id': 'pmid:1', 'resolved_source_unit_ids': ['e']}, [unit], [neighbor, unit],
        ContextPolicy(adjacent_context_enabled=True))
    assert sum(len(u['text']) for u in seen) <= len(text)
    assert result.call['reader_context']['context_source_unit_ids'] == []


def test_actual_context_audit_contains_only_delivered_context():
    from backend.research_pipeline.enrichment.context_reader import _context_metadata, ContextPolicy
    evidence = {'source_unit_id': 'e', 'document_id': 'pmid:1', 'unit_type': 'FULLTEXT_SENTENCE',
                'paragraph_index': 0, 'sentence_index': 1, 'text': 'Such tumors responded.'}
    context = dict(evidence, source_unit_id='c', sentence_index=0, text='A relevant cohort.')
    delivered = [dict(evidence, reader_role='EVIDENCE'), dict(context, reader_role='CONTEXT',
                  context_relation='PRECEDING_SENTENCE', context_for_source_unit_ids=['e'])]
    metadata = _context_metadata([evidence], [context, evidence], {'document_id': 'pmid:1'},
                                 ContextPolicy(adjacent_context_enabled=True), delivered)
    assert metadata['context_source_unit_ids'] == ['c']
    assert metadata['context_characters'] == len(context['text'])
    assert metadata['context_relations'][0]['context_for_source_unit_ids'] == ['e']
    assert metadata['deferred_context_source_unit_ids'] == []
