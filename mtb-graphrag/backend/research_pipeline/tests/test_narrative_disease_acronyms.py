"""Known disease acronyms must remain bound to their own retained observation."""
from backend.research_pipeline.narrative.verifier import _check_entities


def check(text, disease='non-small cell lung cancer', candidate_id='A'):
    source = {'candidates': [
        {'candidate_id': 'A', 'narration_observations': [{'observed': {'disease': disease}}]},
        {'candidate_id': 'B', 'narration_observations': [{'observed': {'disease': 'melanoma'}}]},
    ]}
    output = {'candidate_narratives': [{'candidate_id': candidate_id, 'text': text}]}
    return _check_entities(output, source, {'identifiers': set()})


def test_source_disease_acronym_is_not_an_invented_gene():
    assert check('La fonte descrive NSCLC.') == []
    assert check('La fonte descrive NSCLC.', disease='non-small-cell lung cancer') == []


def test_known_acronym_cannot_be_borrowed_from_another_candidate():
    assert check('La fonte descrive NSCLC.', candidate_id='B')
    assert check('La fonte descrive NSCLC.', disease='melanoma')


def test_unauthorized_gene_is_still_rejected_next_to_a_grounded_acronym():
    violations = check('La fonte descrive NSCLC e BRCA2.')
    assert [v['value'] for v in violations] == ['BRCA2']
