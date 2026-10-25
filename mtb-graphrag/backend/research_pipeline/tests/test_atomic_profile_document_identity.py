"""Source-linked atomic profiles retain gene ownership through document checks."""
from copy import deepcopy

import pytest

from backend.research_pipeline.enrichment.document_verification import minimal_target, structural_verify
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation


def candidate():
    return {'candidate_id': 'PROFILE-FGFR1', 'relation_family': 'EVIDENCE_DRUG',
        'predicate': 'targets_drug', 'graph_path': ['MolecularProfile:263'],
        'object': {'type': 'Drug', 'label': 'infigratinib'},
        'biomarkers': [{'type': 'Variant', 'label': 'FGFR1 Amplification'}],
        'context': {'disease': 'sqNSCLC'}, 'document_identifiers': [{'pmid': '12345678'}],
        'source_properties': {'profile': {'name': 'FGFR1 Amplification'},
                              'evidence': {'evidence_id': '1908', 'significance': 'Sensitivity/Response'}}}


def check(gene='FGFR1', alteration='amplified', linked='FGFR1'):
    text = f'{gene}-{alteration} sqNSCLC responded to BGJ398.'
    unit = {'source_unit_id': 'S', 'document_id': 'pmid:12345678', 'text': text}
    observed = {'source_unit_id': 'S', 'quote': text, 'observed_relation': {
        'subjects': [{'type': 'GENE', 'surface_value': gene},
                     {'type': 'ALTERATION', 'surface_value': alteration, 'linked_gene': linked}],
        'intervention': 'BGJ398', 'intervention_composition': 'SINGLE_AGENT',
        'relation_scope': 'SINGLE', 'molecular_composition': 'SINGLE', 'disease': 'sqNSCLC'}}
    return structural_verify(candidate(), {'document_id': unit['document_id'],
        'resolved_source_unit_ids': ['S']}, unit, observed)


def test_atomic_profile_uses_source_variant_and_gene_links_without_mutation():
    source = candidate(); before = deepcopy(source)
    target = minimal_target(source)
    assert target['genes'] == ['FGFR1']
    assert target['variants'] == ['Amplification']
    assert target['gene_ids'] == ['NCBIGene:2260']
    assert target['variant_ids'] == ['CIViCVariant:267']
    assert source == before


def test_atomic_amplification_licenses_semantic_review_only():
    result = check()
    assert result['structural_status'] == 'PASS', result['structural_reason_codes']
    assert 'final_admission' not in result


@pytest.mark.parametrize('gene,alteration,linked', [
    ('FGFR2', 'amplified', 'FGFR2'), ('FGFR1', 'expression', 'FGFR1'),
    ('FGFR1', 'nonamplified', 'FGFR1'), ('FGFR1', 'amplified', 'FGFR2'),
])
def test_profile_identity_preserves_gene_and_alteration(gene, alteration, linked):
    assert check(gene, alteration, linked)['structural_status'] != 'PASS'


def test_amplification_word_form_requires_gene_scoped_concept():
    assert entity_relation('Amplification', 'amplified', domain='VARIANT', gene_id='NCBIGene:2260') == 'CANONICAL_ALIAS'
    for value in ['nonamplified', 'not amplified', 'overexpressed', 'amplified or deleted']:
        assert entity_relation('Amplification', value, domain='VARIANT', gene_id='NCBIGene:2260') not in {'IDENTICAL', 'CANONICAL_ALIAS'}
    assert entity_relation('Amplification', 'amplified', domain='VARIANT') not in {'IDENTICAL', 'CANONICAL_ALIAS'}


def test_compound_profile_is_not_reduced_to_one_component():
    source = candidate()
    source['source_properties']['profile']['name'] = 'FGFR1 Amplification OR FGFR2 Amplification'
    target = minimal_target(source)
    assert target['genes'] == []
    assert target['variants'] == ['FGFR1 Amplification']


@pytest.mark.parametrize('change', [
    {'graph_path': []}, {'graph_path': ['MolecularProfile:263', 'MolecularProfile:264']},
    {'graph_path': ['MolecularProfile:264']},
    {'source_properties': {'profile': {'name': 'FGFR1 Amplification', 'gene_ids': ['NCBIGene:2263']}}},
    {'source_properties': {'profile': {'name': 'FGFR1 Amplification', 'variant_ids': ['CIViCVariant:1']}}},
    {'source_properties': {'profile': {'name': 'FGFR1 Amplification', 'components': [{'name': 'FGFR2 Amplification'}]}}},
])
def test_profile_recovery_requires_unique_consistent_source_identity(change):
    source = candidate(); source.update(change)
    assert minimal_target(source)['genes'] == []


def test_documented_squamous_acronym_keeps_histology_and_context():
    from backend.research_pipeline.terminology.case_resolution import compare_disease_context
    from backend.research_pipeline.terminology.matching import registry
    reg = registry()
    assert compare_disease_context('Lung Squamous Cell Carcinoma', 'sqNSCLC', reg)['relation'] == 'VERIFIED_ALIAS'
    assert compare_disease_context('Lung Adenocarcinoma', 'sqNSCLC', reg)['relation'] == 'DIFFERENT'
    assert compare_disease_context('Lung Squamous Cell Carcinoma', 'metastatic sqNSCLC', reg)['relation'] == 'SAME_CONCEPT_CONTEXT_UNRESOLVED'
