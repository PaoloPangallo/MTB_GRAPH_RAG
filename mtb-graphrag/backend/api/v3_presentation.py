"""Presentation adapter for the native V3 retrieval result.

The retriever remains the source of truth for buckets and gate decisions.  This
module only projects its typed output into a product-facing response: clinical
claims are kept separate from technical records, provenance is made explicit,
and internal reason codes receive stable human-readable messages.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.pipeline.evidence.retrieval.pipeline import RetrievalOutcome

_BUCKETS = {
    "primary_ranked_results": "primary",
    "retained_with_warning": "warning",
    "audit_only_results": "audit",
    "rejected_by_native_constraints": "rejected",
}

_REASON_MESSAGES = {
    "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM": "Record tecnico utilizzato per conservare la provenienza",
    "CLASS_RELATION_UNVERIFIED": "La relazione tra classe e intervento non e verificata",
    "BIOMARKER_MISMATCH": "Il biomarcatore non coincide con quello del caso",
    "NATIVE_BIOMARKER_MISMATCH": "Il biomarcatore non coincide con quello del caso",
    "DISEASE_MISMATCH": "La malattia non coincide con quella del caso",
    "INTERVENTION_MISMATCH": "Il trattamento non coincide con quello richiesto",
    "NATIVE_INTERVENTION_MISMATCH": "Il trattamento non coincide con quello richiesto",
    "CLAIM_DISEASE_SCOPE_BROADER_THAN_QUERY": "L'ambito di malattia e piu ampio della domanda",
    "RESULT_NOT_SEPARABLE_FOR_QUERY_SUBTYPE": "Il risultato non e separabile per il sottotipo richiesto",
    "PRECLINICAL_NOT_CLINICAL_BENEFIT": "L'evidenza e preclinica e non dimostra beneficio clinico",
    "SINGLE_INCOMPATIBLE_GATE_BLOCKS_PRIMARY": "Un gate strutturale incompatibile blocca la promozione",
    "CLAIM_DEPRECATED": "La claim e ritirata dal corpus attivo",
}

_GATE_ORDER = (
    ("claim_status_result", "claim_status"),
    ("domain_match_result", "domain"),
    ("biomarker_match_result", "biomarker"),
    ("disease_match_result", "disease"),
    ("intervention_match_result", "intervention_identity"),
    ("formulation_match_result", "formulation"),
    ("direction_match_result", "direction"),
)


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _message(code: str) -> str:
    return _REASON_MESSAGES.get(code, "Decisione strutturale registrata dal gate V3")


def _reason_codes(result: Any) -> list[dict[str, str]]:
    return [
        {"code": str(code), "human_message": _message(str(code))}
        for code in (getattr(result, "reason_codes", ()) or ())
    ]


def _status_for_gate(axis: Mapping[str, Any], bucket: str) -> str:
    if axis.get("compatible") is False or axis.get("rejected_by_native_constraints"):
        return "fail"
    if axis.get("status") in {"deprecated_claim", "audit_only"}:
        return "not_applicable"
    if bucket == "warning":
        return "warning"
    return "pass"


def _gate_trace(result: Any) -> list[dict[str, Any]]:
    gate = _as_dict(getattr(result, "gate", {}))
    final_bucket = _BUCKETS.get(str(getattr(result, "bucket", "")), "audit")
    trace: list[dict[str, Any]] = []
    for key, name in _GATE_ORDER:
        axis = _as_dict(gate.get(key))
        if not axis:
            continue
        codes = [str(code) for code in (axis.get("reason_codes") or ())]
        trace.append(
            {
                "gate": name,
                "status": _status_for_gate(axis, final_bucket),
                "reason_code": codes[0] if codes else None,
                "reason_codes": codes,
                "message": _message(codes[0]) if codes else "Gate valutato senza reason code",
            }
        )
    if not trace and gate:
        trace.append(
            {
                "gate": "structural_gate",
                "status": "pass" if final_bucket == "primary" else final_bucket,
                "reason_code": None,
                "reason_codes": [],
                "message": "Traccia strutturale disponibile nel risultato nativo",
            }
        )
    return trace


def _provenance(result: Any) -> dict[str, Any]:
    source = _as_dict(getattr(result, "provenance", {}))
    source_ids = [str(item) for item in (source.get("source_ids") or ())]
    locators = [dict(item) for item in (source.get("locators") or ())]
    source_unit_ids = [str(item) for item in (source.get("source_unit_ids") or ())]
    parent_id = str(source.get("parent_id") or getattr(result, "parent_id", "") or "") or None
    if locators:
        status = "VERIFIED_LOCATOR"
    elif source_ids or source_unit_ids:
        status = "ALTERNATIVE_SOURCE_AVAILABLE"
    elif parent_id:
        status = "PARENT_ONLY"
    else:
        status = "SOURCE_IDENTIFIER_MISSING"
    missing: list[str] = []
    if not source_ids:
        missing.append("source_ids")
    if not locators:
        missing.append("locators")
    return {
        "status": status,
        "pmid": next((item for item in source_ids if item.upper().startswith("PUBMED:")), None),
        "doi": next((item for item in source_ids if item.upper().startswith("DOI:")), None),
        "nct": next((item for item in source_ids if item.upper().startswith("NCT:")), None),
        "url": next((item.get("url") for item in locators if item.get("url")), None),
        "locator": locators[0] if locators else None,
        "source_ids": source_ids,
        "source_unit_ids": source_unit_ids,
        "parent_record_id": parent_id,
        "source_unit_id": source_unit_ids[0] if source_unit_ids else None,
        "is_verifiable": bool(locators or source_ids or source_unit_ids),
        "missing_fields": missing,
        "raw": source,
    }


def _candidate_kind(result: Any) -> str:
    claim_type = str(getattr(result, "claim_type", "") or "")
    gate = _as_dict(getattr(result, "gate", {}))
    status = _as_dict(gate.get("claim_status_result"))
    if claim_type == "graph_evidence_record":
        return "provenance_container"
    if claim_type == "unresolved_association" or str(getattr(result, "claim_id", "")).startswith("UNR-"):
        return "unresolved_association"
    if claim_type == "unsupported_association" or str(getattr(result, "claim_id", "")).startswith("UNS-"):
        return "unsupported_association"
    if bool(status.get("deprecated")) or claim_type == "deprecated_claim":
        return "deprecated_claim"
    return "evidence_claim"


def _claim_record(result: Any) -> dict[str, Any]:
    gate = _as_dict(getattr(result, "gate", {}))
    direction = _as_dict(gate.get("direction_match_result"))
    formulation = _as_dict(gate.get("formulation_match_result"))
    status = _as_dict(gate.get("claim_status_result"))
    bucket = _BUCKETS.get(str(getattr(result, "bucket", "")), "audit")
    intervention = str(getattr(result, "canonical_intervention", "") or "") or None
    members = [str(item) for item in (getattr(result, "intervention_members", ()) or ())]
    # The native V3 result has no source claim text. Never synthesize a clinical
    # sentence from tuple fields; the UI can use the structured fields and ID.
    claim_text = None
    return {
        "claim_id": str(getattr(result, "claim_id", "")),
        "candidate_kind": _candidate_kind(result),
        "subject": None,
        "relation": None,
        "object": None,
        "structured_tuple_complete": False,
        "claim_text": claim_text,
        "disease": str(getattr(result, "disease_scope", "") or "") or None,
        "biomarker": str(getattr(result, "biomarker", "") or "") or None,
        "intervention": intervention,
        "formulation": formulation.get("claim_form"),
        "regimen": members if len(members) > 1 else None,
        "direction": direction.get("direction_match_type"),
        "evidence_type": str(getattr(result, "claim_type", "") or "") or None,
        "applicability": bucket,
        "separability": formulation.get("relation_status"),
        "status": status.get("status"),
        "bucket": bucket,
        "score": _as_dict(getattr(result, "score", {})),
        "rank": int(getattr(result, "rank", 0) or 0),
        "reason_codes": _reason_codes(result),
        "gate_trace": _gate_trace(result),
        "qualifiers": [str(item) for item in (getattr(result, "warnings", ()) or ())],
        "parent_graph_evidence_record": {
            "parent_id": str(getattr(result, "parent_id", "") or "") or None,
            "graph_evidence_id": str(getattr(result, "graph_evidence_id", "") or "") or None,
        },
        "source_unit": _provenance(result).get("source_unit_id"),
        "provenance": _provenance(result),
    }


def _technical_record(result: Any) -> dict[str, Any]:
    record = _claim_record(result)
    kind = record["candidate_kind"]
    record["technical_kind"] = kind
    return record


def present_retrieval_outcome(outcome: RetrievalOutcome) -> dict[str, Any]:
    """Create the stable product response without changing native semantics."""
    payload = outcome.payload
    results = list(getattr(payload, "all_results", ()) or ())
    evidence: dict[str, list[dict[str, Any]]] = {
        "primary": [], "warning": [], "audit": [], "rejected": []
    }
    technical: dict[str, list[dict[str, Any]]] = {
        "provenance_containers": [],
        "unresolved_associations": [],
        "unsupported_associations": [],
        "deprecated_claims": [],
        "other": [],
    }
    for result in results:
        record = _claim_record(result)
        kind = record["candidate_kind"]
        if kind == "evidence_claim":
            evidence[record["bucket"]].append(record)
        elif kind == "provenance_container":
            technical["provenance_containers"].append(_technical_record(result))
        elif kind == "unresolved_association":
            technical["unresolved_associations"].append(_technical_record(result))
        elif kind == "unsupported_association":
            technical["unsupported_associations"].append(_technical_record(result))
        elif kind == "deprecated_claim":
            technical["deprecated_claims"].append(_technical_record(result))
        else:
            technical["other"].append(_technical_record(result))
    claim_records = sum(len(items) for items in evidence.values())
    technical_count = sum(len(items) for items in technical.values())
    native_query = dict(getattr(payload, "query", {}) or {})
    case_context = dict(native_query.get("normalized") or native_query)
    gate_query = dict(case_context.get("gate_query") or {})
    for key, value in gate_query.items():
        case_context.setdefault(key, value)
    if native_query.get("original") is not None:
        case_context["original"] = dict(native_query.get("original") or {})
    return {
        "case_context": case_context,
        "summary": {
            "total_records": int(getattr(payload, "candidate_count", len(results)) or len(results)),
            "claim_records": claim_records,
            "technical_records": technical_count,
            "primary": len(evidence["primary"]),
            "warning": len(evidence["warning"]),
            "audit_claims": len(evidence["audit"]),
            "rejected_claims": len(evidence["rejected"]),
        },
        "evidence": evidence,
        "technical_records": technical,
        "abstention": not evidence["primary"] and not evidence["warning"],
        "metadata": {
            "backend_name": outcome.backend_name,
            "repository_version": outcome.repository_version,
            "policy_mode": outcome.policy_mode,
            "corpus_hash": str(getattr(payload, "corpus_hash", "")),
            "gate_version": str(getattr(payload, "gate_version", "")),
            "schema_version": str(getattr(payload, "schema_version", "")),
            "latency_ms": int(outcome.latency_ms),
            "latency_breakdown_ms": dict(getattr(payload, "latency_ms", {}) or {}),
            "run_id": str(getattr(payload, "run_id", "")),
            "pipeline_version": outcome.pipeline_version,
            "warnings": list(outcome.warnings),
            "gate_decisions": dict(getattr(payload, "gate_decisions", {}) or {}),
        },
    }


__all__ = ["present_retrieval_outcome"]
