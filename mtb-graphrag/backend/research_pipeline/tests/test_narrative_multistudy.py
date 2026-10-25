"""Coverage is checked per retained observation, independently of source cards."""
from copy import deepcopy

import pytest

from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.narrator import narrative_hash
from backend.research_pipeline.narrative.presentation import build_narrative_presentation
from backend.research_pipeline.narrative.verifier import verify_narrative
from backend.research_pipeline.tests.test_narrative_source_first import dossier, narrative


def multistudy(same_document=False):
    data = dossier()
    entry = data['paper_evidence'][0]
    first = entry['documentary_findings'][0]
    first['observed'] = {'disease': 'melanoma', 'intervention': 'trametinib',
                         'finding': 'First documented observation.'}
    second = deepcopy(first)
    second['source']['source_unit_id'] = 'SU-2'
    second['observed']['finding'] = 'Second documented observation.'
    if not same_document:
        second['source'].update(document_id='pmid:200', public_source_identity='pmid:200')
        entry['source_bibliography'].append({'document_id': 'pmid:200',
            'public_source_identity': 'pmid:200', 'title': 'Second synthetic study'})
    entry['documentary_findings'].append(second)
    return data


def covered_output(source):
    result = narrative(source, 'La relazione viene esaminata attraverso le osservazioni delle fonti.')
    result['dossier_narration_contract']['version'] = 'dossier-narration/1.3'
    candidates = source['candidates']
    result['canonical_sources'] = {c['candidate_id']: deepcopy(c.get('source_cards') or []) for c in candidates}
    result['canonical_observations'] = {c['candidate_id']: deepcopy(c.get('narration_observations') or []) for c in candidates}
    for entry, candidate in zip(result['candidate_narratives'], candidates):
        observations = candidate.get('narration_observations') or []
        entry['observation_narratives'] = [{'observation_id': o['observation_id'],
            'text': 'La fonte descrive il profilo molecolare esaminato.'} for o in observations]
        entry['study_comparison'] = {'observation_ids': [o['observation_id'] for o in observations],
            'text': 'Le fonti descrivono osservazioni distinte sul profilo molecolare esaminato.'}
    result['narrative_hash'] = narrative_hash(result)
    return result


def check(data, source, output):
    output['narrative_hash'] = narrative_hash(output)
    return verify_narrative(data, source, output)


def test_projection_keeps_every_observation_and_separates_studies():
    original = multistudy()
    before = deepcopy(original)
    candidate = build_narrator_input(original)['candidates'][0]
    observations = candidate['narration_observations']
    assert len(observations) == 2
    assert len({o['observation_id'] for o in observations}) == 2
    assert len({o['study_id'] for o in observations}) == 2
    assert [o['observed'] for o in observations] == [f['observed'] for f in original['paper_evidence'][0]['documentary_findings']]
    assert original == before


@pytest.mark.parametrize('mutation,code', [
    ('omit', 'NARRATIVE_OBSERVATION_COVERAGE_MISMATCH'),
    ('duplicate', 'NARRATIVE_OBSERVATION_COVERAGE_MISMATCH'),
    ('unknown', 'NARRATIVE_OBSERVATION_COVERAGE_MISMATCH'),
    ('comparison_missing', 'NARRATIVE_STUDY_COMPARISON_MISSING'),
    ('comparison_incomplete', 'NARRATIVE_COMPARISON_COVERAGE_MISMATCH'),
    ('alter_fact', 'NARRATIVE_OBSERVATION_BLOCK_MISMATCH'),
])
def test_each_omission_or_changed_observation_is_rejected(mutation, code):
    data = multistudy(); source = build_narrator_input(data); output = covered_output(source)
    item = output['candidate_narratives'][0]
    if mutation == 'omit': item['observation_narratives'].pop()
    if mutation == 'duplicate': item['observation_narratives'].append(deepcopy(item['observation_narratives'][0]))
    if mutation == 'unknown': item['observation_narratives'][0]['observation_id'] = 'unknown'
    if mutation == 'comparison_missing': item.pop('study_comparison')
    if mutation == 'comparison_incomplete': item['study_comparison']['observation_ids'].pop()
    if mutation == 'alter_fact': output['canonical_observations']['P1'][0]['observed'] = {}
    assert code in check(data, source, output)['reason_codes']


def test_complete_coverage_passes_and_appears_in_presentation():
    data = multistudy(); source = build_narrator_input(data); output = covered_output(source)
    verdict = check(data, source, output)
    assert verdict['status'] == 'PASS', verdict['reason_codes']
    view = build_narrative_presentation(data, output, verdict)['candidates'][0]
    assert len(view['observation_explanations']) == 2
    assert view['study_comparison']['text']
    assert len(view['narration_observations']) == 2
    assert 'La fonte descrive' in view['generated_explanation']


def test_multiple_passages_of_one_study_remain_separate_without_mandatory_comparison():
    data = multistudy(same_document=True); source = build_narrator_input(data)
    output = covered_output(source); output['candidate_narratives'][0].pop('study_comparison')
    assert len({o['study_id'] for o in source['candidates'][0]['narration_observations']}) == 1
    assert check(data, source, output)['status'] == 'PASS'


def test_excluded_observation_stays_out_of_narration_coverage():
    data = multistudy()
    data['paper_evidence'][0]['documentary_findings'][1]['disposition'] = 'EXCLUDED_RECORD'
    source = build_narrator_input(data)
    assert len(source['candidates'][0]['narration_observations']) == 1


def test_nested_explanations_are_checked_for_unsupported_claims():
    data = multistudy(); source = build_narrator_input(data); output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] += ' Il tasso di risposta è 87%.'
    assert 'NARRATIVE_UNAUTHORIZED_NUMBER' in check(data, source, output)['reason_codes']


def test_one_observation_cannot_borrow_another_studys_quote_or_identifier():
    data = multistudy()
    data['paper_evidence'][0]['documentary_findings'][1]['quotation'] = 'The second source reports a separate observation on the research profile.'
    source = build_narrator_input(data); output = covered_output(source)
    text = 'Fonte pmid:200: "The second source reports a separate observation on the research profile."'
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = text
    assert 'NARRATIVE_OBSERVATION_SOURCE_MISMATCH' in check(data, source, output)['reason_codes']


def test_one_observation_cannot_borrow_another_studys_quantity():
    data = multistudy()
    data['paper_evidence'][0]['documentary_findings'][1]['observed']['finding'] = 'The response rate was 87%.'
    source = build_narrator_input(data); output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = 'Il tasso di risposta è 87%.'
    assert 'NARRATIVE_OBSERVATION_NUMBER_MISMATCH' in check(data, source, output)['reason_codes']


def test_one_observation_cannot_borrow_another_studys_identifier_without_a_quote():
    data = multistudy(); source = build_narrator_input(data); output = covered_output(source)
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = 'La fonte pmid:200 descrive il profilo molecolare.'
    assert 'NARRATIVE_OBSERVATION_SOURCE_MISMATCH' in check(data, source, output)['reason_codes']


def test_legacy_presentation_resolves_observation_ids_like_the_input():
    from backend.research_pipeline.narrative.coverage import narration_observations
    from backend.research_pipeline.narrative.source_cards import build_source_cards
    entry = {'candidate_id': 'P1', 'document_id': 'pmid:100',
             'quote_source_unit_id': 'SU-1',
             'quote_valid': True, 'quote': 'An authenticated passage describes this research profile.'}
    projected = {**entry, 'source_cards': build_source_cards(entry)}
    assert len(narration_observations(projected)) == 1
    assert narration_observations(entry) == narration_observations(projected)
