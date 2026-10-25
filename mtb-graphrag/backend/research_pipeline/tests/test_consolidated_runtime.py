"""Canonical publication regressions with controlled providers, never live LLMs."""
from unittest.mock import patch
from pathlib import Path

from backend.research_pipeline.dossier import builder
from backend.research_pipeline.tests import test_document_verification as fixture


def test_accounting_failure_marks_run_partial_without_losing_evidence(monkeypatch):
    original = builder.build_relation_aware_report

    def remove_claims(*args, **kwargs):
        report = original(*args, **kwargs)
        report['claims'] = []
        return report

    fixture_path = Path(__file__).resolve().parents[4] / 'experiments_real/consolidation_20261013/root_fixture/fixture.py'
    with patch.object(fixture, '__file__', str(fixture_path)), patch.object(
        builder, 'build_relation_aware_report', side_effect=remove_claims
    ):
        run, callbacks = fixture._run(
            'EGFR L858R showed sensitivity to erlotinib in lung cancer.',
            'SAME', case_id='consolidation-accounting-fail',
        )
    report = run.relation_aware_report
    assert report['source_unit_retrieval']['strategies_used'] == ['RRF_STRUCTURE_MEDCPT']
    assert report['pipeline_accounting']['bidirectional_reconciliation']['status'] == 'FAIL'
    assert run.status == 'PARTIAL'
    assert report['run_status'] == 'PARTIAL'
    assert report['publication_status'] == 'INCOMPLETE'
    assert len(callbacks) == 1  # Fixture invocation, not a provider call.
    assert len(report['paper_evidence'][0]['accepted_evidence_records']) == 1
    stage = next(s for s in run.stages if s.stage_id == 'stage_13_dossier')
    assert stage.status == 'WARNING'
    assert 'EVIDENCE_CLAIM_RECONCILIATION_FAILED' in stage.reason_codes
    from backend.api import research_routes
    from backend.research_pipeline.public_schemas import DossierResponse
    with patch.object(research_routes, '_snapshot_or_404', return_value=run.to_dict()):
        response = research_routes.get_dossier(run.run_id)
    DossierResponse.model_validate(response)
    assert response['status'] == 'PARTIAL'
    assert response['technical_run_status'] == 'COMPLETED'
    assert response['publication_status'] == 'INCOMPLETE'
    assert 'riconciliazione' in response['dossier_markdown'].lower()
    assert 'EVIDENCE_CLAIM_RECONCILIATION_FAILED' in response['dossier_markdown']
    assert len(response['dossier']['paper_evidence'][0]['accepted_evidence_records']) == 1


def test_live_sourceunit_fusion_is_provenant_filtered_top5_and_fails_closed(monkeypatch):
    from types import SimpleNamespace
    from backend.research_pipeline.retrieval import canonical_rrf
    from backend.research_pipeline.retrieval.live_sourceunit_selection import (
        select_live_papers_for_association,
    )
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _paper_candidate

    candidate = _paper_candidate()
    document = SimpleNamespace(
        candidate_id=candidate['candidate_id'], document_id='pmid:12345678',
        bundle_id='bundle:one', resolved=True, full_text_available=True,
        lineage={'requested_document_id': 'pmid:12345678'},
    )
    units = {}
    for index in range(8):
        gene = 'EGFR T790M' if index == 7 else 'EGFR L858R'
        uid = f'SU-{index}'
        units[uid] = {'source_unit_id': uid, 'document_id': 'pmid:12345678',
                      'unit_type': 'FULLTEXT_PARAGRAPH', 'section': 'results',
                      'text': f'{gene} showed sensitivity to erlotinib in lung cancer. Unique result {index}.'}
    association = {'candidate_id': candidate['candidate_id'], 'candidate': candidate}
    resolution = SimpleNamespace(documents=(document,))
    source_ids = set(units)
    scores = {uid: float(index) for index, uid in enumerate(sorted(source_ids))}
    monkeypatch.delenv('RESEARCH_PIPELINE_SOURCEUNIT_STRATEGY', raising=False)
    monkeypatch.setattr(canonical_rrf, 'dense_scores', lambda _selection: (scores, {'model': 'fixture-medcpt', 'cache': 'fixture'}))
    selected = select_live_papers_for_association(association, units, resolution=resolution)
    assert selected['selected_papers'][0]['retrieval_strategy'] == canonical_rrf.STRATEGY
    paper = selected['selected_papers'][0]
    assert len(paper['resolved_source_unit_ids']) == 5
    assert 'SU-7' not in paper['resolved_source_unit_ids']
    assert paper['document_id'] == document.document_id
    trace = paper['selector']['matched_features']['retrieval']['selected_component_ranks']
    assert len(trace) == 5
    assert all(row['fusion_rank'] and row['structure_rank'] and row['medcpt_rank'] for row in trace)
    assert paper['selector']['top_k'] == 5
    from backend.research_pipeline.dossier.accounting import apply_publication_integrity
    mixed = apply_publication_integrity({
        'run_status': 'COMPLETED', 'pipeline_accounting': {'bidirectional_reconciliation': {'status': 'PASS'}},
        'paper_evidence': [{'support_level': 'FULL_SUPPORT', 'evidence_composition': {
            'record_count': 2, 'unique_publication_count': 1, 'mixed_support': True,
            'counts_by_support_result': {'FULL_SUPPORT': 1, 'NO_SUPPORT': 1}}}],
    })
    from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
    rendered = render_dossier_markdown(mixed)
    assert '"mixed_support": true' in rendered
    assert '"NO_SUPPORT": 1' in rendered

    monkeypatch.setattr(canonical_rrf, 'dense_scores', lambda _selection: (_ for _ in ()).throw(RuntimeError('fixture checkpoint unavailable')))
    fallback = select_live_papers_for_association(association, units, resolution=resolution)
    assert fallback['selected_papers'][0]['retrieval_strategy'] == canonical_rrf.BASELINE
    assert fallback['retrieval_fallbacks'][0]['reason'].startswith('RuntimeError: fixture checkpoint unavailable')


def test_fallback_attempt_survives_document_cap(monkeypatch):
    from types import SimpleNamespace
    from backend.research_pipeline.retrieval import canonical_rrf
    from backend.research_pipeline.retrieval import live_sourceunit_selection as live
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import _paper_candidate

    candidate = _paper_candidate()
    documents = tuple(SimpleNamespace(
        candidate_id=candidate['candidate_id'], document_id=f'pmid:{i}',
        bundle_id=f'bundle:{i}', resolved=True, full_text_available=True,
        lineage={'requested_document_id': f'pmid:{i}'},
    ) for i in range(1, 4))
    units = {f'SU-{i}': {'source_unit_id': f'SU-{i}', 'document_id': f'pmid:{i}',
             'unit_type': 'FULLTEXT_PARAGRAPH', 'section': 'results',
             'text': f'EGFR L858R sensitivity to erlotinib result {i}.'} for i in range(1, 4)}
    monkeypatch.setattr(canonical_rrf, 'dense_scores', lambda _selection: (_ for _ in ()).throw(RuntimeError('offline fixture')))
    monkeypatch.setattr(live, 'MAX_PAPERS_PER_ASSOCIATION', 2)
    result = live.select_live_papers_for_association(
        {'candidate_id': candidate['candidate_id'], 'candidate': candidate}, units,
        resolution=SimpleNamespace(documents=documents))
    assert len(result['selected_papers']) == 2
    assert len(result['retrieval_attempts']) == 3
    assert len(result['retrieval_fallbacks']) == 3
    capped = next(row for row in result['excluded_papers']
                  if row['reason_codes'] == ['MAX_PAPERS_PER_ASSOCIATION_EXCEEDED'])
    assert capped['retrieval_strategy'] == canonical_rrf.BASELINE
    assert capped['retrieval_fallback_reason'].startswith('RuntimeError: offline fixture')
