from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any

from benchmarks.mtb_evidence.escat_curation_mvp.models import EscatAssessmentRecord
from benchmarks.mtb_evidence.escat_shadow_dossier.adapter import present_assessment


def provenance_extension(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    provenance = value.get("provenance") if isinstance(value.get("provenance"), dict) else {}
    claim_sources = value.get("claim_level_sources", value.get("claim_sources", []))
    parent_sources = value.get("parent_level_publications", value.get("parent_sources", []))
    source_units = value.get("source_unit", value.get("source_units", []))
    locators = value.get("locators", [])
    return {
        "claim_level_sources": copy.deepcopy(claim_sources or []),
        "parent_level_publications": copy.deepcopy(parent_sources or []),
        "source_unit": copy.deepcopy(source_units or []),
        "locators": copy.deepcopy(locators or []),
        "provenance_status": value.get("provenance_status", provenance.get("status", "NOT_ASSESSED")),
        "first_missing_link": value.get("first_missing_link"),
        "ambiguities": copy.deepcopy(value.get("ambiguities", [])),
    }


def document_support_extension(value: dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {
            "status": "NOT_ASSESSED",
            "document_identifier": None,
            "identifier_scope": None,
            "text_availability": None,
            "supporting_passage": None,
            "locator": None,
            "support_level": None,
            "supported_fields": [],
            "unsupported_fields": [],
            "method": None,
            "limitations": ["document_support_module_not_executed"],
        }
    result = copy.deepcopy(value)
    result.setdefault("status", "PARTIALLY_AVAILABLE")
    result.setdefault("document_identifier", None)
    result.setdefault("identifier_scope", None)
    result.setdefault("text_availability", None)
    result.setdefault("supporting_passage", None)
    result.setdefault("locator", None)
    result.setdefault("support_level", result.get("support_type"))
    result.setdefault("supported_fields", [])
    result.setdefault("unsupported_fields", [])
    result.setdefault("method", None)
    result.setdefault("limitations", [])
    return result


def ontology_extension(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    result = {
        "disease": copy.deepcopy(value.get("disease", {})),
        "biomarker": copy.deepcopy(value.get("biomarker", value.get("variant", {}))),
        "intervention": copy.deepcopy(value.get("intervention", {})),
        "diagnostic_entity": copy.deepcopy(value.get("diagnostic_entity", {})),
        "shadow_only": True,
    }
    return result


def _records_by_claim(
    assessments: Iterable[EscatAssessmentRecord | dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, list[EscatAssessmentRecord | dict[str, Any]]]:
    if assessments is None:
        return {}
    if isinstance(assessments, dict):
        result: dict[str, list[EscatAssessmentRecord | dict[str, Any]]] = {}
        for claim_id, value in assessments.items():
            result[claim_id] = list(value) if isinstance(value, list) else [value]
        return result
    result = {}
    for record in assessments:
        claim_id = record.claim_id if isinstance(record, EscatAssessmentRecord) else record.get("claim_id")
        if claim_id:
            result.setdefault(str(claim_id), []).append(record)
    return result


def escat_extension(
    claim_id: str,
    assessments: Iterable[EscatAssessmentRecord | dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return present_assessment(
        claim_id,
        list(assessments or []),
        ruleset_status="RESEARCH_DRAFT",
    )
