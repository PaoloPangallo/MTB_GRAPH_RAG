from dataclasses import replace
from types import SimpleNamespace
from backend.research_pipeline.experimental.sourceunit_selector import select, SourceUnitSelectionInput
from backend.research_pipeline.retrieval import live_sourceunit_selection as live
from backend.research_pipeline.retrieval.canonical_rrf import select_rrf
import pytest


def _record(cid, doc):
    return SimpleNamespace(candidate_id=cid, document_id=doc, bundle_id=cid + doc,
                           resolved=True, full_text_available=False, lineage={}, content_hash='snapshot')


@pytest.mark.parametrize('profile', ['focused-v1', 'canonical'])
def test_cap_is_applied_before_expensive_selection_and_reuse_rebinds_hash(monkeypatch, profile):
    if profile == 'focused-v1':
        monkeypatch.setenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', profile)
    else:
        monkeypatch.delenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', raising=False)
    monkeypatch.setattr(live, 'MAX_PAPERS_PER_ASSOCIATION', 1)
    candidate = {'candidate_id': 'a', 'biomarkers': [{'gene': 'BRAF', 'alteration': 'V600E'}],
                 'interventions': [{'label': 'dabrafenib'}]}
    units = {'one': {'source_unit_id': 'one', 'document_id': 'pmid:1', 'unit_type': 'ABSTRACT', 'text': 'BRAF V600E dabrafenib response.'},
             'two': {'source_unit_id': 'two', 'document_id': 'pmid:2', 'unit_type': 'ABSTRACT', 'text': 'Other cancer.'}}
    resolution = SimpleNamespace(documents=[_record(c, d) for c in ('a', 'b') for d in ('pmid:1', 'pmid:2')])
    index = live.SelectionIndex.build(resolution, units)
    calls = []
    def scorer(value, top_k):
        calls.append(value.document_id)
        return select(value, top_k=top_k)
    first = live.select_live_papers_for_association({'candidate_id': 'a', 'candidate': candidate}, units,
                resolution=resolution, selection_index=index, selector_fn=scorer)
    other = dict(candidate, candidate_id='b')
    second = live.select_live_papers_for_association({'candidate_id': 'b', 'candidate': other}, units,
                resolution=resolution, selection_index=index, selector_fn=scorer)
    assert calls == (['pmid:1'] if profile == 'focused-v1' else ['pmid:1', 'pmid:2'])
    if profile == 'focused-v1':
        assert first['deferred_documents'][0]['document_id'] == 'pmid:2'
    paper = second['selected_papers'][0]
    assert paper['selection_reused']
    expected = SourceUnitSelectionInput.from_candidate(other, 'pmid:1', [units['one']], selection_intent=paper.get('selection_intent'))
    assert paper['selector']['input_hash'] == expected.input_hash()
    assert paper['selector']['candidate_id'] == 'b'
    uncached = live.select_live_papers_for_association({'candidate_id': 'b', 'candidate': other}, units,
                resolution=resolution, selector_fn=scorer)
    assert paper['selector'] == uncached['selected_papers'][0]['selector']


def test_relevant_cell_survives_hierarchy(monkeypatch):
    monkeypatch.setenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', 'focused-v1')
    units = [{'source_unit_id': 'p', 'document_id': 'pmid:1', 'unit_type': 'FULLTEXT_PARAGRAPH', 'text': 'Unrelated information.'},
             {'source_unit_id': 'c', 'document_id': 'pmid:1', 'unit_type': 'TABLE_CELL', 'text': 'BRAF V600E dabrafenib resistance'}]
    candidate = {'biomarkers': [{'gene': 'BRAF', 'alteration': 'V600E'}], 'interventions': [{'label': 'dabrafenib'}]}
    selection = SourceUnitSelectionInput.from_candidate(candidate, 'pmid:1', units)
    result = select_rrf(selection, strategy='BM25_STRUCTURE', top_k=1)
    assert result.selected_source_unit_ids == ('c',)


def test_trial_selection_never_contains_private_full_units(monkeypatch):
    import json
    monkeypatch.setenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', 'focused-v1')
    doc = 'nct:NCT12345678'
    units = {'u': {'source_unit_id': 'u', 'document_id': doc, 'unit_type': 'BRIEF_SUMMARY', 'text': 'PRIVATE FULL REGISTRY TEXT'}}
    record = _record('a', doc)
    resolution = SimpleNamespace(documents=[record])
    index = live.SelectionIndex.build(resolution, units)
    selection = live.select_live_papers_for_association({'candidate_id': 'a', 'candidate': {'candidate_id': 'a'}},
        units, resolution=resolution, selection_index=index)
    assert 'PRIVATE FULL REGISTRY TEXT' not in json.dumps(selection)
    assert selection['selected_papers'][0]['trial_fact_provenance']['nct_id'] == 'NCT12345678'


def test_duplicate_document_keeps_exclusion_lineage(monkeypatch):
    monkeypatch.setenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', 'focused-v1')
    record = _record('a', 'pmid:1')
    duplicate = _record('a', 'pmid:1')
    duplicate.bundle_id = 'other-bundle'
    units = {'u': {'source_unit_id': 'u', 'document_id': 'pmid:1', 'unit_type': 'ABSTRACT', 'text': 'BRAF response'}}
    association = {'candidate_id': 'a', 'candidate': {'candidate_id': 'a', 'biomarkers': [{'type': 'Gene', 'label': 'BRAF'}]}}
    result = live.select_live_papers_for_association(association, units,
        resolution=SimpleNamespace(documents=[record, duplicate]), selector_fn=select)
    assert len(result['selected_papers']) == 1
    assert any(e['bundle_id'] == 'other-bundle' and e['reason_codes'] == ['DUPLICATE_DOCUMENT_ID'] for e in result['excluded_papers'])
