"""A01 executor plan; scenario semantics are read directly from A01."""

from __future__ import annotations

from typing import Any

from .cache_factory import create_operational_cache
from .operational_runner import CanonicalOperationalRunner
from .protocol_loader import load_a01_bindings


def plan_operational_scenario(protocol: Any, scenario_id: str) -> dict[str, Any]:
    bindings = load_a01_bindings(protocol)
    scenario = next((item for item in bindings["scenarios"] if item["scenario_id"] == scenario_id), None)
    if scenario is None:
        raise ValueError(scenario_id)
    cache = create_operational_cache(protocol, scenario_id)
    return {"scenario_id": scenario_id, "binding": scenario, "cache_plan": cache.__dict__, "execution": "DISARMED"}


def execute_operational_scenario(protocol: Any, scenario_id: str, context: Any) -> dict[str, Any]:
    """Execute one A01 property at its canonical component boundary.

    Operational units are document/parser/selector conformance checks. They
    do not enter the clinical EvidenceRetrievalPipeline and never construct a
    synthetic query or CaseContext.
    """
    root = protocol.root.parents[1]
    runner = CanonicalOperationalRunner(protocol, root / "research_frozen_artifacts" / "operational_v2")
    result = runner.run(scenario_id)
    return {
        "scenario_id": result.scenario_id,
        "unit_id": result.unit_id,
        "initial_state": result.initial_state,
        "component_path": result.component_path,
        "observables": result.observables,
        "runtime_terminal_state": result.runtime_terminal_state,
        "expected_observable": result.expected_observable,
        "actual_observable": result.actual_observable,
        "controlled_outcome": result.controlled_outcome,
        "property_test_pass": result.property_test_pass,
        "artifact_provenance": result.artifact_provenance,
        "synthetic_query_count": result.synthetic_query_count,
        "infrastructure_status": result.infrastructure_status,
    }
