"""Regressions from the real BRAF trace, with unrelated negative controls."""
from copy import deepcopy
from backend.research_pipeline.experimental import sourceunit_selector as selector
from backend.research_pipeline.enrichment.proposition_assertion import comparative_cohort_outcome
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.terminology.case_resolution import resolve_case
from backend.research_pipeline.terminology.registry import Registry
from backend.research_pipeline.tests.test_terminology_registry import term
from backend.research_pipeline.tests.test_relation_support_contract_v5 import observation

CAUTION = ('The 3-year rate of overall survival was 86% in the combination-therapy group and 77% in the placebo group '
           '(hazard ratio for death, 0.57; 95% CI, 0.42 to 0.79; P=0.0006), but this level of improvement '
           'did not cross the prespecified interim analysis boundary of P=0.000019.')
OUTCOME = ('Adjuvant use of combination therapy with dabrafenib plus trametinib resulted in a significantly lower '
           'risk of recurrence in patients with stage III melanoma with BRAF V600E or V600K mutations than '
           'the adjuvant use of placebo and was not associated with new toxic effects.')


def test_statistical_boundary_caution_is_not_hard_incompatible():
    candidate={'candidate_id':'gca', 'direction':'Supports', 'disease':[{'label':'melanoma'}],
               'biomarkers':[{'type':'Gene','label':'BRAF'},{'type':'Variant','label':'V600K'}]}
    selection=selector.SourceUnitSelectionInput.from_candidate(candidate,'pmid:1',[])
    features=selector.match_features(CAUTION,selection)
    assert 'EXPLICIT_NEGATION_MISMATCH' not in features['hard_incompatibility']
    assert features['polarity_relevance']==('STATISTICAL_CAUTION',)


def test_adjuvant_recurrence_is_an_asserted_cohort_outcome():
    assert comparative_cohort_outcome(OUTCOME,'dabrafenib plus trametinib',('braf','v600k'),'stage III melanoma')
    for text in [OUTCOME.replace('resulted in','may result in'),
                 OUTCOME.replace('with BRAF V600E or V600K','without BRAF V600E or V600K'),
                 OUTCOME.replace('dabrafenib plus trametinib','placebo',1),
                 'An earlier study reported that '+OUTCOME]:
        assert not comparative_cohort_outcome(text,'dabrafenib plus trametinib',('braf','v600k'),'stage III melanoma')


def trial_enrichment():
    value=observation(gene='BRAF',alteration=None,drug=None,direction='UNKNOWN',disease='melanoma')
    value.update({'source_unit_id':'u','quote':'BRAF genotyping in patients with melanoma.'})
    value['observed_relation']['trial_context']={'nct_id':'NCT02279004'}
    return value


def validate_trial(value,document='nct:NCT02279004',unit_document=None):
    return validate_enrichment_v3('V3_TRANSPORT_VALID',value,candidate={},
      paper_bundle={'document_id':document,'resolved_source_unit_ids':['u']},
      source_units_by_id={'u':{'document_id':unit_document or document,'text':value['quote']}})


def test_nct_identity_is_grounded_by_selected_registry_document():
    result=validate_trial(trial_enrichment())
    assert result['outcome']=='ENRICHMENT_V3_ACCEPTED',result
    assert result['trial_identity_grounding']['basis']=='SOURCE_DOCUMENT_ID'


def test_nct_identity_does_not_license_another_trial_or_other_fields():
    value=trial_enrichment()
    assert validate_trial(value,document='nct:NCT00000001')['outcome']=='QUOTE_INVALID'
    assert validate_trial(value,unit_document='nct:NCT00000001')['outcome']=='QUOTE_INVALID'
    assert validate_trial(value,document='pmid:28891408')['outcome']=='QUOTE_INVALID'
    value['observed_relation']['trial_context']['trial_status']='RECRUITING'
    assert validate_trial(value)['reason_codes']==['TRIAL_TRIAL_STATUS_NOT_GROUNDED']


def test_conjoined_drugs_keep_original_mention_and_resolved_components():
    registry=Registry([term('Drug:1','dabrafenib','INTERVENTION','PREFERRED'),
                       term('Drug:2','trametinib','INTERVENTION','PREFERRED')],'test')
    original={'target_intervention':{'raw_value':'dabrafenib e trametinib'}}
    result=resolve_case(original,registry)['entity_resolution']['interventions'][0]
    assert result['raw_value']=='dabrafenib e trametinib'
    assert result['concept_ids']==()  # no invented identifier for the combined mention
    assert result['component_resolution_status']=='RESOLVED_COMPONENTS'
    assert [r['concept_ids'] for r in result['components']]==[('Drug:1',),('Drug:2',)]
    assert original=={'target_intervention':{'raw_value':'dabrafenib e trametinib'}}


def test_statistical_caution_does_not_erase_an_independent_negation():
    candidate={'candidate_id':'gca', 'direction':'Supports', 'disease':[{'label':'melanoma'}],
               'biomarkers':[{'type':'Gene','label':'BRAF'},{'type':'Variant','label':'V600K'}]}
    selection=selector.SourceUnitSelectionInput.from_candidate(candidate,'pmid:1',[])
    text='BRAF V600K melanoma did not respond to treatment. Overall survival did not cross the prespecified interim analysis boundary.'
    features=selector.match_features(text,selection)
    assert features['polarity_relevance']!=('STATISTICAL_CAUTION',)


def test_hybrid_selection_reserves_statistical_caution_and_real_contrast():
    from backend.research_pipeline.retrieval.canonical_rrf import select_rrf
    candidate={'candidate_id':'gca','direction':'Supports','disease':[{'label':'melanoma'}],
               'biomarkers':[{'type':'Gene','label':'BRAF'},{'type':'Variant','label':'V600K'}]}
    texts={f'positive-{i}':f'BRAF V600K was associated with response in melanoma cohort {i}.' for i in range(6)}
    texts.update(caution=CAUTION,negative='BRAF V600K did not support response in melanoma.')
    units=[{'source_unit_id':uid,'document_id':'pmid:1','text':text,'unit_type':'ABSTRACT_SENTENCE'} for uid,text in texts.items()]
    selection=selector.SourceUnitSelectionInput.from_candidate(candidate,'pmid:1',units)
    result=select_rrf(selection,top_k=5,dense_scorer=lambda s:({uid:100-i for i,uid in enumerate(texts)},{}))
    assert 'caution' in result.selected_source_unit_ids
    assert 'negative' in result.selected_source_unit_ids
    assert len(result.selected_source_unit_ids)==5


def test_partial_components_do_not_look_fully_resolved():
    registry=Registry([term('Drug:1','dabrafenib','INTERVENTION','PREFERRED')],'test')
    result=resolve_case({'target_intervention':{'raw_value':'dabrafenib e unknownagent'}},registry)['entity_resolution']['interventions'][0]
    assert result['component_resolution_status']=='PARTIAL_COMPONENTS'
    assert result['components'][1]['status']=='UNMAPPED'
def test_all_verified_target_interventions_are_resolved_without_inventing_regimen():
    from copy import deepcopy
    from backend.research_pipeline.terminology.case_resolution import resolve_case
    original = {
        'target_intervention': {'raw_value': 'dabrafenib'},
        'target_interventions': [{'raw_value': 'dabrafenib'}, {'raw_value': 'trametinib'}],
    }
    before = deepcopy(original)
    registry = Registry([term('Drug:1', 'dabrafenib', 'INTERVENTION', 'PREFERRED'),
                         term('Drug:2', 'trametinib', 'INTERVENTION', 'PREFERRED')], 'test')
    result = resolve_case(original, registry)['entity_resolution']['interventions']
    assert [row['raw_value'] for row in result] == ['dabrafenib', 'trametinib']
    assert all(row['status'] == 'RESOLVED' for row in result)
    assert all(not row.get('components') for row in result)
    assert original == before
