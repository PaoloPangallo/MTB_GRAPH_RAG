"""Canonical Paper Reader caller for prompt/transport 3.0."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from . import prompt_v3 as prompt
from . import transport as tr


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
    if not isinstance(args, dict) or set(args) != required or any(not isinstance(args[k], str) for k in required):
        return "INVALID_TOOL_ARGUMENTS", None, ["ARGUMENT_SHAPE_INVALID"]
    if args["decision"] not in {"QUOTE", "ABSTAIN"} \
            or args["observed_direction"] not in prompt.DIRECTIONS \
            or args["observed_evidence_type"] not in prompt.EVIDENCE_TYPES:
        return "INVALID_TOOL_ARGUMENTS", None, ["ENUM_VALUE_INVALID"]
    return "V3_TRANSPORT_VALID", {k: value.strip() for k, value in args.items()}, []


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
