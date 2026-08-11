"""Common execution envelope validation."""

from __future__ import annotations

from typing import Any

from .guards import CallCounts


def validate_envelope(protocol: Any, envelope: dict[str, Any]) -> None:
    required = protocol.schemas["common_execution_envelope"]["required_fields"]
    missing = [field for field in required if field not in envelope]
    if missing:
        raise ValueError(f"missing envelope fields: {missing}")
    if envelope["normative_identity"]["protocol_version"] != "1.2":
        raise ValueError("envelope protocol version mismatch")


def build_envelope(protocol: Any, identity: dict[str, Any], *, dataset_hashes: dict[str, str],
                   model_configuration: dict[str, Any], selector_configuration: dict[str, Any],
                   started_at: str, completed_at: str, status: str, failure_class: str | None,
                   raw_reason_code: str | None, input_hash: str, output_hash: str | None,
                   counts: CallCounts, raw_payload_path: str | None, raw_payload_sha256: str | None,
                   scientific_payload: dict[str, Any]) -> dict[str, Any]:
    envelope = {
        "schema_version": "final-evaluation-results/1.2",
        "identity": identity,
        "normative_identity": {
            **protocol.hashes,
            "protocol_version": "1.2",
            "harness_commit": identity.get("harness_commit"),
        },
        "dataset_hashes": dict(dataset_hashes),
        "model_configuration": dict(model_configuration),
        "selector_configuration": dict(selector_configuration),
        "started_at": started_at,
        "completed_at": completed_at,
        "status": status,
        "failure_class": failure_class,
        "raw_reason_code": raw_reason_code,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "runtime_call_counts": {"runtime": 0},
        "model_call_counts": {"parser": counts.parser, "gemma": counts.gemma, "narrator": counts.narrator, "other": counts.other_model},
        "network_call_counts": {"network": counts.network},
        "raw_payload_path": raw_payload_path,
        "raw_payload_sha256": raw_payload_sha256,
        "scientific_payload": scientific_payload,
    }
    validate_envelope(protocol, envelope)
    return envelope
