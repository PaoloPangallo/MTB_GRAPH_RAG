"""Pure contracts shared by planning, smoke execution, and later official runs."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

SCHEMA_VERSION = "mtb-final-experiment-harness/1.0"
BASE_COMMIT = "84bcecaafdee60206799fd0a245cb78f816b257e"
CORPUS_VERSION = "qualified_claim_repository/1.4"
CORPUS_HASH = "31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa"
GATE_VERSION = "qualified_claim_structural_gate/1.3"
RETRIEVER_VERSION = "qualified_claim_retriever/1.0"
GENERATOR_VERSION = "final_experiment_generator/1.0"
CONTENT_SHA256 = "e2c634e85f458d207f97837a939ef32a0eae52f02239c2f9436a3020fcb7cd7b"

REQUIRED_ARTIFACTS = (
    "protocol_v1.md", "protocol_v1.json", "queries_candidate_audit.jsonl",
    "queries_v1.jsonl", "systems_v1.json", "models_v1.json", "metrics_v1.json",
    "gold_external_manifest.json", "run_manifest_schema.json", "result_schema.json",
    "analysis_plan_v1.md", "smoke_test_report.json", "readiness_report.json",
    "run_plan_v1.jsonl",
)


class GoldClosedError(RuntimeError):
    """Official execution was requested while the external gold is closed."""


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    """Hash a mapping after blanking only its top-level hash slot."""
    normalized = deepcopy(dict(payload))
    normalized["content_sha256"] = ""
    return hashlib.sha256(_canonical_bytes(normalized)).hexdigest()


def run_key(run_spec: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(dict(run_spec))).hexdigest()


def decide_resume(
    run_spec: Mapping[str, Any], existing: Iterable[Mapping[str, Any]]
) -> str:
    """Return run/skip; fail on duplicate or incompatible identity reuse."""
    key = run_key(run_spec)
    rows = list(existing)
    seen_specs: set[bytes] = set()
    for row in rows:
        stored_spec = row.get("run_spec")
        if not isinstance(stored_spec, Mapping):
            raise ValueError("existing run record lacks run_spec")
        expected_key = run_key(stored_spec)
        if row.get("run_key") != expected_key:
            raise ValueError(f"stored run key/spec mismatch: {row.get('run_key')}")
        fingerprint = _canonical_bytes(dict(stored_spec))
        if fingerprint in seen_specs:
            raise ValueError(f"duplicate stored run spec: {expected_key}")
        seen_specs.add(fingerprint)
    matches = [row for row in rows if row.get("run_key") == key]
    if len(matches) > 1:
        raise ValueError(f"duplicate run identity: {key}")
    if not matches:
        return "run"
    row = matches[0]
    if dict(row.get("run_spec", {})) != dict(run_spec):
        raise ValueError(f"incompatible run identity: {key}")
    if row.get("status") == "complete":
        result_digest = str(row.get("result_content_sha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", result_digest):
            raise ValueError(f"complete run lacks a bound result digest: {key}")
        result = row.get("result")
        if not isinstance(result, Mapping):
            raise ValueError(f"complete run lacks an inline result artifact: {key}")
        if canonical_sha256(result) != result_digest:
            raise ValueError(f"complete run result digest mismatch: {key}")
        return "skip_complete"
    return "run"


def assert_gold_closed(manifest: Mapping[str, Any]) -> None:
    if manifest.get("state") != "NOT_OPENED_FOR_FINAL_EXPERIMENT":
        raise ValueError("unexpected gold state during protocol-freeze phase")


def guard_official_mode(manifest_path: Path) -> None:
    """Read the metadata-only manifest and stop before resolving payload paths."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("state") == "NOT_OPENED_FOR_FINAL_EXPERIMENT":
        raise GoldClosedError(
            "official runs are disabled until a new explicit authorization"
        )
    raise GoldClosedError("this frozen runner contains no authorized official path")


def validate_artifact(payload: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "generated_at", "base_commit", "corpus_version",
        "corpus_hash", "gate_version", "retriever_version",
        "generator_version", "content_sha256",
    }
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"missing artifact metadata: {sorted(missing)}")
    if payload["base_commit"] != BASE_COMMIT or payload["corpus_hash"] != CORPUS_HASH:
        raise ValueError("artifact repository/corpus identity mismatch")
    if payload["corpus_version"] != CORPUS_VERSION:
        raise ValueError("artifact corpus version mismatch")
    if payload["gate_version"] != GATE_VERSION:
        raise ValueError("artifact gate identity mismatch")
    if payload["retriever_version"] != RETRIEVER_VERSION:
        raise ValueError("artifact retriever identity mismatch")
    if payload["generator_version"] != GENERATOR_VERSION:
        raise ValueError("artifact generator identity mismatch")
    if payload["content_sha256"] != canonical_sha256(payload):
        raise ValueError("artifact content_sha256 mismatch")


def _validate_text_artifact(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^content_sha256: ([0-9a-f]{64})$", text, re.MULTILINE)
    if match is None:
        raise ValueError(f"{path.name}: missing content_sha256")
    normalized = text[:match.start(1)] + text[match.end(1):]
    if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != match.group(1):
        raise ValueError(f"{path.name}: content_sha256 mismatch")
    for expected in (BASE_COMMIT, CORPUS_VERSION, CORPUS_HASH, GATE_VERSION, RETRIEVER_VERSION, GENERATOR_VERSION):
        if expected not in text:
            raise ValueError(f"{path.name}: frozen identity mismatch")


def validate_frozen_inputs(root: Path) -> dict[str, int]:
    """Validate every frozen input before planning or smoke execution."""
    missing = [name for name in REQUIRED_ARTIFACTS if not (root / name).is_file()]
    if missing:
        raise ValueError(f"missing frozen artifacts: {missing}")
    json_files = jsonl_rows = text_files = 0
    for path in sorted(root.glob("*.json")):
        validate_artifact(json.loads(path.read_text(encoding="utf-8")))
        json_files += 1
    for path in sorted(root.glob("*.jsonl")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line:
                continue
            try:
                validate_artifact(json.loads(line))
            except Exception as exc:
                raise ValueError(f"{path.name}:{line_number}: {exc}") from exc
            jsonl_rows += 1
    for path in [*sorted(root.glob("*.md")), *sorted((root / "prompts_v1").glob("*.txt"))]:
        _validate_text_artifact(path)
        text_files += 1
    gold = json.loads((root / "gold_external_manifest.json").read_text(encoding="utf-8"))
    assert_gold_closed(gold)
    systems = json.loads((root / "systems_v1.json").read_text(encoding="utf-8"))
    prompt_manifest = {}
    for path in sorted((root / "prompts_v1").glob("*.txt")):
        match = re.search(r"^content_sha256: ([0-9a-f]{64})$", path.read_text(encoding="utf-8"), re.MULTILINE)
        if match is None:
            raise ValueError(f"{path.name}: prompt hash missing")
        prompt_manifest[path.name] = match.group(1)
    prompt_bundle = hashlib.sha256(_canonical_bytes(prompt_manifest)).hexdigest()
    if prompt_manifest != systems.get("prompt_manifest") or prompt_bundle != systems.get("prompt_bundle_sha256"):
        raise ValueError("prompt bundle digest mismatch")
    repo_root = root.parents[2]
    source_manifest = systems.get("source_manifest")
    if not isinstance(source_manifest, dict) or not source_manifest:
        raise ValueError("source manifest missing")
    actual_sources = {}
    for name in source_manifest:
        path = repo_root / name
        if not path.is_file():
            raise ValueError(f"runtime source missing: {name}")
        actual_sources[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    source_bundle = hashlib.sha256(_canonical_bytes(actual_sources)).hexdigest()
    if actual_sources != source_manifest or source_bundle != systems.get("source_bundle_sha256"):
        raise ValueError("runtime source bundle digest mismatch")
    source_pattern = re.compile(r'^CONTENT_SHA256 = "([0-9a-f]{64})"$', re.MULTILINE)
    source_files = 0
    for path in sorted(root.glob("*.py")):
        source_text = path.read_text(encoding="utf-8")
        match = source_pattern.search(source_text)
        if match is None:
            raise ValueError(f"{path.name}: source content hash missing")
        normalized = source_text[:match.start(1)] + source_text[match.end(1):]
        if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != match.group(1):
            raise ValueError(f"{path.name}: source content hash mismatch")
        source_files += 1
    return {"json_files": json_files, "jsonl_rows": jsonl_rows, "text_files": text_files, "source_files": source_files}


def plan_runs(systems: Mapping[str, Any], queries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Expand the frozen model/system/query/replica matrix without execution."""
    planned: list[dict[str, Any]] = []
    models = systems["evaluation_models"]
    for model in models:
        for query in queries:
            for system_id, replicas in (("S1", 2), ("S2", 5), ("S3", 2)):
                if system_id != "S3" and not query.get("comparative_inclusion", False):
                    continue
                for replica in range(1, replicas + 1):
                    spec = {
                        "system": system_id,
                        "query_id": query["query_id"],
                        "model": model,
                        "replica": replica,
                        "base_commit": BASE_COMMIT,
                        "corpus_hash": CORPUS_HASH,
                        "gate_version": GATE_VERSION,
                        "retriever_version": RETRIEVER_VERSION,
                        "generator_version": GENERATOR_VERSION,
                        "systems_config_sha256": systems["content_sha256"],
                        "query_config_sha256": query["content_sha256"],
                        "prompt_bundle_version": "prompts_v1",
                        "prompt_bundle_sha256": systems["prompt_bundle_sha256"],
                        "source_bundle_sha256": systems["source_bundle_sha256"],
                    }
                    planned.append(spec | {"run_key": run_key(spec)})
    keys = [row["run_key"] for row in planned]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate run keys in frozen plan")
    return planned