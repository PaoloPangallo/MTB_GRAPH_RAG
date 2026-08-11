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
