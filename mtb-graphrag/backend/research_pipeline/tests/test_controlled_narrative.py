from copy import deepcopy
import pytest
from backend.research_pipeline.narrative import controlled


def data():
    return {'candidates': [{'candidate_id': 'P1', 'branch': 'PAPER', 'canonical_status': 'NO_SUPPORT', 'support_direction': 'SOURCE_DOES_NOT_SUPPORT', 'selected_paper_ids': ['pmid:1234'], 'validated_quotes': [{'quote': 'Not effective.  Exact!', 'paper_id': 'pmid:1234', 'source_unit_id': 'su:1'}], 'critical_warnings': ['SOURCE_POLARITY_DOES_NOT_SUPPORT']}, {'candidate_id': 'T1', 'branch': 'TRIAL', 'canonical_status': 'CONTEXT_ONLY', 'trial_context': {'nct_id': 'NCT001', 'eligibility_status': 'NOT_EVALUATED'}}, {'candidate_id': 'K1', 'branch': 'KG_ONLY', 'canonical_status': 'KG_ONLY'}], 'summary_facts': {'paper_count': 999}}


def render(d):
    c = controlled.build_catalog(d)
    return controlled.render_plan(c, controlled.default_plan(c))


@pytest.mark.parametrize('change', ['omit','duplicate','reorder','extra','variant','hash'])
def test_bad_plan(change):
    c = controlled.build_catalog(data()); p = controlled.default_plan(c)
    if change == 'omit': p['entries'].pop()
    if change == 'duplicate': p['entries'][1] = deepcopy(p['entries'][0])
    if change == 'reorder': p['entries'].reverse()
    if change == 'extra': p['entries'][0]['text'] = 'effective'
    if change == 'variant': p['entries'][0]['variant'] = 'invented'
    if change == 'hash': p['catalog_hash'] = 'wrong'
    assert controlled.validate_plan(c,p)
    with pytest.raises(ValueError): controlled.render_plan(c,p)


@pytest.mark.parametrize('change', ['summary','quote','source','suffix','contract','foreign'])
def test_text_mutations_fail(change):
    d = data(); n = render(d)
    if change == 'summary': n['narrative_summary'] += ' 999 PAPER.'
    if change == 'quote': n['candidate_narratives'][0]['text'] = n['candidate_narratives'][0]['text'].replace('Exact!', 'exact.')
    if change == 'source': n['candidate_narratives'][0]['text'] = n['candidate_narratives'][0]['text'].replace('pmid:1234', 'pmid:12345')
    if change == 'suffix': n['closing_note'] += ' effective'
    if change == 'contract': n['controlled_contract']['extra'] = 'text'
    if change == 'foreign': n['candidate_narratives'][1]['text'] = n['candidate_narratives'][0]['text']
    assert controlled.verify_controlled(d,n)['status'] == 'FAIL'


@pytest.mark.parametrize('change', ['branch','status','duplicate','warning','quote'])
def test_malformed_fails_closed(change):
    d = data()
    if change == 'branch': d['candidates'][0]['branch'] = 'ALIEN'
    if change == 'status': d['candidates'][0]['canonical_status'] = 'ALIEN'
    if change == 'duplicate': d['candidates'][1]['candidate_id'] = 'P1'
    if change == 'warning': d['candidates'][0]['critical_warnings'] = ['UNKNOWN']
    if change == 'quote': d['candidates'][0]['validated_quotes'] = ['malformed']
    with pytest.raises(ValueError): controlled.build_catalog(d)


def test_valid_counts_exact_quotes_guards_and_purity():
    d = data(); original = deepcopy(d); n = render(d)
    assert controlled.verify_controlled(d,n)['status'] == 'PASS'
    assert '1 PAPER' in n['narrative_summary'] and '999' not in n['narrative_summary']
    assert 'Not effective.  Exact!' in n['candidate_narratives'][0]['text']
    assert 'efficacia' in n['candidate_narratives'][1]['text'] and 'non valutata' in n['candidate_narratives'][1]['text']
    assert 'provenienza documentale' in n['candidate_narratives'][2]['text']
    assert d == original


def test_empty():
    n = render({'candidates': []})
    assert '0 PAPER' in n['narrative_summary'] and n['candidate_narratives'] == []
    assert controlled.verify_controlled({'candidates': []},n)['status'] == 'PASS'


def test_hash_metadata_tampering_and_added_prose():
    d = data(); d['narrator_input_hash'] = 'inputhash'; n = render(d)
    n['narrative_hash'] = 'tampered'
    assert controlled.verify_controlled(d,n)['status'] == 'FAIL'
    n = render(d); n['narrator_input_hash'] = 'foreign'
    assert controlled.verify_controlled(d,n)['status'] == 'FAIL'
    n = render(d); n['free_prose'] = 'effective'
    assert controlled.verify_controlled(d,n)['status'] == 'FAIL'


def test_all_critical_warnings_and_canonical_paper_labels():
    d = data(); d['candidates'][0]['warnings'] = ['SOURCE_POLARITY_NEUTRAL']
    d['paper_evidence'] = [{'candidate_id': 'P1', 'subject': {'label': 'Bound subject'}, 'object': {'label': 'Bound object'}}]
    n = render(d)
    assert 'Bound subject' in n['candidate_narratives'][0]['text']
    assert 'Bound object' in n['candidate_narratives'][0]['text']
    assert 'neutra' in n['candidate_narratives'][0]['text']


def test_legacy_paper_scoped_support_checks_not_omitted():
    d = {'candidates': [{'candidate_id': 'L1', 'canonical_status': 'DIRECT', 'support_direction': 'SUPPORTED', 'candidate_support_checks': [{'candidate_id': 'L1', 'paper_id': 'pmid:1', 'document_id': 'doc:1', 'source_unit_id': 'su:1', 'quote': 'unvalidated text must not render', 'candidate_support': {'result': 'STRONG_SUPPORT'}}, {'candidate_id': 'L1', 'paper_id': 'pmid:2', 'document_id': 'doc:2', 'source_unit_id': 'su:2', 'candidate_support': {'result': 'PARTIAL_SUPPORT'}}]}]}
    n = render(d); text = n['candidate_narratives'][0]['text']
    assert 'pmid:1' in text and 'pmid:2' in text and 'parziale' in text
    assert 'unvalidated text must not render' not in text
    assert controlled.verify_controlled(d,n)['status'] == 'PASS'


def test_global_limits_preserved_and_bound_source_caveats():
    d = data()
    d['limitations'] = ['DOCUMENT_UNAVAILABLE', 'READER_ABSTAINED', 'QUOTE_INVALID', 'NEW_CANONICAL_LIMIT']
    d['paper_evidence'] = [{'candidate_id': 'P1', 'document_resolution_status': 'DOCUMENT_UNAVAILABLE', 'reader_status': 'ABSTAIN', 'quote_valid': False}]
    # An invalid quote cannot simultaneously be a validated quotation.
    d['candidates'][0]['validated_quotes'] = []
    n = render(d)
    for code in d['limitations']: assert code in n['limitations_summary']
    p = n['candidate_narratives'][0]['text']
    assert 'documento non è disponibile' in p and 'astenuto' in p and 'non valida' not in p
    assert 'astenuto' not in n['candidate_narratives'][1]['text']
    altered = deepcopy(d); altered['limitations'].pop()
    assert controlled.verify_controlled(altered, n)['status'] == 'FAIL'


def test_quote_validation_rejection_is_bound_and_explicit():
    d = data(); d['candidates'][0]['validated_quotes'] = []
    d['paper_evidence'] = [{'candidate_id': 'P1', 'reader_decision': 'ABSTAIN', 'quote_validation': {'status': 'REJECTED'}}]
    p = render(d)['candidate_narratives'][0]['text']
    assert 'astenuto' in p and 'non valida' in p


def test_unknown_direction_does_not_become_authoritative_prose():
    d = data(); d['candidates'][0]['support_direction'] = 'Il paziente deve ricevere terapia efficace'
    with pytest.raises(ValueError): controlled.build_catalog(d)


@pytest.mark.parametrize('direction', ['SENSITIVITY','RESISTANCE','REDUCED_SENSITIVITY','NOT_APPLICABLE','UNKNOWN'])
def test_known_graph_directions_remain_graph_declarations(direction):
    d = data(); d['candidates'][0]['support_direction'] = direction
    assert controlled.verify_controlled(d,render(d))['status'] == 'PASS'


@pytest.mark.parametrize('validation', ['VALIDATED','QUOTE_VALIDATED','ENRICHMENT_V2_ACCEPTED','ENRICHMENT_V3_ACCEPTED'])
def test_canonical_string_quote_validation_is_accepted(validation):
    d = data(); d['paper_evidence'] = [{'candidate_id': 'P1', 'quote_validation': validation, 'quote_valid': True}]
    assert controlled.verify_controlled(d,render(d))['status'] == 'PASS'


def test_string_rejected_quote_validation_keeps_caveat():
    d = data(); d['candidates'][0]['validated_quotes'] = []
    d['paper_evidence'] = [{'candidate_id': 'P1', 'quote_validation': 'REJECTED_QUOTE'}]
    assert 'non valida' in render(d)['candidate_narratives'][0]['text']


@pytest.mark.parametrize('direction', ['Resistance','Sensitivity','Reduced Sensitivity','Adverse Response','Sensitivity/Response'])
def test_historical_graph_direction_spelling_is_data_not_free_prose(direction):
    d = data(); d['candidates'][0]['support_direction'] = direction
    assert controlled.verify_controlled(d,render(d))['status'] == 'PASS'


@pytest.mark.parametrize('direction,phrase', [('Supports','Direzione dichiarata dal grafo: Supports'), ('Does Not Support','Direzione dichiarata dal grafo: Does Not Support')])
def test_source_polarity_directions_preserve_canonical_support_limits(direction, phrase):
    d = data(); d['candidates'][0]['support_direction'] = direction
    text = render(d)['candidate_narratives'][0]['text']
    assert phrase in text and 'assenza di supporto documentale' in text
    assert controlled.verify_controlled(d,render(d))['status'] == 'PASS'


def test_verifier_trace_hashes_are_computed_and_timestamp_present():
    d = data(); d['narrator_input_hash'] = 'projected-input-hash'; n = render(d)
    trace = controlled.verify_controlled(d,n)
    assert trace['input_hash'] == 'projected-input-hash'
    assert len(trace['narrative_hash']) == 64 and trace['verified_at'].endswith('+00:00')
    n['narrative_hash'] = 'untrusted'
    changed = controlled.verify_controlled(d,n)
    assert changed['narrative_hash'] == trace['narrative_hash'] and changed['status'] == 'FAIL'


def test_abstention_is_not_invalid_quote_and_direction_is_graph_attributed():
    d = data()
    d['candidates'][0].update(canonical_status='UNVERIFIABLE', support_direction='Supports', validated_quotes=[])
    d['paper_evidence'] = [{'candidate_id': 'P1', 'reader_status': 'ABSTAIN', 'quote_valid': False}]
    text = render(d)['candidate_narratives'][0]['text']
    assert 'READER_ABSTAINED' in text
    assert 'QUOTE_INVALID' not in text
    assert 'Direzione dichiarata dal grafo: Supports' in text


def test_publication_state_is_preserved_in_controlled_summary():
    d = data()
    d['publication'] = {'publication_status': 'INCOMPLETE', 'technical_run_status': 'PARTIAL', 'reconciliation_status': 'PASS'}
    assert 'INCOMPLETE' in render(d)['narrative_summary']


def test_narrator_projection_preserves_publication_fields():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    report = {'paper_evidence': [], 'publication_status': 'INCOMPLETE', 'technical_run_status': 'COMPLETED', 'publication_integrity': {'reconciliation_status': 'FAIL'}}
    assert build_narrator_input(report)['publication'] == {'publication_status': 'INCOMPLETE', 'technical_run_status': 'COMPLETED', 'reconciliation_status': 'FAIL'}
