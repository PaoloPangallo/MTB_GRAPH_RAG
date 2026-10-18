"""Source-first explanations preserve bibliographic identity and literal text."""
from copy import deepcopy

from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.narrator import narrative_hash, _argument_errors
from backend.research_pipeline.narrative.output_contract import valid_body
from backend.research_pipeline.narrative.presentation import build_narrative_presentation
from backend.research_pipeline.narrative.verifier import verify_narrative

QUOTE = 'The source describes the molecular profile examined in this research example.'
TITLE = 'A synthetic publication title for source binding'


def dossier():
    return {'case_id': 'SOURCE-FIRST', 'documentary_contract_version': 'documentary-findings/1.1',
            'case_summary': {'disease': 'melanoma', 'gene': 'BRAF', 'variant': 'V600K'},
            'paper_evidence': [{
                'candidate_id': 'P1', 'document_id': 'pmcid:PMC100', 'relation': 'has_evidence_statement',
                'source_bibliography': [{'document_id': 'pmcid:PMC100', 'public_source_identity': 'pmid:100',
                                         'title': TITLE, 'journal': 'Test journal'}],
                'documentary_findings': [{'disposition': 'RETAINED_RECORD',
                    'source': {'document_id': 'pmcid:PMC100', 'public_source_identity': 'pmid:100',
                               'source_unit_id': 'SU-1'},
                    'quotation': QUOTE, 'observed': {},
                    'checks': {'quotation': {'status': 'AUTHENTICATED'}}}],
            }], 'limitations': []}


def narrative(source, text):
    output = {'narrative_summary': source.get('case_overview') or 'La ricerca riguarda melanoma e BRAF V600K.',
              'candidate_narratives': [{'candidate_id': 'P1', 'text': text}],
              'limitations_summary': '', 'closing_note': '',
              'dossier_narration_contract': {'version': 'dossier-narration/1.1',
                                             'input_hash': source['narrator_input_hash']},
              'narrator_input_hash': source['narrator_input_hash']}
    output['narrative_hash'] = narrative_hash(output)
    return output


def test_title_public_identity_and_quote_reach_narrator_and_presentation():
    original = dossier()
    before = deepcopy(original)
    source = build_narrator_input(original)
    card = source['candidates'][0]['source_cards'][0]
    assert card['title'] == TITLE
    assert card['public_source_identity'] == 'pmid:100'
    assert card['validated_quote'] == QUOTE
    assert card['url'] == 'https://pubmed.ncbi.nlm.nih.gov/100/'
    # Source details are visible even when model prose is rejected or unavailable.
    presentation = build_narrative_presentation(original, None, {'status': 'FAIL'})
    assert presentation['candidates'][0]['sources'][0]['title'] == TITLE
    assert presentation['candidates'][0]['sources'][0]['validated_quote'] == QUOTE
    assert original == before


def test_source_first_text_requires_identity_title_and_quote():
    original = dossier()
    source = build_narrator_input(original)
    output = narrative(source, 'Il documento descrive il profilo molecolare ricercato.')
    result = verify_narrative(original, source, output)
    for code in ('NARRATIVE_SOURCE_IDENTIFICATION_OMITTED', 'NARRATIVE_SOURCE_TITLE_OMITTED',
                 'NARRATIVE_SOURCE_QUOTE_OMITTED'):
        assert code in result['reason_codes']
    output = narrative(source, f'Fonte: {TITLE} (PMID:100). Citazione: "{QUOTE}". Il passaggio descrive il profilo ricercato.')
    assert verify_narrative(original, source, output)['status'] == 'PASS'


def test_optional_footer_fields_can_be_empty():
    body = {'narrative_summary': 'Sintesi del caso.',
            'candidate_narratives': [{'candidate_id': 'P1', 'text': 'Osservazione.'}],
            'limitations_summary': '', 'closing_note': ''}
    assert _argument_errors(body) == []
    assert valid_body(body)


def test_excluded_or_unauthenticated_content_is_not_promoted_to_a_quote():
    original = dossier()
    original['paper_evidence'][0]['documentary_findings'][0]['disposition'] = 'EXCLUDED_RECORD'
    source = build_narrator_input(original)
    assert source['candidates'][0]['source_cards'][0]['validated_quote'] is None


def test_builder_keeps_bound_bibliography():
    from backend.research_pipeline.dossier.builder import _paper_result_fields
    supplied = {'source_bibliography': deepcopy(dossier()['paper_evidence'][0]['source_bibliography'])}
    assert _paper_result_fields(supplied)['source_bibliography'] == supplied['source_bibliography']


def test_quoted_source_title_is_metadata_and_keeps_candidate_binding():
    source = build_narrator_input(dossier())
    text = f'Fonte: "{TITLE}" (PMID:100). Citazione: "{QUOTE}".'
    assert verify_narrative(dossier(), source, narrative(source, text))['status'] == 'PASS'


def test_metadata_remains_visible_without_a_reader_observation():
    original = dossier()
    original['paper_evidence'][0]['documentary_findings'] = []
    source = build_narrator_input(original)
    card = source['candidates'][0]['source_cards'][0]
    assert card['title'] == TITLE
    assert card['validated_quote'] is None
    assert card['disposition'] == 'METADATA_ONLY'


def test_case_overview_preserves_question_instead_of_substituting_source_drug():
    original = dossier()
    original['case_summary']['intervention'] = 'dabrafenib e trametinib'
    source = build_narrator_input(original)
    assert 'dabrafenib e trametinib' in source['case_overview']
    output = narrative(source, f'Fonte: {TITLE} (PMID:100). Citazione: "{QUOTE}".')
    output['narrative_summary'] = 'La domanda riguarda trametinib.'
    output['narrative_hash'] = narrative_hash(output)
    assert 'NARRATIVE_CASE_OVERVIEW_CHANGED' in verify_narrative(original, source, output)['reason_codes']


def test_subjunctive_negation_keeps_local_scope():
    from backend.research_pipeline.narrative.lexicon import support_claim_hits
    assert support_claim_hits('La malattia non sia stata confermata come identica.') == []
    assert support_claim_hits('La malattia non sia stata confermata. La relazione è confermata.')


def test_literal_source_blocks_are_bound_separately_from_model_explanation():
    source = build_narrator_input(dossier())
    output = narrative(source, 'Il passaggio descrive il profilo molecolare esaminato.')
    output['dossier_narration_contract']['version'] = 'dossier-narration/1.2'
    output['canonical_sources'] = {'P1': deepcopy(source['candidates'][0]['source_cards'])}
    assert verify_narrative(dossier(), source, output)['status'] == 'PASS'
    output['canonical_sources']['P1'][0]['validated_quote'] = 'invented'
    assert 'NARRATIVE_SOURCE_BLOCK_MISMATCH' in verify_narrative(dossier(), source, output)['reason_codes']
