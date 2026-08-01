"""Manifest-bound launcher for G1.1 batch operations."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .campaign_tooling_g1_1 import (
    DEFAULT_RUNTIME_MANIFEST,
    REPO_ROOT,
    ToolingError,
    load_runtime_manifest,
    read_jsonl,
    resolve_batch,
    validate_responses,
    verify_packet, resolve_manifest_path,
)


def _paths(batch: dict) -> tuple[Path, Path]:
    reviewer_root = __import__("benchmarks.mtb_evidence.evaluation.scripts.campaign_tooling_g1_1", fromlist=["CAMPAIGN_ROOT"]).CAMPAIGN_ROOT / batch["reviewer_id"]
    try:
        output = resolve_manifest_path(batch["output_path"], reviewer_root / "responses")
    except ToolingError as exc:
        raise ToolingError("OUTPUT_PATH_MISMATCH", str(exc)) from exc
    try:
        audit = resolve_manifest_path(batch["audit_log_path"], reviewer_root / "audit_logs")
    except ToolingError as exc:
        raise ToolingError("AUDIT_PATH_MISMATCH", str(exc)) from exc
    return output, audit


def preflight(manifest: dict, reviewer: str, batch_id: str) -> tuple[dict, Path, Path]:
    batch = resolve_batch(manifest, reviewer, batch_id)
    result = verify_packet(batch)
    output, audit = _paths(batch)
    if batch.get("protocol_version") != "G1.1":
        raise ToolingError("PROTOCOL_VERSION_MISMATCH", batch.get("protocol_version", ""))
    return batch, output, audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manifest-bound G1.1 annotation batch launcher")
    parser.add_argument("--reviewer", required=True, choices=["reviewer_A", "reviewer_B"])
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--mode", required=True, choices=["annotate", "validate-responses", "status"])
    args = parser.parse_args(argv)
    try:
        manifest = load_runtime_manifest(DEFAULT_RUNTIME_MANIFEST)
        batch, output, audit = preflight(manifest, args.reviewer, args.batch_id)
        if args.mode == "annotate":
            command = [sys.executable, "-m", "benchmarks.mtb_evidence.evaluation.scripts.annotate_g1_1", "--packet", str(REPO_ROOT / batch["packet_path"]), "--reviewer", args.reviewer, "--output", str(output), "--audit-log", str(audit)]
            return subprocess.call(command, cwd=REPO_ROOT)
        if args.mode == "validate-responses":
            print(json.dumps(validate_responses(batch, output, audit, mode="partial"), ensure_ascii=False, sort_keys=True))
        else:
            result = validate_responses(batch, output, audit, mode="partial")
            print(json.dumps({"reviewer": args.reviewer, "batch_id": args.batch_id, **result}, ensure_ascii=False, sort_keys=True))
        return 0
    except ToolingError as exc:
        print(json.dumps({"failure_class": exc.failure_class, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
