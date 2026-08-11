"""A01 executor plan; scenario semantics are read directly from A01."""

from __future__ import annotations

from typing import Any

from .cache_factory import create_operational_cache
from .protocol_loader import load_a01_bindings


def plan_operational_scenario(protocol: Any, scenario_id: str) -> dict[str, Any]:
    bindings = load_a01_bindings(protocol)
    scenario = next((item for item in bindings["scenarios"] if item["scenario_id"] == scenario_id), None)
    if scenario is None:
        raise ValueError(scenario_id)
    cache = create_operational_cache(protocol, scenario_id)
    return {"scenario_id": scenario_id, "binding": scenario, "cache_plan": cache.__dict__, "execution": "DISARMED"}
