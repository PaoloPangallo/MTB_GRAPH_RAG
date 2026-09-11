"""Canonical Paper Reader caller for prompt/transport 3.0."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from . import prompt_v3 as prompt
from . import transport as tr
from .canonical_normalizer import normalize_observed_relation


def _transport(status: int | None, response: dict | None, error: str | None):
    if error or (status is not None and status >= 400):
        return "HTTP_ERROR", None, [error or f"HTTP_{status}"]
    calls = (((response or {}).get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
    if len(calls) != 1 or (calls[0].get("function") or {}).get("name") != prompt.TOOL_NAME:
        return "INVALID_TOOL_CALL", None, ["EXPECTED_SINGLE_READER_TOOL_CALL"]
    raw = (calls[0].get("function") or {}).get("arguments")
    try:
        args = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENTS_NOT_JSON"]
    required = set(prompt.TOOL_SCHEMA["required"])
    if not isinstance(args, dict) or not required.issubset(args) or any(
            not isinstance(args[k], (str, dict, type(None))) for k in required):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENT_SHAPE_INVALID"]
    if args["decision"] not in {"QUOTE", "ABSTAIN"} \
            or args.get("observed_direction", "UNKNOWN") not in prompt.DIRECTIONS \
            or args.get("observed_evidence_type", "UNKNOWN") not in prompt.EVIDENCE_TYPES:
        return "INVALID_TOOL_ARGUMENTS", None, ["ENUM_VALUE_INVALID"]
    if args["decision"] == "ABSTAIN" and args.get("abstain_reason") not in prompt.ABSTAIN_REASONS:
        return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_REASON_INVALID"]
    relation = args.get("observed_relation")
    if args["decision"] == "QUOTE":
        if not isinstance(args.get("quote"), str) or not isinstance(args.get("source_unit_id"), str):
            return "INVALID_TOOL_ARGUMENTS", None, ["QUOTE_FIELDS_REQUIRED_FOR_QUOTE"]
        if not isinstance(relation, dict):
            return "INVALID_TOOL_ARGUMENTS", None, ["OBSERVED_RELATION_REQUIRED_FOR_QUOTE"]
        if args.get("abstain_reason") is not None:
            return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_REASON_PRESENT_DESPITE_QUOTE"]
    if args["decision"] == "ABSTAIN":
        if relation is not None or args.get("quote") is not None or args.get("source_unit_id") is not None:
            return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_FIELDS_PRESENT"]
        if args.get("abstain_reason") not in prompt.ABSTAIN_REASONS:
            return "INVALID_TOOL_ARGUMENTS", None, ["ABSTAIN_REASON_REQUIRED_FOR_ABSTAIN"]
    if isinstance(relation, dict):
        if not isinstance(relation.get("subjects"), list) or any(not isinstance(item, dict) for item in relation["subjects"]):
            return "INVALID_TOOL_ARGUMENTS", None, ["OBSERVED_RELATION_SUBJECTS_INVALID"]
        args["observed_relation"] = normalize_observed_relation(relation)
        # Legacy fields are compatibility telemetry derived from the canonical
        # relation; they are never accepted as an independent source of truth.
        subjects = args["observed_relation"].get("subjects") or []
        args.update({
            "observed_disease": args["observed_relation"].get("disease") or "",
            "observed_gene": next((item["surface_value"] for item in subjects if item.get("type") == "GENE"), ""),
            "observed_alteration": next((item["surface_value"] for item in subjects if item.get("type") == "ALTERATION"), ""),
            "observed_drug": args["observed_relation"].get("intervention") or "",
            "observed_direction": args["observed_relation"].get("effect_direction") or "UNKNOWN",
            "observed_evidence_type": args["observed_relation"].get("evidence_scope") or "UNKNOWN",
        })
    return "V3_TRANSPORT_VALID", {
        k: value.strip() if isinstance(value, str) else value for k, value in args.items()
    }, []


def call_enricher_v3(case_id: str, candidate_id: str, paper_id: str,
                     case_context: dict[str, Any], candidate: dict[str, Any],
                     source_units: list[dict[str, Any]], run_index: int = 0) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": prompt.SYSTEM_PROMPT},
        {"role": "user", "content": prompt.render_request(case_context, candidate, paper_id, source_units)},
    ]
    payload = tr.build_payload(prompt.TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=1400)
    started = time.perf_counter()
    status, response, error, retries = tr.post_with_infra_retry(payload)
    outcome, args, reasons = _transport(status, response, error)
    enrichment = None if args is None else {
        **args, "author_claim_quote": args["quote"], "candidate_id": candidate_id,
        "case_id": case_id, "paper_id": paper_id, "model": tr.model_name(),
        "prompt_version": prompt.PROMPT_VERSION, "transport_version": prompt.TRANSPORT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    usage = (response or {}).get("usage") or {}
    return {
        "case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id,
        "model": tr.model_name(), "prompt_version": prompt.PROMPT_VERSION,
        "transport_version": prompt.TRANSPORT_VERSION, "transport_result": outcome,
        "transport_reason_codes": reasons, "enrichment": enrichment,
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "latency_ms": round((time.perf_counter() - started) * 1000, 3), "retry_count": retries,
    }
