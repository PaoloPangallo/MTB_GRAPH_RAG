"""Evidence citations from an automated judge must resolve to the saved payload."""
from copy import deepcopy

from evaluation.run_narrator_semantic_audit import (
    DIMENSIONS, calibration_cases, judge_errors, prepare_cases, schema_for_payload,
)


def test_prepared_cases_preserve_all_generated_text_and_source_observations():
    rows = prepare_cases()
    assert len(rows) == 10
    assert sum(row['origin'] == 'SYNTHETIC_CONTRACT_FIXTURE' for row in rows) == 6
    assert all(row['payload']['narrative']['candidate_narratives'] for row in rows)
    assert all(row['payload']['candidates'][0]['observations'] for row in rows)


def judgement():
    return {'verdict': 'REVISION_REQUIRED', 'summary': 'Il testo modifica il risultato.',
            'dimensions': [{'dimension': key, 'judgement': 'ISSUE' if key == 'outcomes' else 'OK',
                            'reason': 'Confronto effettuato.'} for key in DIMENSIONS],
            'findings': [{'severity': 'MAJOR', 'category': 'outcomes',
                'narrative_pointer': '/narrative/text', 'narrative_excerpt': 'sopravvivenza',
                'input_pointer': '/candidates/0/observations/0/quotation',
                'input_excerpt': 'risk of recurrence', 'explanation': 'Gli esiti differiscono.'}]}


def test_judge_evidence_must_be_literal_and_resolvable():
    payload = {'narrative': {'text': 'Migliora la sopravvivenza.'},
               'candidates': [{'observations': [{'quotation': 'A lower risk of recurrence.'}]}]}
    result = judgement()
    assert judge_errors(result, payload) == []
    changed = deepcopy(result); changed['findings'][0]['input_excerpt'] = 'Invented source words'
    assert 'INPUT_EXCERPT_NOT_FOUND' in judge_errors(changed, payload)
    changed = deepcopy(result); changed['findings'][0]['narrative_pointer'] = '/missing'
    assert 'NARRATIVE_POINTER_INVALID' in judge_errors(changed, payload)


def test_acceptance_cannot_hide_major_findings_or_missing_dimensions():
    payload = {'narrative': {'text': 'Migliora la sopravvivenza.'},
               'candidates': [{'observations': [{'quotation': 'A lower risk of recurrence.'}]}]}
    result = judgement(); result['verdict'] = 'ACCEPTABLE'
    assert 'VERDICT_FINDINGS_INCONSISTENT' in judge_errors(result, payload)
    result = judgement(); result['dimensions'].pop()
    assert 'DIMENSION_COVERAGE_INVALID' in judge_errors(result, payload)


def test_calibration_has_known_errors_and_clean_controls():
    rows = calibration_cases()
    assert len(rows) == 10
    assert sum(row['expected_verdict'] == 'REVISION_REQUIRED' for row in rows) == 8
    assert sum(row['expected_verdict'] == 'ACCEPTABLE' for row in rows) == 2
    assert len({row['name'] for row in rows}) == 10
    comparison = next(row['payload'] for row in rows if row['name'] == 'false_agreement')
    observations = comparison['candidates'][0]['observations']
    assert all(o['study_id'] == o['source']['document_id'] for o in observations)


def test_findings_must_match_their_dimension_and_point_to_prose():
    payload = {'narrative': {'text': 'Migliora la sopravvivenza.', 'candidate_id': 'P1'},
               'candidates': [{'observations': [{'quotation': 'A lower risk of recurrence.'}]}]}
    result = judgement(); result['dimensions'][1]['judgement'] = 'OK'
    assert 'FINDING_WITHOUT_ISSUE_DIMENSION' in judge_errors(result, payload)
    result = judgement(); result['findings'][0].update(narrative_pointer='/narrative/candidate_id', narrative_excerpt='P1')
    assert 'NARRATIVE_POINTER_INVALID' in judge_errors(result, payload)
    result = judgement(); result['findings'][0]['input_pointer'] = '/candidates/-1/observations/0/quotation'
    assert 'INPUT_POINTER_INVALID' in judge_errors(result, payload)
    schema = schema_for_payload(payload)
    fields = schema['properties']['findings']['items']['properties']
    assert fields['narrative_pointer']['enum'] == ['/narrative/text']


def test_semantic_report_preserves_disagreement_and_separates_calibration():
    from evaluation.build_narrator_semantic_report import build_audit
    report = build_audit()
    assert report['summary']['audited_cases'] == 10
    assert report['summary']['mechanical_passes'] == 10
    assert report['summary']['codex_verdicts']['REVISION_REQUIRED'] == 3
    assert report['summary']['calibration_usable'] == 10
    assert report['summary']['calibration_error_cases_detected'] == 8
    row = next(row for row in report['cases'] if row['name'] == 'BRAF_24508103')
    assert row['codex_review']['verdict'] == 'ACCEPTABLE_WITH_NOTES'
    assert row['provider_review']['verdict'] == 'ACCEPTABLE'
    assert report['same_model_as_narrator'] is True


def test_html_counts_and_grader_limit_follow_the_data():
    from evaluation.build_narrator_semantic_report import build_audit, render_html
    report = build_audit()
    report['summary']['provider_verdicts'] = {'ACCEPTABLE': 6, 'REVISION_REQUIRED': 3, 'UNASSESSABLE': 1}
    report['summary']['usable_judgements'] = 19
    report['same_model_as_narrator'] = False
    report['cases'][0]['provider_review'] = None
    html = render_html(report)
    assert '19 giudizi su 20' in html
    assert '1 giudizi inutilizzabili' in html
    assert 'Il valutatore utilizza un modello diverso' in html


def test_new_case_connection_can_be_cited_without_replacing_historical_inputs():
    from evaluation.run_narrator_semantic_audit import REPO
    rows = prepare_cases(REPO / 'evaluation/multistudy_narrator_verified/results.json')
    assert len(rows) == 10
    assert prepare_cases('evaluation/multistudy_narrator_verified/results.json') == rows
    schema = schema_for_payload({'narrative': {'candidate_narratives': [
        {'observation_narratives': [{'case_relevance': 'Il caso riguarda una combinazione.'}]}]},
        'case': {'disease': 'melanoma'}})
    assert '/narrative/candidate_narratives/0/observation_narratives/0/case_relevance' in schema['properties']['findings']['items']['properties']['narrative_pointer']['enum']


def test_repair_report_compares_actual_saved_responses_and_keeps_baseline():
    from evaluation.build_narrator_repair_report import build_repair_report
    report = build_repair_report()
    assert report['summary']['cases'] == 10
    assert report['summary']['sources_and_observations_unchanged'] == 10
    assert report['summary']['semantic_acceptable'] == 10
    assert report['summary']['mechanical_pass'] == 10
    assert all(case['before_verdict'] for case in report['cases'])
