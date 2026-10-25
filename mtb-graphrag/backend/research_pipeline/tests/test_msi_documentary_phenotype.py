"""Future-fix contracts; controlled Reader outputs, actual cached source quotations.

These are NOT real model outputs. No provider or document resolver is called.
The JSON fixture was produced by the cached-only audit with zero network calls.
"""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from backend.research_pipeline.enrichment.document_verification import minimal_target
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.retrieval import kg_retrieval as kg
from backend.research_pipeline.terminology.loader import get_registry

AUDIT = json.loads((Path(__file__).parent / 'fixtures/msi_controlled_cached_publications.json').read_text(encoding='utf-8'))

@pytest.fixture(params=AUDIT['results'], ids=lambda x: x['document_id'])
def actual_case(request):
    fixture = deepcopy(request.param)
    candidate = deepcopy(kg._linked_candidates(kg.load_candidates(), get_registry())[fixture['candidate_id']])
    return candidate, fixture['reader_observation'], fixture['source_unit']['text']


def assess(case):
    candidate, observation, quote = case
    return assess_relation_support(candidate, observation, source_unit_text=quote)


def test_target_carries_source_phenotype_identity_without_a_gene(actual_case):
    candidate, _, _ = actual_case
    target = minimal_target(candidate)
    identity = target.get('phenotype') or {}
    assert identity.get('source_profile_id') == 'CIViCProfile:5118'
    assert identity.get('source_variant_ids') == ['CIViCVariant:4944']
    assert identity.get('name') == 'MSI'
    assert identity.get('value') == 'HIGH'
    assert identity.get('registry_version') == get_registry().version
    assert target['genes'] == []
    assert target['candidate_drug'] is None


def test_literal_biomarker_confirms_source_phenotype_only(actual_case):
    result = assess(actual_case)
    assert result['fields'].get('phenotype') == 'CONFIRMED'
    assert 'phenotype' in result['central']
    assert result['fields']['gene'] == 'NOT_APPLICABLE'
    assert result['fields']['drug'] == 'NOT_APPLICABLE'
    # A mixed cohort is not an MSI-H-only effect estimate.
    assert result['result'] != 'FULL_SUPPORT'
    scope = result.get('phenotype_scope') or {}
    assert scope.get('population_relation') == 'BROADER_OR_ALTERNATIVE'
    assert scope.get('subgroup_effect_established') is False


@pytest.mark.parametrize('value', ['MSI', 'MSI-L', 'MSS', 'dMMR', 'High'])
def test_other_or_unspecified_subject_cannot_confirm_high(actual_case, value):
    candidate, observation, quote = actual_case
    # Include an actual quote span even when this controlled subject is invalid:
    # support must not silently use the case query or upstream profile as proof.
    observation['observed_relation']['subjects'] = [{'type': 'BIOMARKER', 'surface_value': value, 'linked_gene': None}]
    result = assess((candidate, observation, quote))
    assert result['fields'].get('phenotype') == 'NOT_CONFIRMED'
    assert result['result'] != 'FULL_SUPPORT'


def test_negated_or_uncertain_assertion_cannot_be_promoted(actual_case):
    candidate, observation, quote = actual_case
    for assertion in ['RELATION_NEGATED', 'RELATION_UNCERTAIN', 'ENTITY_CO_OCCURRENCE']:
        observation['observed_relation']['relation_assertion'] = assertion
        result = assess((candidate, observation, quote))
        assert not result['predicates']['relation_full_specificity']
        assert result['result'] != 'FULL_SUPPORT'


def test_unlinked_profile_descriptor_cannot_establish_identity(actual_case):
    candidate, observation, quote = actual_case
    candidate['entity_resolution']['profile_id'] = 'CIViCProfile:12'
    candidate['source_properties']['profile']['name'] = 'BRAF V600E'
    candidate['subject'] = {'id': 'MolecularProfile:12', 'label': 'BRAF V600E', 'type': 'MolecularProfile'}
    # Graph lineage still names MSI profile5118: contradictory source identities.
    target = minimal_target(candidate)
    assert not target.get('phenotype')
    result = assess((candidate, observation, quote))
    assert result['fields'].get('phenotype') in {'UNKNOWN', 'NOT_CONFIRMED', 'NOT_APPLICABLE'}
    assert result['result'] != 'FULL_SUPPORT'


@pytest.mark.parametrize('part', ['profile_id', 'source_profile_id', 'component', 'ast', 'subject', 'graph'])
def test_source_lineage_parts_are_independently_required(actual_case, part):
    candidate, _, _ = actual_case
    if part == 'profile_id':
        candidate['entity_resolution']['profile_id'] = 'CIViCProfile:12'
    elif part == 'source_profile_id':
        candidate['source_properties']['profile']['molecular_profile_id'] = '12'
    elif part == 'component':
        candidate['entity_resolution']['profile']['component_ids'] = ['CIViCVariant:12']
    elif part == 'ast':
        candidate['entity_resolution']['profile']['ast']['op'] = 'ENTITY'
    elif part == 'subject':
        candidate['subject']['id'] = 'MolecularProfile:12'
    else:
        candidate['graph_path'] = ['MolecularProfile:12', 'Variant:4944']
    assert not minimal_target(candidate).get('phenotype')


@pytest.mark.parametrize('operator,expected', [('or', 'BROADER_OR_ALTERNATIVE'), ('and', 'INTERSECTION'), ('/', 'UNKNOWN')])
def test_population_operator_is_literal_not_cooccurrence(actual_case, operator, expected):
    candidate, observation, quote = actual_case
    # Controlled derivatives exercise grammar, not actual publication results.
    quote = quote.replace(' or ', ' ' + operator + ' ')
    observation['quote'] = quote
    result = assess((candidate, observation, quote))
    assert result['phenotype_scope']['population_relation'] == expected
    assert result['phenotype_scope']['subgroup_effect_established'] is False
    assert result['result'] != 'FULL_SUPPORT'



def test_phenotype_survives_documentary_projection_and_reading_notice(actual_case):
    from backend.research_pipeline.dossier.observations import project_record
    from backend.research_pipeline.dossier.reading import build_reading_guide
    candidate, observation, quote = actual_case
    support = assess(actual_case)
    record = {'candidate_support': support, 'observed_relation': observation['observed_relation'],
              'quote': quote, 'quote_valid': True, 'relation_family': 'EVIDENCE_STATEMENT'}
    finding = project_record(record, {'candidate_id': candidate['candidate_id']}, 'RETAINED_RECORD')
    assert finding['requested_target']['phenotype'] == support['phenotype']
    assert finding['limitations']['phenotype_scope'] == support['phenotype_scope']
    assert finding['checks']['correspondence']['phenotype_scope'] == support['phenotype_scope']
    guide = build_reading_guide({'paper_evidence': [{'documentary_findings': [finding]}]})
    notices = guide['findings'][0]['notices']
    assert any(n['code'] == 'PHENOTYPE_IDENTITY_CORRESPONDENCE' for n in notices)
    assert any(n['code'] == 'PHENOTYPE_ALTERNATIVE_POPULATION' for n in notices)


def test_source_phenotype_reader_payload_is_optional_and_search_target_only(actual_case):
    from backend.research_pipeline.enrichment.prompt_v3 import render_request
    candidate, _, _ = actual_case
    rendered = json.loads(render_request({}, candidate, 'audit:controlled', []))
    assert rendered['candidate']['phenotype']['source_profile_id'] == 'CIViCProfile:5118'
    assert rendered['candidate_role'] == 'SEARCH_TARGET_NOT_OBSERVED_FACT'
    candidate['source_properties']['profile']['name'] = 'BRAF V600E'
    rendered = json.loads(render_request({}, candidate, 'audit:controlled', []))
    assert 'phenotype' not in rendered['candidate']



def test_ordinary_gene_target_keeps_optional_phenotype_absent():
    from backend.research_pipeline.enrichment.prompt_v3 import render_request
    candidate = {'subject': {'type': 'Gene', 'label': 'BRAF'}, 'biomarkers': [{'type': 'Gene', 'label': 'BRAF'}]}
    assert 'phenotype' not in minimal_target(candidate)
    assert 'phenotype' not in json.loads(render_request({}, candidate, 'audit:controlled', []))['candidate']


def test_separate_mentions_do_not_establish_a_population_operator(actual_case):
    candidate, observation, quote = actual_case
    quote = quote.replace(' or ', '. Separately, ')
    observation['quote'] = quote
    result = assess((candidate, observation, quote))
    assert result['phenotype_scope']['logical_operator'] == 'UNKNOWN'
    assert result['phenotype_scope']['population_relation'] == 'UNKNOWN'
    assert result['phenotype_scope']['literal_span'] is None



def test_controlled_reader_transport_and_validator_accept_cached_gene_free_quote(actual_case):
    from backend.research_pipeline.enrichment import prompt_v3
    from backend.research_pipeline.enrichment.enricher_v3 import _transport
    from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
    candidate, controlled, quote = actual_case
    # Reconstruct a controlled tool message; never label this a real Reader run.
    args = {k: v for k, v in controlled.items() if k in prompt_v3.TOOL_SCHEMA['properties']}
    wire = {'choices': [{'message': {'tool_calls': [{'function': {
        'name': prompt_v3.TOOL_NAME, 'arguments': json.dumps(args)}}]}}]}
    status, observation, errors = _transport(200, wire, None)
    assert status == 'V3_TRANSPORT_VALID'
    assert not errors
    uid = observation['source_unit_id']
    doc = next(r['document_id'] for r in AUDIT['results'] if r['candidate_id'] == candidate['candidate_id'])
    unit = {'source_unit_id': uid, 'document_id': doc, 'text': quote}
    validation = validate_enrichment_v3(status, observation, candidate=candidate,
        paper_bundle={'document_id': doc, 'source_unit_ids': [uid]}, source_units_by_id={uid: unit})
    assert validation['outcome'] == 'ENRICHMENT_V3_ACCEPTED'
    assert observation['observed_relation']['subjects'][0]['type'] == 'BIOMARKER'
    assert observation['observed_relation']['subjects'][0].get('linked_gene') is None
