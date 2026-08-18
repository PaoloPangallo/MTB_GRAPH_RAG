from __future__ import annotations

from types import SimpleNamespace

import pytest

from evaluation.final_evaluation_harness.common.execution import RealExecutionContext
from evaluation.final_evaluation_harness.common.ledger import AppendOnlyLedger
from evaluation.final_evaluation_harness.common.production_loop import execute_sealed_plan


class _Registry:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)

    def resolve(self, _unit):
        outcome = next(self.outcomes)

        class _Executor:
            def execute(self, _planned, _context):
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        return _Executor()


def _context(path):
    return RealExecutionContext(ledger=AppendOnlyLedger(path))


def _units(*names):
    return [SimpleNamespace(run_id="run_" + str(name) * 64) for name in names]


def test_structured_failed_unit_is_persisted_and_next_unit_runs(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    context = _context(ledger_path)
    results = execute_sealed_plan(
        _units("1", "2"), context, _Registry([
            {"status": "FAILED", "raw_reason_code": "NO_DOCUMENT_RESOLVED"},
            {"status": "COMPLETE"},
        ]), tmp_path, campaign_open=True,
    )

    assert [result.status for result in results] == ["FAILED", "COMPLETE"]
    events = context.ledger.events()
    complete = [event for event in events if event["event"] == "COMPLETE"]
    assert [event["unit_status"] for event in complete] == ["FAILED", "COMPLETE"]
    assert len(list((tmp_path / "raw_attempts").glob("*.json"))) == 2
    assert context.ledger.reconcile() == []


def test_structured_partial_and_stopped_are_local_terminal_outcomes(tmp_path):
    context = _context(tmp_path / "ledger.jsonl")
    results = execute_sealed_plan(
        _units("1", "2"), context, _Registry([
            {"status": "PARTIAL"}, {"status": "STOPPED"},
        ]), tmp_path, campaign_open=True,
    )
    assert [result.status for result in results] == ["PARTIAL", "STOPPED"]
    assert [event["unit_status"] for event in context.ledger.events() if event["event"] == "COMPLETE"] == ["PARTIAL", "STOPPED"]


def test_unclassified_exception_remains_campaign_fatal(tmp_path):
    context = _context(tmp_path / "ledger.jsonl")
    with pytest.raises(RuntimeError, match="INVARIANT_FAILURE"):
        execute_sealed_plan(
            _units("1", "2"), context, _Registry([
                RuntimeError("INVARIANT_FAILURE"), {"status": "COMPLETE"},
            ]), tmp_path, campaign_open=True,
        )
    events = context.ledger.events()
    assert any(event["event"] == "INFRASTRUCTURE_FAILED" for event in events)
    assert not any(event.get("run_id") == "run_2" for event in events)
