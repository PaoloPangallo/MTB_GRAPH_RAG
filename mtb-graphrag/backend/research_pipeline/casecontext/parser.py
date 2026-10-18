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


def _raw_value(value: Any) -> str | None:
    if isinstance(value, dict):
        return value.get("raw_value")
    return value if isinstance(value, str) else None


def _canonical_assertion(value: Any) -> str:
    return {
        "ASSERTED": "PRESENT", "PRESENT": "PRESENT", "ABSENT": "ABSENT",
        "NEGATED": "NEGATED", "UNCERTAIN": "UNCERTAIN",
        "HYPOTHETICAL": "UNCERTAIN", "HISTORICAL": "HISTORICAL",
    }.get(str(value or "UNKNOWN").upper(), "UNKNOWN")


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


def normalize_empty_alterations(arguments: dict[str, Any]) -> dict[str, Any]:
    """Canonicalize only an alteration object that contains no information."""
    normalized = copy.deepcopy(arguments)
    for biomarker in normalized.get("biomarkers") or []:
        alteration = biomarker.get("alteration") if isinstance(biomarker, dict) else None
        if (
            isinstance(alteration, dict)
            and set(alteration) == {"raw_value", "quote"}
            and all(value is None or value == "" for value in alteration.values())
        ):
            biomarker["alteration"] = None
    return normalized


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
    normalized_arguments = normalize_empty_alterations(arguments)
    empty_alteration_normalized = normalized_arguments != arguments
    normalized_arguments, disease_event = normalize_disease_scalar(normalized_arguments, clinical_text)
    normalized_arguments, target_event = normalize_target_intervention_scalar(normalized_arguments, clinical_text)
    if disease_event is None and target_event is None and not empty_alteration_normalized:
        return response_json, None, None
    function["arguments"] = json.dumps(normalized_arguments, ensure_ascii=False, separators=(",", ":")) if isinstance(raw_arguments, str) else normalized_arguments
    return normalized_response, disease_event, target_event


def adapt_case_context(case_id: str, parser_output: dict[str, Any], clinical_text: str) -> dict[str, Any]:
    """Convert the minimal Parser v2 result to the legacy internal contract."""
    rich_contract = any(key in parser_output for key in (
        "diseases", "interventions", "trial_mentions", "companion_diagnostic_mentions",
    )) or any(
        isinstance(item, dict) and any(key in item for key in ("alteration_type", "assertion_status", "clinical_role"))
        for item in parser_output.get("biomarkers") or []
    )

    raw_diseases = parser_output.get("diseases") or []
    if not raw_diseases and parser_output.get("disease"):
        raw_diseases = [{
            "value": parser_output.get("disease"),
            "assertion_status": "UNKNOWN",
            "clinical_role": "PRIMARY",
        }]
    diseases: list[dict[str, Any]] = []
    for item in raw_diseases:
        value_payload = item.get("value") if isinstance(item, dict) and "value" in item else item
        if not _raw_value(value_payload):
            continue
        diseases.append({
            "value": _raw_value(value_payload),
            "normalized_value": _normalize(_raw_value(value_payload)),
            "source_spans": [_span(value_payload, clinical_text)] if _span(value_payload, clinical_text) else [],
            "assertion_status": _canonical_assertion((item or {}).get("assertion_status")),
            "clinical_role": (item or {}).get("clinical_role") or "PRIMARY",
            "quote": (value_payload or {}).get("quote") if isinstance(value_payload, dict) else _raw_value(value_payload),
        })

    biomarkers = []
    for item in parser_output.get("biomarkers") or []:
        gene = item.get("gene")
        alteration = item.get("alteration")
        gene_raw = _raw_value(gene)
        alteration_raw = _raw_value(alteration)
        raw_parts = [part for part in (gene_raw, alteration_raw) if part]
        gene_span = _span(gene, clinical_text) if isinstance(gene, dict) else None
        alteration_span = _span(alteration, clinical_text) if isinstance(alteration, dict) else None
        record = {
            "gene": gene_raw,
            "alteration": alteration_raw,
            "raw_value": " ".join(raw_parts) or None,
            "normalized_value": _normalize(" ".join(raw_parts)) if raw_parts else None,
            "source_spans": [span for span in (gene_span, alteration_span) if span],
        }
        if rich_contract:
            record.update({
                "alteration_type": item.get("alteration_type"),
                "assertion_status": _canonical_assertion(item.get("assertion_status")),
                "clinical_role": item.get("clinical_role") or "PRIMARY",
                "gene_source_spans": [gene_span] if gene_span else [],
                "alteration_source_spans": [alteration_span] if alteration_span else [],
                "gene_quote": (gene or {}).get("quote") if isinstance(gene, dict) else None,
                "alteration_quote": (alteration or {}).get("quote") if isinstance(alteration, dict) else None,
            })
        biomarkers.append(record)

    raw_interventions = parser_output.get("interventions") or []
    if not raw_interventions:
        raw_interventions.extend(
            {"name": item, "role": "PREVIOUS", "assertion_status": "UNKNOWN"}
            for item in parser_output.get("previous_interventions") or []
        )
        if parser_output.get("target_intervention"):
            raw_interventions.append({
                "name": parser_output["target_intervention"],
                "role": "TARGET", "assertion_status": "UNKNOWN",
            })
    interventions = []
    for item in raw_interventions:
        name = item.get("name") if isinstance(item, dict) else item
        name_raw = _raw_value(name)
        if not name_raw:
            continue
        interventions.append({
            "name": name_raw,
            "normalized_value": _normalize(name_raw),
            "source_spans": [_span(name, clinical_text)] if _span(name, clinical_text) else [],
            "role": (item or {}).get("role") or "UNCERTAIN",
            "assertion_status": _canonical_assertion((item or {}).get("assertion_status")),
            "quote": (name or {}).get("quote") if isinstance(name, dict) else name_raw,
        })

    def _mention_list(key: str) -> list[dict[str, Any]]:
        """Canonicalize structured mentions without hiding quote provenance.

        Retrieval-facing identifiers remain scalar (for example ``nct_id``),
        while every scalar that came from text gets a sibling ``*_quote``.
        This avoids forcing downstream matching code to understand the parser's
        internal ``{raw_value, quote}`` wrapper.
        """
        output: list[dict[str, Any]] = []
        fields = {
            "trial_mentions": ("nct_id", "trial_name", "phase", "status"),
            "companion_diagnostic_mentions": (
                "name", "associated_gene", "associated_drug", "specimen",
                "platform", "identifier",
            ),
        }
        for original in parser_output.get(key) or []:
            item = copy.deepcopy(original) if isinstance(original, dict) else {"value": original}
            for field_name in fields.get(key, ()):
                value_payload = item.get(field_name)
                if isinstance(value_payload, dict):
                    item[field_name] = _raw_value(value_payload)
                    item[f"{field_name}_quote"] = value_payload.get("quote") or item[field_name]
                elif value_payload is not None and f"{field_name}_quote" not in item:
                    item[f"{field_name}_quote"] = str(value_payload)
            output.append(item)
        return output

    target = next((item for item in interventions if item["role"] == "TARGET"), None)
    previous = [item for item in interventions if item["role"] == "PREVIOUS"]
    legacy_disease = diseases[0] if diseases else None

    result = {
        "case_id": case_id,
        "schema_version": "end-to-end-pilot-casecontext/1.0",
        "disease": _field(parser_output.get("disease") or (
            {"raw_value": legacy_disease["value"], "quote": legacy_disease["quote"]}
            if legacy_disease else None
        ), clinical_text),
        "biomarkers": biomarkers,
        "previous_interventions": [
            _field({"raw_value": item["name"], "quote": item["quote"]}, clinical_text)
            for item in previous
        ],
        "target_intervention": (
            _field({"raw_value": target["name"], "quote": target["quote"]}, clinical_text)
            if target else None
        ),
        "query_intent": parser_output.get("query_intent"),
        "clinical_question": parser_output.get("clinical_question"),
        "uncertainties": list(parser_output.get("ambiguities") or []),
    }
    if rich_contract:
        result.update({
            "diseases": diseases,
            "interventions": interventions,
            "trial_mentions": _mention_list("trial_mentions"),
            "companion_diagnostic_mentions": _mention_list("companion_diagnostic_mentions"),
            "ambiguities": list(parser_output.get("ambiguities") or []),
        })
    return result


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
        repairable_shape = (
            attempt["transport_result"] == "INVALID_TOOL_ARGUMENTS"
            and bool(attempt["transport_reason_codes"])
            and all(reason.endswith("_KEYS_INVALID") for reason in attempt["transport_reason_codes"])
        )
        if (attempt["transport_result"] != "FORCED_TOOL_IGNORED" and not repairable_shape) or attempt_number == 2:
            break
        if attempt["transport_result"] == "INVALID_TOOL_ARGUMENTS":
            messages.append({
                "role": "user",
                "content": "The previous tool arguments failed schema validation: "
                + ", ".join(attempt["transport_reason_codes"])
                + ". Extract again from the original clinical text using the same schema. "
                "Every value object needs raw_value and quote; use null for absent values, "
                "never {}. Preserve literal quotes and do not infer missing facts.",
            })
            payload = tr.build_payload(prompt.CASECONTEXT_TOOL_DEFINITION, prompt.TOOL_NAME, messages, seed=run_index, max_tokens=2048)

    final = structured_attempts[-1]
    parser_attempts = [
        {
            "attempt": item["attempt"],
            "http_status": item["status_code"],
            "finish_reason": item["finish_reason"],
            "tool_calls_present": item["tool_calls_present"],
            "reason_codes": item["transport_reason_codes"],
            "transport_result": item["transport_result"],
            "retry_count": item["retry_count"],
            "input_tokens": item["input_tokens"],
            "output_tokens": item["output_tokens"],
            "latency_ms": item["latency_ms"],
        }
        for item in structured_attempts
    ]
    retry_result = None
    if len(structured_attempts) == 2:
        first_result = structured_attempts[0]["transport_result"]
        if final["transport_result"] == "FORCED_TOOL_VALID":
            retry_result = first_result + "_RECOVERED"
        else:
            retry_result = first_result + "_FINAL"

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
        "input_tokens": sum(item["input_tokens"] for item in structured_attempts) if all(type(item["input_tokens"]) is int for item in structured_attempts) else None,
        "output_tokens": sum(item["output_tokens"] for item in structured_attempts) if all(type(item["output_tokens"]) is int for item in structured_attempts) else None,
        "latency_ms": sum(item["latency_ms"] for item in structured_attempts),
        "retry_count": sum(item["retry_count"] for item in structured_attempts),
        "model_call_count": len(structured_attempts) + sum(item["retry_count"] for item in structured_attempts),
        "token_usage_complete": all(type(item["input_tokens"]) is int and type(item["output_tokens"]) is int and not item["retry_count"] for item in structured_attempts),
        "status_code": final["status_code"],
    }
