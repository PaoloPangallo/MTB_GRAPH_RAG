"""Deterministic execution identifiers bound to the loaded protocol."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _legacy_identity(protocol: Any, harness_commit: str) -> dict[str, Any]:
    return {
        "runtime_commit": protocol.hashes["runtime_commit"],
        "protocol_version": protocol.manifest["protocol_version"],
        "protocol_sha256": protocol.hashes["protocol_sha256"],
        "inherited_A01_sha256": protocol.hashes["inherited_A01_sha256"],
        "S01_package_sha256": protocol.hashes["S01_package_sha256"],
        "harness_commit": harness_commit,
    }


def plan_seed_id(protocol: Any, harness_commit: str) -> str:
    if protocol.manifest.get("protocol_version") != "1.7.1":
        return "fe_" + _sha(_legacy_identity(protocol, harness_commit))
    return "fe_" + _sha({
        "runtime_commit": protocol.hashes["runtime_commit"],
        "protocol_version": protocol.manifest["protocol_version"],
        "evaluation_boundary": protocol.manifest.get("evaluation_boundary"),
        "gca_sha256": protocol.manifest.get("gca_sha256"),
        "benchmark_sha256": protocol.manifest.get("benchmark_sha256"),
        "gold_sha256": protocol.manifest.get("gold_sha256"),
        "closure_manifest_sha256": protocol.manifest.get("closure_manifest_sha256"),
        "frozen_document_manifest_sha256": protocol.manifest.get("frozen_document_manifest_sha256"),
        "frozen_source_unit_index_sha256": protocol.manifest.get("frozen_source_unit_index_sha256"),
        "model_config_sha256": protocol.manifest.get("model_config_sha256"),
        "model_identity_sha256": protocol.manifest.get("model_identity_sha256"),
        "prompt_identity_sha256": protocol.manifest.get("prompt_identity_sha256"),
    })


def evaluation_id(protocol: Any, harness_commit: str) -> str:
    if not isinstance(harness_commit, str) or re.fullmatch(r"[0-9a-f]{40}", harness_commit) is None:
        raise ValueError("harness_commit must be the full 40-character lowercase Git SHA")
    identity = _legacy_identity(protocol, harness_commit)
    for key in (
        "evaluation_boundary", "gca_sha256", "benchmark_sha256", "gold_sha256",
        "sealed_plan_sha256", "closure_manifest_sha256",
        "frozen_document_manifest_sha256", "frozen_source_unit_index_sha256",
        "model_config_sha256", "model_identity_sha256", "prompt_identity_sha256",
    ):
        if key in protocol.manifest:
            identity[key] = protocol.manifest[key]
    return "fe_" + _sha(identity)


def run_id(eval_id: str, testbed: str, case_id: str, arm: str, repetition_id: str) -> str:
    return "run_" + _sha({
        "evaluation_id": eval_id,
        "testbed": testbed,
        "case_id": case_id,
        "arm": arm,
        "repetition_id": repetition_id,
    })


def attempt_id(run: str, ordinal: int) -> str:
    if ordinal < 1:
        raise ValueError("attempt ordinal must be positive")
    return f"{run}/a{ordinal:04d}"
