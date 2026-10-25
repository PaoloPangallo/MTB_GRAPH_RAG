"""Checked dimensions retain observation identity and cannot license relations.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import pytest
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.tests.test_narrative_semantic_repairs import repaired
from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check


def case_with_checked_gene():
    data, _, _ = repaired()
    data['paper_evidence'][0]['support_level'] = 'NO_SUPPORT'
    for index, finding in enumerate(data['paper_evidence'][0]['documentary_findings']):
        finding['checks']['correspondence']['fields'].update(
            gene='CONFIRMED' if index == 0 else 'NOT_CONFIRMED',
            alteration='NOT_CONFIRMED', disease='NOT_CONFIRMED')
    source = build_narrator_input(data)
    output = covered_output(source)
    return data, source, output


@pytest.mark.parametrize('prose', [
    'La citazione è autenticata e il gene è confermato, sebbene l’alterazione e la malattia non siano confermate nei controlli di corrispondenza.',
    'Nei controlli di corrispondenza il gene è confermato.',
])
def test_valid_local_checked_gene_is_not_a_full_relation_assertion(prose):
    data, source, output = case_with_checked_gene()
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = prose
    assert check(data, source, output)['status'] == 'PASS'


@pytest.mark.parametrize('location,prose', [
    ('first', 'Il gene è confermato e la relazione è pienamente supportata.'),
    ('first', 'La relazione è confermata.'),
    ('first', 'La variante è confermata.'),
    ('first', 'Il gene è pienamente confermato.'),
    ('first', 'Non è vero che il gene è confermato.'),
    ('first', 'Il gene è confermato come prova di pieno supporto.'),
    ('first', 'Il gene è confermato; la relazione è confermata.'),
    ('second', 'Il gene è confermato.'),
    ('lead', 'Il gene è confermato.'),
])
def test_checked_gene_cannot_license_a_different_assertion_or_observation(location, prose):
    data, source, output = case_with_checked_gene()
    item = output['candidate_narratives'][0]
    if location == 'lead':
        item['text'] = prose
    else:
        item['observation_narratives'][0 if location == 'first' else 1]['text'] = prose
    assert check(data, source, output)['status'] == 'FAIL'


def test_recognized_negative_check_statement_must_match_its_local_record():
    data, source, output = case_with_checked_gene()
    output['candidate_narratives'][0]['observation_narratives'][0]['text'] = (
        'Nei controlli di corrispondenza il gene non è confermato.')
    assert 'NARRATIVE_OBSERVATION_CHECK_MISMATCH' in check(data, source, output)['reason_codes']


def test_actual_saved_kras_narration_keeps_original_input_binding():
    import json
    root = Path(__file__).resolve().parents[4]
    path = root / 'experiments_real/full_validation_budget_repaired_20261020/kras-g12d-panitumumab/run.json'
    if not path.is_file():
        pytest.skip('Optional saved real KRAS run is not installed')
    run = json.loads(path.read_text(encoding='utf-8'))
    stage13 = next(s for s in run['stages'] if s['stage_id'] == 'stage_13_dossier')['output_preview']
    legacy = stage13['dossier']
    canonical = dict(stage13['relation_aware_report'])
    # Exact augmentation recorded in orchestrator.py before narrate_and_verify.
    canonical.update(case_id=run['case_id'], case_context=legacy['case_context'],
                     candidate_therapies=legacy.get('candidate_therapies', []),
                     provenance=legacy.get('provenance', {}))
    source = build_narrator_input(canonical)
    narrative = next(s for s in run['stages'] if s['stage_id'] == 'stage_14_narrator')['output_preview']['narrative']
    assert source['narrator_input_hash'] == narrative['narrator_input_hash'] == 'c6083dd470cd4196b7f03f68d915fa208aaf92ce0417af2b1a9a2809e1610227'
    from backend.research_pipeline.narrative.verifier import verify_narrative
    assert verify_narrative(canonical, source, narrative)['status'] == 'PASS'
