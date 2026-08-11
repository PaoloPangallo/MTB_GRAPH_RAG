"""Plans isolated operational caches without mutating the frozen baseline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CachePlan:
    scenario_id: str
    baseline: str
    target: str | None
    isolated: bool = True
    read_only_baseline: bool = True


def create_operational_cache(protocol: Any, scenario_id: str, *, execute: bool = False, root: Path | None = None) -> CachePlan:
    bindings = __import__("json").loads((protocol.a01_root / "operational_scenario_bindings.json").read_text(encoding="utf-8"))
    scenarios = {item["scenario_id"]: item for item in bindings["scenarios"]}
    if scenario_id not in scenarios:
        raise ValueError(f"unknown A01 scenario: {scenario_id}")
    plan = CachePlan(scenario_id, "AUTHORIZED_DOCUMENT_CACHE_43", scenarios[scenario_id].get("selected_document_id"))
    if execute:
        if root is None:
            raise ValueError("execution cache root is required")
        target = root / f"operational_cache_{scenario_id}"
        target.mkdir(parents=True, exist_ok=False)
    return plan
