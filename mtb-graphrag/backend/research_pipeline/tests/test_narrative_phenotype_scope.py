"""Optional phenotype population scope remains mandatory at every support grade."""
import pytest
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.tests.test_narrative_semantic_repairs import repaired
from backend.research_pipeline.tests.test_narrative_multistudy import covered_output, check

LITERAL = 'MSI-high or mismatch repair deficient'
SCOPE_NOTE = 'La corrispondenza del fenotipo non stabilisce un effetto specifico del sottogruppo.'


def scoped_data(grade):
    data, _, _ = repaired()
    entry = data['paper_evidence'][0]
    entry['support_level'] = grade
    for finding in entry['documentary_findings']:
        finding.setdefault('limitations', {})['phenotype_scope'] = {
            'population_relation': 'BROADER_OR_ALTERNATIVE', 'logical_operator': 'OR',
            'literal_span': LITERAL, 'subgroup_effect_established': False}
        finding['checks']['correspondence']['phenotype_scope'] = dict(finding['limitations']['phenotype_scope'])
    return data


@pytest.mark.parametrize('grade', ['FULL_SUPPORT', 'PARTIAL_SUPPORT', 'NO_SUPPORT', 'CONTRADICTORY', 'UNVERIFIABLE'])
def test_population_scope_is_projected_independently_of_aggregate_grade(grade):
    source = build_narrator_input(scoped_data(grade))
    required = source['candidates'][0]['required_limitations']
    assert any(item['text'] == LITERAL and item['kind'] == 'OPTIONAL_PHENOTYPE_SCOPE' for item in required)
    assert any(item['text'] == SCOPE_NOTE for item in required)


@pytest.mark.parametrize('grade', ['FULL_SUPPORT', 'PARTIAL_SUPPORT', 'NO_SUPPORT'])
def test_omitted_population_scope_rejects_generated_prose_even_at_full_support(grade):
    data = scoped_data(grade)
    source = build_narrator_input(data)
    output = covered_output(source)
    result = check(data, source, output)
    assert 'NARRATIVE_CRITICAL_LIMITATION_OMITTED' in result['reason_codes']
    assert any(item.get('omitted') == 'OPTIONAL_PHENOTYPE_SCOPE_NOT_STATED' for item in result['critical_omissions'])
    output['candidate_narratives'][0]['text'] += ' Ambito della popolazione riportato nella fonte: ' + LITERAL + '.'
    assert check(data, source, output)['status'] == 'FAIL'
    output['candidate_narratives'][0]['text'] += ' ' + SCOPE_NOTE
    assert 'NARRATIVE_OBSERVATION_PHENOTYPE_SCOPE_OMITTED' in check(data, source, output)['reason_codes']
    for item in output['candidate_narratives'][0]['observation_narratives']:
        item['text'] += ' Ambito della popolazione: ' + LITERAL + '. ' + SCOPE_NOTE
    assert check(data, source, output)['status'] == 'PASS'


def test_unresolved_population_scope_still_requires_the_recorded_no_subgroup_effect_caveat():
    data = scoped_data('FULL_SUPPORT')
    for finding in data['paper_evidence'][0]['documentary_findings']:
        for scope in (finding['limitations']['phenotype_scope'], finding['checks']['correspondence']['phenotype_scope']):
            scope.update(population_relation='UNKNOWN', logical_operator='UNKNOWN', literal_span=None)
    source = build_narrator_input(data)
    assert any(item['text'] == SCOPE_NOTE for item in source['candidates'][0]['required_limitations'])


def test_scope_from_one_study_cannot_satisfy_a_different_studys_population_bound():
    data = scoped_data('FULL_SUPPORT')
    other_literal = 'MSI-high and mismatch repair deficient'
    second = data['paper_evidence'][0]['documentary_findings'][1]
    for scope in (second['limitations']['phenotype_scope'], second['checks']['correspondence']['phenotype_scope']):
        scope.update(population_relation='INTERSECTION', logical_operator='AND', literal_span=other_literal)
    source = build_narrator_input(data)
    output = covered_output(source)
    for item in output['candidate_narratives'][0]['observation_narratives']:
        item['text'] += ' Ambito della popolazione: ' + LITERAL + '. ' + SCOPE_NOTE
    assert 'NARRATIVE_OBSERVATION_PHENOTYPE_SCOPE_OMITTED' in check(data, source, output)['reason_codes']
    output['candidate_narratives'][0]['observation_narratives'][1]['text'] += ' Ambito dell’altra fonte: ' + other_literal + '.'
    assert check(data, source, output)['status'] == 'PASS'

@pytest.mark.parametrize('prefix', ['Non è vero che ', 'It is not true that ', 'È falso che '])
@pytest.mark.parametrize('negated_bound', ['caveat', 'literal'])
def test_denied_population_bound_cannot_satisfy_the_local_scope_obligation(prefix, negated_bound):
    data = scoped_data('NO_SUPPORT')
    source = build_narrator_input(data)
    output = covered_output(source)
    for item in output['candidate_narratives'][0]['observation_narratives']:
        if negated_bound == 'caveat':
            item['text'] += ' Ambito: ' + LITERAL + '. ' + prefix + SCOPE_NOTE
        else:
            item['text'] += ' ' + prefix + LITERAL + '. ' + SCOPE_NOTE
    assert 'NARRATIVE_OBSERVATION_PHENOTYPE_SCOPE_OMITTED' in check(data, source, output)['reason_codes']


def test_intrinsic_negative_caveat_and_an_unrelated_negation_keep_valid_scope():
    data = scoped_data('NO_SUPPORT')
    source = build_narrator_input(data)
    output = covered_output(source)
    for item in output['candidate_narratives'][0]['observation_narratives']:
        item['text'] += ' Non sono riportati altri dettagli. Ambito: ' + LITERAL + '. ' + SCOPE_NOTE
    assert check(data, source, output)['status'] == 'PASS'


def test_a_separately_stated_unnegated_bound_satisfies_the_obligation():
    data = scoped_data('NO_SUPPORT')
    source = build_narrator_input(data)
    output = covered_output(source)
    for item in output['candidate_narratives'][0]['observation_narratives']:
        item['text'] += ' Non è vero che ' + SCOPE_NOTE + ' Ambito: ' + LITERAL + '. ' + SCOPE_NOTE
    assert check(data, source, output)['status'] == 'PASS'

@pytest.mark.parametrize('opening,closing', [('"', '"'), ('«', '»')])
def test_quotation_marks_do_not_change_a_scope_assertions_polarity(opening, closing):
    from backend.research_pipeline.narrative.verifier import _scope_bound_present
    assert _scope_bound_present(opening + SCOPE_NOTE + closing, SCOPE_NOTE)
    assert not _scope_bound_present('Non è vero che ' + opening + SCOPE_NOTE + closing, SCOPE_NOTE)
