"""Reuse document work without reusing evidence across different relations."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.research_pipeline.documents.live_resolution import resolve_live_documents
from backend.research_pipeline import live_providers
from backend.research_pipeline.pipeline import CallBudget


def test_resolve_identifier_once_but_preserve_every_candidate_binding(tmp_path):
    cache = SimpleNamespace(
        root=tmp_path, manifest_path=tmp_path / "absent.jsonl", resolver_version="test",
        has_text_payload=lambda record: True,
        resolve_live_identifier=Mock(return_value={
            "document_id": "nct:NCT12345678", "availability": "METADATA_ONLY",
            "local_cache_path": "trial.json", "content_hash": "content", "cache_hit": False,
            "retrieval_mode": "LIVE_FETCH",
        }),
    )
    associations = [{"candidate_id": cid, "available_bundles": [{
        "bundle_id": f"bundle-{cid}", "document_id": "nct:NCT12345678",
        "provenance_identifier": {"nct": "NCT12345678"},
    }]} for cid in ("one", "two", "three")]
    result = resolve_live_documents(associations, cache, {})
    assert cache.resolve_live_identifier.call_count == 1
    assert [d.candidate_id for d in result.documents] == ["one", "two", "three"]
    assert all(d.resolved for d in result.documents)
    assert result.network_fetch_count == 1
    assert result.documents[1].lineage["resolution_reused"] is True


def test_different_identifiers_do_not_share_resolution(tmp_path):
    cache = SimpleNamespace(
        root=tmp_path, manifest_path=tmp_path / "absent", resolver_version="test",
        has_text_payload=lambda record: True,
        resolve_live_identifier=Mock(side_effect=lambda item: {
            "document_id": "pmid:" + item["pmid"], "availability": "ABSTRACT_AVAILABLE",
            "cache_hit": True,
        }),
    )
    associations = [{"candidate_id": "one", "available_bundles": [{
        "bundle_id": f"b-{pmid}", "document_id": "pmid:" + pmid,
        "provenance_identifier": {"pmid": pmid},
    } for pmid in ("12345678", "12345679")]}]
    assert len(resolve_live_documents(associations, cache, {}).documents) == 2
    assert cache.resolve_live_identifier.call_count == 2


def test_selection_index_reads_unit_collection_once():
    from backend.research_pipeline.retrieval.live_sourceunit_selection import SelectionIndex

    units = Mock()
    units.values.return_value = [
        {"source_unit_id": "a", "document_id": "doc-a", "text": "text a"},
        {"source_unit_id": "b", "document_id": "doc-b", "text": "text b"},
    ]
    resolution = SimpleNamespace(documents=[SimpleNamespace(candidate_id="c", resolved=True)])
    index = SelectionIndex.build(resolution, units)
    for _ in range(30):
        assert index.units_by_document_id["doc-a"][0]["source_unit_id"] == "a"
        assert len(index.records_by_candidate_id["c"]) == 1
    units.values.assert_called_once()


def _reader_args():
    return ("case", "candidate", "doc", {"disease": "disease"},
            {"candidate_id": "candidate", "interventions": [{"label": "drug-a"}]},
            "drug-a", [{"source_unit_id": "SU-1", "document_id": "doc", "text": "Exact text."}])


def _response():
    return (200, {"choices": [{"message": {"tool_calls": [{"function": {
        "name": "submit_paper_relation_observation",
        "arguments": '{"decision":"ABSTAIN","abstain_reason":"NO_RELEVANT_EVIDENCE"}',
    }}]}}]}, None, 0)


def test_same_run_identical_reader_input_spends_budget_once_and_copies_result():
    reader = live_providers.make_run_enricher()
    budget = CallBudget(20)
    with patch("backend.research_pipeline.enrichment.transport.post_with_infra_retry", return_value=_response()) as post:
        first = reader(budget, *_reader_args())
        first["enrichment"]["notes"] = "mutation must not contaminate cache"
        second = reader(budget, *_reader_args())
    assert post.call_count == budget.used == 1
    assert "mutation must not contaminate cache" != second["enrichment"].get("notes")
    assert second["reader_response_reused"] is True
    assert second["model_call_count"] == 0


@pytest.mark.parametrize("changed", ["drug", "case", "text", "unit_id", "candidate", "document", "model"])
def test_reader_reuse_never_crosses_effective_input(changed):
    reader = live_providers.make_run_enricher()
    args = list(deepcopy(_reader_args()))
    budget = CallBudget(20)
    with patch("backend.research_pipeline.enrichment.transport.post_with_infra_retry", return_value=_response()) as post:
        reader(budget, *_reader_args())
        if changed == "drug":
            args[5] = "drug-b"
            args[4]["interventions"][0]["label"] = "drug-b"
        elif changed == "case": args[3]["disease"] = "other"
        elif changed == "text": args[6][0]["text"] = "Different text."
        elif changed == "unit_id": args[6][0]["source_unit_id"] = "SU-2"
        elif changed == "candidate": args[1] = args[4]["candidate_id"] = "other"
        elif changed == "document": args[2] = "other-doc"
        with patch("backend.research_pipeline.enrichment.transport.model_name", return_value="other" if changed == "model" else "gemma4:cloud"):
            # Pin the initial model separately below: model changes are part of the payload key.
            reader(budget, *args)
    assert post.call_count == budget.used == 2


def test_cache_is_run_scoped_and_does_not_reuse_transport_failures():
    budget = CallBudget(20)
    with patch("backend.research_pipeline.enrichment.transport.post_with_infra_retry", return_value=(503, {}, None, 1)) as post:
        reader = live_providers.make_run_enricher()
        reader(budget, *_reader_args())
        reader(budget, *_reader_args())
    assert post.call_count == 2
    with patch("backend.research_pipeline.enrichment.transport.post_with_infra_retry", return_value=_response()) as post:
        live_providers.make_run_enricher()(budget, *_reader_args())
        live_providers.make_run_enricher()(budget, *_reader_args())
    assert post.call_count == 2


def test_persistent_rate_limit_stops_reader_instead_of_sending_more_candidates():
    with patch("backend.research_pipeline.enrichment.transport.post_with_infra_retry", return_value=(429, {}, None, 1)):
        with pytest.raises(live_providers.LiveStageFailed) as failure:
            live_providers.enricher_fn(CallBudget(20), *_reader_args())
    assert failure.value.reason_code == "PROVIDER_RATE_LIMITED"


def test_indexed_and_unindexed_selection_are_identical():
    from backend.research_pipeline.retrieval.live_sourceunit_selection import SelectionIndex, select_live_papers_for_association
    from backend.research_pipeline.tests.test_live_runtime_integration import _candidate, _resolution, _units
    from backend.research_pipeline.experimental.sourceunit_selector import select

    candidate = _candidate()
    association = {"candidate_id": candidate["candidate_id"], "candidate": candidate}
    resolution = _resolution()
    units = _units("pmid:24658966")
    baseline = select_live_papers_for_association(association, units, resolution=resolution, selector_fn=select)
    indexed = select_live_papers_for_association(
        association, units, resolution=resolution, selection_index=SelectionIndex.build(resolution, units), selector_fn=select)
    assert indexed == baseline


def test_disease_only_trial_is_explicitly_marked_without_claiming_molecular_match():
    from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate
    case = {"disease": {"normalized_value": "Lung Cancer"},
            "biomarkers": [{"gene": "EGFR", "alteration": "L858R"}], "query_intent": "THERAPY_DISCOVERY"}
    candidate = {"candidate_id": "trial", "predicate": "trial_has_drug", "biomarkers": [],
                 "disease": [], "interventions": [], "document_identifiers": [{"nct": "NCT12345678"}],
                 "trial_context": {"conditions": ["Lung Cancer"], "genes": [], "retrieval_only": True}}
    accepted, reasons = _match_candidate(case, candidate)
    assert accepted
    assert "TRIAL_DISEASE_CONTEXT_ONLY" in reasons
    assert "BIOMARKER_COMPATIBLE" not in reasons


@pytest.mark.parametrize("failed_component", ["reader", "semantic"])
def test_orchestrator_stops_on_rate_limit_and_preserves_failed_attempt(failed_component):
    from backend.pipeline.agentic.ledger import EventLedger
    from backend.research_pipeline import orchestrator
    from backend.research_pipeline.casecontext.parser import adapt_case_context
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import (
        ControlledDocumentRuntime, _paper_candidate, _parser_output, _source_unit, _reader_observation,
    )
    text = "lung cancer with EGFR L858R; discover associated therapies."
    parsed = _parser_output(text, interventions=())
    parsed["query_intent"] = "THERAPY_DISCOVERY"
    context = adapt_case_context("limited", parsed, text)
    candidates = {cid: _paper_candidate(cid, relation_family="EVIDENCE_DRUG",
        semantic_key=f"Evidence:{cid}",
        document_identifiers=[{"pmid": "12345678"}]) for cid in ("one", "two")}
    def parser(budget, case_id, _text):
        budget.spend("parser", case_id)
        return {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": context,
                "model": "controlled", "prompt_version": "controlled"}
    def reader(budget, *args):
        budget.spend("reader", "limited")
        if failed_component == "semantic":
            return _reader_observation(args[4], args[6])
        failure = live_providers.LiveStageFailed("stage_9_paper_context_enricher", "PROVIDER_RATE_LIMITED", "HTTP 429")
        failure.call_result = {"transport_result": "HTTP_ERROR", "transport_reason_codes": ["HTTP_429"]}
        raise failure
    def semantic(budget, *args):
        budget.spend("semantic", "limited")
        return {"infrastructure_failure": "PROVIDER_RATE_LIMITED", "transport_result": "HTTP_ERROR",
                "transport_reason_codes": ["HTTP_429"]}
    budget = CallBudget(20)
    reader_mock = Mock(side_effect=reader)
    with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates", return_value=candidates):
        run = orchestrator.run_case(case_id="limited", clinical_text=text, call_parser_fn=parser,
            call_enricher_fn=reader_mock, budget=budget, ledger=Mock(spec=EventLedger), source_units_by_id={},
            call_semantic_alignment_fn=semantic,
            validate_fn=live_providers.validate_fn,
            document_runtime=ControlledDocumentRuntime([_source_unit(
                "EGFR L858R showed sensitivity to erlotinib in lung cancer.",
                document_id="pmid:12345678", unit_id="su")]))
    assert reader_mock.call_count == 1
    assert run.status == "FAILED" and run.stopped_at == "PROVIDER_RATE_LIMITED"
    assert budget.used == run.llm_calls == (2 if failed_component == "reader" else 3)
    stage_id = "stage_9_paper_context_enricher" if failed_component == "reader" else "stage_10_enrichment_validation"
    stage = next(s for s in run.stages if s.stage_id == stage_id)
    assert stage.artifact_origin == "GENERATED_NOW"
    assert stage.output_preview["failed_call"]["transport_reason_codes"] == ["HTTP_429"]


def test_semantic_provider_preserves_rate_limit_identity():
    from backend.research_pipeline.enrichment.semantic_alignment import call_semantic_alignment
    with patch("backend.research_pipeline.enrichment.transport.post_with_infra_retry", return_value=(429, {}, None, 1)):
        result = call_semantic_alignment(CallBudget(20), "case", {}, {"required_context": "exact text"})
    assert result["infrastructure_failure"] == "PROVIDER_RATE_LIMITED"
    assert result["transport_reason_codes"] == ["HTTP_429"]


def test_frontend_fixture_has_current_event_vocabulary():
    import json
    from pathlib import Path
    from backend.research_pipeline.events import EVENT_TYPES
    path = Path(__file__).resolve().parents[3] / "frontend/src/research/__fixtures__/runtime-contract.json"
    assert set(json.loads(path.read_text(encoding="utf-8"))["event_types"]) == set(EVENT_TYPES)


def test_parser_rate_limit_is_named_as_provider_failure():
    from backend.pipeline.agentic.ledger import EventLedger
    from backend.research_pipeline import orchestrator
    reader = Mock()
    run = orchestrator.run_case(case_id="limited-parser", clinical_text="lung cancer with EGFR L858R",
        call_parser_fn=lambda *args: {"transport_result": "HTTP_ERROR", "status_code": 429,
                                     "transport_reason_codes": ["HTTP_429"]},
        call_enricher_fn=reader, budget=CallBudget(20), ledger=Mock(spec=EventLedger), source_units_by_id={})
    assert run.stopped_at == "PROVIDER_RATE_LIMITED" and run.status == "FAILED"
    assert run.llm_calls == 1
    reader.assert_not_called()


def test_custom_selector_cannot_remove_units_from_later_candidates():
    from backend.pipeline.agentic.ledger import EventLedger
    from backend.research_pipeline import orchestrator
    from backend.research_pipeline.casecontext.parser import adapt_case_context
    from backend.research_pipeline.tests.test_orchestrated_pre_freeze_matrix import (
        ControlledDocumentRuntime, _paper_candidate, _parser_output, _source_unit, _reader_observation,
    )
    text = "lung cancer with EGFR L858R; discover associated therapies."
    parsed = _parser_output(text, interventions=())
    parsed["query_intent"] = "THERAPY_DISCOVERY"
    context = adapt_case_context("isolation", parsed, text)
    candidates = {cid: _paper_candidate(cid, semantic_key=f"Evidence:{cid}") for cid in ("one", "two")}
    selected_counts, reader_counts = [], []
    def selector(association, units, **kwargs):
        selected_counts.append(len(units))
        units.clear()
        bundle = association["available_bundles"][0]
        return {"selected_papers": [{**bundle, "resolved_source_unit_ids": ["su"]}], "excluded_papers": []}
    def reader(budget, case, cid, doc, ctx, candidate, drug, units):
        reader_counts.append(len(units))
        return _reader_observation(candidate, units)
    with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates", return_value=candidates):
        run = orchestrator.run_case(case_id="isolation", clinical_text=text,
            call_parser_fn=lambda *args: {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": context},
            call_enricher_fn=reader, select_papers_fn=selector, validate_fn=live_providers.validate_fn,
            budget=CallBudget(20), ledger=Mock(spec=EventLedger), source_units_by_id={},
            document_runtime=ControlledDocumentRuntime([_source_unit(
                "EGFR L858R showed sensitivity to erlotinib in lung cancer.",
                document_id="pmid:12345678", unit_id="su")]))
    assert run.status in {"COMPLETED", "PARTIAL"}
    assert selected_counts == reader_counts == [1, 1]
