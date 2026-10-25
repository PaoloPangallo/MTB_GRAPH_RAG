"""Deterministic identity validation for provenance-derived trial records."""

from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def read_trial_structure(cache_root: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """Read arm membership literally from the identity/hash-checked NCT payload."""
    root = Path(cache_root).resolve()
    relative = record.get('local_cache_path')
    if not relative:
        raise ValueError('TRIAL_STRUCTURE_PAYLOAD_MISSING')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('TRIAL_STRUCTURE_PATH_INVALID')
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if not record.get('content_hash') or digest != record['content_hash']:
        raise ValueError('TRIAL_STRUCTURE_DIGEST_MISMATCH')
    protocol = json.loads(payload)['protocolSection']
    expected = str(record.get('document_id') or '')
    if expected != 'nct:' + str(protocol.get('identificationModule', {}).get('nctId') or ''):
        raise ValueError('TRIAL_STRUCTURE_IDENTITY_MISMATCH')
    arms = protocol.get('armsInterventionsModule', {}).get('armGroups') or []
    if not isinstance(arms, list) or any(not isinstance(arm, dict) for arm in arms):
        raise ValueError('TRIAL_STRUCTURE_SHAPE_INVALID')
    return {'arm_groups': arms, 'arm_group_status': 'RECORDED' if arms else 'NOT_RECORDED',
            'trial_structure_provenance': {'document_id': expected, 'snapshot_digest': digest,
                'json_pointer': '/protocolSection/armsInterventionsModule/armGroups'}}


def normalize_nct(value: Any) -> str | None:
    text = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return text if re.fullmatch(r"NCT\d{8}", text) else None


def resolve_trial_record(
    expected_nct: Any, record: Mapping[str, Any] | None, *,
    resolved_payload: bool | None = None,
) -> dict[str, Any]:
    """Validate cached trial identity without inferring efficacy or eligibility."""
    expected = normalize_nct(expected_nct)
    if expected is None:
        return {
            "trial_resolution_status": "INVALID_IDENTITY",
            "declared_nct_id": str(expected_nct or "") or None,
            "resolved_nct_id": None,
            "provenance_status": "TRIAL_ID_INVALID",
            "eligibility_status": "NOT_EVALUATED",
        }
    if not record:
        return {
            "trial_resolution_status": "UNAVAILABLE",
            "declared_nct_id": expected,
            "resolved_nct_id": None,
            "provenance_status": "TRIAL_RECORD_UNAVAILABLE",
            "eligibility_status": "NOT_EVALUATED",
        }
    raw_identity = record.get("nct_id") or record.get("study_identifier")
    if not raw_identity:
        document_id = str(record.get("document_id") or "")
        raw_identity = document_id.split(":", 1)[1] if ":" in document_id else document_id
    resolved = normalize_nct(raw_identity)
    if resolved != expected:
        return {
            "trial_resolution_status": "INVALID_IDENTITY",
            "declared_nct_id": expected,
            "resolved_nct_id": resolved,
            "provenance_status": "TRIAL_IDENTITY_MISMATCH",
            "eligibility_status": "NOT_EVALUATED",
        }
    availability = str(record.get("availability") or "").upper()
    recognized = {"METADATA_ONLY", "ABSTRACT_AVAILABLE", "PMC_XML_AVAILABLE", "LOCAL_PDF_AVAILABLE"}
    if availability in {"RESOLUTION_FAILED", "NCT_NOT_FOUND", "NOT_RESOLVED", "UNAVAILABLE"}:
        return {
            **dict(record),
            "trial_resolution_status": availability,
            "declared_nct_id": expected,
            "resolved_nct_id": None,
            "provenance_status": f"TRIAL_{availability}",
            "eligibility_status": "NOT_EVALUATED",
        }
    if availability not in recognized:
        return {
            **dict(record), "trial_resolution_status": "NOT_RESOLVED",
            "declared_nct_id": expected, "resolved_nct_id": None,
            "provenance_status": "TRIAL_AVAILABILITY_UNRECOGNIZED",
            "eligibility_status": "NOT_EVALUATED",
        }
    if resolved_payload is not True:
        return {
            **dict(record),
            "trial_resolution_status": "RESOLUTION_FAILED",
            "declared_nct_id": expected,
            "resolved_nct_id": None,
            "provenance_status": "TRIAL_PAYLOAD_MISSING",
            "eligibility_status": "NOT_EVALUATED",
        }
    return {
        **dict(record),
        "trial_resolution_status": "AVAILABLE",
        "declared_nct_id": expected,
        "resolved_nct_id": resolved,
        "provenance_status": "TRIAL_RECORD_RESOLVED",
        "eligibility_status": "NOT_EVALUATED",
        "evidence_interpretation": "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE",
    }
