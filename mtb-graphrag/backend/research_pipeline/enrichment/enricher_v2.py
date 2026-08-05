"""Paper Context Enricher v2.0 caller. All metadata (enrichment_id, case_id,
candidate_id, paper_id, model, prompt_version, transport_version, payload
hash, timestamp, lineage) is added locally after a valid transport -- never
produced by the model. Local normalization is limited to trimming outer
whitespace on the model's own string fields; no punctuation fixes, no
translation, no quote reconstruction, no regex-based free-text recovery, no
second LLM pass (section 4).
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

from . import prompt_v2 as prompt
from . import transport as tr
from .transport_v2 import transport_result_v2


def _enrichment_id(case_id: str, candidate_id: str, paper_id: str, run_index: int) -> str:
    payload = json.dumps({"case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id, "run_index": run_index, "version": prompt.PROMPT_VERSION}, sort_keys=True)
    return "PCEV2-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _trim_only(args: dict[str, str]) -> dict[str, str]:
    """Trims outer whitespace only -- no other normalization is applied to model output."""
    return {key: value.strip() if isinstance(value, str) else value for key, value in args.items()}


def call_enricher_v2(case_id: str, candidate_id: str, paper_id: str, case_context: dict[str, Any], candidate_summary: dict[str, Any], drug: str, source_units: list[dict[str, Any]], run_index: int = 0) -> dict:
    messages = [
        {"role": "system", "content": prompt.SYSTEM_PROMPT},
        {"role": "user", "content": prompt.render_request(case_context, candidate_summary, drug, paper_id, source_units)},
    ]
    payload = tr.build_payload(prompt.TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=1024)
    started = time.perf_counter()
    status_code, response_json, network_error, retry_count = tr.post_with_infra_retry(payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    response_hash = tr.sha(str(response_json)) if response_json is not None else None
    transport_outcome, finish_reason, raw_args, reasons = transport_result_v2(status_code, response_json, network_error)

    enrichment = None
    if raw_args is not None:
        args = _trim_only(raw_args)
        enrichment = {
            "enrichment_id": _enrichment_id(case_id, candidate_id, paper_id, run_index),
            "case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id,
            "decision": args["decision"], "source_unit_id": args["source_unit_id"],
            "author_claim_quote": args["author_claim_quote"], "author_context_summary": args["author_context_summary"],
            "abstention_reason": args["abstention_reason"],
            "model": tr.MODEL, "prompt_version": prompt.PROMPT_VERSION, "transport_version": prompt.TRANSPORT_VERSION,
            "payload_hash": tr.sha(json.dumps(args, ensure_ascii=False, sort_keys=True)),
            "timestamp": datetime.now(timezone.utc).isoformat(), "lineage": {"case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id, "run_index": run_index},
        }

    usage = (response_json or {}).get("usage") or {}
    return {
        "case_id": case_id, "candidate_id": candidate_id, "paper_id": paper_id, "run_index": run_index,
        "model": tr.MODEL, "endpoint": tr.OPENAI_COMPAT_ENDPOINT, "delivery_transport": "OLLAMA_FORCED_TOOL_CHOICE_V2",
        "prompt_version": prompt.PROMPT_VERSION, "transport_version": prompt.TRANSPORT_VERSION,
        "transport_result": transport_outcome, "transport_reason_codes": reasons, "finish_reason": finish_reason,
        "enrichment": enrichment, "raw_response_hash": response_hash,
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "latency_ms": latency_ms, "retry_count": retry_count, "status_code": status_code,
    }
