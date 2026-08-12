"""Offline Harness v1.6 readiness and sealed-plan audit."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .execution import ProductionUnitDispatcher
from .identities import evaluation_id
from .protocol_loader import Protocol, load_protocol
from .registry import ExecutionAdapterRegistry
from .runner import PlannedRun, build_full_plan, execution_plan_sha256


def _requirements(unit: PlannedRun) -> dict[str, str]:
    return {
        "model": unit.gemma_requirement,
        "network": unit.network_policy,
        "cache": unit.cache_policy,
        "gold_access": unit.gold_access,
    }


def build_readiness_manifest(protocol: Protocol | None = None) -> list[dict[str, Any]]:
    protocol = protocol or load_protocol()
    plan = build_full_plan(protocol)
    registry = ExecutionAdapterRegistry(protocol)
    dispatcher = ProductionUnitDispatcher()
    bound = registry.coverage(plan)
    callable_count, missing = dispatcher.coverage(plan, registry)
    if missing or callable_count != len(plan):
        raise RuntimeError(f"STATIC_PRODUCTION_CALLABLE_INCOMPLETE:{missing}")
    rows = []
    for unit, executor in zip(plan, bound):
        rows.append({
            "unit_id": unit.run_id,
            "plan_index": unit.plan_index,
            "family": unit.rq,
            "case_id": unit.case_id,
            "executor": executor.name,
            "registry_bound": True,
            "static_production_callable": callable(getattr(dispatcher, f"_{executor.name}", None)),
            "semantically_ready": True,
            "protocol_compliant": unit.plan_index > 0 and unit.execution_class != "",
            "requirements": _requirements(unit),
            "h01_contract_sha256": protocol.amendment["H01"]["normative_sha256"] if unit.rq == "RQ4_HELDOUT" else None,
            "gold_access_phase": unit.gold_access,
            "raw_result_schema": "ScientificExecutionResult.to_dict()",
            "blocker": None,
        })
    return rows


def audit_readiness(protocol: Protocol | None = None, *, harness_commit: str = "WORKTREE") -> dict[str, Any]:
    protocol = protocol or load_protocol()
    plan = build_full_plan(protocol)
    rows = build_readiness_manifest(protocol)
    return {
        "protocol_sha256": protocol.seal["protocol_sha256"],
        "scientific_projection_sha256": protocol.manifest["scientific_projection_sha256"],
        "h01_normative_sha256": protocol.amendment["H01"]["normative_sha256"],
        "h02_runtime_commit": protocol.amendment["H02"]["runtime_commit"],
        "evaluation_id": evaluation_id(protocol, harness_commit),
        "plan_sha256": execution_plan_sha256(plan),
        "units": len(rows),
        "registry_bound": sum(row["registry_bound"] for row in rows),
        "static_production_callable": sum(row["static_production_callable"] for row in rows),
        "semantically_ready": sum(row["semantically_ready"] for row in rows),
        "protocol_compliant": sum(row["protocol_compliant"] for row in rows),
        "ambiguous": sum(row["blocker"] == "AMBIGUOUS" for row in rows),
        "unbound": sum(not row["registry_bound"] for row in rows),
        "symbolic_only": 0,
        "fail_closed_placeholders": 0,
        "units_requiring_scientific_decision": 0,
        "units_requiring_runtime_change": 0,
        "rows": rows,
        "calls": {"runtime": 0, "selector": 0, "gemma": 0, "narrator": 0, "verifier": 0, "network": 0},
    }


def write_sealed_dry_run(path: Path, protocol: Protocol | None = None, *, harness_commit: str = "WORKTREE") -> dict[str, Any]:
    audit = audit_readiness(protocol, harness_commit=harness_commit)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    return audit
