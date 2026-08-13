from __future__ import annotations

from evaluation.final_evaluation_harness.common.h02_ledger_adapter import H02LedgerAdapter
from evaluation.final_evaluation_harness.common.execution import ProductionUnitDispatcher, RealExecutionContext
from evaluation.final_evaluation_harness.common.lifecycle import CampaignLedger
from evaluation.final_evaluation_harness.common.guards import ModelGuard, NetworkGuard, RuntimeGuard
from evaluation.final_evaluation_harness.common.production_loop import execute_sealed_plan
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.registry import ExecutionAdapterRegistry
from evaluation.final_evaluation_harness.common.runner import build_plan
from backend.research_pipeline.contracts import StageProducer
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline.orchestrator import RunRecorder


def test_h02_recorder_methods_bridge_to_campaign_ledger(tmp_path):
    campaign_ledger = CampaignLedger(tmp_path / "ledger.jsonl")
    adapter = H02LedgerAdapter(
        campaign_ledger,
        attempt_id="run_" + "a" * 64 + "/a0001",
        final_run_id="run_" + "a" * 64,
    )
    recorder = RunRecorder(adapter, "h02-run-1", em.CANONICAL_MODE)
    producer = StageProducer(kind="DETERMINISTIC", component="test", version="1")

    recorder.run_created("CASE-1", "clinical text", {"cache": "fixture"})
    recorder.start("stage_1_case_input", producer)
    recorder.finish("stage_1_case_input", producer, output_preview={"ok": True})
    recorder.emit_domain_event("DOMAIN_EVENT", "stage_1_case_input", producer, value=1)
    recorder.skip_remaining("NOT_IMPLEMENTED")
    recorder.run_completed("COMPLETED", None, 0)

    events = campaign_ledger.events()
    assert events
    assert all(event["attempt_id"] == "run_" + "a" * 64 + "/a0001" for event in events)
    assert all(event["run_id"] == "run_" + "a" * 64 for event in events)
    assert all(event["h02_run_id"] == "h02-run-1" for event in events)
    assert events[0]["event"] == "RUN_CREATED"
    assert events[0]["h02_payload"]["case_id"] == "CASE-1"
    assert events[0]["h02_component"] == "orchestrator"


def test_h02_adapter_preserves_legacy_event_fields(tmp_path):
    ledger = CampaignLedger(tmp_path / "ledger.jsonl")
    adapter = H02LedgerAdapter(
        ledger,
        attempt_id="run_" + "b" * 64 + "/a0001",
        final_run_id="run_" + "b" * 64,
    )
    adapter.append(
        "h02-run-2", "EVENT", "component", {"answer": 42},
        tool_name="tool", tool_version="v1",
    )
    event = ledger.events()[0]
    assert event["event"] == "EVENT"
    assert event["h02_run_id"] == "h02-run-2"
    assert event["h02_component"] == "component"
    assert event["h02_payload"] == {"answer": 42}
    assert event["h02_tool_name"] == "tool"
    assert event["h02_tool_version"] == "v1"


def test_official_rq3_dispatch_reaches_real_recorder_adapter(tmp_path, monkeypatch):
    from backend.research_pipeline import orchestrator
    from types import SimpleNamespace

    def fake_run_case(**kwargs):
        recorder = RunRecorder(kwargs["ledger"], kwargs["run_id"], "LIVE")
        producer = StageProducer(kind="DETERMINISTIC", component="orchestrator", version="test")
        recorder.run_created(kwargs["case_id"], kwargs["clinical_text"], {"cache": "fixture"})
        recorder.run_completed("COMPLETED", None, 0)
        return SimpleNamespace(to_dict=lambda: {"status": "COMPLETE", "run_id": kwargs["run_id"]})

    monkeypatch.setattr(orchestrator, "run_case", fake_run_case)
    protocol = load_protocol()
    unit = next(item for item in build_plan("rq3", protocol) if item.arm == "CANONICAL")
    ledger = CampaignLedger(tmp_path / "ledger.jsonl")
    fake = SimpleNamespace(call=lambda *args, **kwargs: {}, select=lambda *args, **kwargs: None)
    context = RealExecutionContext(
        protocol=protocol,
        casecontext_parser=lambda *args, **kwargs: {},
        gemma=fake,
        narrator=fake,
        cache_factory=SimpleNamespace(),
        ledger=ledger,
        network_guard=NetworkGuard("PROHIBITED"),
        model_guard=ModelGuard(),
        runtime_guard=RuntimeGuard(),
        production_dispatcher=ProductionUnitDispatcher(),
    )
    results = execute_sealed_plan(
        [unit], context, ExecutionAdapterRegistry(protocol), tmp_path, campaign_open=True,
    )
    assert results[0].status == "COMPLETE"
    events = ledger.events()
    assert [event["event"] for event in events[:3]] == ["ATTEMPT_RESERVED", "RUN_CREATED", "RUN_COMPLETED"]
    assert events[-2]["event"] == "RAW_COMMITTED"
    assert events[-1]["event"] == "COMPLETE"
    h02_events = [event for event in events if event.get("h02_namespace") == "research_pipeline"]
    assert h02_events and all(event["h02_run_id"].startswith("h02:") for event in h02_events)


def test_all_rq3_arms_cross_h02_ledger_boundary(tmp_path, monkeypatch):
    from backend.research_pipeline import orchestrator
    from types import SimpleNamespace

    def fake_run_case(**kwargs):
        recorder = RunRecorder(kwargs["ledger"], kwargs["run_id"], "LIVE")
        recorder.run_created(kwargs["case_id"], kwargs["clinical_text"], {"cache": "fixture"})
        recorder.run_completed("COMPLETED", None, 0)
        return SimpleNamespace(to_dict=lambda: {"status": "COMPLETE"})

    monkeypatch.setattr(orchestrator, "run_case", fake_run_case)
    protocol = load_protocol()
    units = build_plan("rq3", protocol)
    methods = {
        "CANONICAL": ProductionUnitDispatcher()._RQ3FullSystemExecutor,
        "A": ProductionUnitDispatcher()._RQ3AblationAExecutor,
        "B": ProductionUnitDispatcher()._RQ3AblationBExecutor,
        "C": ProductionUnitDispatcher()._RQ3AblationCExecutor,
        "D": ProductionUnitDispatcher()._RQ3AblationDExecutor,
    }
    for unit in units:
        ledger = CampaignLedger(tmp_path / unit.arm / "ledger.jsonl")
        fake = SimpleNamespace(call=lambda *args, **kwargs: {}, select=lambda *args, **kwargs: None)
        context = RealExecutionContext(
            protocol=protocol, casecontext_parser=lambda *args, **kwargs: {}, gemma=fake,
            narrator=fake, cache_factory=SimpleNamespace(), ledger=ledger,
            current_attempt_id="run_" + unit.run_id.split("run_", 1)[1] + "/a0001",
            current_run_id=unit.run_id,
        )
        methods[unit.arm](unit, context)
        events = ledger.events()
        assert any(event.get("h02_namespace") == "research_pipeline" for event in events)
        assert all(event["h02_run_id"].startswith("h02:") for event in events)
