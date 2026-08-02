from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .module_status import build_module_status
from .modules import (
    _records_by_claim,
    document_support_extension,
    escat_extension,
    ontology_extension,
    provenance_extension,
)


def core_snapshot_fingerprint(core_result: dict[str, Any]) -> str:
    canonical = json.dumps(core_result, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mapping(value: dict[str, Any] | None) -> dict[str, Any]:
    return value or {}


def build_claim_extensions(
    claims: list[dict[str, Any]],
    *,
    provenance_by_claim: dict[str, dict[str, Any]] | None = None,
    document_support_by_claim: dict[str, dict[str, Any] | None] | None = None,
    ontology_by_claim: dict[str, dict[str, Any]] | None = None,
    escat_assessments: Any = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    claim_ids = [str(claim["claim_id"]) for claim in claims if claim.get("claim_id")]
    known = set(claim_ids)
    provenance = _mapping(provenance_by_claim)
    document_support = _mapping(document_support_by_claim)
    ontology = _mapping(ontology_by_claim)
    escat = _records_by_claim(escat_assessments)
    extensions: dict[str, dict[str, Any]] = {}
    for claim_id in claim_ids:
        extensions[claim_id] = {
            "provenance": provenance_extension(provenance.get(claim_id)),
            "document_support": document_support_extension(document_support.get(claim_id)),
            "ontology_alignment": ontology_extension(ontology.get(claim_id)),
            "clinical_actionability": escat_extension(claim_id, escat.get(claim_id, [])),
        }

    orphan_records: list[dict[str, Any]] = []
    for source_name, source in (("provenance", provenance), ("document_support", document_support), ("ontology", ontology)):
        for claim_id in sorted(set(source) - known):
            orphan_records.append({"source": source_name, "claim_id": claim_id})
    for claim_id in sorted(set(escat) - known):
        orphan_records.append({"source": "escat", "claim_id": claim_id})
    missing_references = [
        {"source": "claims", "reference": index}
        for index, claim in enumerate(claims)
        if not claim.get("claim_id")
    ]
    return extensions, {"orphan_records": orphan_records, "missing_references": missing_references}


def _diagnostic_context(value: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(value or {})
    result.setdefault("records", [])
    result.setdefault("status", "NOT_ASSESSED")
    result.setdefault("limitations", [])
    return result


def build_dossier(
    core_result: dict[str, Any],
    *,
    run: dict[str, Any] | None = None,
    case_context: dict[str, Any] | None = None,
    provenance_by_claim: dict[str, dict[str, Any]] | None = None,
    document_support_by_claim: dict[str, dict[str, Any] | None] | None = None,
    ontology_by_claim: dict[str, dict[str, Any]] | None = None,
    escat_assessments: Any = None,
    diagnostic_context: dict[str, Any] | None = None,
    technical_records: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
    generated_at: str | None = None,
    dossier_version: str = "unified_dossier_contract/1.0",
) -> dict[str, Any]:
    before_hash = core_snapshot_fingerprint(core_result)
    core_copy = copy.deepcopy(core_result)
    after_hash = core_snapshot_fingerprint(core_copy)
    claims = list(core_copy.get("claims", []))
    extensions, diagnostics = build_claim_extensions(
        claims,
        provenance_by_claim=provenance_by_claim,
        document_support_by_claim=document_support_by_claim,
        ontology_by_claim=ontology_by_claim,
        escat_assessments=escat_assessments,
    )
    run_copy = copy.deepcopy(run or {})
    run_copy.setdefault("execution_mode", "OFFLINE")
    run_copy["core_snapshot_integrity"] = {
        "before_hash": before_hash,
        "after_hash": after_hash,
        "unchanged": before_hash == after_hash and core_copy == core_result,
    }
    return {
        "dossier_version": dossier_version,
        "run": run_copy,
        "case_context": copy.deepcopy(case_context or {}),
        "core_result": core_copy,
        "claim_extensions": extensions,
        "diagnostic_context": _diagnostic_context(diagnostic_context),
        "technical_records": copy.deepcopy(technical_records if technical_records is not None else core_copy.get("technical_records", [])),
        "module_status": build_module_status(),
        "limitations": list(limitations or []),
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "association_diagnostics": diagnostics,
    }
