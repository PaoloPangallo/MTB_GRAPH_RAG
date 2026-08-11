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
    implementation: type["BoundExecutor"] | None = None

    def execute(self, planned_unit: PlannedRun, context: Any) -> Any:
        for adapter_name in self.adapter_names:
            if not hasattr(context, adapter_name):
                raise AdapterBindingError(f"missing execution adapter: {adapter_name}")
        dispatch = getattr(context, "execute", None)
        if not callable(dispatch):
            raise AdapterBindingError("execution context does not provide dispatch")
        return dispatch(planned_unit, self)


class RQ1DeterministicExecutor(BoundExecutor): pass
class RQ2SelectorExecutor(BoundExecutor): pass
class RQ2GemmaExecutor(BoundExecutor): pass
class RQ3FullSystemExecutor(BoundExecutor): pass
class RQ3AblationAExecutor(BoundExecutor): pass
class RQ3AblationBExecutor(BoundExecutor): pass
class RQ3AblationCExecutor(BoundExecutor): pass
class RQ3AblationDExecutor(BoundExecutor): pass
class RQ4DevelopmentExecutor(BoundExecutor): pass
class RQ4HeldoutExecutor(BoundExecutor): pass
class NarrativeExecutor(BoundExecutor): pass
class NarrativeHostileExecutor(BoundExecutor): pass
class NarrativeControlExecutor(BoundExecutor): pass
class OperationalExecutor(BoundExecutor): pass
class ControlledFailureExecutor(BoundExecutor): pass
class LatencyExecutor(BoundExecutor): pass
class ReliabilityStratumAExecutor(BoundExecutor): pass
class ReliabilityStratumBExecutor(BoundExecutor): pass

_EXECUTOR_TYPES = {cls.__name__: cls for cls in (
    RQ1DeterministicExecutor, RQ2SelectorExecutor, RQ2GemmaExecutor,
    RQ3FullSystemExecutor, RQ3AblationAExecutor, RQ3AblationBExecutor,
    RQ3AblationCExecutor, RQ3AblationDExecutor, RQ4DevelopmentExecutor,
    RQ4HeldoutExecutor, NarrativeExecutor, OperationalExecutor,
    ControlledFailureExecutor, LatencyExecutor,
    ReliabilityStratumAExecutor, ReliabilityStratumBExecutor,
    NarrativeHostileExecutor, NarrativeControlExecutor,
)}

_BINDINGS = {
    "DETERMINISTIC_ONLY": ("RQ1DeterministicExecutor", ()),
    "SELECTOR_ONLY": ("RQ2SelectorExecutor", ("selector",)),
    "SELECTOR_PLUS_GEMMA": ("RQ2GemmaExecutor", ("selector", "gemma", "quote_validator")),
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
            adapters = {
                "CANONICAL": ("canonical_runtime",),
                "A": ("canonical_runtime",),
                "B": ("canonical_runtime", "selector"),
                "C": ("canonical_runtime", "quote_validator"),
                "D": ("canonical_runtime", "narrative_verifier"),
            }[planned_unit.arm]
            return self._validate_requirements(planned_unit, _make(name, key, adapters))
        if planned_unit.rq.startswith("RQ4") and key == "CANONICAL_RUNTIME":
            name = "RQ4HeldoutExecutor" if planned_unit.testbed == "HELDOUT_ARCHITECTURAL_35" else "RQ4DevelopmentExecutor"
            return self._validate_requirements(planned_unit, _make(name, key, ("canonical_runtime", "casecontext_parser")))
        if planned_unit.rq == "RELIABILITY" and planned_unit.testbed == "RELIABILITY_STRATUM_A":
            return self._validate_requirements(planned_unit, _make("ReliabilityStratumAExecutor", key, ("canonical_runtime",)))
        if planned_unit.rq == "RELIABILITY" and planned_unit.testbed == "RELIABILITY_STRATUM_B":
            return self._validate_requirements(planned_unit, _make("ReliabilityStratumBExecutor", key, ("selector", "gemma", "quote_validator")))
        if planned_unit.rq == "NARRATIVE":
            if key == "NARRATIVE_HOSTILE_VERIFIER":
                return self._validate_requirements(planned_unit, _make("NarrativeHostileExecutor", key, ("narrative_verifier",)))
            if key == "NARRATIVE_CONTROL":
                return self._validate_requirements(planned_unit, _make("NarrativeControlExecutor", key, ("narrator", "narrative_verifier")))
            raise AdapterBindingError("REAL_EXECUTION_ADAPTER_NOT_BOUND")
        try:
            name, adapters = _BINDINGS[key]
        except KeyError as exc:
            raise AdapterBindingError("REAL_EXECUTION_ADAPTER_NOT_BOUND") from exc
        if not name or not isinstance(adapters, tuple):
            raise AdapterBindingError("AMBIGUOUS_EXECUTION_ADAPTER_BINDING")
        return self._validate_requirements(planned_unit, _make(name, key, adapters))

    @staticmethod
    def _validate_requirements(planned_unit: PlannedRun, bound: BoundExecutor) -> BoundExecutor:
        required = {
            "canonical_runtime_requirement": "canonical_runtime",
            "selector_requirement": "selector",
            "casecontext_parser_requirement": "casecontext_parser",
            "gemma_requirement": "gemma",
            "narrator_requirement": "narrator",
            "quote_validator_requirement": "quote_validator",
            "narrative_verifier_requirement": "narrative_verifier",
        }
        missing = [adapter for field, adapter in required.items()
                   if getattr(planned_unit, field) == "REQUIRED" and adapter not in bound.adapter_names]
        if missing:
            raise AdapterBindingError(f"REAL_EXECUTION_ADAPTER_NOT_BOUND: {','.join(missing)}")
        return bound

    def coverage(self, plan: list[PlannedRun]) -> list[BoundExecutor]:
        return [self.resolve(unit) for unit in plan]


def binding_manifest(plan: list[PlannedRun], registry: ExecutionAdapterRegistry) -> list[dict[str, Any]]:
    return [{"plan_index": unit.plan_index, "testbed": unit.testbed, "arm": unit.arm,
             "execution_class": unit.execution_class, "executor_name": registry.resolve(unit).name}
            for unit in plan]


def binding_manifest_sha256(plan: list[PlannedRun], registry: ExecutionAdapterRegistry) -> str:
    payload = json.dumps(binding_manifest(plan, registry), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _make(name: str, execution_class: str, adapter_names: tuple[str, ...]) -> BoundExecutor:
    try:
        cls = _EXECUTOR_TYPES[name]
    except KeyError as exc:
        raise AdapterBindingError("REAL_EXECUTION_ADAPTER_NOT_BOUND") from exc
    return cls(name, execution_class, adapter_names, cls)
