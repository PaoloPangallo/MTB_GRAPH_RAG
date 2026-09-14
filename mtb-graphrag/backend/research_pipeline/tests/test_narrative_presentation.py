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
            "source_refs": [], "claims": [],
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
