"""Append-only campaign state and attempt reconciliation primitives."""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class LifecycleError(RuntimeError):
    pass


class CampaignState(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PREFLIGHT_VALIDATED = "PREFLIGHT_VALIDATED"
    PLAN_SEALED = "PLAN_SEALED"
    PRE_PROVIDER_SNAPSHOT_VALIDATED = "PRE_PROVIDER_SNAPSHOT_VALIDATED"
    CAMPAIGN_OPEN = "CAMPAIGN_OPEN"
    RUNNING = "RUNNING"
    SCIENTIFIC_RUNS_COMPLETE = "SCIENTIFIC_RUNS_COMPLETE"
    POST_PROVIDER_SNAPSHOT_COMPLETE = "POST_PROVIDER_SNAPSHOT_COMPLETE"
    PROMOTION_PENDING = "PROMOTION_PENDING"
    PROMOTED = "PROMOTED"
    PROVIDER_MODEL_METADATA_DRIFT = "PROVIDER_MODEL_METADATA_DRIFT"
    FAILED_PRE_START = "FAILED_PRE_START"
    INTERRUPTED = "INTERRUPTED"


class CampaignLedger:
    """Single append-only ledger for campaign and attempt events."""
    TERMINAL_ATTEMPTS = {"COMPLETE", "INFRASTRUCTURE_FAILED", "INCOMPLETE"}

    def __init__(self, path: Path):
        self.path = path

    def events(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def append(self, event: str, *, attempt_id: str | None = None, run_id: str | None = None, **extra) -> None:
        existing = self.events()
        if event == "ATTEMPT_RESERVED" and attempt_id and any(x.get("attempt_id") == attempt_id for x in existing):
            raise LifecycleError(f"duplicate attempt reservation: {attempt_id}")
        if event in self.TERMINAL_ATTEMPTS and attempt_id and any(x.get("attempt_id") == attempt_id and x.get("event") in self.TERMINAL_ATTEMPTS for x in existing):
            raise LifecycleError(f"duplicate terminal attempt: {attempt_id}")
        payload = {"event": event, **extra}
        if attempt_id is not None:
            payload["attempt_id"] = attempt_id
        if run_id is not None:
            payload["run_id"] = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def reconcile(self) -> list[str]:
        events = self.events()
        terminals = {x.get("attempt_id") for x in events if x.get("event") in self.TERMINAL_ATTEMPTS}
        orphans = sorted({x.get("attempt_id") for x in events if x.get("event") == "ATTEMPT_RESERVED"} - terminals)
        for attempt_id in orphans:
            self.append("INCOMPLETE", attempt_id=attempt_id, reason="ORPHAN_ATTEMPT_RESERVED")
        return orphans


@dataclass(frozen=True)
class CampaignResult:
    state: CampaignState
    events: list[str]
    ledger_events: list[dict]
