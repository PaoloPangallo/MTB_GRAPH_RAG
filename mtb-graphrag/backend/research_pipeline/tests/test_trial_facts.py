from backend.research_pipeline.documents.trial_facts import extract_trial_facts, bind_trial_relation


def test_trial_identity_is_metadata_not_an_efficacy_quote():
    units = [{'source_unit_id': 'u', 'document_id': 'nct:NCT06172296',
              'unit_type': 'INTERVENTION', 'text': 'Carboplatin', 'content_hash': 'hash'}]
    facts = extract_trial_facts({'document_id': 'nct:NCT06172296', 'units': units}, 'snapshot')
    candidate = {'candidate_id': 'c', 'interventions': [{'label': 'Carboplatin'}]}
    call = bind_trial_relation(candidate, facts, 'case')
    assert call['model_call_count'] == 0
    assert call['enrichment']['quote'] == 'Carboplatin'
    assert call['enrichment']['observed_relation']['trial_context'] == {}
    assert call['trial_facts']['nct_id'] == 'NCT06172296'
    assert call['enrichment']['effect_direction'] == 'UNKNOWN'
    assert call['trial_facts']['eligibility_status'] == 'NOT_EVALUATED'


def test_trial_snapshot_changes_identity():
    record = {'document_id': 'nct:NCT06172296', 'units': []}
    assert extract_trial_facts(record, 'a')['snapshot_digest'] != extract_trial_facts(record, 'b')['snapshot_digest']


def test_invalid_identity_cannot_become_a_trial_fact():
    import pytest
    with pytest.raises(ValueError):
        extract_trial_facts({'document_id': 'nct:bad', 'units': []}, 'x')
