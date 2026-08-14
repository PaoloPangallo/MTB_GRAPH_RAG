from __future__ import annotations

from types import SimpleNamespace

from evaluation.final_evaluation_harness.common.execution import (
    RealExecutionContext,
    ScientificExecutionResult,
)
from evaluation.final_evaluation_harness.common.registry import ExecutionAdapterRegistry
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import PlannedRun, build_full_plan, build_plan
from evaluation.final_evaluation_harness.common.production_loop import execute_sealed_plan
from evaluation.final_evaluation_harness.common.ledger import AppendOnlyLedger
from evaluation.final_evaluation_harness.common.guards import ForbiddenOperation, ModelGuard, NetworkGuard, RuntimeGuard
from pathlib import Path
import pytest


def _unit(rq="RQ1", execution_class="DETERMINISTIC_ONLY"):
    return PlannedRun(testbed="TB", rq=rq, case_id="CASE", arm="primary", repetition_id="primary",
                      run_id="run_" + "a" * 64, plan_index=1, execution_class=execution_class,
                      canonical_runtime_requirement="PROHIBITED", selector_requirement="PROHIBITED",
                      casecontext_parser_requirement="PROHIBITED", gemma_requirement="PROHIBITED",
                      narrator_requirement="PROHIBITED", quote_validator_requirement="PROHIBITED",
                      narrative_verifier_requirement="PROHIBITED", network_policy="PROHIBITED",
                      network_expectation="NONE", cache_policy="READ_ONLY_EXISTING_DATA",
                      dataset_hashes={"dataset_bundle_sha256": "x"}, gold_access="PROHIBITED",
                      terminal_expectation="PATH_DEPENDENT")


def test_scientific_result_is_transport_only_wrapper():
    result = ScientificExecutionResult.from_native({"status": "ABSTAIN", "reason_codes": ["X"]})
    assert result.status == "ABSTAIN"
    assert result.scientific_payload == {"status": "ABSTAIN", "reason_codes": ["X"]}
    assert result.to_dict()["scientific_payload"]["status"] == "ABSTAIN"


def test_real_context_dispatches_bound_executor_without_reimplementing_it():
    calls = []

    class FakeContext:
        selector = object()
        def execute(self, unit, executor):
            calls.append((unit.plan_index, executor.name))
            return ScientificExecutionResult.from_native({"status": "COMPLETE"})

    unit = _unit()
    bound = ExecutionAdapterRegistry(SimpleNamespace()).resolve(unit)
    result = bound.execute(unit, FakeContext())
    assert calls == [(1, "RQ1DeterministicExecutor")]
    assert result.status == "COMPLETE"


def test_real_context_requires_production_dispatcher():
    context = RealExecutionContext(production_dispatcher=None)
    try:
        context.execute(_unit(), SimpleNamespace(name="RQ1DeterministicExecutor"))
    except RuntimeError as exc:
        assert str(exc) == "REAL_EXECUTION_DISPATCHER_NOT_CONFIGURED"
    else:
        raise AssertionError("missing production dispatcher was accepted")


def test_production_context_requires_all_three_guards():
    with pytest.raises(RuntimeError, match="REAL_EXECUTION_GUARDS_NOT_CONFIGURED"):
        RealExecutionContext.from_production(SimpleNamespace())


def test_runtime_guard_fails_closed_for_prohibited_unit():
    guard = RuntimeGuard()
    unit = _unit(execution_class="DETERMINISTIC_ONLY")
    guard.bind(unit)
    with pytest.raises(Exception):
        guard.assert_allowed("REQUIRED")


@pytest.mark.parametrize("missing", ("runtime", "model", "network"))
def test_each_missing_production_guard_fails_closed(missing):
    guards = {"runtime": RuntimeGuard(), "model": ModelGuard(), "network": NetworkGuard("PROHIBITED")}
    guards[missing] = None
    with pytest.raises(RuntimeError, match="REAL_EXECUTION_GUARDS_NOT_CONFIGURED"):
        RealExecutionContext.from_production(SimpleNamespace(), **{
            "runtime_guard": guards["runtime"], "model_guard": guards["model"], "network_guard": guards["network"]})


def test_prohibited_model_and_network_calls_fail_closed():
    model = ModelGuard()
    unit = _unit()
    unit = unit.__class__(**{**unit.__dict__, "gemma_requirement": "PROHIBITED"})
    model.bind(unit)
    with pytest.raises(ForbiddenOperation):
        model.assert_allowed("REQUIRED", role="gemma")
    network = NetworkGuard("CANONICAL_RUNTIME_POLICY")
    unit = unit.__class__(**{**unit.__dict__, "network_policy": "PROHIBITED"})
    network.bind(unit)
    with pytest.raises(ForbiddenOperation):
        network.assert_allowed("CANONICAL_RUNTIME_POLICY")


def test_real_context_uses_production_dispatcher_contract():
    class Dispatcher:
        def execute(self, unit, context, executor):
            return {"status": "CONTROLLED_FAILURE", "reason": executor.name}
    result = RealExecutionContext(production_dispatcher=Dispatcher()).execute(
        _unit(), SimpleNamespace(name="RQ1DeterministicExecutor"))
    assert result.status == "CONTROLLED_FAILURE"
    assert result.scientific_payload["reason"] == "RQ1DeterministicExecutor"


def test_production_loop_reserves_persists_and_completes_with_fake_context(tmp_path: Path):
    unit = _unit()
    class FakeContext:
        selector = object()
        ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl")
        def execute(self, planned, executor):
            return ScientificExecutionResult.from_native({"status": "COMPLETE", "scientific": planned.case_id})
    context = FakeContext()
    registry = ExecutionAdapterRegistry(SimpleNamespace())
    results = execute_sealed_plan([unit], context, registry, tmp_path, campaign_open=True)
    assert results[0].scientific_payload["scientific"] == "CASE"
    assert [event["event"] for event in context.ledger.events()] == ["ATTEMPT_RESERVED", "RAW_COMMITTED", "COMPLETE"]
    assert len(list((tmp_path / "raw_attempts").glob("*.json"))) == 1


def test_production_coverage_reports_only_concrete_methods_without_execution():
    protocol = load_protocol()
    plan = build_full_plan(protocol)
    from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher
    dispatcher = ProductionUnitDispatcher()
    covered, missing = dispatcher.coverage(plan, ExecutionAdapterRegistry(protocol))
    assert covered == 222
    assert missing == []


def test_rq1_and_rq2_offline_dispatch_use_frozen_local_artifacts():
    protocol = load_protocol()
    from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher
    dispatcher = ProductionUnitDispatcher()
    rq1 = dispatcher._RQ1DeterministicExecutor(build_plan("rq1", protocol)[0], None)
    assert rq1["metrics"]["eligible_paths"] == 46864
    rq2 = build_plan("rq2", protocol)
    first_k = dispatcher._run_rq2_offline(rq2[0], SimpleNamespace())
    assert first_k["arm"] == "FIRST_K"
    assert len(first_k["selected_source_unit_ids"]) == 5


def test_reliability_b_frozen_arm_uses_selector_contract():
    protocol = load_protocol()
    unit = build_plan("reliability", protocol)[21]
    assert unit.testbed == "RELIABILITY_STRATUM_B"
    assert unit.arm == "DETERMINISTIC_SELECTOR_K5_TO_SAME_GEMMA_TO_SAME_QUOTE_VALIDATOR"
    from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher
    dispatcher = ProductionUnitDispatcher()
    context = SimpleNamespace(selector=SimpleNamespace(select=lambda selection, top_k=5:
        SimpleNamespace(selected_source_unit_ids=["SU-1"], ranked_source_units=[])))
    result = dispatcher._run_rq2_offline(unit, context)
    assert result["arm"] == unit.arm
    assert result["selected_source_unit_ids"] == ["SU-1"]


def test_latency_pair_uses_frozen_document_resolver_contract():
    protocol = load_protocol()
    unit = build_plan("latency", protocol)[0]
    calls = []

    class Document:
        cache_hit = True
        document_id = "pmid:15705718"
        reason_codes = ("CACHE_HIT", "DOCUMENT_RESOLVED")
        availability = "ABSTRACT_AVAILABLE"
        resolved = True

    class Resolution:
        documents = (Document(),)

    class Resolver:
        def resolve(self, associations):
            calls.append(associations)
            return Resolution(), 1.25

    from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher
    result = ProductionUnitDispatcher()._LatencyExecutor(
        unit, SimpleNamespace(timing=None, latency_document_resolver=Resolver())
    )
    assert result["cache_observable"] == "CACHE_HIT"
    assert result["document_id"] == "pmid:15705718"
    assert result["elapsed_ms"] == 1.25
    assert len(calls) == 1
    association = calls[0][0]
    assert association["candidate_id"] == "GCA-0000980ba01970f893f8e4d7"
    assert association["available_bundles"][0]["document_id"] == "pmid:15705718"
    assert association["available_bundles"][0]["provenance_identifier"] == {"pmid": "15705718"}


def test_latency_pair_real_document_runtime_preserves_only_cache_delta():
    protocol = load_protocol()
    from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher

    class NetworkGuard:
        def assert_allowed(self, _policy):
            return None

        def record(self):
            return None

    context = SimpleNamespace(protocol=protocol, network_guard=NetworkGuard())
    dispatcher = ProductionUnitDispatcher()
    results = {
        unit.arm: dispatcher._LatencyExecutor(unit, context)
        for unit in build_plan("latency", protocol)
    }

    hit = results["LAT-HIT"]
    miss = results["LAT-MISS"]
    assert hit["cache_observable"] == "CACHE_HIT"
    assert hit["cache_initial_state"] == "TARGET_SEEDED"
    assert hit["network_fetch_count"] == 0
    assert miss["cache_observable"] == "CACHE_MISS"
    assert miss["cache_initial_state"] == "SAME_PLAN_TARGET_EXCLUDED"
    assert miss["network_fetch_count"] >= 1
    assert hit["gca_id"] == miss["gca_id"] == "GCA-0000980ba01970f893f8e4d7"
    assert hit["document_id"] == miss["document_id"] == "pmid:15705718"
    assert hit["component_path"] == miss["component_path"]
    assert not any(field in hit or field in miss for field in ("query_id", "biomarker", "disease"))


def test_rq3_enricher_budget_boundary_preserves_structured_case_context(monkeypatch):
    protocol = load_protocol()
    unit = build_plan("rq3", protocol)[0]
    from evaluation.final_evaluation_harness.common.case_resolution import resolve_production_case
    resolved_case_id, case = resolve_production_case(unit.case_id)
    captured = {}

    class Parser:
        def __call__(self, case_id, text, run_index=0):
            return {"transport_result": "FORCED_TOOL_VALID", "case_context_raw": {
                "case_id": case_id, "disease": {}, "biomarkers": [],
                "previous_interventions": [], "target_intervention": None,
                "query_intent": "THERAPY_DISCOVERY", "clinical_question": text,
                "uncertainties": [],
            }}

    class Gemma:
        def call(self, *args, **kwargs):
            captured["case_context"] = args[3]
            return {"transport_result": "FORCED_TOOL_VALID", "enrichment": None}

    class Orchestrator:
        @staticmethod
        def run_case(**kwargs):
            parsed = kwargs["call_parser_fn"](None, kwargs["case_id"], kwargs["clinical_text"])
            kwargs["call_enricher_fn"](None, kwargs["case_id"], "candidate", "paper", parsed["case_context_raw"], {}, "", [])
            return SimpleNamespace(to_dict=lambda: {"status": "COMPLETE"})

    import backend.research_pipeline.orchestrator as orchestrator
    monkeypatch.setattr(orchestrator, "run_case", Orchestrator.run_case)
    context = SimpleNamespace(
        casecontext_parser=Parser(), gemma=Gemma(), narrator=SimpleNamespace(call=lambda *a, **k: {}),
        cache_factory=None,
        ledger=SimpleNamespace(), current_attempt_id="a", current_run_id="r",
        protocol=protocol,
    )
    from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher
    ProductionUnitDispatcher()._run_case(unit, context)
    assert isinstance(captured["case_context"], dict)
    assert captured["case_context"]["case_id"] == resolved_case_id


def test_real_gemma_enricher_contract_renders_structured_case_context(monkeypatch):
    import json
    from backend.research_pipeline import replay
    from backend.research_pipeline.enrichment import enricher_v2

    captured = {}

    def fake_transport(payload):
        captured["payload"] = payload
        name = payload["tool_choice"]["function"]["name"]
        args = {
            "decision": "ABSTAIN", "source_unit_id": "",
            "author_claim_quote": "", "author_context_summary": "",
            "abstention_reason": "OFFLINE_CONTRACT_FIXTURE",
        }
        body = {"choices": [{"finish_reason": "tool_calls", "message": {
            "tool_calls": [{"function": {"name": name, "arguments": json.dumps(args)}}]
        }}]}
        return 200, body, None, 0

    monkeypatch.setattr(
        "backend.research_pipeline.enrichment.transport.post_with_infra_retry",
        fake_transport,
    )
    case_context = replay._parser_outputs_by_case()["CASE-1-therapy-evaluation-strong-match"]["case_context_raw"]
    result = enricher_v2.call_enricher_v2(
        "CASE-1-therapy-evaluation-strong-match", "candidate-1", "PMID-1",
        case_context, {"candidate_id": "candidate-1"}, "panitumumab", [],
    )
    assert isinstance(case_context, dict)
    assert result["transport_result"] == "V2_TRANSPORT_VALID"
    rendered = captured["payload"]["messages"][-1]["content"]
    assert '"disease"' in rendered
    assert "metastatic colorectal cancer" in rendered
