"""Fail-closed mapping from frozen planned units to existing adapters."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .runner import PlannedRun


class AdapterBindingError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundExecutor:
    name: str
    execution_class: str
    adapter_names: tuple[str, ...]

    def execute(self, planned_unit: PlannedRun, context: Any) -> Any:
        dispatch = getattr(context, "execute", None)
        if not callable(dispatch):
            raise AdapterBindingError("execution context does not provide dispatch")
        return dispatch(planned_unit, self)


_BINDINGS = {
    "DETERMINISTIC_ONLY": ("RQ1DeterministicExecutor", ()),
    "SELECTOR_ONLY": ("RQ2SelectorExecutor", ("selector",)),
    "SELECTOR_PLUS_GEMMA": ("RQ2GemmaExecutor", ("selector", "gemma", "quote_validator")),
    "CANONICAL_RUNTIME": ("RQ3CanonicalExecutor", ("canonical_runtime",)),
    "NARRATOR_PIPELINE": ("NarrativeExecutor", ("narrator", "narrative_verifier")),
    "OPERATIONAL_RUNTIME_NETWORK_ALLOWED": ("OperationalExecutor", ("canonical_runtime", "document_resolver")),
    "CONTROLLED_FAILURE_FIXTURE": ("ControlledFailureExecutor", ("canonical_runtime",)),
    "LATENCY_PAIR": ("LatencyExecutor", ("canonical_runtime", "document_resolver")),
}


class ExecutionAdapterRegistry:
    def __init__(self, protocol: Any):
        self.protocol = protocol

    def resolve(self, planned_unit: PlannedRun) -> BoundExecutor:
        key = planned_unit.execution_class
        if planned_unit.rq == "RQ3" and key == "CANONICAL_RUNTIME":
            names = {"CANONICAL": "RQ3FullSystemExecutor", "A": "RQ3AblationAExecutor", "B": "RQ3AblationBExecutor", "C": "RQ3AblationCExecutor", "D": "RQ3AblationDExecutor"}
            name = names.get(planned_unit.arm)
            if name is None:
                raise AdapterBindingError("REAL_EXECUTION_ADAPTER_NOT_BOUND")
            return BoundExecutor(name, key, ("canonical_runtime", "ablation_wiring"))
        if planned_unit.rq.startswith("RQ4") and key == "CANONICAL_RUNTIME":
            name = "RQ4HeldoutExecutor" if planned_unit.testbed == "HELDOUT_ARCHITECTURAL_35" else "RQ4DevelopmentExecutor"
            return BoundExecutor(name, key, ("canonical_runtime",))
        try:
            name, adapters = _BINDINGS[key]
        except KeyError as exc:
            raise AdapterBindingError("REAL_EXECUTION_ADAPTER_NOT_BOUND") from exc
        if not name or not isinstance(adapters, tuple):
            raise AdapterBindingError("AMBIGUOUS_EXECUTION_ADAPTER_BINDING")
        return BoundExecutor(name, key, adapters)

    def coverage(self, plan: list[PlannedRun]) -> list[BoundExecutor]:
        return [self.resolve(unit) for unit in plan]


def binding_manifest(plan: list[PlannedRun], registry: ExecutionAdapterRegistry) -> list[dict[str, Any]]:
    return [{"plan_index": unit.plan_index, "testbed": unit.testbed, "arm": unit.arm,
             "execution_class": unit.execution_class, "executor_name": registry.resolve(unit).name}
            for unit in plan]


def binding_manifest_sha256(plan: list[PlannedRun], registry: ExecutionAdapterRegistry) -> str:
    payload = json.dumps(binding_manifest(plan, registry), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
