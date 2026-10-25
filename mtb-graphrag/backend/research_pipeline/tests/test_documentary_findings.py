from copy import deepcopy
import json

from backend.research_pipeline.dossier.observations import project_documentary_findings


def report(record):
    return {'paper_evidence': [{'candidate_id': 'C1', 'relation_family': 'PAPER_EVIDENCE',
                              'subject': {'label': 'ALK F1174L'}, 'object': {'label': 'crizotinib'},
                              'support_level': 'FULL_SUPPORT', 'accepted_evidence_records': [record]}],
            'clinical_trials': [], 'kg_only_relations': []}


def test_observation_does_not_infer_correspondence_from_legacy_verdict():
    raw = report({'evidence_id': 'E1', 'quote': 'No response.', 'quote_valid': True,
                  'paper_id': 'pmid:1', 'source_unit_id': 'SU1',
                  'observed_relation': {'effect_direction': 'RESISTANCE'}})
    saved = deepcopy(raw)
    result = project_documentary_findings(raw)
    assert raw == saved
    finding = result['paper_evidence'][0]['documentary_findings'][0]
    assert finding['checks']['quotation']['status'] == 'AUTHENTICATED'
    assert finding['checks']['structural']['status'] == 'NOT_RECORDED'
    assert finding['observed']['effect_direction'] == 'RESISTANCE'
    assert finding['scientific_correctness'] == 'NOT_INDEPENDENTLY_EVALUATED'
    assert finding['source']['source_unit_id'] == 'SU1'


def test_technical_error_is_not_semantic_assessment():
    result = project_documentary_findings(report({'evidence_id': 'E1', 'quote_valid': True,
        'document_verification': {'final_admission': 'TECHNICAL_ERROR',
                                  'verification_status': 'TECHNICAL_ERROR', 'semantic_assessment': {'certainty': 'UNKNOWN'}}}))
    assert result['paper_evidence'][0]['documentary_findings'][0]['checks']['semantic']['status'] == 'TECHNICAL_ERROR'


def test_invalid_quote_not_presented_and_rejected_record_not_lost():
    raw = report({'evidence_id': 'E1', 'quote_valid': True})
    raw['paper_evidence'][0]['rejected_evidence'] = [{'evidence_id': 'E2', 'quote': 'fabricated', 'quote_valid': False}]
    result = project_documentary_findings(raw)
    findings = result['paper_evidence'][0]['documentary_findings']
    assert len(findings) == 2
    assert findings[1]['quotation'] is None
    assert findings[1]['checks']['quotation']['status'] == 'NOT_ESTABLISHED'
    assert findings[1]['disposition'] == 'EXCLUDED_RECORD'
    assert result['documentary_summary']['record_count'] == 2


def test_statement_policy_and_no_source_families_remain_distinct():
    raw = report({'evidence_id': 'E1', 'relation_family': 'EVIDENCE_STATEMENT'})
    raw['clinical_trials'] = [{'candidate_id': 'T1', 'nct_id': 'NCT00000001'}]
    raw['kg_only_relations'] = [{'candidate_id': 'K1'}]
    result = project_documentary_findings(raw)
    assert result['paper_evidence'][0]['documentary_findings'][0]['checks']['semantic']['status'] == 'NOT_REQUIRED_BY_POLICY'
    assert result['clinical_trials'][0]['documentary_scope'] == 'REGISTRY_INFORMATION_NOT_EFFICACY'
    assert result['kg_only_relations'][0]['documentary_scope'] == 'GRAPH_PROVENANCE_ONLY'


def test_reader_projection_excludes_curator_answers_and_preserves_target_identity():
    from backend.research_pipeline.enrichment.prompt_v3 import render_request
    payload = json.loads(render_request({}, {'candidate_id': 'C', 'biomarkers': [{'label': 'ALK F1174L'}],
        'object': {'type': 'EvidenceStatement', 'label': 'CURATOR_ANSWER'},
        'source_properties': {'evidence': {'evidence_statement': 'CURATOR_ANSWER'}}}, 'pmid:1', []))
    assert 'CURATOR_ANSWER' not in json.dumps(payload)
    assert payload['candidate']['biomarkers'] == [{'label': 'ALK F1174L'}]
    assert payload['candidate_role'] == 'SEARCH_TARGET_NOT_OBSERVED_FACT'


def test_builder_preserves_abstention_and_unexecuted_work():
    from backend.research_pipeline.dossier.builder import build_relation_aware_report
    from backend.research_pipeline.tests.test_dossier_aggregation_redesign import _candidate
    candidate = _candidate()
    result = build_relation_aware_report({}, [candidate], {candidate['candidate_id']: {
        'reader_attempts': [{'decision': 'ABSTAIN', 'abstain_reason': 'NO_RELEVANT_EVIDENCE', 'paper_id': 'pmid:123'}]}})
    assert result['paper_evidence'][0]['documentary_attempts'][0]['abstain_reason'] == 'NO_RELEVANT_EVIDENCE'
    result['pending_reader_requests'] = [{'candidate_id': candidate['candidate_id'], 'paper_id': 'pmid:456'}]
    projected = project_documentary_findings(result)
    assert projected['paper_evidence'][0]['documentary_attempts'][-1]['reader_attempt_status'] == 'NOT_EXECUTED'


def test_rejected_audit_uses_exact_record_identity_without_losing_structural_block():
    from backend.research_pipeline.dossier.builder import build_relation_aware_report
    from backend.research_pipeline.tests.test_dossier_aggregation_redesign import _candidate
    candidate = _candidate()
    record = {'evidence_id': 'BLOCKED', 'paper_id': 'pmid:123', 'source_unit_id': 'SU1',
              'quote_valid': False, 'quote': 'must not be quoted', 'relation_family': 'EVIDENCE_DRUG',
              'document_verification': {'structural_status': 'MISMATCH', 'final_admission': 'NOT_RUN_STRUCTURAL'}}
    result = build_relation_aware_report({}, [candidate], {candidate['candidate_id']: {'evidence_records': [record]}})
    finding = result['paper_evidence'][0]['documentary_findings'][0]
    assert finding['disposition'] == 'EXCLUDED_RECORD'
    assert finding['quotation'] is None
    assert finding['checks']['structural']['status'] == 'MISMATCH'
    assert finding['checks']['semantic']['status'] == 'NOT_EXECUTED'
    assert finding['limitations']['rejection_reason']


def test_tampered_projection_blocks_publication_without_deleting_records():
    from backend.research_pipeline.dossier.accounting import apply_publication_integrity
    raw = report({'evidence_id': 'E1', 'quote_valid': True, 'quote': 'No response.'})
    raw['run_status'] = 'COMPLETED'
    raw['pipeline_accounting'] = {'bidirectional_reconciliation': {'status': 'PASS'}}
    projected = project_documentary_findings(raw)
    assert apply_publication_integrity(projected)['publication_status'] == 'COMPLETE'
    projected['paper_evidence'][0]['documentary_findings'][0]['observed'] = {'fabricated': True}
    failed = apply_publication_integrity(projected)
    assert failed['publication_status'] == 'INCOMPLETE'
    assert 'DOCUMENTARY_PROJECTION_MISMATCH' in failed['publication_integrity']['reason_codes']
    assert failed['paper_evidence'][0]['accepted_evidence_records'][0]['quote'] == 'No response.'


def test_narrative_and_markdown_use_same_observations_and_preserve_negative_results():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.narrative.controlled import build_catalog, default_plan, render_plan, verify_controlled
    from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
    raw = report({'evidence_id': 'E1', 'quote_valid': True, 'quote': 'No response.', 'paper_id': 'pmid:1',
                  'source_unit_id': 'SU1', 'observed_relation': {'effect_direction': 'RESISTANCE'}})
    raw['limitations'] = []
    projected = project_documentary_findings(raw)
    source = build_narrator_input(projected)
    catalog = build_catalog(source)
    narrative = render_plan(catalog, default_plan(catalog))
    assert verify_controlled(source, narrative)['status'] == 'PASS'
    text = narrative['candidate_narratives'][0]['text']
    assert 'No response.' in text and 'RESISTANCE' in text
    assert 'supporto documentale completo' not in text
    markdown = render_dossier_markdown(projected)
    assert 'RESISTANCE' in markdown and 'NOT_INDEPENDENTLY_EVALUATED' in markdown
    assert '##### FULL_SUPPORT' not in markdown
    narrative['candidate_narratives'][0]['text'] += ' Clinical efficacy established.'
    assert verify_controlled(source, narrative)['status'] == 'FAIL'


def test_api_preserves_new_contract_and_markdown_without_provider_calls():
    from unittest.mock import patch
    from backend.api import research_routes
    raw = report({'evidence_id': 'E1', 'quote_valid': True, 'quote': 'No response.',
                  'paper_id': 'pmid:1', 'source_unit_id': 'SU1'})
    raw['run_status'] = 'COMPLETED'
    raw['pipeline_accounting'] = {'bidirectional_reconciliation': {'status': 'PASS'}}
    projected = project_documentary_findings(raw)
    with patch.object(research_routes, '_snapshot_or_404', return_value={
            'status': 'COMPLETED', 'relation_aware_report': projected, 'stages': []}):
        response = research_routes.get_dossier('OFFLINE')
    assert response['dossier']['documentary_contract_version'] == 'documentary-findings/1.1'
    assert response['dossier']['publication_status'] == 'COMPLETE'
    assert response['dossier']['paper_evidence'][0]['documentary_findings'][0]['quotation'] == 'No response.'
    assert 'No response.' in response['dossier_markdown']
