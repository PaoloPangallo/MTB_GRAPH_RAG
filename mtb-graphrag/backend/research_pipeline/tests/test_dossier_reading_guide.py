from copy import deepcopy
from unittest.mock import patch

from backend.research_pipeline.dossier.observations import project_documentary_findings
from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown


def dossier():
    return project_documentary_findings({
        'run_status': 'COMPLETED',
        'pipeline_accounting': {'bidirectional_reconciliation': {'status': 'PASS'}},
        'case_summary': {'disease': 'metastatic melanoma', 'intervention': 'dabrafenib + trametinib'},
        'paper_evidence': [{'candidate_id': 'P', 'accepted_evidence_records': [{
            'evidence_id': 'E', 'paper_id': 'pmid:28891408', 'source_unit_id': 'SU',
            'quote': 'Adjuvant therapy reduced recurrence in resected stage III melanoma.',
            'quote_valid': True, 'relation_family': 'EVIDENCE_STATEMENT',
            'observed_relation': {'disease': 'stage III melanoma', 'intervention': 'dabrafenib + trametinib',
                                  'effect_direction': 'SENSITIVITY_RESPONSE', 'molecular_composition': 'ALTERNATIVES'},
        }]}],
        'clinical_trials': [
            {'candidate_id': 'T1', 'nct_id': 'NCT02465060', 'title': 'MATCH', 'status': 'RECRUITING'},
            {'candidate_id': 'T2', 'nct_id': 'nct:NCT02465060', 'title': 'MATCH', 'status': 'RECRUITING'},
            {'candidate_id': 'T3', 'nct_id': 'NCT02465060', 'title': 'MATCH', 'status': 'COMPLETED'},
            {'candidate_id': 'T4', 'nct_id': 'invalid'}, {'candidate_id': 'T5'},
        ],
        'kg_only_relations': [], 'limitations': [],
    })


def test_reading_guide_preserves_facts_and_highlights_scope_without_clinical_judgment():
    from backend.research_pipeline.dossier.reading import build_reading_guide
    report = dossier()
    original = deepcopy(report)
    guide = build_reading_guide(report)
    assert report == original
    finding = guide['findings'][0]
    assert finding['requested_disease'] == 'metastatic melanoma'
    assert finding['observed_disease'] == 'stage III melanoma'
    assert finding['disease_text_comparison'] == 'DIFFERENT_RECORDED_TEXT'
    assert {'DISEASE_DESCRIPTIONS_DIFFER', 'MOLECULAR_ALTERNATIVES', 'STRUCTURAL_CHECK_NOT_RECORDED',
            'SEMANTIC_CHECK_NOT_REQUIRED', 'BROAD_OUTCOME_CATEGORY'} <= {n['code'] for n in finding['notices']}
    assert 'clinical_applicability' not in finding
    assert guide['clinical_applicability'] == 'NOT_EVALUATED'


def test_trials_group_by_valid_id_and_keep_conflicting_snapshots_and_unknowns():
    from backend.research_pipeline.dossier.reading import build_reading_guide
    guide = build_reading_guide(dossier())
    assert guide['trial_association_count'] == 5
    assert guide['identified_study_count'] == 1
    assert guide['unidentified_trial_association_count'] == 2
    assert guide['trial_groups'][0]['entry_indexes'] == [0, 1, 2]
    assert guide['trial_groups'][0]['snapshot_indexes'] == [0, 2]
    assert guide['trial_groups'][0]['conflicting_snapshots'] is True
    assert len(guide['trial_groups']) == 3


def test_guide_is_freshly_computed_at_api_boundary():
    from backend.api import research_routes
    report = dossier()
    report['reading_guide'] = {'identified_study_count': 999}
    with patch.object(research_routes, '_snapshot_or_404', return_value={
        'status': 'COMPLETED', 'relation_aware_report': report, 'stages': [],
    }):
        response = research_routes.get_dossier('READING')
    assert response['reading_guide']['identified_study_count'] == 1
    from backend.research_pipeline.dossier.accounting import apply_publication_integrity
    assert response['dossier'] == apply_publication_integrity(report)
    assert report['reading_guide']['identified_study_count'] == 999


def test_export_groups_studies_links_sources_and_shows_scope_not_generic_response():
    text = render_dossier_markdown(dossier())
    assert text.count('### Studio 1\n') == 1
    assert '**Studi identificati distinti:** 1' in text
    assert '**Associazioni a trial:** 5' in text
    assert 'https://pubmed.ncbi.nlm.nih.gov/28891408/' in text
    assert 'Descrizioni della patologia diverse' in text
    assert 'Classificazione generale del risultato' in text
    assert 'Adjuvant therapy reduced recurrence' in text


def test_missing_descriptions_and_historical_records_do_not_gain_equivalence():
    from backend.research_pipeline.dossier.reading import build_reading_guide
    report = dossier()
    report['case_summary'] = {}
    report['paper_evidence'][0]['documentary_findings'][0]['observed'] = {}
    finding = build_reading_guide(report)['findings'][0]
    assert finding['disease_text_comparison'] == 'NOT_RECORDED'
    assert finding['intervention_text_comparison'] == 'NOT_RECORDED'
    assert build_reading_guide({'paper_evidence': [{'candidate_id': 'OLD'}]})['findings'] == []
