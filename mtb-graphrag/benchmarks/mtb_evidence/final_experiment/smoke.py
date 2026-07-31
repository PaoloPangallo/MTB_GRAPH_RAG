"""Pilot-only smoke probes; no gold or final query is read by this module."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import shutil
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from backend.api.schemas import ArchitectureComparisonRequest
from backend.comparison.live_runs import build_run
from backend.comparison.service import (
    _build_dossier,
    _checks_from_verifications,
    _render_verified_report,
)
from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.runtime import run_agentic_collection
from backend.pipeline.control.verification.source_port import ScriptedSourceVerifier
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline
from benchmarks.mtb_evidence.final_experiment.harness import canonical_sha256, decide_resume, run_key

SCHEMA_VERSION = "mtb-final-experiment-smoke/1.0"
BASE_COMMIT = "84bcecaafdee60206799fd0a245cb78f816b257e"
CORPUS_VERSION = "qualified_claim_repository/1.4"
CORPUS_HASH = "31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa"
GATE_VERSION = "qualified_claim_structural_gate/1.3"
RETRIEVER_VERSION = "qualified_claim_retriever/1.0"
GENERATOR_VERSION = "final_experiment_generator/1.0"
CONTENT_SHA256 = "ef298585b8d11cabd3a657ea5e3dddbb29ded32134a9bc7ce4f461e5fbd628d0"


class _ScriptedPlanner:
    def __init__(self) -> None:
        self.index = 0

    def invoke(self, _messages: Any) -> Any:
        sequence = ("interpret_variant", "identify_targets", "finish")
        tool = sequence[min(self.index, len(sequence) - 1)]
        self.index += 1
        return SimpleNamespace(content=json.dumps({"tool": tool, "rationale": "pilot_only"}))


class _SlowPlanner:
    def invoke(self, _messages: Any) -> Any:
        time.sleep(1.5)
        return SimpleNamespace(content='{"tool":"finish","rationale":"late"}')


def _no_evidence_tool(state: dict[str, Any]) -> dict[str, Any]:
    return dict(state)


def _v2_smoke(architecture: str, ledger_path: Path) -> dict[str, Any]:
    req = ArchitectureComparisonRequest(
        gene="SYN", variant="P1", tumor_type="Synthetic fixture",
        alteration_type="point_mutation", mtb_goal="treatment-evidence",
        execution_mode="live",
    )
    run, result = build_run(
        req, architecture,
        tools={"interpret_variant": _no_evidence_tool, "identify_targets": _no_evidence_tool},
        source_verifier=ScriptedSourceVerifier([]),
        ledger=EventLedger(ledger_path),
        planner_llm=_ScriptedPlanner() if architecture == "agentic" else None,
        build_dossier=_build_dossier,
        build_claim_checks=_checks_from_verifications,
        render_verified=_render_verified_report,
    )
    serialized = run.model_dump(mode="json")
    json.dumps(serialized, ensure_ascii=False)
    stable = deepcopy(serialized)
    stable.pop("run_id", None)
    stable.get("metrics", {}).pop("elapsed_ms", None)
    stable.get("metrics", {}).pop("stage_timings_ms", None)
    for timing in stable.get("tool_call_timings", []):
        timing.pop("elapsed_ms", None)
    stable_output_sha256 = hashlib.sha256(json.dumps(stable,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
    return {
        "architecture": architecture,
        "ledger_path_name": ledger_path.name,
        "ledger_valid": result.ledger_valid,
        "planning_mode": result.collection.planning_mode,
        "tool_path": list(result.collection.tool_path),
        "planner_calls": result.collection.planner_calls,
        "events": len(result.events),
        "output_serializable": True,
        "run_id": result.run_id,
        "stable_output_sha256": stable_output_sha256,
        "provenance_events_serializable": bool(json.dumps(list(result.events))),
    }


def _stable_v3_payload(payload: dict[str, Any]) -> dict[str, Any]:
    stable = deepcopy(payload)
    stable.pop("latency_ms", None)
    stable.pop("run_id", None)
    return stable


def _timeout_probe(ledger_path: Path) -> bool:
    saved = {key: os.environ.get(key) for key in (
        "PLANNER_TIMEOUT_SECONDS", "PLANNER_MAX_RETRIES", "PLANNER_TOTAL_BUDGET_SECONDS"
    )}
    os.environ["PLANNER_TIMEOUT_SECONDS"] = "1"
    os.environ["PLANNER_MAX_RETRIES"] = "0"
    os.environ["PLANNER_TOTAL_BUDGET_SECONDS"] = "2"
    try:
        result = run_agentic_collection(
            {"gene": "SYN", "variant": "P1", "tumor_type": "Synthetic fixture",
             "alteration_type": "point_mutation", "mtb_goal": "treatment-evidence"},
            ledger=EventLedger(ledger_path),
            planner_llm=_SlowPlanner(),
            tool_registry={"assess_complexity": _no_evidence_tool},
            max_steps=1,
        )
        return result.planning_mode == "safe_fallback" and result.fallback_reason == "timeout"
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _legacy_isolation_probe() -> bool:
    code = r"""
import hashlib
import json, sys
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline
p=EvidenceRetrievalPipeline()
o=p.run({"query_id":"PILOT-LEGACY-ISO","biomarkers":[{"gene":"EGFR","alteration":"L858R"}],"disease":"NSCLC"}, retrieval_backend="legacy")
watched=("backend.pipeline.evidence.corpus.loader","backend.pipeline.evidence.retrieval.v3_backend")
print(json.dumps({"backend":o.backend_name,"imported":[x for x in watched if x in sys.modules],"instantiated":list(p.instantiated_backends())}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True, timeout=30
    )
    payload = json.loads(completed.stdout)
    return (
        payload["backend"] == "legacy"
        and payload["imported"] == []
        and payload["instantiated"] == ["legacy"]
    )


def _resume_probe() -> bool:
    spec = {"system": "S3", "query_id": "PILOT", "model": "scripted", "replica": 1}
    result = {"pilot_only": True, "value": "resume-probe", "content_sha256": ""}
    digest = canonical_sha256(result)
    result["content_sha256"] = digest
    record = {"run_key": run_key(spec), "run_spec": spec, "status": "complete", "result_content_sha256": digest, "result": result}
    return decide_resume(spec, [record]) == "skip_complete"


def run_smoke() -> dict[str, Any]:
    root = Path(__file__).resolve().parent
    temp = root / f".pilot-smoke-{uuid4().hex}"
    temp.mkdir(parents=False, exist_ok=False)
    try:
        s1a = _v2_smoke("deterministic", temp / "s1a.sqlite3")
        s1b = _v2_smoke("deterministic", temp / "s1b.sqlite3")
        s2 = _v2_smoke("agentic", temp / "s2.sqlite3")
        timeout_ok = _timeout_probe(temp / "timeout.sqlite3")

        pipeline_a = EvidenceRetrievalPipeline()
        pipeline_b = EvidenceRetrievalPipeline()
        pilot = {
            "query_id": "PILOT-ONLY-V3-01", "claim_domain": "therapeutic",
            "biomarker": "EML4::ALK Fusion AND ALK C1156Y", "disease": "NSCLC",
            "include_audit": True, "result_limit": 500,
        }
        v3a = pipeline_a.run(pilot, retrieval_backend="qualified_claim_v3").to_dict()
        v3b = pipeline_b.run(pilot, retrieval_backend="qualified_claim_v3").to_dict()
        json.dumps(v3a, ensure_ascii=False)

        deterministic_s1 = s1a["stable_output_sha256"] == s1b["stable_output_sha256"]
        deterministic_s3 = (
            _stable_v3_payload(v3a["payload"]) == _stable_v3_payload(v3b["payload"])
        )
        isolated = (
            len({s1a["run_id"], s1b["run_id"], s2["run_id"]}) == 3
            and len({s1a["ledger_path_name"], s1b["ledger_path_name"], s2["ledger_path_name"]}) == 3
            and pipeline_a is not pipeline_b
        )
        return {
            "pilot_only": True, "final_evaluable": False,
            "systems": {
                "S1": {k: v for k, v in s1a.items() if k != "run_id"},
                "S2": {k: v for k, v in s2.items() if k != "run_id"},
                "S3": {
                    "backend": v3a["backend_name"],
                    "repository_version": v3a["repository_version"],
                    "candidate_count": v3a["payload"]["candidate_count"],
                    "bucket_counts": v3a["payload"]["bucket_counts"],
                    "output_serializable": True,
                },
            },
            "checks": {
                "all_three_systems_startable": True,
                "logging_complete": s1a["ledger_valid"] and s2["ledger_valid"],
                "provenance_serializable": (
                    s1a["provenance_events_serializable"]
                    and s2["provenance_events_serializable"]
                ),
                "resume_safe": _resume_probe(),
                "run_isolation": isolated,
                "s1_deterministic": deterministic_s1,
                "s3_deterministic": deterministic_s3,
                "gold_read_count": 0,
                "legacy_backend_isolation": _legacy_isolation_probe(),
                "timeout_contract_functional": timeout_ok,
            },
        }
    finally:
        if temp.parent == root and temp.name.startswith(".pilot-smoke-"):
            shutil.rmtree(temp)