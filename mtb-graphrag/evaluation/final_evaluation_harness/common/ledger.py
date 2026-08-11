"""Append-only JSONL lifecycle ledger."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LedgerError(RuntimeError):
    """Invalid append-only lifecycle operation."""


class AppendOnlyLedger:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, event: dict[str, Any]) -> None:
        if not event.get("event") or not event.get("attempt_id"):
            raise LedgerError("event and attempt_id are required")
        existing = self.events()
        attempt = event["attempt_id"]
        prior = [item["event"] for item in existing if item.get("attempt_id") == attempt]
        allowed = {
            "ATTEMPT_RESERVED": {None},
            "RAW_COMMITTED": {"ATTEMPT_RESERVED"},
            "COMPLETE": {"ATTEMPT_RESERVED", "RAW_COMMITTED"},
            "INFRASTRUCTURE_FAILED": {"ATTEMPT_RESERVED", "RAW_COMMITTED"},
            "INCOMPLETE": {"ATTEMPT_RESERVED", "RAW_COMMITTED"},
        }
        event_name = event["event"]
        if event_name not in allowed or (prior and prior[-1] not in allowed[event_name]) or (not prior and event_name != "ATTEMPT_RESERVED"):
            raise LedgerError(f"invalid lifecycle transition: {prior} -> {event_name}")
        if event["event"] == "ATTEMPT_RESERVED" and any(item.get("attempt_id") == attempt for item in existing):
            raise LedgerError(f"duplicate attempt reservation: {attempt}")
        terminal = {"COMPLETE", "INFRASTRUCTURE_FAILED", "INCOMPLETE"}
        if event["event"] in terminal and any(item.get("attempt_id") == attempt and item.get("event") in terminal for item in existing):
            raise LedgerError(f"duplicate terminal event: {attempt}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def reconcile(self) -> list[str]:
        events = self.events()
        terminal = {e["attempt_id"] for e in events if e.get("event") in {"RAW_COMMITTED", "COMPLETE", "INFRASTRUCTURE_FAILED", "INCOMPLETE"}}
        orphans = sorted({e["attempt_id"] for e in events if e.get("event") == "ATTEMPT_RESERVED"} - terminal)
        for attempt in orphans:
            self.append({"event": "INCOMPLETE", "attempt_id": attempt, "reason": "ORPHAN_ATTEMPT_RESERVED"})
        return orphans
