from backend.research_pipeline.terminology.case_resolution import disease_context, resolve_case
from backend.research_pipeline.terminology.loader import get_registry
from backend.research_pipeline.terminology.molecular import molecular_observation, resolve_variant


def test_italian_squamous_lung_histology_retains_metastatic_scope():
    result = disease_context('carcinoma squamoso del polmone metastatico', get_registry())
    assert result['status'] == 'RESOLVED'
    assert result['concept_ids'] == ('DOID:3907',)
    assert result['residual_context'] == 'metastatic'
    assert result['approved_alias_source'].startswith('https://media.aiom.it/')


def test_literal_italian_amplification_resolves_without_rewriting_observation():
    item = {'gene': 'FGFR1', 'alteration': 'amplificazione', 'alteration_type': 'AMPLIFICATION',
            'assertion_status': 'PRESENT', 'source_spans': [{'quote': 'FGFR1 amplificazione'}]}
    resolved = resolve_case({'biomarkers': [item]}, get_registry())
    record = resolved['entity_resolution']['biomarkers'][0]
    assert record['variant']['concept_ids'] == ('CIViCVariant:267',)
    assert record['variant']['raw_value'] == 'amplificazione'
    assert record['observation']['raw_alteration'] == 'amplificazione'
    assert record['observation']['qualifier_status'] == 'COMPATIBLE'
    assert record['observation']['source_spans'][0]['quote'] == 'FGFR1 amplificazione'


def test_unspecified_msi_exposes_unsupported_phenotype_without_inventing_high():
    observation = molecular_observation({'gene': None, 'alteration': 'MSI',
                                        'alteration_type': 'PHENOTYPE'}, get_registry()).to_dict()
    assert observation['phenotype_name'] == 'MSI'
    assert observation['phenotype_value'] == 'UNSPECIFIED'
    assert observation['phenotype_resolution_status'] == 'UNSUPPORTED_DOMAIN'
    assert observation['concept_ids'] == ()


def test_translation_does_not_consume_unknown_qualifiers_or_conflicting_types():
    registry = get_registry()
    gene = registry.resolve('GENE', 'FGFR1')
    assert resolve_variant(gene, 'amplificazione sospetta', registry).status == 'UNMAPPED'
    observation = molecular_observation({'gene': 'FGFR1', 'alteration': 'amplificazione',
                                         'alteration_type': 'EXPRESSION'}, registry)
    assert observation.qualifier_status == 'CONFLICT'
    assert observation.concept_ids == ()
    disease = disease_context('carcinoma squamoso del polmone sospetto', registry)
    assert disease['status'] == 'UNMAPPED'
    assert disease['unresolved_context_words'] == ['sospetto']
