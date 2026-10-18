from unittest.mock import patch

from backend.api import research_routes


def test_api_exposes_fallback_origin_without_turning_model_failure_into_pass():
    text = {"narrative_summary": "Sintesi canonica.", "candidate_narratives": [],
            "limitations_summary": "Limiti.", "closing_note": "Nessuna raccomandazione."}
    snapshot = {"status": "PARTIAL", "relation_aware_report": {"case_summary": {"case_id": "C"},
        "paper_evidence": [], "clinical_trials": [], "kg_only_relations": []}, "stages": [
        {"stage_id": "stage_15_narrative_verifier", "output_preview": {
            "verified_narrative": None, "deterministic_narrative": text,
            "presentation_mode": "DETERMINISTIC_NARRATIVE_FALLBACK",
            "verification": {"status": "FAIL", "reason_codes": ["NARRATIVE_ABSENT"]},
            "deterministic_verification": {"status": "PASS", "reason_codes": []}}}]}
    with patch.object(research_routes, "_snapshot_or_404", return_value=snapshot):
        result = research_routes.get_dossier("R")
    assert result["narrative"] == text
    assert result["narrative_verification"]["status"] == "PASS"
    assert result["model_narrative_verification"]["status"] == "FAIL"
    assert result["narrative_generation_origin"] == "DETERMINISTIC_FALLBACK"


def test_provenance_preserves_current_reader_abstention_reason():
    snapshot = {'case_id': 'C', 'stages': [
        {'stage_id': 'stage_5_kg_retrieval', 'output_preview': {'associations': [{'candidate_id': 'P'}]}},
        {'stage_id': 'stage_9_paper_context_enricher', 'output_preview': {'calls': [{'candidate_id': 'P', 'paper_id': 'pmid:1', 'enrichment': {'decision': 'ABSTAIN', 'abstain_reason': 'NO_RELEVANT_EVIDENCE'}}]}},
    ]}
    with patch.object(research_routes, '_snapshot_or_404', return_value=snapshot):
        result = research_routes.get_provenance('R')
    entry = next(c for c in result['items'][0]['chain'] if c['level'] == 'AUTHOR_QUOTE')
    assert entry['abstentions'][0]['abstention_reason'] == 'NO_RELEVANT_EVIDENCE'


def test_provenance_current_quote_is_not_classified_as_abstention():
    snapshot = {'case_id': 'C', 'stages': [
        {'stage_id': 'stage_5_kg_retrieval', 'output_preview': {'associations': [{'candidate_id': 'P'}]}},
        {'stage_id': 'stage_9_paper_context_enricher', 'output_preview': {'calls': [{'candidate_id': 'P', 'paper_id': 'pmid:1', 'enrichment': {'decision': 'QUOTE', 'quote': 'Literal.', 'source_unit_id': 'SU-1'}}]}},
    ]}
    with patch.object(research_routes, '_snapshot_or_404', return_value=snapshot):
        result = research_routes.get_provenance('R')
    entry = next(c for c in result['items'][0]['chain'] if c['level'] == 'AUTHOR_QUOTE')
    assert entry['abstentions'] == []
    assert entry['rejected_quotes'][0]['author_claim_quote'] == 'Literal.'


def test_api_and_markdown_fail_closed_on_inconsistent_narrative_state():
    narrative = {'narrative_summary': 'UNVERIFIED PROSE', 'candidate_narratives': []}
    snapshot = {'status': 'PARTIAL', 'relation_aware_report': {'paper_evidence': [], 'clinical_trials': [], 'kg_only_relations': []}, 'stages': [
        {'stage_id': 'stage_15_narrative_verifier', 'output_preview': {'verified_narrative': narrative, 'verification': {'status': 'FAIL'}, 'presentation_mode': 'VERIFIED_NARRATIVE'}}]}
    with patch.object(research_routes, '_snapshot_or_404', return_value=snapshot):
        result = research_routes.get_dossier('R')
    assert result['narrative'] is None
    assert result['presentation_mode'] == 'STRUCTURED_DOSSIER_FALLBACK'
    assert 'UNVERIFIED PROSE' not in result['dossier_markdown']


def test_provenance_never_borrows_acceptance_from_another_source_unit():
    snapshot = {'case_id': 'C', 'stages': [
        {'stage_id': 'stage_5_kg_retrieval', 'output_preview': {'associations': [{'candidate_id': 'P'}]}},
        {'stage_id': 'stage_9_paper_context_enricher', 'output_preview': {'calls': [{'candidate_id': 'P', 'paper_id': 'pmid:1', 'enrichment': {'decision': 'QUOTE', 'quote': 'Other unit.', 'source_unit_id': 'SU-2'}}]}},
        {'stage_id': 'stage_10_enrichment_validation', 'output_preview': {'validations': [{'candidate_id': 'P', 'paper_id': 'pmid:1', 'source_unit_id': 'SU-1', 'outcome': 'ENRICHMENT_V3_ACCEPTED'}]}},
    ]}
    with patch.object(research_routes, '_snapshot_or_404', return_value=snapshot):
        result = research_routes.get_provenance('R')
    entry = next(c for c in result['items'][0]['chain'] if c['level'] == 'AUTHOR_QUOTE')
    assert entry['accepted_quotes'] == []
    assert result['items'][0]['document_grounded'] is False


def test_exact_quote_binding_and_ambiguous_legacy_linkage():
    import hashlib
    call = {'paper_id': 'pmid:1', 'enrichment': {'quote': 'Literal.', 'source_unit_id': 'SU-1'}}
    valid = {'paper_id': 'pmid:1', 'source_unit_id': 'SU-1', 'quote_hash': hashlib.sha256(b'Literal.').hexdigest(), 'outcome': 'ENRICHMENT_V3_ACCEPTED'}
    assert research_routes._reader_validation_link(call, [valid], [call])[0] == valid
    other = {'paper_id': 'pmid:1', 'enrichment': {'quote': 'Other literal.', 'source_unit_id': 'SU-1'}}
    assert research_routes._reader_validation_link(other, [valid], [call, other])[0] is None
    legacy = {'paper_id': 'pmid:1', 'outcome': 'ENRICHMENT_V3_ACCEPTED'}
    assert research_routes._reader_validation_link(call, [legacy], [call])[0] == legacy
    assert research_routes._reader_validation_link(call, [legacy], [call, other])[0] is None


def test_document_alias_from_selection_links_real_resolved_quote():
    import hashlib
    bundle = 'live:P:pmid:1'
    call = {'candidate_id': 'P', 'paper_id': 'pmcid:PMC2', 'enrichment': {'decision': 'QUOTE', 'quote': 'Literal.', 'source_unit_id': 'SU-2'}}
    validation = {'candidate_id': 'P', 'paper_id': bundle, 'source_unit_id': 'SU-2', 'quote_hash': hashlib.sha256(b'Literal.').hexdigest(), 'outcome': 'ENRICHMENT_V3_ACCEPTED'}
    snapshot = {'case_id': 'C', 'stages': [
        {'stage_id': 'stage_5_kg_retrieval', 'output_preview': {'associations': [{'candidate_id': 'P'}]}},
        {'stage_id': 'stage_8_paper_selection', 'output_preview': {'selections': [{'candidate_id': 'P', 'selected_papers': [{'bundle_id': bundle, 'document_id': 'pmcid:PMC2', 'requested_document_id': 'pmid:1'}]}]}},
        {'stage_id': 'stage_9_paper_context_enricher', 'output_preview': {'calls': [call]}},
        {'stage_id': 'stage_10_enrichment_validation', 'output_preview': {'validations': [validation]}},
    ]}
    with patch.object(research_routes, '_snapshot_or_404', return_value=snapshot):
        result = research_routes.get_provenance('R')
    entry = next(c for c in result['items'][0]['chain'] if c['level'] == 'AUTHOR_QUOTE')
    assert len(entry['accepted_quotes']) == 1
    assert entry['accepted_quotes'][0]['provenance_linkage_basis'] == 'EXACT_SOURCE_UNIT_AND_QUOTE_HASH'
    snapshot['stages'][1]['output_preview']['selections'][0]['selected_papers'][0]['document_id'] = 'pmcid:PMC3'
    with patch.object(research_routes, '_snapshot_or_404', return_value=snapshot):
        result = research_routes.get_provenance('R')
    entry = next(c for c in result['items'][0]['chain'] if c['level'] == 'AUTHOR_QUOTE')
    assert entry['accepted_quotes'] == []
