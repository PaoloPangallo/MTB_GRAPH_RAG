"""Deterministic final campaign manifest generation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .support_levels import summarize_support_levels


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _terminal_counts(ledger: list[dict[str, Any]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for event in ledger:
        if event.get("event") != "COMPLETE":
            continue
        counts[str(event.get("unit_status") or "COMPLETE")] += 1
    return counts


def build_final_results_manifest(
    *,
    protocol: Any,
    campaign_root: Path,
    expected_units: int,
    evaluation_id: str,
    output_directory: str,
) -> dict[str, Any]:
    """Build a manifest only after every planned unit has a terminal result."""

    ledger_path = campaign_root / "ledger.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    counts = _terminal_counts(ledger)
    accounted = sum(counts.values())
    if accounted != expected_units:
        raise RuntimeError(f"FINAL_RESULTS_NOT_ACCOUNTED:{accounted}/{expected_units}")
    artifacts: dict[str, str] = {}
    for path in sorted(campaign_root.rglob("*")):
        if path.is_file() and path.name != "final_results_manifest.json":
            artifacts[str(path.relative_to(campaign_root)).replace("\\", "/")] = _sha256(path)
    raw_results = []
    for path in sorted((campaign_root / "raw_attempts").glob("*.json")):
        raw_results.append(json.loads(path.read_text(encoding="utf-8")))
    support_summary = summarize_support_levels(raw_results)
    hashes = getattr(protocol, "hashes", {})
    manifest = {
        "manifest_version": f"final-results/{protocol.manifest.get('protocol_version')}",
        "evaluation_id": evaluation_id,
        "protocol_version": protocol.manifest.get("protocol_version"),
        "evaluation_boundary": protocol.manifest.get("evaluation_boundary"),
        "canonical_runtime_commit": hashes.get("runtime_commit"),
        "evaluation_protocol_commit": protocol.manifest.get("evaluation_protocol_commit"),
        "sealed_plan_sha256": protocol.manifest.get("sealed_plan_sha256"),
        "seal_manifest_sha256": protocol.manifest.get("seal_manifest_sha256"),
        "gca_sha256": protocol.manifest.get("gca_sha256"),
        "frozen_document_manifest_sha256": protocol.manifest.get("frozen_document_manifest_sha256"),
        "sourceunit_index_sha256": protocol.manifest.get("sourceunit_index_sha256"),
        "evaluation_protocol_commit": protocol.manifest.get("evaluation_protocol_commit"),
        "dependency_lock_sha256": protocol.manifest.get("dependency_lock_sha256"),
        "expected_units": expected_units,
        "accounted_units": accounted,
        "unit_status_counts": dict(sorted(counts.items())),
        "quote_validation": {"validated": support_summary["quote_validated"]},
        "document_support_levels": support_summary["support_levels"],
        "document_support_level_denominator": support_summary["support_level_denominator"],
        "candidate_support_checks_per_paper": support_summary["per_paper"],
        "output_directory": output_directory,
        "artifacts": artifacts,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return manifest
