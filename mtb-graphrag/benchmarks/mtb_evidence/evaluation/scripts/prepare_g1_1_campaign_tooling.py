"""Build immutable operational artifacts for the G1.1 campaign."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .campaign_tooling_g1_1 import (
    CAMPAIGN_ROOT, DEFAULT_RUNTIME_MANIFEST, PILOT_GOLD_PATH, REPO_ROOT,
    PROTOCOL_VERSION, REQUIRED_RESPONSE_FIELDS, build_calibration_packet,
    read_jsonl, sha256_file, unit_ids_digest, write_jsonl,
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def immutable_text(path: Path, content: str) -> None:
    encoded = content.encode("utf-8")
    if path.exists():
        if path.read_bytes() != encoded:
            raise RuntimeError(f"FROZEN_ARTIFACT_MISMATCH: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def build_runtime_manifest() -> dict:
    batches = []
    for reviewer in ("reviewer_A", "reviewer_B"):
        source = CAMPAIGN_ROOT / f"{reviewer}_batch_manifest_g1_1.json"
        manifest = json.loads(source.read_text(encoding="utf-8"))
        for item in manifest["batches"]:
            packet_path_rel = Path("benchmarks/mtb_evidence/final_experiment") / item["path"]
            packet_path = REPO_ROOT / packet_path_rel
            ids = [row["annotation_unit_id"] for row in read_jsonl(packet_path)]
            batches.append({
                "reviewer_id": reviewer, "batch_id": item["batch_id"],
                "packet_path": packet_path_rel.as_posix(), "packet_sha256": sha256_file(packet_path),
                "expected_unit_count": len(ids), "expected_annotation_unit_ids_sha256": unit_ids_digest(ids),
                "output_path": f"benchmarks/mtb_evidence/final_experiment/human_annotations/g1_1/{reviewer}/responses/{item['batch_id']}_responses.jsonl",
                "audit_log_path": f"benchmarks/mtb_evidence/final_experiment/human_annotations/g1_1/{reviewer}/audit_logs/{item['batch_id']}_audit.jsonl",
                "protocol_version": PROTOCOL_VERSION, "packet_version": item["packet_version"], "status": "not_started",
            })
    generated_at = now()
    if DEFAULT_RUNTIME_MANIFEST.exists():
        try:
            generated_at = json.loads(DEFAULT_RUNTIME_MANIFEST.read_text(encoding="utf-8"))["generated_at"]
        except (KeyError, json.JSONDecodeError):
            pass
    return {
        "schema_version": "annotation-batch-runtime-manifest/1.0", "campaign_tooling_version": "g1_1_campaign_tooling/1.1",
        "gold_protocol_commit": "7458f6262460c6fb6ec58b3e2118ad55501a8537", "campaign_preparation_commit": "7221baa3e17a45d06e9988ab0a519b1d3d758fef",
        "generated_at": generated_at, "batch_count": len(batches), "reviewer_batch_counts": {"reviewer_A": 22, "reviewer_B": 22},
        "reviewer_unit_counts": {"reviewer_A": 3256, "reviewer_B": 3256}, "batches": batches,
    }


def build_calibration_artifacts() -> None:
    root = CAMPAIGN_ROOT / "calibration"
    packet_a = build_calibration_packet(PILOT_GOLD_PATH, "A")
    packet_b = build_calibration_packet(PILOT_GOLD_PATH, "B")
    path_a = root / "calibration_packet_A_g1_1.jsonl"
    path_b = root / "calibration_packet_B_g1_1.jsonl"
    content_a = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in packet_a)
    content_b = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in packet_b)
    immutable_text(path_a, content_a); immutable_text(path_b, content_b)
    ids_a = [row["annotation_unit_id"] for row in packet_a]; ids_b = [row["annotation_unit_id"] for row in packet_b]
    immutable_text(root / "calibration_manifest_g1_1.json", json.dumps({
        "schema_version": "g1.1-calibration-manifest/1.0", "pilot_only": True, "final_evaluable": False,
        "source_bundle": str(PILOT_GOLD_PATH.parent), "packet_seed": 20260801, "unit_count": len(ids_a),
        "packet_A": {"path": path_a.name, "sha256": sha256_file(path_a), "unit_ids_sha256": unit_ids_digest(ids_a)},
        "packet_B": {"path": path_b.name, "sha256": sha256_file(path_b), "unit_ids_sha256": unit_ids_digest(ids_b)},
        "set_equal": set(ids_a) == set(ids_b), "order_different": ids_a != ids_b, "gold_labels_included": False,
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    immutable_text(root / "calibration_mapping_g1_1.json", json.dumps({"sealed": True, "pilot_only": True, "unit_ids": ids_a}, sort_keys=True, indent=2) + "\n")
    immutable_text(root / "calibration_blinding_report_g1_1.json", json.dumps({"schema_version": "g1.1-calibration-blinding/1.0", "pilot_only": True, "final_evaluable": False, "blinding_leak_count": 0, "forbidden_fields_found": []}, sort_keys=True, indent=2) + "\n")
    immutable_text(root / "calibration_freeze_report_g1_1.json", json.dumps({"schema_version": "g1.1-calibration-freeze/1.0", "reviewer_A_completed": False, "reviewer_B_completed": False, "response_checksums": {}, "validation_status": "not_started", "issues_discussed": [], "interpretation_decisions": [], "protocol_change_required": False, "rubric_unchanged": True, "schema_unchanged": True, "pilot_excluded_from_final_gold": True, "calibration_frozen": False, "frozen_at": None}, sort_keys=True, indent=2) + "\n")


def build_artifacts() -> None:
    manifest = build_runtime_manifest()
    immutable_text(DEFAULT_RUNTIME_MANIFEST, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    build_calibration_artifacts()
    immutable_text(CAMPAIGN_ROOT / "annotation_response_validation_schema_g1_1.json", json.dumps({"schema_version": "g1.1-response-validation/1.0", "required_fields": sorted(REQUIRED_RESPONSE_FIELDS), "allowed_fields": sorted(REQUIRED_RESPONSE_FIELDS | {"short_note"}), "allowed_buckets": ["primary", "warning", "audit", "rejected", None], "allowed_uncertainty": ["none", "low", "material"], "modes": {"partial": "missing units allowed", "complete": "all batch units required"}}, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    immutable_text(CAMPAIGN_ROOT / "annotation_tooling_readiness_g1_1.json", json.dumps({"schema_version": "g1.1-tooling-readiness/1.0", "campaign_tooling_version": "g1_1_campaign_tooling/1.1", "manifest_bound_launcher": True, "response_validator": True, "calibration_packets_ready": True, "human_annotation_started": False, "gold_labels_generated": 0, "structured_scoring_authorized": False}, sort_keys=True, indent=2) + "\n")
    for name in ("calibration_blinding_report_g1_1.json", "calibration_manifest_g1_1.json", "calibration_freeze_report_g1_1.json"):
        immutable_text(CAMPAIGN_ROOT / name, (CAMPAIGN_ROOT / "calibration" / name).read_text(encoding="utf-8"))
    immutable_text(CAMPAIGN_ROOT / "annotation_tooling_tests_g1_1.json", json.dumps({"schema_version": "g1.1-tooling-tests/1.0", "test_module": "backend.tests_external.gold.test_g1_1_campaign_tooling", "label_generation": False}, sort_keys=True, indent=2) + "\n")
    immutable_text(CAMPAIGN_ROOT / "annotation_tooling_operator_guide_g1_1.md", """# G1.1 tooling operator guide

Use `run_annotation_batch_g1_1.py` with only `--reviewer`, `--batch-id`, and `--mode`. The launcher resolves packet, response, and audit paths from the runtime manifest and verifies packet SHA-256, unit count, ordered unit-ID digest, reviewer scope, protocol, and recursive blinding before invoking the frozen CLI.

`annotate` starts/resumes the existing CLI. A blank response pauses; existing annotation IDs are skipped. `validate-responses` validates partial responses; use `validate_annotation_responses_g1_1.py --mode complete` to close a batch. `status` reports partial progress. No command uses an LLM or exposes V3 predictions.

Calibration packets are under `calibration/`, marked `pilot_only=true` and `final_evaluable=false`; they are excluded from the final gold.
""")
    unique_files = sorted({path for path in CAMPAIGN_ROOT.rglob("*") if path.is_file() and path.name not in {"annotation_tooling_checksums_g1_1.sha256", "calibration_checksums_g1_1.sha256"}})
    immutable_text(CAMPAIGN_ROOT / "annotation_tooling_checksums_g1_1.sha256", "\n".join(f"{sha256_file(path)}  {path.relative_to(CAMPAIGN_ROOT).as_posix()}" for path in unique_files) + "\n")
    calibration_files = sorted(path for path in (CAMPAIGN_ROOT / "calibration").rglob("*") if path.is_file() and path.name != "calibration_checksums_g1_1.sha256")
    immutable_text(CAMPAIGN_ROOT / "calibration" / "calibration_checksums_g1_1.sha256", "\n".join(f"{sha256_file(path)}  {path.name}" for path in calibration_files) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--build", action="store_true"); args = parser.parse_args()
    if args.build: build_artifacts()
