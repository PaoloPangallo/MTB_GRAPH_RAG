"""Failures observed in the 20-case campaign; software contracts, not clinical gold."""
from copy import deepcopy

import pytest

from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.terminology.case_resolution import disease_context, disease_matches, compare_disease_context
from backend.research_pipeline.terminology import molecular
from backend.research_pipeline.retrieval import kg_retrieval as kr
from backend.research_pipeline.casecontext.pair_grounding import ground_pair
from backend.research_pipeline.casecontext import pipeline as cc
from backend.research_pipeline.terminology.matching import trace


def test_trial_retrieval_trace_uses_effective_conditions_and_provenance():
    provenance = {'nct_id': 'NCT00000001', 'record_hash': 'test-record'}
    result = trace({'disease': {'raw_value': 'carcinoma colorettale'}}, {
        'disease': [], 'trial_context': {
            'conditions': ['Colorectal Cancer'], 'provenance': provenance}})
    scope = result['disease_retrieval_scope'][0]
    assert scope['eligible']
    assert scope['scope'] == 'SOURCE_BROADER_THAN_QUERY_NOT_IDENTITY'
    assert scope['ontology_path']
    assert scope['origin'] == 'TRIAL_CONTEXT'
    assert scope['provenance'] == provenance
    assert result['candidate_diseases'][0]['raw_value'] == 'Colorectal Cancer'


@pytest.mark.parametrize('italian,canonical', [
    ('adenocarcinoma polmonare', 'Lung Adenocarcinoma'),
    ('carcinoma colorettale', 'Colorectal Carcinoma'),
    ('carcinoma mammario', 'Breast Carcinoma'),
    ('carcinoma ovarico', 'Ovarian Carcinoma'),
    ('carcinoma tiroideo', 'Thyroid Carcinoma'),
    ('colangiocarcinoma', 'Cholangiocarcinoma'),
    ('tumore stromale gastrointestinale', 'Gastrointestinal Stromal Tumor'),
    ('leucemia mieloide cronica', 'Chronic Myeloid Leukemia'),
])
def test_italian_disease_keeps_exact_histology_and_source(italian, canonical):
    registry = get_registry()
    result = disease_context(italian, registry)
    assert tuple(result['concept_ids']) == registry.resolve('DISEASE', canonical).concept_ids
    assert result['raw_value'] == italian
    assert result['approved_alias_source']


def test_italian_scope_is_preserved_and_translated_only_by_explicit_lexicon():
    result = disease_context('adenocarcinoma polmonare metastatico recidivato', get_registry())
    assert tuple(result['concept_ids']) == ('DOID:3910',)
    assert result['raw_residual_context'] == 'metastatico recidivato'
    assert result['residual_context'] == 'metastatic recurrent'
    assert compare_disease_context('adenocarcinoma polmonare metastatico', 'Lung Adenocarcinoma', get_registry())['classification'] == 'MATCH_CONTEXTUAL'


def test_partial_generic_word_does_not_establish_unknown_specific_disease():
    result = disease_context('adenocarcinoma di sede sconosciuta inventata', get_registry())
    assert result['status'] != 'RESOLVED'
    assert result['partial_concept_ids'] == ['DOID:299']
    assert 'PARTIAL_DISEASE_MENTION' in result['reasons']


def test_curated_core_with_unknown_qualifiers_licenses_review_only():
    registry = get_registry()
    observed = 'progressive papillary thyroid cancer refractory to radioactive iodine'
    comparison = compare_disease_context('Papillary Thyroid Carcinoma', observed, registry)
    assert comparison['observed']['status'] == 'UNMAPPED'
    assert comparison['relation'] == 'SAME_CONCEPT_CONTEXT_UNRESOLVED'
    assert comparison['classification'] == 'MATCH_CONTEXTUAL'
    assert not disease_matches('Papillary Thyroid Carcinoma', observed, registry)
    assert not kr._term_matches('Papillary Thyroid Carcinoma', observed)


def test_retrieval_can_consult_source_backed_broader_disease_without_claiming_identity():
    registry = get_registry()
    assert kr._term_matches('carcinoma colorettale metastatico', 'Colorectal Cancer')
    assert not disease_matches('carcinoma colorettale metastatico', 'Colorectal Cancer', registry)
    assert compare_disease_context('carcinoma colorettale metastatico', 'Colorectal Cancer', registry)['classification'] != 'MATCH'
    assert not kr._term_matches('carcinoma colorettale', 'Breast Cancer')
    assert not kr._term_matches('Colorectal Cancer', 'Colorectal Carcinoma')
    assert not kr._term_matches('Lung Adenocarcinoma', 'Carcinoma')


@pytest.mark.parametrize('gene,alteration', [('KIF5B-RET', 'fusione'), ('RET', 'fusione KIF5B-RET')])
def test_explicit_hyphen_fusion_links_only_the_pinned_ordered_profile(gene, alteration):
    item = {'gene': gene, 'alteration': alteration, 'alteration_type': 'FUSION', 'assertion_status': 'PRESENT'}
    before = deepcopy(item)
    observation = molecular.molecular_observation(item, get_registry())
    assert item == before
    assert observation.fusion_partners == ('KIF5B', 'RET')
    assert observation.fusion.status == 'RESOLVED'
    assert observation.fusion.concept_ids == ('CIViCVariant:273',)
    assert molecular.fusion_partners('KIF5B-RET') == ()  # a bare hyphen stays ambiguous


def test_unlinked_ros1_fusion_preserves_partners_without_inventing_concept():
    observation = molecular.molecular_observation({'gene': 'ROS1', 'alteration': 'fusione CD74-ROS1', 'alteration_type': 'FUSION'}, get_registry())
    assert observation.fusion_partners == ('CD74', 'ROS1')
    assert observation.fusion.status == 'UNMAPPED'
    assert not observation.fusion.concept_ids


@pytest.mark.parametrize('item', [
    {'gene': 'KIF5B-RET', 'alteration': None},
    {'gene': 'KIF5B-RET', 'alteration': 'amplification', 'alteration_type': 'FUSION'},
    {'gene': 'BRAF', 'alteration': 'fusione KIF5B-RET', 'alteration_type': 'FUSION'},
    {'gene': 'RET-KIF5B', 'alteration': 'fusione', 'alteration_type': 'FUSION'},
    {'gene': 'HLA-DRA', 'alteration': 'fusione', 'alteration_type': 'FUSION'},
])
def test_ambiguous_conflicting_or_reversed_fusion_does_not_link_ret_profile(item):
    observation = molecular.molecular_observation(item, get_registry())
    assert observation.fusion is None or observation.fusion.status != 'RESOLVED'


def test_prefix_fusion_marker_is_grounded_in_one_contiguous_span():
    text = 'RET fusione KIF5B-RET.'
    pair = ground_pair(text, 'KIF5B-RET', 'fusione')
    assert pair and pair['quote'] == 'fusione KIF5B-RET'
    assert text[pair['start_offset']:pair['end_offset']] == pair['quote']
    assert ground_pair('KIF5B-RET. fusione', 'KIF5B-RET', 'fusione') is None
    assert ground_pair('BRAF fusione KIF5B-RET', 'BRAF', 'fusione KIF5B-RET') is None
    assert ground_pair('assenza di fusione KIF5B-RET', 'KIF5B-RET', 'fusione')['negated']


def test_real_ret_fusion_survives_the_full_grounding_projection():
    text = 'Lung Adenocarcinoma. RET fusione KIF5B-RET. Target selpercatinib.'
    def span(value):
        start = text.index(value)
        return {'quote': value, 'start_offset': start, 'end_offset': start + len(value)}
    context = {'disease': {'raw_value': 'Lung Adenocarcinoma', 'normalized_value': 'Lung Adenocarcinoma', 'source_spans': [span('Lung Adenocarcinoma')]},
        'biomarkers': [{'gene': 'KIF5B-RET', 'alteration': 'fusione', 'alteration_type': 'fusion', 'assertion_status': 'PRESENT', 'source_spans': [span('KIF5B-RET'), span('fusione')], 'gene_source_spans': [span('KIF5B-RET')], 'alteration_source_spans': [span('fusione')]}],
        'target_intervention': {'raw_value': 'selpercatinib', 'normalized_value': 'selpercatinib', 'source_spans': [span('selpercatinib')]}, 'query_intent': 'THERAPY_EVALUATION'}
    chain = cc.run(text, context)
    projected = cc.build_retrieval_case_context(context, chain['mentions'])
    assert projected['biomarkers'][0]['alteration'] == 'fusione'
    observation = molecular.molecular_observation(projected['biomarkers'][0], get_registry())
    assert observation.fusion.concept_ids == ('CIViCVariant:273',)
