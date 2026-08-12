from __future__ import annotations

import pytest
from types import SimpleNamespace

from evaluation.final_evaluation_harness.common.case_resolution import resolve_production_case
from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher
from evaluation.final_evaluation_harness.common.execution import RealExecutionContext
from evaluation.final_evaluation_harness.common.guards import ModelGuard, NetworkGuard, RuntimeGuard
from evaluation.final_evaluation_harness.common.ledger import AppendOnlyLedger
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.production_loop import execute_sealed_plan
from evaluation.final_evaluation_harness.common.registry import ExecutionAdapterRegistry
from evaluation.final_evaluation_harness.common.runner import build_plan


def test_full_system_resolves_to_frozen_canonical_case():
    case_id, case = resolve_production_case("FULL_SYSTEM")
    assert case_id == "CASE-1-therapy-evaluation-strong-match"
    assert case["case_id"] == case_id
    assert case["clinical_text"]


def test_unknown_production_case_fails_closed():
    with pytest.raises(RuntimeError, match="REAL_EXECUTION_INPUT_NOT_RESOLVED:UNKNOWN_CASE_FOR_TEST"):
        resolve_production_case("UNKNOWN_CASE_FOR_TEST")


def test_all_rq3_arms_resolve_same_canonical_input(monkeypatch):
    captured = []

    class Run:
        def to_dict(self):
            return {"status": "COMPLETE", "case_id": captured[-1]["case_id"]}

    def fake_run_case(**kwargs):
        captured.append(kwargs)
        return Run()

    from backend.research_pipeline import orchestrator
    monkeypatch.setattr(orchestrator, "run_case", fake_run_case)
    units = build_plan("rq3", load_protocol())
    dispatcher = ProductionUnitDispatcher()
    context = SimpleNamespace(
        casecontext_parser=lambda *args, **kwargs: {},
        gemma=SimpleNamespace(call=lambda *args, **kwargs: {}),
        narrator=SimpleNamespace(call=lambda *args, **kwargs: {}),
        cache_factory=SimpleNamespace(),
        ledger=SimpleNamespace(),
    )
    methods = {
        "CANONICAL": dispatcher._RQ3FullSystemExecutor,
        "A": dispatcher._RQ3AblationAExecutor,
        "B": dispatcher._RQ3AblationBExecutor,
        "C": dispatcher._RQ3AblationCExecutor,
        "D": dispatcher._RQ3AblationDExecutor,
    }
    for unit in units:
        methods[unit.arm](unit, context)
    assert len(captured) == 5
    assert {item["case_id"] for item in captured} == {"CASE-1-therapy-evaluation-strong-match"}
    assert [item.get("case_id") for item in captured] == ["CASE-1-therapy-evaluation-strong-match"] * 5
    assert captured[0].get("match_verifier_fn") is None
    assert captured[1].get("match_verifier_fn") is not None
    assert captured[2].get("source_unit_selector_fn") is not None
    assert captured[3].get("validate_fn") is not None
    assert captured[4].get("research_frozen_artifacts") is True


def test_rq3_canonical_reaches_raw_and_ledger_lifecycle(tmp_path, monkeypatch):
    from backend.research_pipeline import orchestrator

    class Run:
        def to_dict(self):
            return {"status": "COMPLETE", "resolved_case_id": "CASE-1-therapy-evaluation-strong-match"}

    monkeypatch.setattr(orchestrator, "run_case", lambda **_kwargs: Run())
    protocol = load_protocol()
    unit = next(item for item in build_plan("rq3", protocol) if item.arm == "CANONICAL")
    ledger = AppendOnlyLedger(tmp_path / "ledger.jsonl")
    fake_adapter = SimpleNamespace(call=lambda *args, **kwargs: {}, select=lambda *args, **kwargs: None)
    context = RealExecutionContext(
        protocol=protocol,
        casecontext_parser=lambda *args, **kwargs: {},
        gemma=fake_adapter,
        narrator=fake_adapter,
        cache_factory=SimpleNamespace(),
        ledger=ledger,
        network_guard=NetworkGuard("PROHIBITED"),
        model_guard=ModelGuard(),
        runtime_guard=RuntimeGuard(),
        production_dispatcher=ProductionUnitDispatcher(),
    )
    result = execute_sealed_plan([unit], context, ExecutionAdapterRegistry(protocol), tmp_path, campaign_open=True)
    assert result[0].status == "COMPLETE"
    assert [event["event"] for event in ledger.events()] == ["ATTEMPT_RESERVED", "RAW_COMMITTED", "COMPLETE"]
    raw_files = list((tmp_path / "raw_attempts").glob("*.json"))
    assert len(raw_files) == 1


def test_official_start_rq3_canonical_resolves_and_completes(tmp_path, monkeypatch):
    import evaluation.final_evaluation_harness.start as start
    from evaluation.final_evaluation_harness.common.execution import ProductionAdapterFactory

    protocol = load_protocol()
    unit = next(item for item in build_plan("rq3", protocol) if item.arm == "CANONICAL")

    class Run:
        def to_dict(self):
            return {"status": "COMPLETE", "resolved_case_id": "CASE-1-therapy-evaluation-strong-match"}

    from backend.research_pipeline import orchestrator
    monkeypatch.setattr(orchestrator, "run_case", lambda **_kwargs: Run())
    fake = SimpleNamespace(call=lambda *args, **kwargs: {}, select=lambda *args, **kwargs: None,
                            validate=lambda *args, **kwargs: {}, verify_authority=lambda *args, **kwargs: {})
    monkeypatch.setattr(ProductionAdapterFactory, "canonical_runtime", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "selector", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "parser", staticmethod(lambda: (lambda *args, **kwargs: {})))
    monkeypatch.setattr(ProductionAdapterFactory, "gemma", staticmethod(lambda *args, **kwargs: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "narrator", staticmethod(lambda *args, **kwargs: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "quote_validator", staticmethod(lambda *args, **kwargs: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "narrative_verifier", staticmethod(lambda *args, **kwargs: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "document_runtime", staticmethod(lambda: SimpleNamespace(resolve=lambda value: value)))

    plan_sha = "p" * 64
    campaign = tmp_path / "evaluation" / "final_evaluation"
    result = start.run_official_start(
        protocol=protocol,
        source_root=protocol.root.parents[1],
        expected_head="a" * 40,
        plans=[unit.__dict__],
        plan_sha=plan_sha,
        expected_evaluation_id="fe_rq3_fixture",
        argv=["--arm", "--confirm-evaluation-id", "fe_rq3_fixture", "--confirm-plan-sha", plan_sha,
              "--confirm-start", "FINAL_EVALUATION_1_6"],
        campaign_root=campaign,
        metadata_request=lambda _model: {"details": {"family": "gemma4", "parameter_size": "32682372656",
                                                       "quantization_level": "BF16"},
                                         "model_info": {"gemma4.context_length": 262144}},
        dispatch=start.run_production_dispatch,
        environment_validator=lambda: None,
        prompt_validator=lambda: None,
        head_validator=lambda *_args: None,
    )
    assert result == "DISPATCHED"
    events = (campaign / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert any('"event": "ATTEMPT_RESERVED"' in line for line in events)
    assert any('"event": "RAW_COMMITTED"' in line for line in events)
    assert any('"event": "COMPLETE"' in line for line in events)
    assert len(list((campaign / "raw_attempts").glob("*.json"))) == 1
