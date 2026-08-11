"""Dry-run planning shared by all frozen testbed entry points."""

from __future__ import annotations

import argparse
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
        specs = [("SOURCEUNIT_SELECTOR_INDEPENDENT_20", "RQ2", [f"{candidate}|{document}" for candidate, document in pairs], ["FIRST_K", "BM25", "DETERMINISTIC_SELECTOR", "GOLD"])]
    elif kind == "rq3":
        specs = [("RQ3_FULL_SYSTEM", "RQ3", ["FULL_SYSTEM"], ["CANONICAL", "ABLATION_A", "ABLATION_B", "ABLATION_C", "ABLATION_D"])]
    elif kind == "rq4":
        dev = [json.loads(line)["case_id"] for line in (protocol.root.parent / "rq4_casecontext_robustness" / "benchmark.jsonl").read_text(encoding="utf-8").splitlines() if line]
        heldout = json.loads((protocol.root.parent / "final_protocol" / "heldout" / "architectural_challenge_cases.json").read_text(encoding="utf-8"))["cases"]
        specs = [("CASECONTEXT_ROBUSTNESS_35", "RQ4_DEVELOPMENT", dev, ["CANONICAL"]), ("HELDOUT_ARCHITECTURAL_35", "RQ4_HELDOUT", [item["case_id"] for item in heldout], ["CANONICAL"])]
    elif kind == "narrative":
        hostile = json.loads((protocol.root.parent / "final_protocol" / "heldout" / "narrative_heldout_cases.json").read_text(encoding="utf-8"))["cases"]
        controls = json.loads((protocol.root.parent / "final_protocol" / "heldout" / "narrative_heldout_valid_control.json").read_text(encoding="utf-8"))["cases"]
        specs = [("NARRATIVE_HELDOUT_20", "NARRATIVE", [item["case_id"] for item in hostile], ["CANONICAL"]), ("NARRATIVE_VALID_CONTROLS_5", "NARRATIVE", [item["case_id"] for item in controls], ["CANONICAL"])]
    elif kind == "operational":
        bindings = load_a01_bindings(protocol)
        specs = [(item["scenario_id"], "OPERATIONAL_A01", [item["scenario_id"]], ["PROPERTY_TEST"]) for item in bindings["scenarios"]]
    elif kind == "reliability":
        reliability = json.loads((protocol.root.parent / "final_protocol" / "reliability_subset.json").read_text(encoding="utf-8"))
        specs = [("RELIABILITY_STRATUM_A", "RELIABILITY", sorted(reliability["by_source"]["HELDOUT_ARCHITECTURAL_35"]), ["CANONICAL"]), ("RELIABILITY_STRATUM_B", "RELIABILITY", sorted(reliability["by_source"]["SOURCEUNIT_SELECTOR_INDEPENDENT_20_positive"]), ["DETERMINISTIC_SELECTOR_K5_TO_SAME_GEMMA_TO_SAME_QUOTE_VALIDATOR"])]
    elif kind == "latency":
        specs = [("SAME-DOCUMENT CACHE LATENCY PAIR", "LATENCY", ["GCA-0000980ba01970f893f8e4d7"], ["LAT-HIT", "LAT-MISS"])]
    else:
        raise ValueError(f"unknown runner: {kind}")
    result: list[PlannedRun] = []
    repetitions = ["primary"] if kind != "reliability" else ["r01", "r02", "r03"]
    for testbed, rq, cases, arms in specs:
        for case in sorted(cases):
            for arm in arms:
                for repetition in repetitions:
                    result.append(PlannedRun(testbed, rq, case, arm, repetition, run_id(eid, testbed, case, arm, repetition)))
    return result


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
        "protocol_version": "1.2",
        "protocol_sha256": protocol.hashes["protocol_sha256"],
        "kind": kind,
        "planned_executions": len(plans),
        "plans": [asdict(item) for item in plans],
        "calls": {"runtime": 0, "selector": 0, "model": 0, "network": 0},
        "result_directory_created": False,
    }


def cli(kind: str) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", required=True)
    args = parser.parse_args()
    if not args.dry_run:
        raise SystemExit("START_FINAL_EVALUATION_REQUIRED")
    import json
    print(json.dumps(dry_run(kind), ensure_ascii=False, sort_keys=True, indent=2))
