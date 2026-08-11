from __future__ import annotations

from types import SimpleNamespace

from evaluation.final_evaluation_harness.common.execution import (
    RealExecutionContext,
    ScientificExecutionResult,
)
from evaluation.final_evaluation_harness.common.registry import ExecutionAdapterRegistry
from evaluation.final_evaluation_harness.common.runner import PlannedRun
from evaluation.final_evaluation_harness.common.production_loop import execute_sealed_plan
from evaluation.final_evaluation_harness.common.ledger import AppendOnlyLedger
from pathlib import Path


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
