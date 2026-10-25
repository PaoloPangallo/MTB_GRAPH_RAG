from types import SimpleNamespace
from backend.research_pipeline.retrieval.document_plan import plan_documents


def test_pertinent_abstract_precedes_unrelated_fulltext():
    records = [SimpleNamespace(document_id='pmid:1', bundle_id='a', full_text_available=True),
               SimpleNamespace(document_id='pmid:2', bundle_id='b', full_text_available=False)]
    units = {'pmid:1': [{'unit_type': 'TITLE', 'text': 'Other cancer therapies'}],
             'pmid:2': [{'unit_type': 'ABSTRACT', 'text': 'BRAF dabrafenib trametinib resistance in melanoma'}]}
    intent = {'case_question': {'interventions': ['dabrafenib and trametinib']},
              'candidate_target': {'biomarkers': [{'gene': 'BRAF'}]}}
    plan = plan_documents(records, units, intent, 1)
    assert [r.document_id for r in plan['selected']] == ['pmid:2']
    assert [r.document_id for r in plan['deferred']] == ['pmid:1']


def test_unbounded_plan_keeps_negative_documents():
    records = [SimpleNamespace(document_id='pmid:1', bundle_id='a', full_text_available=False)]
    assert plan_documents(records, {}, {}, None)['selected'] == records


def test_candidate_drug_remains_relevant_in_discovery():
    records = [SimpleNamespace(document_id='pmid:1', bundle_id='a', full_text_available=True),
               SimpleNamespace(document_id='pmid:2', bundle_id='b', full_text_available=False)]
    units = {'pmid:1': [{'unit_type': 'TITLE', 'text': 'BRAF V600E vemurafenib'}],
             'pmid:2': [{'unit_type': 'TITLE', 'text': 'BRAF V600E dabrafenib'}]}
    intent = {'candidate_target': {'interventions': [{'label': 'dabrafenib'}],
                                    'biomarkers': [{'gene': 'BRAF', 'alteration': 'V600E'}]}}
    assert plan_documents(records, units, intent, 1)['selected'][0].document_id == 'pmid:2'
