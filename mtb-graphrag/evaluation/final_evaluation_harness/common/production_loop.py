"""Mechanical sealed-plan execution loop; no scientific interpretation."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .execution import RealExecutionContext, ScientificExecutionResult
from .identities import attempt_id
from .ledger import AppendOnlyLedger
from .raw_writer import write_raw_once


def _append_event(ledger: Any, event: str, *, attempt_id_value: str, run_id: str, **extra: Any) -> None:
    """Transport lifecycle events through the ledger's canonical API.

    The official START lifecycle supplies ``CampaignLedger`` (event name plus
    keyword fields), while offline execution supplies ``AppendOnlyLedger``
    (one validated event mapping).  Normalize at this single boundary rather
    than weakening either ledger's contract.
    """
    from .lifecycle import CampaignLedger

    if isinstance(ledger, CampaignLedger):
        ledger.append(event, attempt_id=attempt_id_value, run_id=run_id, **extra)
        return
    ledger.append({"event": event, "attempt_id": attempt_id_value, "run_id": run_id, **extra})


def execute_sealed_plan(plan: list[Any], context: RealExecutionContext, registry: Any,
                        campaign_root: Path, *, campaign_open: bool = False) -> list[ScientificExecutionResult]:
    if not campaign_open:
        raise RuntimeError("CAMPAIGN_NOT_OPEN")
    ledger = context.ledger or AppendOnlyLedger(campaign_root / "ledger.jsonl")
    raw_root = campaign_root / "raw_attempts"
    results: list[ScientificExecutionResult] = []
    completed = {e.get("run_id") for e in ledger.events() if e.get("event") == "COMPLETE"}
    ledger.reconcile()
    for unit in plan:
        if unit.run_id in completed:
            continue
        prior = [e for e in ledger.events() if e.get("run_id") == unit.run_id and e.get("event") == "ATTEMPT_RESERVED"]
        aid = attempt_id(unit.run_id, len(prior) + 1)
        _append_event(ledger, "ATTEMPT_RESERVED", attempt_id_value=aid, run_id=unit.run_id)
        started = datetime.now(timezone.utc).isoformat()
        try:
            context.current_attempt_id = aid
            context.current_run_id = unit.run_id
            result = registry.resolve(unit).execute(unit, context)
            if not isinstance(result, ScientificExecutionResult):
                result = ScientificExecutionResult.from_native(result)
            payload = {"attempt_id": aid, "run_id": unit.run_id, "started_at": started, **result.to_dict()}
            path, digest = write_raw_once(raw_root, aid, payload)
            _append_event(ledger, "RAW_COMMITTED", attempt_id_value=aid, run_id=unit.run_id,
                          raw_path=str(path), raw_sha256=digest)
            _append_event(ledger, "COMPLETE", attempt_id_value=aid, run_id=unit.run_id)
            results.append(result)
        except Exception:
            _append_event(ledger, "INFRASTRUCTURE_FAILED", attempt_id_value=aid, run_id=unit.run_id)
            raise
        finally:
            context.current_attempt_id = None
            context.current_run_id = None
    return results
