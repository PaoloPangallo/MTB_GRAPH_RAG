"""STAGE 9 — research-only dossier preview. Built deterministically from
already-validated data only. Gemma's output appears exclusively under
"author_context" and never overwrites claim/status/support_mask/gate/
provenance."""
from __future__ import annotations

from typing import Any


def build_dossier_preview(case_id: str, case_context: dict[str, Any], verification_summary: dict[str, Any], candidate_therapies: list[dict[str, Any]], limitations: list[str]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "case_context": case_context,
        "case_context_verification": verification_summary,
        "candidate_therapies": candidate_therapies,
        "limitations": limitations,
        "provenance": {
            "dossier_kind": "research_only_end_to_end_pilot_preview",
            "dossier_version": "end-to-end-pilot-dossier/1.0",
            "gemma_role": "paper_context_enricher_only",
            "gemma_never_decides": ["support_status", "direction", "contradiction", "gate", "score", "bucket"],
            "not_wired_to_production_runtime": True,
        },
    }


def build_candidate_therapy_entry(candidate: dict[str, Any], graph_relation: str, document_support: dict[str, Any], enrichments: list[dict[str, Any]], validation_results: list[dict[str, Any]], evaluation: dict[str, Any]) -> dict[str, Any]:
    interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
    return {
        "candidate_id": candidate["candidate_id"],
        "drug": interventions[0] if interventions else None,
        "graph_relation": graph_relation,
        "document_support": document_support,
        "author_context": enrichments,
        "validation_results": validation_results,
        "gate_results": {"bucket": evaluation["gate_bucket"], "support_mask": evaluation["support_mask"]},
        "status": evaluation["status"],
        "warnings": evaluation["warnings"],
    }
