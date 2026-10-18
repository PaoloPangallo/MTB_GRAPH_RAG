from __future__ import annotations

import copy
import json

from backend.research_pipeline.narrative.presentation import (
    AMBIGUOUS_DOCUMENTARY_STATE,
    CONTRADICTORY_DOCUMENTARY_EVIDENCE,
    DOCUMENTARY_EVIDENCE_AVAILABLE,
    NO_VALIDATED_DOCUMENTARY_EVIDENCE,
    SOURCE_DOES_NOT_SUPPORT,
    build_narrative_presentation,
)
from backend.research_pipeline.narrative.narrator import _argument_errors
from backend.research_pipeline.narrative.prompt import TOOL_SCHEMA


def _dossier(*, direction="SUPPORTED", quote=True):
    author_context = []
    if quote:
        author_context.append({
            "paper_id": "PMID-1",
            "source_unit_id": "SU-1",
            "author_claim_quote": "validated words",
            "source_unit_text": "The complete validated source unit text.",
            "presentation_state": "VALIDATED_QUOTE",
        })
    return {
        "case_id": "CASE-1",
        "candidate_therapies": [{
            "candidate_id": "GCA-1",
            "drug": "DRUG-A",
            "graph_relation": "associated_with_sensitivity_to",
            "status": "DIRECT" if direction == "SUPPORTED" else "AMBIGUOUS",
            "warnings": (["SOURCE_POLARITY_DOES_NOT_SUPPORT"]
                         if direction == "SOURCE_DOES_NOT_SUPPORT"
                         else ([] if quote else ["NO_VALIDATED_ENRICHMENT_AVAILABLE"])),
            "gate_results": {
                "bucket": "PRIMARY_BUCKET" if direction == "SUPPORTED" else "WARNING_BUCKET",
                "support_mask": {
                    "disease": "SUPPORTED",
                    "biomarker": "SUPPORTED",
                    "intervention": "SUPPORTED",
                    "direction": direction,
                },
            },
            "document_support": {
                "selected_papers": ["PMID-1"],
                "excluded_papers": ["PMID-X"],
            },
            "author_context": author_context + [{
                "paper_id": "PMID-X",
                "source_unit_id": "SU-X",
                "author_claim_quote": "rejected words",
                "presentation_state": "REJECTED_QUOTE",
            }],
            "validation_results": [],
        }],
        "limitations": ["research_only_pilot"],
        "provenance": {},
    }


def _narrative():
    return {
        "narrative_summary": "Sintesi.",
        "candidate_narratives": [{"candidate_id": "GCA-1", "text": "Spiegazione."}],
        "limitations_summary": "Limiti spiegati.",
        "closing_note": "Nota.",
        "narrative_hash": "hash",
    }


def _relation_aware_dossier():
    return {
        "case_summary": {"case_id": "CASE-R", "intervention": "DRUG-A"},
        "paper_evidence": [{
            "candidate_id": "P", "relation": "associated_with_resistance_to",
            "object": {"label": "DRUG-A"}, "document_id": "pmid:1",
            "quote_source_unit_id": "SU-1", "quote": "validated words",
            "source_unit_text": "Complete source unit.", "quote_valid": True,
            "support_level": "PARTIAL_SUPPORT",
            "support_fields": {"direction": "RESISTANCE"},
        }],
        "clinical_trials": [{
            "candidate_id": "T", "relation": "tested_in_trial",
            "object": {"label": "DRUG-B"}, "nct_id": "NCT00000001",
            "trial_resolution_status": "RESOLVED",
            "eligibility_status": "NOT_EVALUATED",
        }],
        "kg_only_relations": [{
            "candidate_id": "K", "relation": "gene_drug_interaction",
            "object": {"label": "DRUG-C"}, "source_database": "MyCancerGenome",
            "verification_status": "KG_ONLY", "document_provenance": "NOT_AVAILABLE",
        }],
        "limitations": ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"],
    }


def _relation_aware_narrative():
    return {
        "narrative_summary": "Sintesi.",
        "candidate_narratives": [
            {"candidate_id": candidate_id, "text": f"Spiegazione {candidate_id}.",
             "source_refs": [], "claims": []}
            for candidate_id in ("P", "T", "K")
        ],
        "limitations_summary": "Limiti spiegati.",
        "closing_note": "Nota.",
        "narrative_hash": "hash",
    }


def test_relation_aware_report_builds_three_branch_presentation():
    result = build_narrative_presentation(
        _relation_aware_dossier(), _relation_aware_narrative(), {"status": "PASS"})
    by_id = {candidate["candidate_id"]: candidate for candidate in result["candidates"]}

    assert set(by_id) == {"P", "T", "K"}
    assert by_id["P"]["canonical_status"] == "PARTIAL_SUPPORT"
    assert by_id["P"]["support_direction"] == "RESISTANCE"
    assert by_id["P"]["sources"][0]["paper_id"] == "pmid:1"
    assert by_id["P"]["sources"][0]["source_unit_id"] == "SU-1"
    assert by_id["P"]["sources"][0]["source_unit_text"] == "Complete source unit."
    assert by_id["T"]["sources"][0]["paper_id"] == "NCT00000001"
    assert by_id["K"]["sources"][0]["paper_id"] == "MyCancerGenome"
    assert by_id["K"]["generated_explanation"] == "Spiegazione K."


def test_presentation_copies_canonical_fields_and_attaches_explanation_without_mutation():
    dossier = _dossier()
    before = json.dumps(dossier, sort_keys=True)
    result = build_narrative_presentation(dossier, _narrative(), {"status": "PASS"})
    candidate = result["candidates"][0]

    assert candidate["canonical_status"] == "DIRECT"
    assert candidate["support_direction"] == "SUPPORTED"
    assert candidate["intervention"] == "DRUG-A"
    assert candidate["graph_relation"] == "associated_with_sensitivity_to"
    assert candidate["generated_explanation"] == "Spiegazione."
    assert json.dumps(dossier, sort_keys=True) == before


def test_documentary_state_is_deterministic_and_non_support_has_precedence_over_quote():
    supported = build_narrative_presentation(_dossier(), _narrative(), {"status": "PASS"})
    absent = build_narrative_presentation(
        _dossier(direction="NO_DOCUMENT_SIGNAL", quote=False), _narrative(), {"status": "PASS"})
    non_support = build_narrative_presentation(
        _dossier(direction="SOURCE_DOES_NOT_SUPPORT", quote=True), _narrative(), {"status": "PASS"})
    incomplete = build_narrative_presentation(
        _dossier(direction="UNRELATED_EVIDENCE", quote=True), _narrative(), {"status": "PASS"})

    assert supported["candidates"][0]["documentary_support_state"] == DOCUMENTARY_EVIDENCE_AVAILABLE
    assert absent["candidates"][0]["documentary_support_state"] == NO_VALIDATED_DOCUMENTARY_EVIDENCE
    assert non_support["candidates"][0]["documentary_support_state"] == SOURCE_DOES_NOT_SUPPORT
    assert incomplete["candidates"][0]["documentary_support_state"] == "AMBIGUOUS_DOCUMENTARY_STATE"


def test_contradicted_remains_distinct_from_source_does_not_support():
    dossier = _dossier(direction="CONTRADICTED", quote=True)
    result = build_narrative_presentation(dossier, _narrative(), {"status": "PASS"})
    assert result["candidates"][0]["documentary_support_state"] == CONTRADICTORY_DOCUMENTARY_EVIDENCE


def test_documentary_state_labels_are_non_positive_and_deterministic():
    from backend.research_pipeline.narrative.presentation import documentary_state_label

    assert documentary_state_label(DOCUMENTARY_EVIDENCE_AVAILABLE) == "Documentazione validata disponibile"
    assert documentary_state_label(NO_VALIDATED_DOCUMENTARY_EVIDENCE) == "Nessun supporto documentale validato"
    assert documentary_state_label(SOURCE_DOES_NOT_SUPPORT) == "La fonte non supporta la relazione"
    assert documentary_state_label(CONTRADICTORY_DOCUMENTARY_EVIDENCE) == "Evidenza documentale contraddittoria"
    assert documentary_state_label(AMBIGUOUS_DOCUMENTARY_STATE) == "Stato documentale non conclusivo"


def test_sources_include_only_selected_authorized_validated_quotes():
    candidate = build_narrative_presentation(_dossier(), _narrative(), {"status": "PASS"})["candidates"][0]
    assert candidate["sources"] == [{
        "paper_id": "PMID-1",
        "source_unit_id": "SU-1",
        "quote_available": True,
        "validated_quote": "validated words",
        "source_unit_text": "The complete validated source unit text.",
    }]
    assert "rejected words" not in json.dumps(candidate)
    assert "PMID-X" not in json.dumps(candidate)


def test_critical_notices_are_deterministic_and_fallback_never_attaches_explanation():
    dossier = _dossier(direction="SOURCE_DOES_NOT_SUPPORT", quote=True)
    failed = build_narrative_presentation(dossier, _narrative(), {
        "status": "FAIL", "reason_codes": ["NARRATIVE_STATUS_ESCALATION"]})

    assert failed["candidates"][0]["critical_notices"] == ["SOURCE_POLARITY_DOES_NOT_SUPPORT"]
    assert failed["candidates"][0]["generated_explanation"] is None
    assert failed["summary"] is None
    assert failed["presentation_mode"] == "STRUCTURED_DOSSIER_FALLBACK"


def test_abstention_reason_is_exposed_as_a_deterministic_critical_notice():
    dossier = _dossier(direction="NO_DOCUMENT_SIGNAL", quote=False)
    dossier["candidate_therapies"][0]["author_context"].append({
        "presentation_state": "ABSTAINED",
        "abstention_reason": "nessun passaggio rilevante",
    })
    candidate = build_narrative_presentation(dossier, _narrative(), {"status": "PASS"})["candidates"][0]
    assert "ABSTENTION: nessun passaggio rilevante" in candidate["critical_notices"]


def test_schema_requires_non_empty_candidate_array_and_strings():
    properties = TOOL_SCHEMA["properties"]
    assert properties["candidate_narratives"]["minItems"] == 1
    assert properties["narrative_summary"]["minLength"] == 1
    assert properties["candidate_narratives"]["items"]["properties"]["text"]["minLength"] == 1


def test_argument_validation_rejects_empty_explanation_and_duplicate_ids():
    base = {
        "narrative_summary": "Sintesi",
            "candidate_narratives": [{
                "candidate_id": "GCA-1", "text": "Spiegazione",
            }],
        "limitations_summary": "Limiti",
        "closing_note": "Nota",
    }
    assert _argument_errors(base) == []
    empty = copy.deepcopy(base)
    empty["candidate_narratives"][0]["text"] = "  "
    assert any("EMPTY_STRING" in value for value in _argument_errors(empty))
    duplicate = copy.deepcopy(base)
    duplicate["candidate_narratives"].append(copy.deepcopy(duplicate["candidate_narratives"][0]))
    assert any("DUPLICATE_CANDIDATE_ID" in value for value in _argument_errors(duplicate))


def test_relation_quotes_keep_all_admitted_record_identities():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    entry = {'candidate_id': 'P', 'relation': 'targets_drug', 'document_id': 'pmid:111', 'representative_document_id': 'pmid:222', 'quote': 'First quote.', 'quote_source_unit_id': 'SU-222', 'quote_valid': True, 'support_level': 'FULL_SUPPORT', 'accepted_evidence_records': [
        {'evidence_id': 'E1', 'paper_id': 'pmid:222', 'source_unit_id': 'SU-222', 'quote': 'First quote.', 'quote_valid': True},
        {'evidence_id': 'E2', 'paper_id': 'pmid:333', 'source_unit_id': 'SU-333', 'quote': 'Second quote.', 'quote_valid': True},
        {'evidence_id': 'E3', 'paper_id': 'pmid:444', 'source_unit_id': 'SU-444', 'quote': 'Blocked.', 'quote_valid': False},
    ]}
    dossier = {'paper_evidence': [entry]}
    sources = build_narrative_presentation(dossier, None, None)['candidates'][0]['sources']
    assert [(s['paper_id'], s['source_unit_id'], s['validated_quote']) for s in sources if s['quote_available']] == [('pmid:222', 'SU-222', 'First quote.'), ('pmid:333', 'SU-333', 'Second quote.')]
    quotes = build_narrator_input(dossier)['candidates'][0]['validated_quotes']
    assert [(q['paper_id'], q['source_unit_id']) for q in quotes] == [('pmid:222', 'SU-222'), ('pmid:333', 'SU-333')]


def test_representative_quote_uses_representative_document_in_legacy_shape():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    dossier = {'paper_evidence': [{'candidate_id': 'P', 'document_id': 'pmid:111', 'representative_document_id': 'pmid:222', 'quote': 'Literal.', 'quote_valid': True, 'quote_source_unit_id': 'SU-222'}]}
    assert build_narrative_presentation(dossier, None, None)['candidates'][0]['sources'][0]['paper_id'] == 'pmid:222'
    assert build_narrator_input(dossier)['candidates'][0]['validated_quotes'][0]['paper_id'] == 'pmid:222'


def test_record_projection_is_deterministic_and_never_invents_missing_identity():
    from backend.research_pipeline.narrative.evidence_sources import paper_sources
    record = {'evidence_id': 'E1', 'paper_id': 'pmid:2', 'source_unit_id': 'SU-2', 'quote': 'Literal.', 'quote_valid': True, 'candidate_support': {'result': 'NO_SUPPORT'}}
    entry = {'document_id': 'pmid:1', 'quote_valid': True, 'quote': 'Fallback must not leak.', 'quote_source_unit_id': 'SU-1', 'accepted_evidence_records': [record, dict(record), {'quote': 'Missing source.', 'quote_valid': True}]}
    original = copy.deepcopy(entry)
    sources = paper_sources(entry)
    assert len(sources) == 1 and sources[0]['support_result'] == 'NO_SUPPORT'
    assert entry == original and paper_sources(entry) == sources
    assert paper_sources({'document_id': 'pmid:1', 'quote_valid': True, 'quote': 'No unit.'})[0]['quote_available'] is False


def test_controlled_narrative_renders_each_admitted_quote_at_its_own_source():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.narrative.controlled import build_catalog, default_plan, render_plan, verify_controlled
    entry = {'candidate_id': 'P', 'relation': 'targets_drug', 'document_id': 'pmid:1', 'support_level': 'FULL_SUPPORT', 'accepted_evidence_records': [
        {'evidence_id': 'E1', 'paper_id': 'pmid:2', 'source_unit_id': 'SU-2', 'quote': 'First literal.', 'quote_valid': True, 'candidate_support': {'result': 'FULL_SUPPORT'}},
        {'evidence_id': 'E2', 'paper_id': 'pmid:3', 'source_unit_id': 'SU-3', 'quote': 'Second literal.', 'quote_valid': True, 'candidate_support': {'result': 'NO_SUPPORT'}},
    ]}
    projected = build_narrator_input({'paper_evidence': [entry]})
    catalog = build_catalog(projected)
    narrative = render_plan(catalog, default_plan(catalog))
    text = narrative['candidate_narratives'][0]['text']
    assert 'fonte pmid:2, SourceUnit SU-2' in text
    assert 'fonte pmid:3, SourceUnit SU-3' in text
    assert 'Esito del record: assenza di supporto documentale' in text
    assert verify_controlled(projected, narrative)['status'] == 'PASS'


def test_markdown_does_not_publish_failed_narrative_or_wrong_legacy_source():
    from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
    dossier = {'paper_evidence': [{'candidate_id': 'P', 'document_id': 'pmid:1', 'representative_document_id': 'pmid:2', 'quote': 'Legacy literal.', 'quote_valid': True, 'quote_source_unit_id': 'SU-2'}]}
    markdown = render_dossier_markdown(dossier, {'narrative_summary': 'UNVERIFIED PROSE'}, 'VERIFIED_NARRATIVE', {'status': 'FAIL'})
    assert 'UNVERIFIED PROSE' not in markdown
    assert '**Documento:** pmid:2' in markdown
