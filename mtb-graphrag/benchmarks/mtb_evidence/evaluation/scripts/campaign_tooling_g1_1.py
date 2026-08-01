"""Shared, manifest-bound helpers for the G1.1 annotation campaign tooling."""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
CAMPAIGN_ROOT = REPO_ROOT / "benchmarks/mtb_evidence/final_experiment/human_annotations/g1_1"
GOLD_ROOT = REPO_ROOT / "benchmarks/mtb_evidence/final_experiment/gold_g1_1"
DEFAULT_RUNTIME_MANIFEST = CAMPAIGN_ROOT / "annotation_batch_runtime_manifest_g1_1.json"
PILOT_GOLD_PATH = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\MTB_Evidence_gold_pilot_v1_bundle\mtb_evidence_gold_pilot_v1.jsonl")
PROTOCOL_VERSION = "G1.1"
FORBIDDEN_BLIND_FIELDS = {
    "predicted_bucket", "bucket_prediction", "score", "rank", "reason_code",
    "reason_codes", "gate_trace", "gate_outcomes", "gate_outcome", "status_gate_outcome",
    "status_gate_prediction", "system_id", "run_id", "run_key", "output_path",
    "original_position", "semantic_hash", "normalized_semantic_sha256", "model_score",
}
REQUIRED_RESPONSE_FIELDS = {
    "annotation_unit_id", "reviewer_id", "evaluable", "bucket", "source_checked",
    "source_available", "biomarker_match", "disease_scope_match", "intervention_match",
    "formulation_match", "direction_match", "regimen_or_aggregate_status",
    "separability_status", "applicability_status", "provenance_status", "uncertainty",
    "rationale_codes", "annotated_at", "annotation_protocol_version",
}
RESPONSE_ALLOWED_FIELDS = REQUIRED_RESPONSE_FIELDS | {"short_note"}
ALLOWED_BUCKETS = {"primary", "warning", "audit", "rejected", None}
ALLOWED_UNCERTAINTY = {"none", "low", "material"}


class ToolingError(RuntimeError):
    def __init__(self, failure_class: str, message: str):
        super().__init__(message)
        self.failure_class = failure_class


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def unit_ids_digest(ids: list[str]) -> str:
    return sha256_bytes(canonical_json(ids))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolingError("JSONL_READ_FAILURE", f"Unable to read JSONL {path}: {exc}") from exc


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8", newline="\n")


def resolve_manifest_path(value: str, expected_root: Path | None = None) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise ToolingError("MANIFEST_PATH_ESCAPE", value)
    resolved = (REPO_ROOT / candidate).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise ToolingError("MANIFEST_PATH_ESCAPE", value) from exc
    if expected_root is not None:
        root = expected_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ToolingError("MANIFEST_PATH_SCOPE_MISMATCH", value) from exc
    return resolved


def load_runtime_manifest(path: Path = DEFAULT_RUNTIME_MANIFEST) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolingError("RUNTIME_MANIFEST_FAILURE", f"Unable to load runtime manifest: {exc}") from exc


def resolve_batch(manifest: dict[str, Any], reviewer: str, batch_id: str, reviewer_root: str | None = None) -> dict[str, Any]:
    if reviewer not in {"reviewer_A", "reviewer_B"}:
        raise ToolingError("UNKNOWN_REVIEWER", reviewer)
    if reviewer_root is not None and reviewer_root != reviewer:
        raise ToolingError("REVIEWER_BATCH_MISMATCH", f"{reviewer_root} cannot use {reviewer}")
    batch = next((item for item in manifest.get("batches", []) if item.get("reviewer_id") == reviewer and item.get("batch_id") == batch_id), None)
    if batch is None:
        raise ToolingError("UNKNOWN_BATCH", f"{reviewer}/{batch_id}")
    return batch


def _recursive_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _recursive_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _recursive_keys(child)


def _blinding_errors(rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows):
        leaked = FORBIDDEN_BLIND_FIELDS & set(_recursive_keys(row))
        if leaked:
            errors.append(f"row {index}: forbidden fields {sorted(leaked)}")
    return errors


def verify_packet(batch: dict[str, Any], rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    reviewer = batch.get("reviewer_id")
    packet_root = CAMPAIGN_ROOT / str(reviewer) / "batches"
    path = resolve_manifest_path(batch["packet_path"], packet_root)
    if not path.exists():
        raise ToolingError("PACKET_NOT_FOUND", str(path))
    actual_hash = sha256_file(path)
    if actual_hash != batch["packet_sha256"]:
        raise ToolingError("PACKET_CHECKSUM_MISMATCH", f"expected {batch['packet_sha256']} got {actual_hash}")
    packet_rows = rows if rows is not None else read_jsonl(path)
    expected_count = int(batch["expected_unit_count"])
    if len(packet_rows) != expected_count:
        raise ToolingError("PACKET_UNIT_COUNT_MISMATCH", f"expected {expected_count} got {len(packet_rows)}")
    ids = [row.get("annotation_unit_id") for row in packet_rows]
    if any(not isinstance(item, str) for item in ids):
        raise ToolingError("PACKET_UNIT_SET_MISMATCH", "missing annotation_unit_id")
    if len(set(ids)) != len(ids) or unit_ids_digest(ids) != batch["expected_annotation_unit_ids_sha256"]:
        raise ToolingError("PACKET_UNIT_SET_MISMATCH", "annotation_unit_id digest mismatch")
    for row in packet_rows:
        if row.get("annotation_protocol_version") != PROTOCOL_VERSION:
            raise ToolingError("PROTOCOL_VERSION_MISMATCH", "packet row protocol mismatch")
    blind_errors = _blinding_errors(packet_rows)
    if blind_errors:
        raise ToolingError("BLINDING_FAILURE", "; ".join(blind_errors))
    if batch.get("protocol_version") != PROTOCOL_VERSION:
        raise ToolingError("PROTOCOL_VERSION_MISMATCH", batch.get("protocol_version", ""))
    return {"packet_path": str(path), "packet_sha256": actual_hash, "unit_count": len(packet_rows), "blinding_passed": True}


def _response_errors(row: dict[str, Any], expected_reviewer: str, expected_ids: set[str]) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_RESPONSE_FIELDS - set(row)
    if missing:
        errors.append("missing:" + ",".join(sorted(missing)))
    extras = set(row) - RESPONSE_ALLOWED_FIELDS
    if extras:
        errors.append("unknown_fields:" + ",".join(sorted(extras)))
    unit_id = row.get("annotation_unit_id")
    if not isinstance(unit_id, str) or not re.fullmatch(r"G1\.1-.+", unit_id):
        errors.append("invalid_annotation_unit_id")
    elif unit_id not in expected_ids:
        errors.append("unit_not_in_batch")
    if row.get("reviewer_id") != expected_reviewer:
        errors.append("wrong_reviewer")
    if row.get("annotation_protocol_version") != PROTOCOL_VERSION:
        errors.append("wrong_protocol")
    for field in ("evaluable", "source_checked", "source_available"):
        if field in row and type(row[field]) is not bool:
            errors.append(field + "_not_boolean")
    for field in ("biomarker_match", "disease_scope_match", "intervention_match", "formulation_match", "direction_match", "regimen_or_aggregate_status", "separability_status", "applicability_status", "provenance_status"):
        if field in row and not isinstance(row[field], str):
            errors.append(field + "_not_string")
    if row.get("bucket") not in ALLOWED_BUCKETS:
        errors.append("invalid_bucket")
    if row.get("evaluable") is False and row.get("bucket") is not None:
        errors.append("bucket_on_non_evaluable")
    if row.get("source_checked") is True and row.get("source_available") is False:
        errors.append("source_checked_without_source")
    if row.get("uncertainty") not in ALLOWED_UNCERTAINTY:
        errors.append("invalid_uncertainty")
    if not isinstance(row.get("rationale_codes"), list) or not all(isinstance(item, str) for item in row.get("rationale_codes", [])):
        errors.append("rationale_codes_not_string_array")
    if not isinstance(row.get("annotated_at"), str) or not row.get("annotated_at"):
        errors.append("annotated_at_missing")
    leaked = FORBIDDEN_BLIND_FIELDS & set(_recursive_keys(row))
    if leaked:
        errors.append("forbidden_fields:" + ",".join(sorted(leaked)))
    return errors


def validate_responses(batch: dict[str, Any], output_path: Path, audit_path: Path, mode: str = "partial") -> dict[str, Any]:
    packet_path = resolve_manifest_path(batch["packet_path"], CAMPAIGN_ROOT / batch["reviewer_id"] / "batches")
    packet_rows = read_jsonl(packet_path)
    expected_ids = {row["annotation_unit_id"] for row in packet_rows}
    responses = read_jsonl(output_path) if output_path.exists() else []
    audit = read_jsonl(audit_path) if audit_path.exists() else []
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(responses):
        unit_id = row.get("annotation_unit_id")
        if not isinstance(unit_id, str):
            errors.append(f"row {index}: unit_id_not_string")
        elif unit_id in seen:
            errors.append(f"row {index}: duplicate_unit")
        if isinstance(unit_id, str):
            seen.add(unit_id)
        row_errors = _response_errors(row, batch["reviewer_id"], expected_ids)
        errors.extend(f"row {index}: {item}" for item in row_errors)
    saved_events = [event for event in audit if event.get("event") == "annotation_saved"]
    if any(event.get("reviewer_id") != batch["reviewer_id"] for event in saved_events):
        errors.append("audit_wrong_reviewer")
    saved_ids = [event.get("annotation_unit_id") for event in saved_events if event.get("reviewer_id") == batch["reviewer_id"]]
    if set(saved_ids) != seen or len(saved_ids) != len(set(saved_ids)):
        errors.append("audit_response_mismatch")
    missing = expected_ids - seen
    extra = seen - expected_ids
    if mode == "complete" and missing:
        errors.append("missing_units")
    if mode not in {"partial", "complete"}:
        errors.append("invalid_mode")
    return {"passed": not errors, "mode": mode, "response_count": len(responses), "expected_count": len(expected_ids), "missing_units": len(missing), "extra_units": len(extra), "schema_errors": len(errors), "errors": errors}


def response_fixture(annotation_unit_id: str, reviewer_id: str) -> dict[str, Any]:
    return {
        "annotation_unit_id": annotation_unit_id, "reviewer_id": reviewer_id, "evaluable": True, "bucket": "audit",
        "source_checked": False, "source_available": False, "biomarker_match": "unknown", "disease_scope_match": "unknown",
        "intervention_match": "unknown", "formulation_match": "unknown", "direction_match": "unknown",
        "regimen_or_aggregate_status": "unknown", "separability_status": "unknown", "applicability_status": "unknown",
        "provenance_status": "unknown", "uncertainty": "material", "rationale_codes": [],
        "annotated_at": "2026-08-01T00:00:00+00:00", "annotation_protocol_version": PROTOCOL_VERSION,
    }


def build_calibration_packet(path: Path, reviewer: str, seed: int = 20260801) -> list[dict[str, Any]]:
    records = read_jsonl(path)
    rows: list[dict[str, Any]] = []
    for record in records:
        case_id = record["case_id"]
        query = {key: record.get(key) for key in ("pilot_id", "category", "case_context", "question", "gene", "variant", "disease", "required_context")}
        for claim in record.get("claims", []):
            sources = [{key: source.get(key) for key in ("source_record_id", "source_type", "source_id", "title", "url_or_path", "role")} for source in record.get("sources", [])]
            rows.append({
                "annotation_protocol_version": PROTOCOL_VERSION, "annotation_status": "pending",
                "annotation_unit_id": f"CAL-G1.1-{record['pilot_id']}-{claim['claim_id']}", "claim_id": claim["claim_id"],
                "query_id": record["pilot_id"], "query_structured": query,
                "claim_tuple": {key: claim.get(key) for key in ("subject", "relation", "object", "disease", "direction", "mandatory_qualifiers")},
                "source_context": {"sources": sources}, "pilot_only": True, "final_evaluable": False,
            })
    if reviewer == "B":
        random.Random(seed).shuffle(rows)
    return rows
