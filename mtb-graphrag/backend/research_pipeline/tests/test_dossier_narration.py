"""Real text narration, distinct from selecting prewritten variants."""
from copy import deepcopy
import json
from unittest.mock import patch

from backend.research_pipeline.narrative import narrator, prompt
from backend.research_pipeline.narrative.controlled import verify_controlled
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.verifier import verify_narrative
from backend.research_pipeline.tests.test_narrative_verifier import _synthetic_dossier


def generated(source):
    return {
        'narrative_summary': 'Il dossier descrive il caso e le relazioni recuperate.',
        'candidate_narratives': [{'candidate_id': c['candidate_id'],
                                 'text': 'La relazione con PANITUMUMAB è descritta nel dossier.'}
                                for c in source['candidates']],
        'limitations_summary': 'Materiale per ricerca.',
        'closing_note': 'Sintesi per la revisione del dossier.',
    }


def test_live_provider_uses_dossier_narration():
    from backend.research_pipeline import live_providers
    source = build_narrator_input(_synthetic_dossier())
    with patch.object(narrator, 'call_dossier_narrator', return_value={'narrative': None}) as call:
        live_providers.narrator_fn('CASE', source)
    call.assert_called_once_with('CASE', source, run_index=0)


def test_model_receives_content_and_verifiable_fallback_is_always_separate():
    source = build_narrator_input(_synthetic_dossier(quote='patients responded to panitumumab'))
    before = deepcopy(source)
    observed = []

    def provider(payload):
        observed.append(payload)
        args = generated(source)
        return 200, {'choices': [{'finish_reason': 'tool_calls', 'message': {'tool_calls': [
            {'type': 'function', 'function': {'name': prompt.TOOL_NAME,
                                             'arguments': json.dumps(args)}}]}}]}, None, 0

    with patch.object(narrator.tr, 'post_with_infra_retry', side_effect=provider):
        result = narrator.call_dossier_narrator('CASE', source)
    request = observed[0]['messages'][-1]['content']
    assert 'patients responded to panitumumab' in request
    assert 'PANITUMUMAB' in request
    assert 'concise' not in observed[0]['tools'][0]['function']['parameters']['properties']
    assert result['narrative']['generation_origin'] == 'MODEL_DOSSIER_NARRATION'
    assert verify_controlled(source, result['deterministic_fallback'])['status'] == 'PASS'
    assert source == before


def test_generated_contract_rejects_new_numbers_and_stale_binding():
    source = build_narrator_input(_synthetic_dossier())
    output = generated(source)
    output['dossier_narration_contract'] = {'version': 'dossier-narration/1.0',
                                           'input_hash': source['narrator_input_hash']}
    output['narrator_input_hash'] = source['narrator_input_hash']
    output['narrative_hash'] = narrator.narrative_hash(output)
    assert verify_narrative({}, source, output)['status'] == 'PASS'
    output['candidate_narratives'][0]['text'] += ' Il tasso di risposta è 87%.'
    output['narrative_hash'] = narrator.narrative_hash(output)
    assert 'NARRATIVE_UNAUTHORIZED_NUMBER' in verify_narrative({}, source, output)['reason_codes']
    output['dossier_narration_contract']['input_hash'] = 'different'
    assert 'NARRATIVE_INPUT_BINDING_MISMATCH' in verify_narrative({}, source, output)['reason_codes']


def test_generated_contract_rejects_extra_fields_and_does_not_mutate_input():
    source = build_narrator_input(_synthetic_dossier())
    before = deepcopy(source)
    output = generated(source)
    output['dossier_narration_contract'] = {'version': 'dossier-narration/1.0',
                                           'input_hash': source['narrator_input_hash']}
    output['narrator_input_hash'] = source['narrator_input_hash']
    output['narrative_hash'] = narrator.narrative_hash(output)
    output['new_clinical_result'] = 'invented'
    assert 'NARRATIVE_SHAPE_INVALID' in verify_narrative({}, source, output)['reason_codes']
    assert source == before


def test_source_identifiers_do_not_become_clinical_quantities():
    dossier = _synthetic_dossier()
    dossier['candidate_therapies'][0]['document_support']['selected_papers'] = ['EB-0000']
    source = build_narrator_input(dossier)
    output = generated(source)
    output['candidate_narratives'][0]['text'] = 'Il dossier conserva il riferimento EB-0000.'
    output['dossier_narration_contract'] = {'version': 'dossier-narration/1.0',
                                           'input_hash': source['narrator_input_hash']}
    output['narrator_input_hash'] = source['narrator_input_hash']
    output['narrative_hash'] = narrator.narrative_hash(output)
    assert 'NARRATIVE_UNAUTHORIZED_NUMBER' not in verify_narrative({}, source, output)['reason_codes']


def test_documentary_quote_is_bound_to_its_candidate():
    from backend.research_pipeline.narrative.verifier import _check_quotes
    from backend.research_pipeline.narrative.input_projection import allowed_entities
    quote = 'This exact documentary sentence belongs to the first record only.'
    source = {'candidates': [
        {'candidate_id': 'P1', 'documentary_findings': [
            {'disposition': 'RETAINED_RECORD', 'quotation': quote}]},
        {'candidate_id': 'P2', 'documentary_findings': [
            {'disposition': 'EXCLUDED_RECORD', 'quotation': 'Excluded words must remain excluded.'}]}]}
    output = {'candidate_narratives': [{'candidate_id': 'P1', 'text': 'Fonte: "' + quote + '".'}]}
    assert _check_quotes(output, {}, allowed_entities(source), source) == ([], [])
    output['candidate_narratives'][0]['candidate_id'] = 'P2'
    assert _check_quotes(output, {}, allowed_entities(source), source)[0]


def test_transport_exception_preserves_separate_verified_fallback():
    source = build_narrator_input(_synthetic_dossier())
    with patch.object(narrator, 'call_narrator', side_effect=RuntimeError('transport unavailable')):
        result = narrator.call_dossier_narrator('CASE', source)
    assert result['narrative'] is None
    assert result['transport_result'] == 'TRANSPORT_EXCEPTION'
    assert verify_controlled(source, result['deterministic_fallback'])['status'] == 'PASS'


def test_documentary_public_source_identity_has_candidate_scope():
    from backend.research_pipeline.narrative.verifier import _check_entities
    from backend.research_pipeline.narrative.input_projection import allowed_entities
    source = {'candidates': [
        {'candidate_id': 'P1', 'documentary_findings': [{'disposition': 'RETAINED_RECORD',
          'source': {'document_id': 'pmcid:PMC4382632', 'public_source_identity': 'pmid:24508103'}}]},
        {'candidate_id': 'P2', 'documentary_findings': []}]}
    output = {'candidate_narratives': [{'candidate_id': 'P1', 'text': 'Fonte PMID:24508103.'}]}
    assert _check_entities(output, source, allowed_entities(source)) == []
    output['candidate_narratives'][0]['candidate_id'] = 'P2'
    assert _check_entities(output, source, allowed_entities(source))


def test_empty_findings_do_not_establish_failed_document_retrieval():
    from backend.research_pipeline.narrative.input_projection import narrator_input_hash
    source = build_narrator_input(_synthetic_dossier())
    source['candidates'][0].update(documentary_contract_version='documentary-findings/1.1',
                                   documentary_findings=[], documentary_attempts=[])
    source['narrator_input_hash'] = narrator_input_hash(source)
    output = generated(source)
    output['dossier_narration_contract'] = {'version': 'dossier-narration/1.0',
                                           'input_hash': source['narrator_input_hash']}
    output['narrator_input_hash'] = source['narrator_input_hash']
    output['candidate_narratives'][0]['text'] = 'Non sono stati reperiti documenti a supporto.'
    output['narrative_hash'] = narrator.narrative_hash(output)
    assert 'NARRATIVE_UNSUPPORTED_RETRIEVAL_CLAIM' in verify_narrative({}, source, output)['reason_codes']
    output['candidate_narratives'][0]['text'] = 'Il dossier conserva zero osservazioni documentali.'
    output['narrative_hash'] = narrator.narrative_hash(output)
    assert 'NARRATIVE_UNSUPPORTED_RETRIEVAL_CLAIM' not in verify_narrative({}, source, output)['reason_codes']
