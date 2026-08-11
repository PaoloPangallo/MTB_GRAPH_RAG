from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from backend.research_pipeline.documents.live_resolution import DocumentResolution, ResolvedDocument
from backend.research_pipeline.enrichment.validator_v2 import identity_semantic_validator, validate_enrichment_v2
from backend.research_pipeline.experimental.sourceunit_selector import select
from backend.research_pipeline.retrieval.live_sourceunit_selection import select_live_papers_for_association


def _resolution() -> DocumentResolution:
    return DocumentResolution((ResolvedDocument(
        document_id="pmid:1", bundle_id="live:GCA:pmid:1", candidate_id="GCA-1",
        availability="ABSTRACT_AVAILABLE", resolved=True, cache_hit=True,
        document_type="ABSTRACT", source="fixture", metadata_only=False,
        abstract_available=True, full_text_available=False, content_hash="h",
        reason_codes=(), lineage={},
    ),), "cache", "manifest")


def test_selector_strategy_injection_receives_canonical_input_and_keeps_wrapper():
    calls = []
    units = {"SU-1": {"source_unit_id": "SU-1", "document_id": "pmid:1", "text": "ABL1 V299L dasatinib"}}

    def strategy(selection, *, top_k):
        calls.append((selection, top_k))
        return select(selection, top_k=top_k)

    result = select_live_papers_for_association(
        {"candidate_id": "GCA-1", "candidate": {"candidate_id": "GCA-1", "disease": [{"label": "CML"}], "biomarkers": [], "interventions": [{"label": "dasatinib"}]}},
        units, resolution=_resolution(), selector_fn=strategy,
    )
    assert calls and calls[0][0].candidate_id == "GCA-1"
    assert calls[0][1] == 5
    assert result["selected_papers"][0]["resolved_source_unit_ids"] == ["SU-1"]


def test_validator_identity_seam_preserves_transport_gate():
    args = {"decision": "QUOTE", "source_unit_id": "SU-1", "author_claim_quote": "x", "author_context_summary": "y", "abstention_reason": ""}
    result = validate_enrichment_v2(
        "V2_TRANSPORT_VALID", args, candidate={}, paper_bundle={}, source_units_by_id={}, requested_drug="",
        semantic_validator=identity_semantic_validator,
    )
    assert result["outcome"] == "ENRICHMENT_V2_ACCEPTED"
    assert "SEMANTIC_VALIDATION_IDENTITY" in result["reason_codes"]
    rejected = validate_enrichment_v2(
        "BROKEN", args, candidate={}, paper_bundle={}, source_units_by_id={}, requested_drug="",
        semantic_validator=identity_semantic_validator,
    )
    assert rejected["outcome"] == "REJECTED_TRANSPORT"


def test_narrative_bypass_skips_verifier_without_success_verdict():
    recorder = SimpleNamespace(start=lambda *a, **k: None, finish=lambda *a, **k: None)
    with patch("backend.research_pipeline.narrative.input_projection.build_narrator_input", return_value={
        "narrator_input_hash": "h", "contract_version": "v", "counts": {"candidates": 0},
    }):
        from backend.research_pipeline import orchestrator
        calls = []
        orchestrator._narrate_and_verify(
            recorder, "case", {}, lambda *_: {"transport_result": "FORCED_TOOL_VALID", "narrative": {}, "model": "fake"},
            lambda *_: calls.append(True), True, "GENERATED_NOW", "OFFLINE_ABLATION_BYPASS",
        )
    assert calls == []


def test_narrative_bypass_is_not_available_to_canonical_callers():
    from backend.research_pipeline import orchestrator
    import pytest
    with pytest.raises(ValueError, match="restricted to frozen evaluation"):
        orchestrator.run_case(
            case_id="case", clinical_text="text", call_parser_fn=lambda *a: {},
            call_enricher_fn=lambda *a: {}, source_units_by_id={}, budget=None,
            ledger=None, narrative_verifier_mode="OFFLINE_ABLATION_BYPASS",
            research_frozen_artifacts=False,
        )
