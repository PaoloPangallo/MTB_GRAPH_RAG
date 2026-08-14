"""Dry-run planning shared by all frozen testbed entry points."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass
from typing import Any

from .cache_factory import create_operational_cache
from .identities import evaluation_id, run_id
from .protocol_loader import Protocol, load_a01_bindings, load_protocol, load_s01_rows, validate_dataset_registry


@dataclass(frozen=True)
class PlannedRun:
    testbed: str
    rq: str
    case_id: str
    arm: str
    repetition_id: str
    run_id: str
    plan_index: int = 0
    execution_class: str = ""
    canonical_runtime_requirement: str = ""
    selector_requirement: str = ""
    casecontext_parser_requirement: str = ""
    gemma_requirement: str = ""
    narrator_requirement: str = ""
    quote_validator_requirement: str = ""
    narrative_verifier_requirement: str = ""
    network_policy: str = ""
    network_expectation: str = ""
    cache_policy: str = ""
    dataset_hashes: dict[str, str] | None = None
    gold_access: str = ""
    terminal_expectation: str = ""


def planned_run_from_serialized(record: dict[str, Any]) -> PlannedRun:
    """Fail-closed canonical JSON/dict → PlannedRun boundary."""
    if not isinstance(record, dict):
        raise ValueError("sealed plan unit must be an object")
    required = {field.name for field in __import__("dataclasses").fields(PlannedRun)}
    missing = sorted(required - record.keys())
    unknown = sorted(set(record) - required)
    if missing or unknown:
        raise ValueError(f"invalid sealed plan unit fields: missing={missing}, unknown={unknown}")
    if not isinstance(record["plan_index"], int) or isinstance(record["plan_index"], bool) or record["plan_index"] < 1:
        raise ValueError("sealed plan plan_index must be a positive integer")
    for field in required - {"plan_index", "dataset_hashes"}:
        if not isinstance(record[field], str) or not record[field]:
            raise ValueError(f"sealed plan field {field} must be a non-empty string")
    if not isinstance(record["dataset_hashes"], dict) or not record["dataset_hashes"]:
        raise ValueError("sealed plan dataset_hashes must be a non-empty object")
    return PlannedRun(**record)


def planned_runs_from_serialized(records: list[dict[str, Any]]) -> list[PlannedRun]:
    if not isinstance(records, list):
        raise ValueError("sealed plan must be an array")
    result = [planned_run_from_serialized(record) for record in records]
    ids = [unit.run_id for unit in result]
    if len(set(ids)) != len(ids):
        raise ValueError("sealed plan contains duplicate run_id values")
    indices = [unit.plan_index for unit in result]
    if indices != list(range(1, len(result) + 1)):
        raise ValueError("sealed plan plan_index ordering is not contiguous")
    return result


def _metadata(kind: str, testbed: str, arm: str, protocol: Protocol) -> dict[str, Any]:
    rq = kind.upper()
    is_rq2 = kind == "rq2"
    is_rq4 = kind == "rq4"
    is_reliability = kind == "reliability"
    is_operational = kind == "operational"
    is_narrative = kind == "narrative"
    is_latency = kind == "latency"
    if kind == "rq1": execution_class = "DETERMINISTIC_ONLY"
    elif is_rq2: execution_class = "SELECTOR_PLUS_GEMMA" if arm in ("GOLD", "DETERMINISTIC_SELECTOR") else "SELECTOR_ONLY"
    elif is_narrative: execution_class = "NARRATIVE_HOSTILE_VERIFIER" if testbed == "NARRATIVE_HELDOUT_20" else "NARRATIVE_CONTROL"
    elif is_latency: execution_class = "LATENCY_PAIR"
    elif is_operational and arm == "PROPERTY_TEST" and testbed.endswith(("H_parser_failure_fixture", "I_selector_failure_fixture")): execution_class = "CONTROLLED_FAILURE_FIXTURE"
    elif is_operational: execution_class = "OPERATIONAL_RUNTIME_NETWORK_ALLOWED"
    elif is_reliability and testbed == "RELIABILITY_STRATUM_B": execution_class = "SELECTOR_PLUS_GEMMA"
    else: execution_class = "CANONICAL_RUNTIME"
    parser = "REQUIRED" if is_rq4 else ("PATH_DEPENDENT" if kind in ("rq3", "reliability", "operational") else "PROHIBITED")
    selector = "REQUIRED" if (is_rq2 and arm != "GOLD") or (is_reliability and testbed == "RELIABILITY_STRATUM_B") or (kind == "rq3" and arm == "B") else "PROHIBITED"
    gemma = "REQUIRED" if (is_rq2 and arm in ("GOLD", "DETERMINISTIC_SELECTOR")) or (is_reliability and testbed == "RELIABILITY_STRATUM_B") else ("PATH_DEPENDENT" if kind in ("rq3", "rq4", "reliability", "operational") else "PROHIBITED")
    narrator = ("PROHIBITED" if testbed == "NARRATIVE_HELDOUT_20" else "REQUIRED") if is_narrative else ("PATH_DEPENDENT" if kind in ("rq3", "rq4", "reliability", "operational") else "PROHIBITED")
    quote = "REQUIRED" if (is_rq2 and arm in ("GOLD", "DETERMINISTIC_SELECTOR")) or (is_reliability and testbed == "RELIABILITY_STRATUM_B") else ("PATH_DEPENDENT" if kind in ("rq3", "rq4", "reliability", "operational") else "PROHIBITED")
    verifier = "REQUIRED" if is_narrative else ("PATH_DEPENDENT" if kind in ("rq3", "rq4", "reliability", "operational") else "PROHIBITED")
    if is_rq2 or (is_reliability and testbed == "RELIABILITY_STRATUM_B"): network_policy, network_expectation, cache = "PROHIBITED", "NONE", "NO_DOCUMENT_CACHE"
    elif is_latency and arm == "LAT-HIT": network_policy, network_expectation, cache = "CANONICAL_RUNTIME_POLICY", "EXPECTED_ZERO_FETCH", "LATENCY_HIT_CACHE"
    elif is_latency: network_policy, network_expectation, cache = "CANONICAL_RUNTIME_POLICY", "NETWORK_REQUIRED_TO_OBSERVE_PROPERTY", "LATENCY_MISS_CACHE"
    elif is_operational and arm == "PROPERTY_TEST" and testbed == "A_cache_hit": network_policy, network_expectation, cache = "CANONICAL_RUNTIME_POLICY", "EXPECTED_ZERO_FETCH", "A01_SCENARIO_CACHE"
    elif is_operational: network_policy, network_expectation, cache = "CANONICAL_RUNTIME_POLICY", "NETWORK_REQUIRED_TO_OBSERVE_PROPERTY", "A01_SCENARIO_CACHE"
    elif is_reliability and testbed == "RELIABILITY_STRATUM_A": network_policy, network_expectation, cache = "CANONICAL_RUNTIME_POLICY", "PATH_DEPENDENT", "FRESH_ISOLATED_BASELINE_CACHE"
    else: network_policy, network_expectation, cache = "PROHIBITED", "NONE", "READ_ONLY_EXISTING_DATA"
    if is_rq2 or (is_reliability and testbed == "RELIABILITY_STRATUM_B"): hashes = {"dataset_bundle_sha256": protocol.datasets["dataset_hashes"]["dataset_bundle_sha256"], "sourceunit_selector_independent_20": protocol.datasets["dataset_hashes"]["sourceunit_selector_independent_20"], "s01_raw": protocol.datasets["dataset_hashes"]["s01_raw"], "s01_package": protocol.datasets["dataset_hashes"]["s01_package"]}
    elif kind == "rq1": hashes = {"dataset_bundle_sha256": protocol.datasets["dataset_hashes"]["dataset_bundle_sha256"], "gca_repository_2_0_46864": protocol.datasets["dataset_hashes"]["gca_repository_2_0_46864"]}
    elif is_rq4: hashes = {"dataset_bundle_sha256": protocol.datasets["dataset_hashes"]["dataset_bundle_sha256"], "rq4_development": protocol.datasets["dataset_hashes"]["rq4_development"], "heldout_architectural": protocol.datasets["dataset_hashes"]["heldout_architectural"], "heldout_bundle": protocol.datasets["dataset_hashes"]["heldout_bundle"]}
    elif is_narrative: hashes = {"dataset_bundle_sha256": protocol.datasets["dataset_hashes"]["dataset_bundle_sha256"], "narrative_heldout": protocol.datasets["dataset_hashes"]["narrative_heldout"], "narrative_controls": protocol.datasets["dataset_hashes"]["narrative_controls"], "heldout_bundle": protocol.datasets["dataset_hashes"]["heldout_bundle"]}
    else: hashes = {"dataset_bundle_sha256": protocol.datasets["dataset_hashes"]["dataset_bundle_sha256"], "operational_corpus": protocol.datasets["dataset_hashes"]["operational_corpus"], "operational_manifest": protocol.datasets["dataset_hashes"]["operational_manifest"]}
    gold = "ALLOWED_POST_INFERENCE_ONLY" if is_rq4 or is_narrative else "NOT_APPLICABLE"
    return locals()


def _harness_commit(protocol: Protocol) -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=protocol.root.parents[1], capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "WORKTREE"


def build_plan(kind: str, protocol: Protocol | None = None) -> list[PlannedRun]:
    protocol = protocol or load_protocol()
    eid = evaluation_id(protocol, _harness_commit(protocol))
    specs: list[tuple[str, str, list[str], list[str]]] = []
    if kind == "rq1":
        specs = [("GCA_REPOSITORY_2_0_46864", "RQ1", ["GCA_REPOSITORY_2_0_46864"], ["primary"])]
    elif kind == "rq2":
        path = protocol.root.parent / "sourceunit_selector_independent" / "candidate_inventory.jsonl"
        pairs = sorted({(json.loads(line)["candidate_id"], json.loads(line)["document_id_from_provenance"]) for line in path.read_text(encoding="utf-8").splitlines() if line})
        strategies = protocol.metrics["RQ2"]["strategies"]
        specs = [(protocol.metrics["RQ2"]["source_corpus"], "RQ2", [f"{candidate}|{document}" for candidate, document in pairs], [*strategies, "GOLD"])]
    elif kind == "rq3":
        ablations = [key for key in ("A", "B", "C", "D") if key in protocol.ablation]
        if len(ablations) != 4:
            raise ValueError("ablation contract is incomplete")
        specs = [("RQ3_FULL_SYSTEM", "RQ3", ["FULL_SYSTEM"], ["CANONICAL", *ablations])]
    elif kind == "rq4":
        dev = [json.loads(line)["case_id"] for line in (protocol.root.parent / "rq4_casecontext_robustness" / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if line]
        heldout = json.loads((protocol.root.parent / "final_protocol" / "heldout" / "architectural_challenge_cases.json").read_text(encoding="utf-8"))["cases"]
        specs = [("CASECONTEXT_ROBUSTNESS_35", "RQ4_DEVELOPMENT", dev, ["CANONICAL"]), ("HELDOUT_ARCHITECTURAL_35", "RQ4_HELDOUT", [item["case_id"] for item in heldout], ["CANONICAL"])]
    elif kind == "narrative":
        candidate_root = protocol.root.parent / "final_protocol_v1_5_candidates" / "narrative"
        hostile = json.loads((candidate_root / "hostile_manifest.json").read_text(encoding="utf-8"))["cases"]
        controls = json.loads((candidate_root / "controls_manifest.json").read_text(encoding="utf-8"))["cases"]
        specs = [("NARRATIVE_HELDOUT_20", "NARRATIVE", [item["case_id"] for item in hostile], ["HOSTILE_VERIFIER_ONLY"]), ("NARRATIVE_VALID_CONTROLS_5", "NARRATIVE", [item["case_id"] for item in controls], ["LIVE_NARRATOR_VERIFIER"])]
    elif kind == "operational":
        bindings = load_a01_bindings(protocol)
        specs = [(item["scenario_id"], "OPERATIONAL_A01", [item["scenario_id"]], ["PROPERTY_TEST"]) for item in bindings["scenarios"]]
    elif kind == "reliability":
        reliability = json.loads((protocol.root.parent / "final_protocol" / "reliability_subset.json").read_text(encoding="utf-8"))
        specs = [("RELIABILITY_STRATUM_A", "RELIABILITY", sorted(reliability["by_source"]["HELDOUT_ARCHITECTURAL_35"]), ["CANONICAL"]), ("RELIABILITY_STRATUM_B", "RELIABILITY", sorted(reliability["by_source"]["SOURCEUNIT_SELECTOR_INDEPENDENT_20_positive"]), ["DETERMINISTIC_SELECTOR_K5_TO_SAME_GEMMA_TO_SAME_QUOTE_VALIDATOR"])]
    elif kind == "latency":
        pair = protocol.latency["same_document_cache_latency_pair"]
        specs = [(pair["fixture_id"], "LATENCY", [pair["case_id"]], ["LAT-HIT", "LAT-MISS"])]
    else:
        raise ValueError(f"unknown runner: {kind}")
    result: list[PlannedRun] = []
    repetitions = ["primary"] if kind != "reliability" else list(protocol.reliability["repetitions"])
    for testbed, rq, cases, arms in specs:
        for case in sorted(cases):
            for arm in arms:
                for repetition in repetitions:
                    result.append(PlannedRun(testbed, rq, case, arm, repetition, run_id(eid, testbed, case, arm, repetition)))
    enriched=[]
    for index, plan in enumerate(result, 1):
        meta=_metadata(kind, plan.testbed, plan.arm, protocol)
        values=asdict(plan)
        canonical_required = meta["execution_class"] in ("CANONICAL_RUNTIME", "OPERATIONAL_RUNTIME_NETWORK_ALLOWED", "CONTROLLED_FAILURE_FIXTURE")
        values.update(plan_index=index, execution_class=meta["execution_class"], canonical_runtime_requirement="REQUIRED" if canonical_required else "PROHIBITED", selector_requirement=meta["selector"], casecontext_parser_requirement=meta["parser"], gemma_requirement=meta["gemma"], narrator_requirement=meta["narrator"], quote_validator_requirement=meta["quote"], narrative_verifier_requirement=meta["verifier"], network_policy=meta["network_policy"], network_expectation=meta["network_expectation"], cache_policy=meta["cache"], dataset_hashes=meta["hashes"], gold_access=meta["gold"], terminal_expectation="PRE_SPECIFIED" if kind in ("operational","latency") else "PATH_DEPENDENT")
        enriched.append(PlannedRun(**values))
    return enriched


def dry_run(kind: str) -> dict[str, Any]:
    protocol = load_protocol()
    validate_dataset_registry(protocol)
    plans = build_plan(kind, protocol)
    if kind == "operational":
        for plan in plans:
            create_operational_cache(protocol, plan.case_id, execute=False)
    if kind == "rq2":
        rows = load_s01_rows(protocol)
        if len(rows) != 1697:
            raise RuntimeError("S01 count mismatch")
    return {
        "protocol_version": protocol.manifest["protocol_version"],
        "protocol_sha256": protocol.hashes["protocol_sha256"],
        "kind": kind,
        "planned_executions": len(plans),
        "plans": [asdict(item) for item in plans],
        "calls": {"runtime": 0, "selector": 0, "model": 0, "network": 0},
        "result_directory_created": False,
    }

def execution_plan_sha256(plans: list[PlannedRun]) -> str:
    payload=[asdict(p) for p in plans]
    encoded=json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_full_plan(protocol: Protocol | None = None) -> list[PlannedRun]:
    """Materialize the frozen top-level order with one-based global indices."""
    protocol = protocol or load_protocol()
    kinds = ("rq1", "rq2", "rq3", "rq4", "narrative", "operational", "reliability", "latency")
    plans = [plan for kind in kinds for plan in build_plan(kind, protocol)]
    return [PlannedRun(**{**asdict(plan), "plan_index": index}) for index, plan in enumerate(plans, 1)]


def cli(kind: str) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    if not args.dry_run:
        raise SystemExit("START_FINAL_EVALUATION_REQUIRED")
    import json
    print(json.dumps(dry_run(kind), ensure_ascii=False, sort_keys=True, indent=2))
