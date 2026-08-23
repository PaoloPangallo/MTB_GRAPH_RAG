"""LLM CaseContext Parser: free clinical text -> raw tool-call arguments ->
CaseContext dict. Never sees the structured record, never queries the KG."""
from __future__ import annotations

import copy
import json
import re
import time
from typing import Any

from . import prompt
from ..enrichment import transport as tr


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.strip()) or None


def _span(payload: dict[str, Any] | None, clinical_text: str) -> dict[str, Any] | None:
    if not payload:
        return None
    quote = payload.get("quote")
    if not isinstance(quote, str) or not quote:
        return None
    start = clinical_text.find(quote)
    return {
        "quote": quote,
        "start_offset": start if start >= 0 else None,
        "end_offset": start + len(quote) if start >= 0 else None,
    }


def _field(payload: dict[str, Any] | None, clinical_text: str) -> dict[str, Any]:
    raw = (payload or {}).get("raw_value")
    span = _span(payload, clinical_text)
    return {
        "raw_value": raw,
        "normalized_value": _normalize(raw),
        "source_spans": [span] if span else [],
    }


def normalize_disease_scalar(arguments: dict[str, Any], clinical_text: str) -> tuple[dict[str, Any], dict[str, str] | None]:
    """Convert only a verifiable scalar disease value to the v2 value object."""
    disease = arguments.get("disease")
    if not isinstance(disease, str):
        return arguments, None
    candidate = disease.strip()
    if not candidate:
        return arguments, None
    start = clinical_text.find(candidate)
    if start < 0:
        return arguments, None
    quote = clinical_text[start:start + len(candidate)]
    normalized = dict(arguments)
    normalized["disease"] = {"raw_value": candidate, "quote": quote}
    return normalized, {
        "code": "DISEASE_SCALAR_NORMALIZED",
        "original_value": disease,
        "matched_quote": quote,
    }


def normalize_target_intervention_scalar(arguments: dict[str, Any], clinical_text: str) -> tuple[dict[str, Any], dict[str, str] | None]:
    """Convert only a uniquely verifiable scalar target intervention."""
    target = arguments.get("target_intervention")
    if not isinstance(target, str):
        return arguments, None
    if not target or clinical_text.count(target) != 1:
        return arguments, None
    start = clinical_text.find(target)
    normalized = dict(arguments)
    normalized["target_intervention"] = {"raw_value": target, "quote": clinical_text[start:start + len(target)]}
    return normalized, {
        "code": "TARGET_INTERVENTION_SCALAR_NORMALIZED",
        "original_value": target,
        "matched_quote": normalized["target_intervention"]["quote"],
    }


def _normalize_disease_in_response(
    response_json: dict[str, Any] | None,
    clinical_text: str,
) -> tuple[dict[str, Any] | None, dict[str, str] | None, dict[str, str] | None]:
    if not isinstance(response_json, dict):
        return response_json, None, None
    normalized_response = copy.deepcopy(response_json)
    choices = normalized_response.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    tool_calls = message.get("tool_calls") or []
    function = (tool_calls[0].get("function") or {}) if tool_calls else {}
    raw_arguments = function.get("arguments")
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments)
        except (TypeError, ValueError):
            return response_json, None, None
    else:
        arguments = raw_arguments
    if not isinstance(arguments, dict):
        return response_json, None, None
    normalized_arguments, disease_event = normalize_disease_scalar(arguments, clinical_text)
    normalized_arguments, target_event = normalize_target_intervention_scalar(normalized_arguments, clinical_text)
    if disease_event is None and target_event is None:
        return response_json, None, None
    function["arguments"] = json.dumps(normalized_arguments, ensure_ascii=False, separators=(",", ":")) if isinstance(raw_arguments, str) else normalized_arguments
    return normalized_response, disease_event, target_event


def adapt_case_context(case_id: str, parser_output: dict[str, Any], clinical_text: str) -> dict[str, Any]:
    """Convert the minimal Parser v2 result to the legacy internal contract."""
    biomarkers = []
    for item in parser_output.get("biomarkers") or []:
        gene = item.get("gene")
        alteration = item.get("alteration")
        gene_raw = (gene or {}).get("raw_value")
        alteration_raw = (alteration or {}).get("raw_value")
        raw_parts = [part for part in (gene_raw, alteration_raw) if part]
        spans = [span for part in (gene, alteration) for span in [_span(part, clinical_text)] if span]
        biomarkers.append({
            "gene": gene_raw,
            "alteration": alteration_raw,
            "raw_value": " ".join(raw_parts) or None,
            "normalized_value": _normalize(" ".join(raw_parts)) if raw_parts else None,
            "source_spans": spans,
        })

    return {
        "case_id": case_id,
        "schema_version": "end-to-end-pilot-casecontext/1.0",
        "disease": _field(parser_output.get("disease"), clinical_text),
        "biomarkers": biomarkers,
        "previous_interventions": [_field(item, clinical_text) for item in parser_output.get("previous_interventions") or []],
        "target_intervention": _field(parser_output["target_intervention"], clinical_text) if parser_output.get("target_intervention") else None,
        "query_intent": parser_output.get("query_intent"),
        "clinical_question": clinical_text,
        "uncertainties": [],
    }


def _run_parser_attempt(payload: dict[str, Any], clinical_text: str) -> dict[str, Any]:
    started = time.perf_counter()
    status_code, response_json, network_error, retry_count, raw_diagnostics = tr.post_with_infra_retry_with_diagnostics(payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    response_hash = tr.sha(str(response_json)) if response_json is not None else None
    validation_response, disease_normalization, target_intervention_normalization = _normalize_disease_in_response(response_json, clinical_text)
    transport, finish_reason, args, reasons = tr.transport_result(status_code, validation_response, network_error, prompt.TOOL_NAME, prompt.tool_argument_errors)
    usage = (response_json or {}).get("usage") or {}
    choices = (response_json or {}).get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    tool_calls = message.get("tool_calls") or []
    function = (tool_calls[0].get("function") or {}) if tool_calls else {}
    parser_diagnostics = {
        **raw_diagnostics,
        "finish_reason": finish_reason,
        "message_content": message.get("content"),
        "tool_calls_present": bool(tool_calls),
        "tool_name": function.get("name"),
        "function_arguments_raw": function.get("arguments"),
        "validation_errors": reasons,
        "disease_normalization": disease_normalization,
        "target_intervention_normalization": target_intervention_normalization,
    }
    return {
        "transport_result": transport,
        "transport_reason_codes": reasons,
        "finish_reason": finish_reason,
        "case_context_v2": args,
        "parser_diagnostics": parser_diagnostics,
        "raw_response_hash": response_hash,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "latency_ms": latency_ms,
        "retry_count": retry_count,
        "status_code": status_code,
        "tool_calls_present": bool(tool_calls),
    }


def call_parser(case_id: str, clinical_text: str, run_index: int = 0) -> dict:
    messages = [
        {"role": "system", "content": prompt.SYSTEM_PROMPT + "\n" + prompt.TASK_PROMPT},
        {"role": "user", "content": prompt.render_request(case_id, clinical_text)},
    ]
    payload = tr.build_payload(prompt.CASECONTEXT_TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=2048)
    structured_attempts: list[dict[str, Any]] = []
    for attempt_number in (1, 2):
        attempt = _run_parser_attempt(payload, clinical_text)
        attempt["attempt"] = attempt_number
        structured_attempts.append(attempt)
        if attempt["transport_result"] != "FORCED_TOOL_IGNORED" or attempt_number == 2:
            break

    final = structured_attempts[-1]
    parser_attempts = [
        {
            "attempt": item["attempt"],
            "http_status": item["status_code"],
            "finish_reason": item["finish_reason"],
            "tool_calls_present": item["tool_calls_present"],
            "reason_codes": item["transport_reason_codes"],
            "transport_result": item["transport_result"],
        }
        for item in structured_attempts
    ]
    retry_result = None
    if len(structured_attempts) == 2:
        if final["transport_result"] == "FORCED_TOOL_VALID":
            retry_result = "FORCED_TOOL_IGNORED_RECOVERED"
        elif final["transport_result"] == "FORCED_TOOL_IGNORED":
            retry_result = "FORCED_TOOL_IGNORED_FINAL"

    parser_diagnostics = dict(final["parser_diagnostics"])
    parser_diagnostics["attempts"] = parser_attempts
    parser_diagnostics["retry_result"] = retry_result
    internal_context = adapt_case_context(case_id, final["case_context_v2"], clinical_text) if final["case_context_v2"] is not None else None
    return {
        "case_id": case_id, "run_index": run_index, "model": tr.model_name(), "endpoint": tr.endpoint_url(),
        "delivery_transport": tr.OLLAMA_FORCED_TOOL_CHOICE, "prompt_version": prompt.PROMPT_VERSION,
        "transport_result": final["transport_result"], "transport_reason_codes": final["transport_reason_codes"],
        "finish_reason": final["finish_reason"], "case_context_raw": internal_context,
        "case_context_v2": final["case_context_v2"], "parser_diagnostics": parser_diagnostics,
        "parser_attempts": parser_attempts, "retry_result": retry_result,
        "raw_response_hash": final["raw_response_hash"],
        "input_tokens": final["input_tokens"], "output_tokens": final["output_tokens"],
        "latency_ms": final["latency_ms"], "retry_count": final["retry_count"], "status_code": final["status_code"],
    }
