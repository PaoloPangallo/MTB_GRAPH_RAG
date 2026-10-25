"""Regression guards for the concrete omissions found in the semantic audit."""
from copy import deepcopy
import pytest

from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.verifier import verify_narrative
from backend.research_pipeline.tests.test_narrative_multistudy import multistudy, covered_output, check


def repaired():
    data = multistudy()
    data['case_summary']['intervention'] = 'dabrafenib e trametinib'
    for finding in data['paper_evidence'][0]['documentary_findings']:
        finding['clinical_applicability'] = 'NOT_EVALUATED'
        finding['checks']['correspondence'] = {'fields': {'disease': 'NOT_CONFIRMED'}}
    source = build_narrator_input(data)
    output = covered_output(source)
    output['dossier_narration_contract']['version'] = 'dossier-narration/1.4'
    for item in output['candidate_narratives'][0]['observation_narratives']:
        item['case_relevance'] = 'La fonte esamina trametinib; la domanda riguarda la combinazione dabrafenib e trametinib, un intervento diverso.'
    output['limitations_summary'] = source.get('presentation_scope_note', '')
    return data, source, output


def test_case_connection_and_one_shared_scope_note_pass():
    data, source, output = repaired()
    assert source['presentation_scope_note']
    assert check(data, source, output)['status'] == 'PASS'


def test_connection_cannot_disappear_when_all_observations_are_present():
    data, source, output = repaired()
    output['candidate_narratives'][0]['observation_narratives'][1].pop('case_relevance')
    assert 'NARRATIVE_CASE_LINK_OMITTED' in check(data, source, output)['reason_codes']


def test_shared_clinical_scope_cannot_disappear():
    data, source, output = repaired()
    output['limitations_summary'] = ''
    assert 'NARRATIVE_CLINICAL_SCOPE_OMITTED' in check(data, source, output)['reason_codes']


def test_unconfirmed_correspondence_cannot_be_presented_as_unconfirmed_disease():
    data, source, output = repaired()
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] += ' La malattia non è stata confermata.'
    assert 'NARRATIVE_DISEASE_CHECK_MISSTATED' in check(data, source, output)['reason_codes']


def test_connection_is_subject_to_the_same_grounding_checks():
    data, source, output = repaired()
    output['candidate_narratives'][0]['observation_narratives'][0]['case_relevance'] += ' La risposta è 87%.'
    assert 'NARRATIVE_UNAUTHORIZED_NUMBER' in check(data, source, output)['reason_codes']


def test_correspondence_wording_is_allowed_but_does_not_license_a_later_diagnosis_claim():
    data, source, output = repaired()
    text = output['candidate_narratives'][0]['observation_narratives'][0]
    text['text'] += ' La corrispondenza per la malattia non è stata confermata.'
    assert check(data, source, output)['status'] == 'PASS'
    text['text'] += ' La malattia non è stata confermata.'
    assert 'NARRATIVE_DISEASE_CHECK_MISSTATED' in check(data, source, output)['reason_codes']


def test_reported_fact_is_distinct_from_a_treatment_indication():
    from backend.research_pipeline.narrative.lexicon import recommendation_hits
    assert recommendation_hits('È indicato che si tratta di un test sintetico.') == []
    assert recommendation_hits('È indicato iniziare trametinib.')


def test_immediate_trailing_correspondence_qualifier_keeps_the_check_scope():
    data, source, output = repaired()
    text = output['candidate_narratives'][0]['observation_narratives'][0]
    text['text'] += ' La malattia non è stata confermata esplicitamente nei campi di corrispondenza.'
    assert check(data, source, output)['status'] == 'PASS'
    text['text'] += ' La malattia non è stata confermata. I campi di corrispondenza sono disponibili.'
    assert 'NARRATIVE_DISEASE_CHECK_MISSTATED' in check(data, source, output)['reason_codes']


@pytest.mark.parametrize('suffix', [
    '. Nei campi di corrispondenza si registra il confronto.',
    '; nei campi di corrispondenza si registra il confronto.',
    ', nei campi di corrispondenza si registra il confronto.',
])
def test_separate_correspondence_clause_cannot_license_unconfirmed_disease(suffix):
    data, source, output = repaired()
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] += (
        ' La malattia non è stata confermata' + suffix)
    assert 'NARRATIVE_DISEASE_CHECK_MISSTATED' in check(data, source, output)['reason_codes']
