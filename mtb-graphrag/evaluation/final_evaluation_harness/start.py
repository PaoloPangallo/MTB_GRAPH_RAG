"""Explicit, append-only Final Evaluation campaign start workflow.

The CLI remains disarmed unless all non-interactive confirmations are supplied.
The test-only fake campaign below exercises lifecycle ordering without providers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .common.arming import ExecutionDisarmed, ExecutionGate
from .common.identities import evaluation_id
from .common.lifecycle import CampaignLedger, CampaignResult, CampaignState, LifecycleError
from .common.model_identity import GenerationIdentityError, validate_execution_environment, validate_prompt_hashes
from .common.protocol_loader import load_protocol
from .common.provider_snapshot import collect_snapshot, compare_snapshots, validate_metadata
from .common.registry import ExecutionAdapterRegistry, binding_manifest, binding_manifest_sha256
from .common.runner import build_full_plan, execution_plan_sha256, planned_runs_from_serialized
from .common.execution import RealExecutionContext, ProductionUnitDispatcher
from .common.production_loop import execute_sealed_plan
from .common.guards import ModelGuard, NetworkGuard, RuntimeGuard


class CampaignStartError(RuntimeError):
    pass


class RealExecutionNotEnabled(CampaignStartError):
    """Retained for compatibility; valid START no longer raises this guard."""
    pass


def run_production_dispatch(plan, protocol, campaign_root, *, ledger=None, raw_writer=None,
                            network_guard=None, model_guard=None, runtime_guard=None, campaign_open=False):
    """Dispatch a sealed plan through the real context after campaign opening.

    ``main`` remains disarmed in this implementation phase; this function is
    the single production dispatch seam used by the future START workflow.
    """
    if not campaign_open:
        raise CampaignStartError("CAMPAIGN_NOT_OPEN")
    dispatcher = ProductionUnitDispatcher()
    registry = ExecutionAdapterRegistry(protocol)
    covered, missing = dispatcher.coverage(plan, registry)
    if missing:
        raise CampaignStartError(f"REAL_EXECUTION_ADAPTER_NOT_BOUND:{','.join(sorted(set(missing)))}")
    runtime_guard = runtime_guard or RuntimeGuard()
    model_guard = model_guard or ModelGuard()
    network_guard = network_guard or NetworkGuard("CANONICAL_RUNTIME_POLICY")
    context = RealExecutionContext.from_production(
        protocol, ledger=ledger, raw_writer=raw_writer,
        network_guard=network_guard, model_guard=model_guard, runtime_guard=runtime_guard,
        production_dispatcher=dispatcher,
    )
    return execute_sealed_plan(plan, context, registry, campaign_root, campaign_open=True)


EXPECTED_MODEL = {
    "model_alias": "gemma4:31b-cloud",
    "family": "gemma4",
    "parameter_size": "32682372656",
    "quantization": "BF16",
    "context_length": 262144,
}


def validate_start_confirmation(argv: list[str], expected_evaluation_id: str, expected_plan_sha: str) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--arm", action="store_true")
    parser.add_argument("--confirm-evaluation-id")
    parser.add_argument("--confirm-plan-sha")
    parser.add_argument("--confirm-start")
    try:
        args, unknown = parser.parse_known_args(argv)
    except SystemExit as exc:
        raise ExecutionDisarmed("invalid arming arguments") from exc
    if unknown or not args.arm or not args.confirm_evaluation_id or not args.confirm_plan_sha or not args.confirm_start:
        raise ExecutionDisarmed("all explicit confirmations are required")
    if args.confirm_evaluation_id != expected_evaluation_id or args.confirm_plan_sha != expected_plan_sha or args.confirm_start != "FINAL_EVALUATION_1_6":
        raise CampaignStartError("START_CONFIRMATION_MISMATCH")


def materialize_execution_plan() -> tuple[list[dict], str]:
    protocol = load_protocol()
    plans = build_full_plan(protocol)
    return [plan.__dict__ for plan in plans], execution_plan_sha256(plans)


def validate_executor_coverage() -> tuple[int, str]:
    protocol = load_protocol()
    plans = build_full_plan(protocol)
    registry = ExecutionAdapterRegistry(protocol)
    bindings = registry.coverage(plans)
    if len(bindings) != len(plans):
        raise CampaignStartError("REAL_EXECUTION_ADAPTER_NOT_BOUND")
    return len(bindings), binding_manifest_sha256(plans, registry)


def validate_source_head(repo: Path, expected_head: str) -> None:
    actual = _git_head(repo)
    if actual != expected_head:
        raise CampaignStartError("EXECUTION_SOURCE_HEAD_MISMATCH")
    import subprocess
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    if dirty:
        raise CampaignStartError("EXECUTION_SOURCE_DIRTY")


def run_official_start(*, protocol, source_root: Path, expected_head: str, plans: list[dict],
                       plan_sha: str, expected_evaluation_id: str, argv: list[str],
                       campaign_root: Path, metadata_request, dispatch,
                       environment_validator=validate_execution_environment,
                       prompt_validator=validate_prompt_hashes,
                       head_validator=validate_source_head) -> str:
    """Run the official lifecycle wiring with an injectable boundary for tests.

    All identity and environment gates execute before any campaign filesystem
    state is created. ``dispatch`` is the existing sealed-plan coordinator;
    this function deliberately contains no family-specific execution logic.
    """
    head_validator(source_root, expected_head)
    validate_start_confirmation(argv, expected_evaluation_id, plan_sha)
    environment_validator()
    prompt_validator()
    typed_plans = planned_runs_from_serialized(plans)
    if campaign_root.exists():
        raise CampaignStartError("CAMPAIGN_STORAGE_COLLISION")
    campaign_root.parent.mkdir(parents=True, exist_ok=True)
    staging = campaign_root.parent / ".final_evaluation.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    _write_json(staging / "execution_plan.json", plans)
    pre = collect_snapshot(metadata_request, "gemma4:31b-cloud")
    validate_metadata(pre, EXPECTED_MODEL)
    _write_json(staging / "manifest.json", {
        "evaluation_id": expected_evaluation_id,
        "plan_sha256": plan_sha,
        "harness_commit": expected_head,
        "planned_units": len(plans),
        "pre_snapshot": pre,
    })
    (staging / "ledger.jsonl").write_text("", encoding="utf-8")
    staging.replace(campaign_root)
    ledger = CampaignLedger(campaign_root / "ledger.jsonl")
    for event in ("PREFLIGHT_VALIDATED", "PLAN_SEALED", "PRE_PROVIDER_SNAPSHOT_VALIDATED", "CAMPAIGN_OPEN"):
        ledger.append(event)
    dispatch(typed_plans, protocol, campaign_root, ledger=ledger, campaign_open=True)
    ledger.append("SCIENTIFIC_RUNS_COMPLETE")
    post = collect_snapshot(metadata_request, "gemma4:31b-cloud")
    _write_json(campaign_root / "post_snapshot.json", post)
    drift = compare_snapshots(pre, post)
    if drift:
        ledger.append("PROVIDER_MODEL_METADATA_DRIFT", fields=drift)
        raise CampaignStartError("PROVIDER_MODEL_METADATA_DRIFT")
    ledger.append("POST_PROVIDER_SNAPSHOT_COMPLETE")
    ledger.append("PROMOTION_PENDING")
    ledger.append("PROMOTED")
    return "DISPATCHED"


def _write_json(path: Path, value: dict | list) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def _append_campaign_event(ledger: CampaignLedger, event: str, events: list[str], **kwargs) -> None:
    ledger.append(event, **kwargs)
    events.append(event)


def run_fake_campaign(root: Path, plan: list[dict], metadata_request, execute_run, *, resume: bool = False) -> CampaignResult:
    """Structural lifecycle test executor; never calls a real runtime/provider."""
    campaign = root / "evaluation" / "final_evaluation"
    expected_plan_sha = hashlib.sha256(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    events: list[str] = []
    if resume:
        if not campaign.is_dir():
            raise CampaignStartError("RESUME_CAMPAIGN_MISSING")
        manifest = json.loads((campaign / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("plan_sha256") != expected_plan_sha:
            raise CampaignStartError("PLAN_IDENTITY_MISMATCH")
        ledger = CampaignLedger(campaign / "ledger.jsonl")
        ledger.reconcile()
        prior = ledger.events()
        completed = {event.get("run_id") for event in prior if event.get("event") == "COMPLETE"}
        events.extend(event["event"] for event in prior if event["event"] in {"PREFLIGHT_VALIDATED", "PLAN_SEALED", "PRE_PROVIDER_SNAPSHOT_VALIDATED", "CAMPAIGN_OPEN"})
        pre = manifest["pre_snapshot"]
    else:
        staging = root / "evaluation" / ".final_evaluation.staging"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        # The plan is sealed before the provider call, but remains outside the
        # scientific campaign boundary until the PRE snapshot passes.
        _write_json(staging / "execution_plan.json", plan)
        raw_pre = collect_snapshot(metadata_request, "gemma4:31b-cloud")
        try:
            validate_metadata(raw_pre, EXPECTED_MODEL)
        except Exception as exc:
            shutil.rmtree(staging)
            raise CampaignStartError("PROVIDER_MODEL_METADATA_MISMATCH") from exc
        pre = raw_pre
        _write_json(staging / "manifest.json", {"plan_sha256": expected_plan_sha, "planned_units": len(plan), "pre_snapshot": pre})
        (staging / "ledger.jsonl").write_text("", encoding="utf-8")
        campaign.parent.mkdir(parents=True, exist_ok=True)
        staging.replace(campaign)
        ledger = CampaignLedger(campaign / "ledger.jsonl")
        for event in ("PREFLIGHT_VALIDATED", "PLAN_SEALED", "PRE_PROVIDER_SNAPSHOT_VALIDATED", "CAMPAIGN_OPEN"):
            _append_campaign_event(ledger, event, events)
        completed = set()

    for unit in plan:
        if unit["run_id"] in completed:
            continue
        attempt_id = f"{unit['run_id']}/a0001"
        prior_attempts = [event for event in ledger.events() if event.get("run_id") == unit["run_id"] and event.get("event") == "ATTEMPT_RESERVED"]
        ordinal = len(prior_attempts) + 1
        attempt_id = f"{unit['run_id']}/a{ordinal:04d}"
        ledger.append("ATTEMPT_RESERVED", attempt_id=attempt_id, run_id=unit["run_id"])
        execute_run(unit)
        ledger.append("COMPLETE", attempt_id=attempt_id, run_id=unit["run_id"])
        completed.add(unit["run_id"])
    ledger.append("SCIENTIFIC_RUNS_COMPLETE")
    events.append("SCIENTIFIC_RUNS_COMPLETE")
    raw_post = collect_snapshot(metadata_request, "gemma4:31b-cloud")
    _write_json(campaign / "post_snapshot.json", raw_post)
    if compare_snapshots(pre, raw_post):
        ledger.append("PROVIDER_MODEL_METADATA_DRIFT")
        events.append("PROVIDER_MODEL_METADATA_DRIFT")
        return CampaignResult(CampaignState.PROVIDER_MODEL_METADATA_DRIFT, events, ledger.events())
    for event in ("POST_PROVIDER_SNAPSHOT_COMPLETE", "PROMOTION_PENDING", "PROMOTED"):
        ledger.append(event)
        events.append(event)
    return CampaignResult(CampaignState.PROMOTED, events, ledger.events())


def main(argv: list[str] | None = None) -> None:
    argv = list(argv if argv is not None else os.sys.argv[1:])
    protocol = load_protocol()
    source_root = protocol.root.parents[1]
    expected_head = _git_head(source_root)
    plans, plan_sha = materialize_execution_plan()
    validate_executor_coverage()
    eid = evaluation_id(protocol, expected_head)
    validate_start_confirmation(argv, eid, plan_sha)
    validate_source_head(source_root, expected_head)
    try:
        validate_execution_environment()
        validate_prompt_hashes()
    except GenerationIdentityError as exc:
        raise CampaignStartError(str(exc)) from exc
    gate = ExecutionGate()
    gate.arm()
    campaign_root = source_root / "evaluation" / "final_evaluation"
    run_official_start(
        protocol=protocol,
        source_root=source_root,
        expected_head=expected_head,
        plans=plans,
        plan_sha=plan_sha,
        expected_evaluation_id=eid,
        argv=argv,
        campaign_root=campaign_root,
        metadata_request=lambda model: _provider_metadata_request(model),
        dispatch=run_production_dispatch,
    )


def _provider_metadata_request(model: str) -> dict:
    """Use the canonical Ollama metadata client at the authorized START gate."""
    from backend.pipeline.llm.ollama_adapter import OllamaClient, configured_endpoint

    return OllamaClient(configured_endpoint()).show(model)


def _git_head(repo: Path) -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


if __name__ == "__main__":
    main()
