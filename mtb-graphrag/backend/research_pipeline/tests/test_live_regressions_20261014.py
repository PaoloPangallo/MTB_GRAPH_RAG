"""Offline invariants from live failures; never clinical gold or model accuracy."""
from copy import deepcopy

from backend.research_pipeline.dossier.observations import project_documentary_findings
from backend.research_pipeline.enrichment.verification_policy import public_artifact
from backend.research_pipeline.enrichment.canonical_normalizer import entity_relation
from backend.research_pipeline.terminology.surface import molecular_surface
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.dossier.observations import migrate_public_projection


def test_documentary_projection_commutes_with_public_serialization():
    raw = {'paper_evidence': [{'candidate_id': 'C1', 'accepted_evidence_records': [{
        'evidence_id': 'E1', 'document_id': 'pmid:1', 'source_unit_id': 'SU1',
        'quote': 'Observed result.', 'quote_valid': True, 'source_unit_text': 'Observed result.',
        'document_verification': {'target_snapshot': {'profile': 'ALK F1174L', 'evidence_statement': 'CURATOR'},
                                  'GEP_snapshot': {'required_context': 'Observed result.'}}}]}]}
    original = deepcopy(raw)
    projected = project_documentary_findings(raw)
    public = public_artifact(projected)
    assert raw == original
    assert public == project_documentary_findings(public)
    assert 'evidence_statement' not in projected['paper_evidence'][0]['documentary_findings'][0]['requested_target']


def test_old_projection_migration_only_repairs_known_serialization_and_never_tampering():
    raw = {'paper_evidence': [{'candidate_id': 'C1', 'accepted_evidence_records': [{
        'evidence_id': 'E1', 'source_unit_id': 'SU1', 'source_unit_text': 'Observed result.',
        'quote': 'Observed result.', 'quote_valid': True}]}]}
    expected = public_artifact(project_documentary_findings(raw))
    old = deepcopy(expected)
    old['documentary_contract_version'] = 'documentary-findings/1.0'
    finding = old['paper_evidence'][0]['documentary_findings'][0]
    for key in ('source_unit_sha256', 'source_unit_digest_contract', 'source_unit_chars'):
        finding['source'][key] = None
    original = deepcopy(old)
    migrated = migrate_public_projection(old)
    assert old == original
    assert migrated['documentary_projection_migration']['stored_ledger_unchanged'] is True
    assert migrated['paper_evidence'] == expected['paper_evidence']
    from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
    assert 'Osservazioni e ledger originali invariati' in render_dossier_markdown(migrated)
    assert migrate_public_projection(migrated) == migrated
    for path, value in [('observed', {'intervention': 'invented'}), ('quotation', 'invented')]:
        tampered = deepcopy(old)
        tampered['paper_evidence'][0]['documentary_findings'][0][path] = value
        assert migrate_public_projection(tampered) == tampered
    tampered = deepcopy(old)
    tampered['paper_evidence'][0]['documentary_findings'][0]['source']['source_unit_sha256'] = 'bad'
    assert migrate_public_projection(tampered) == tampered


def test_resolved_distinct_gene_still_blocks_as_mismatch(monkeypatch):
    from backend.research_pipeline.enrichment import document_verification as module
    from backend.research_pipeline.tests.test_document_verification import _candidate, _structural
    original = module.entity_relation
    def compare(expected, observed, **kwargs):
        if kwargs.get('domain') == 'GENE' and expected == 'EGFR' and observed == 'KRAS':
            return 'DIFFERENT'
        return original(expected, observed, **kwargs)
    monkeypatch.setattr(module, 'entity_relation', compare)
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _reader_observation, _source_unit
    text = 'EGFR L858R showed sensitivity to erlotinib in lung cancer. KRAS.'
    candidate = _candidate()
    observed = _reader_observation(candidate, [_source_unit(text)])['enrichment']
    observed['observed_relation']['subjects'][0]['surface_value'] = 'KRAS'
    result = _structural(text, candidate=candidate, observed=observed)
    assert result['structural_status'] == 'MISMATCH'


def test_protein_morphology_is_syntax_only_and_does_not_erase_extra_scope():
    assert molecular_surface('F1174L-mutated')['key'] == molecular_surface('F1174L')['key']
    assert entity_relation('F1174L', 'F1174L-mutated', domain='VARIANT') == 'CANONICAL_ALIAS'
    assert entity_relation('F1174L', 'R1275Q', domain='VARIANT') not in {'IDENTICAL', 'CANONICAL_ALIAS'}
    assert molecular_surface('F1174L/R1275Q-mutated')['kind'] == 'EXACT_SURFACE'
    assert molecular_surface('F1174L germline-mutated')['kind'] == 'EXACT_SURFACE'
    assert molecular_surface('p.(F1174L)-mutated')['predicted'] is True


def test_explicit_combination_cannot_validate_as_single_agent():
    quote = 'A combination of dabrafenib and trametinib improved the reported outcome.'
    observation = {'decision': 'QUOTE', 'source_unit_id': 'SU1', 'quote': quote,
        'observed_relation': {'subjects': [], 'intervention': 'combination of dabrafenib and trametinib',
                             'observed_stance': 'SUPPORTS', 'relation_assertion': 'RELATION_ASSERTED',
                             'relation_scope': 'SINGLE', 'molecular_composition': 'SINGLE',
                             'intervention_composition': 'SINGLE_AGENT'}}
    result = validate_enrichment_v3('V3_TRANSPORT_VALID', observation, candidate={},
        paper_bundle={'document_id': 'pmid:1', 'source_unit_ids': ['SU1']},
        source_units_by_id={'SU1': {'document_id': 'pmid:1', 'text': quote}})
    assert result['outcome'] == 'QUOTE_INVALID'
    assert result['reason_codes'] == ['INTERVENTION_SCOPE_CONTRADICTS_LITERAL_REGIMEN']
    observation['observed_relation']['intervention_composition'] = 'COMBINATION'
    assert validate_enrichment_v3('V3_TRANSPORT_VALID', observation, candidate={},
        paper_bundle={'document_id': 'pmid:1', 'source_unit_ids': ['SU1']},
        source_units_by_id={'SU1': {'document_id': 'pmid:1', 'text': quote}})['outcome'] == 'ENRICHMENT_V3_ACCEPTED'


def test_running_store_uses_completed_ledger_stages_without_claiming_recovery(monkeypatch):
    import threading
    from backend.research_pipeline.run_store import RunStore, RunHandle
    from backend.research_pipeline import rehydration
    store = object.__new__(RunStore)
    store._lock = threading.Lock()
    store._ledger = object()
    store._runs = {'R': RunHandle('R', 'C', 'RUNNING', '2026-10-14T00:00:00Z')}
    monkeypatch.setattr(rehydration, 'rehydrate', lambda *args: {
        'run_id': 'R', 'status': 'FAILED', 'completed_at': None, 'stages': [{'stage_id': 'stage_2_casecontext_parser'}],
        'rehydrated': True, 'recovery_status': 'RECOVERED_INCOMPLETE'})
    snapshot = store.snapshot('R')
    assert snapshot['status'] == 'RUNNING'
    assert snapshot['stages'][0]['stage_id'] == 'stage_2_casecontext_parser'
    assert snapshot['rehydrated'] is False
    assert snapshot['recovery_status'] == 'IN_PROGRESS'


def test_running_cost_counts_known_reader_progress_once_and_marks_usage_incomplete():
    from backend.research_pipeline.operational_metrics import operational_summary
    snapshot = {'status': 'RUNNING', 'stages': [{'stage_id': 'stage_2_casecontext_parser',
        'artifact_origin': 'GENERATED_NOW', 'metrics': {'real_llm_calls': 1, 'input_tokens': 100, 'output_tokens': 10}}],
        'work_progress': {'reader_calls': 4}, 'llm_calls': 0}
    metrics = operational_summary(snapshot)
    assert metrics['llm_calls'] == 5
    assert metrics['llm_calls_complete'] is False
    assert metrics['token_usage_complete'] is False


def test_rehydration_new_stage_supersedes_old_reader_progress():
    from backend.research_pipeline import rehydration, events as ev
    from types import SimpleNamespace
    events = [
        {'event_type': ev.RUN_CREATED, 'payload': {'case_id': 'C'}, 'created_at': '2026-10-14', 'sequence': 1},
        {'event_type': ev.PIPELINE_WORK_PROGRESS, 'payload': {'stage_id': 'stage_9_enrichment', 'reader_calls': 4}, 'created_at': '2026-10-14', 'sequence': 2},
        {'event_type': ev.STAGE_STARTED, 'payload': {'stage_id': 'stage_14_narrative'}, 'created_at': '2026-10-14', 'sequence': 3},
    ]
    ledger = SimpleNamespace(events=lambda _: events, verify_chain=lambda _: True)
    snapshot = rehydration.rehydrate(ledger, 'R')
    assert snapshot['work_progress']['reader_calls'] == 4
    assert snapshot['current_stage'] == 'stage_14_narrative'
    assert snapshot['recovery_status'] == 'RECOVERED_INCOMPLETE'
