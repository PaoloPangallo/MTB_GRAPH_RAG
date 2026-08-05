"""LLM CaseContext Parser: free clinical text -> raw tool-call arguments ->
CaseContext dict. Never sees the structured record, never queries the KG."""
from __future__ import annotations

import time

from . import prompt
from ..enrichment import transport as tr


def call_parser(case_id: str, clinical_text: str, run_index: int = 0) -> dict:
    messages = [
        {"role": "system", "content": prompt.SYSTEM_PROMPT + "\n" + prompt.TASK_PROMPT},
        {"role": "user", "content": prompt.render_request(case_id, clinical_text)},
    ]
    payload = tr.build_payload(prompt.CASECONTEXT_TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=2048)
    started = time.perf_counter()
    status_code, response_json, network_error, retry_count = tr.post_with_infra_retry(payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    response_hash = tr.sha(str(response_json)) if response_json is not None else None
    transport, finish_reason, args, reasons = tr.transport_result(status_code, response_json, network_error, prompt.TOOL_NAME, prompt.tool_argument_errors)
    usage = (response_json or {}).get("usage") or {}
    return {
        "case_id": case_id, "run_index": run_index, "model": tr.MODEL, "endpoint": tr.OPENAI_COMPAT_ENDPOINT,
        "delivery_transport": tr.OLLAMA_FORCED_TOOL_CHOICE, "prompt_version": prompt.PROMPT_VERSION,
        "transport_result": transport, "transport_reason_codes": reasons, "finish_reason": finish_reason,
        "case_context_raw": args, "raw_response_hash": response_hash,
        "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
        "latency_ms": latency_ms, "retry_count": retry_count, "status_code": status_code,
    }
