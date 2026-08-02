from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import EscatAssessmentRecord, EscatCurationDraft


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_active_claims(root: Path | None = None) -> dict[str, dict[str, Any]]:
    root = root or repository_root()
    directory = root / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
    claims: dict[str, dict[str, Any]] = {}
    for filename in ("therapeutic_claims.jsonl", "diagnostic_claims.jsonl"):
        for claim in _read_jsonl(directory / filename):
            if not claim.get("deprecated", False):
                claims[str(claim["claim_id"])] = claim
    return claims


def load_availability(root: Path | None = None) -> dict[str, dict[str, str]]:
    path = (root or repository_root()) / "docs/escat_shadow_feasibility/claim_data_availability.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["claim_id"]: row for row in csv.DictReader(handle)}


def load_document_alignment(root: Path | None = None) -> dict[str, dict[str, str]]:
    path = (root or repository_root()) / "docs/pmid_pilot/claim_document_alignment.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["claim_id"]: row for row in csv.DictReader(handle)}


def _field(value: Any, reference: str) -> dict[str, Any]:
    return {"value": value, "origin": "qualified_claim", "level": "claim", "reference": reference}


def _source_entries(claim: dict[str, Any], alignment: dict[str, str]) -> list[dict[str, Any]]:
    provenance = claim.get("provenance") or {}
    values: list[str] = []
    for value in claim.get("source_unit_ids") or []:
        if value and value not in values:
            values.append(value)
    value = provenance.get("source_id")
    if value and value not in values:
        values.append(str(value))
    if alignment.get("pmid"):
        pmid = f"PMID:{alignment['pmid']}"
        if pmid not in values:
            values.append(pmid)
    return [{"source_id": value, "origin": "qualified_claim" if value in (claim.get("source_unit_ids") or []) else "document_alignment", "level": "source_unit" if value.startswith(("SU-", "PU-")) else "document", "claim_specific_support": alignment.get("final_support_status")} for value in values]


def _passage_entries(alignment: dict[str, str]) -> list[dict[str, Any]]:
    text = alignment.get("supporting_passage")
    if not text:
        return []
    return [{"text": text, "locator": alignment.get("locator") or "ABSTRACT", "section": alignment.get("section") or None, "origin": alignment.get("text_origin") or "document", "support_status": alignment.get("final_support_status")}]


def create_draft(claim_id: str, *, root: Path | None = None, assessment_id: str | None = None, created_at=None) -> EscatCurationDraft:
    root = root or repository_root()
    claims = load_active_claims(root)
    availability = load_availability(root).get(claim_id)
    if claim_id not in claims:
        raise KeyError(f"active claim not found: {claim_id}")
    if availability is None:
        raise KeyError(f"availability record not found: {claim_id}")
    claim = claims[claim_id]
    alignment = load_document_alignment(root).get(claim_id, {})
    diagnostic = claim.get("claim_domain") == "diagnostic"
    source_origins = {
        "biomarker": _field(claim.get("biomarker"), claim_id),
        "disease": _field(claim.get("disease_scope"), claim_id),
        "intervention": _field(claim.get("canonical_intervention") or claim.get("intervention"), claim_id),
        "direction": _field(claim.get("direction"), claim_id),
        "evidence_scope": _field(claim.get("evidence_setting"), claim_id),
    }
    missing = ["OFFICIAL_RULESET_NOT_AVAILABLE", "FRAMEWORK_VERSION", "RULE_ID"]
    for name in ("tumour_context_status", "study_design_status", "endpoint_status", "clinical_response_status", "source_status", "source_unit_status", "locator_status", "text_status"):
        state = availability.get(name, "MISSING")
        if state in {"MISSING", "AMBIGUOUS", "PARENT_LEVEL_ONLY"}:
            missing.append(f"{name}:{state}")
    record = EscatAssessmentRecord(
        assessment_id=assessment_id or f"ESCAT-AS-{uuid4().hex}", claim_id=claim_id,
        assessment_status="NOT_APPLICABLE" if diagnostic else "INCOMPLETE",
        biomarker=claim.get("biomarker"), disease=claim.get("disease_scope"),
        intervention=claim.get("canonical_intervention") or claim.get("intervention"),
        direction=claim.get("direction"), evidence_scope=claim.get("evidence_setting"),
        assessment_origin="MANUAL_REVIEW", supporting_sources=_source_entries(claim, alignment),
        supporting_passages=_passage_entries(alignment), reason_codes=["OFFICIAL_RULESET_NOT_AVAILABLE", "PREFILLED_FROM_LOCAL_CLAIM"] + (["NOT_APPLICABLE_DIAGNOSTIC"] if diagnostic else []),
        missing_requirements=missing, source_field_origins=source_origins,
    )
    return EscatCurationDraft(assessment=record, prefilled_fields=source_origins, missing_requirements=missing)
