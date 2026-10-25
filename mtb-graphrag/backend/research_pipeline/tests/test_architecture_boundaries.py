"""Architectural boundaries and durable public output regressions."""
from unittest.mock import Mock

import pytest

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import events, orchestrator
from backend.research_pipeline.contracts import StageProducer


def test_budget_has_a_single_implementation():
    from backend.research_pipeline.budget import CallBudget, CallBudgetExceeded
    from backend.research_pipeline.pipeline import CallBudget as HistoricalBudget
    from backend.research_pipeline.pipeline import CallBudgetExceeded as HistoricalError

    assert CallBudget is HistoricalBudget
    assert CallBudgetExceeded is HistoricalError
    budget = CallBudget(1)
    budget.spend("reader", "case")
    with pytest.raises(CallBudgetExceeded):
        budget.spend("reader", "case")


def test_terminal_stage_event_contains_public_output_without_domain_event():
    ledger = Mock(spec=EventLedger)
    recorder = orchestrator.RunRecorder(ledger, "run", "LIVE")
    producer = StageProducer(kind="DETERMINISTIC", component="eligibility", version="test")
    preview = {"eligible": False, "contradictions": ["explicitly negated anchor"]}
    recorder.finish("stage_3b_pre_retrieval_eligibility_gate", producer, output_preview=preview)
    payload = ledger.append.call_args.args[3]
    assert payload["output_preview"] == preview
    assert ledger.append.call_args.args[1] == events.STAGE_COMPLETED


def test_terminal_preview_still_rejects_document_text():
    ledger = Mock(spec=EventLedger)
    recorder = orchestrator.RunRecorder(ledger, "run", "LIVE")
    producer = StageProducer(kind="DETERMINISTIC", component="eligibility", version="test")
    with pytest.raises(events.ForbiddenPayloadField):
        recorder.finish("stage_3b_pre_retrieval_eligibility_gate", producer,
                        output_preview={"nested": {"full_text": "must not be persisted"}})
    ledger.append.assert_not_called()


def test_recorder_and_presentation_live_in_dedicated_modules():
    from backend.research_pipeline.recording import RunRecorder
    from backend.research_pipeline.narrative.stage_runner import narrate_and_verify

    assert orchestrator.RunRecorder is RunRecorder
    assert orchestrator._narrate_and_verify is narrate_and_verify


def test_admission_identity_includes_the_full_input_not_only_its_preview(tmp_path):
    ledger = EventLedger(tmp_path / "identity.sqlite3")
    recorder = orchestrator.RunRecorder(ledger, "run", "LIVE")
    text = "x" * 600 + "EGFR absent"
    original_time = recorder.run_created("case", text, {})
    assert recorder.run_created("case", text, {}) == original_time
    with pytest.raises(ValueError, match="IDENTITY_MISMATCH"):
        recorder.run_created("case", "x" * 600 + "EGFR amplified", {})
    assert len(ledger.events("run")) == 1


def test_submit_failure_is_durable_and_never_advertised_as_running(tmp_path, monkeypatch):
    from backend.research_pipeline.run_store import RunStore
    monkeypatch.setenv("RESEARCH_LEDGER_PATH", str(tmp_path / "submit.sqlite3"))
    store = RunStore(max_workers=1, queue_capacity=0)
    monkeypatch.setattr(store._executor, "submit", Mock(side_effect=RuntimeError("submit failed")))
    try:
        with pytest.raises(RuntimeError, match="submit failed"):
            store.start(case_id="case", clinical_text="synthetic case")
        handle = store.list_runs()[0]
        assert handle.status == "FAILED"
        assert not store.is_running(handle.run_id)
        assert store.snapshot(handle.run_id)["errors"]
        assert store.ledger.events(handle.run_id)[-1]["event_type"] == events.RUN_COMPLETED
    finally:
        store.shutdown()
