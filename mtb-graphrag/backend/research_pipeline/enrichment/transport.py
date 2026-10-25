"""Generic technical transport infrastructure shared by this pilot's two LLM
components (CaseContext Parser, Paper Context Enricher). Deliberately
self-contained: reuses only the generic *pattern* already validated in the
frozen claim-extractor research work (forced tool_choice over Ollama's
OpenAI-compatible endpoint, infra-only retry, sha256 response hashing) --
no import from benchmarks/mtb_evidence/document_grounded_claims/
llm_claim_extractor, and no claim/support/gate decision logic here.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import requests

from .. import llm_config
from ..budget import active_budget, CallBudgetExceeded
from copy import deepcopy

MAX_FORMAT_ATTEMPTS = 2


def maximum_structured_call_attempts() -> int:
    """Physical upper bound under the existing format and infrastructure retries."""
    return MAX_FORMAT_ATTEMPTS * (MAX_RETRIES_INFRA_ONLY + 1)


def post_with_format_retry(payload: dict, classify) -> tuple[tuple, dict]:
    """At most one fresh format request; never retry a scientific judgment.

    Uses the same source request, a fixed format-only instruction, and the same
    active physical budget. Invalid original output is retained as hashed telemetry.
    """
    attempts, calls, inputs, outputs, complete = [], 0, 0, 0, True
    budget = active_budget()
    physical_start = len(budget.transport_attempts) if budget is not None else 0
    blocked = False
    request = payload
    for index in range(MAX_FORMAT_ATTEMPTS):
        try:
            status, body, error, retries = post_with_infra_retry(request)
        except CallBudgetExceeded:
            if not index:
                raise
            blocked = True
            physical_calls = len(budget.transport_attempts) - physical_start if budget is not None else calls
            if physical_calls > calls:
                # Infrastructure retry may have spent transports before raising.
                attempts.append({'outcome': 'FORMAT_RETRY_BUDGET_EXCEEDED',
                                 'physical_calls_started': physical_calls - calls,
                                 'http_status': None, 'finish_reason': None, 'response_sha256': None})
                calls = physical_calls
                complete = False
            break
        calls += 1 + retries
        usage = (body or {}).get('usage') or {}
        known = not retries and all(type(usage.get(key)) is int for key in ('prompt_tokens', 'completion_tokens'))
        complete = complete and known
        inputs += usage.get('prompt_tokens') if type(usage.get('prompt_tokens')) is int else 0
        outputs += usage.get('completion_tokens') if type(usage.get('completion_tokens')) is int else 0
        outcome = classify(status, deepcopy(body), error)
        choices = (body or {}).get('choices') or [{}]
        attempts.append({'outcome': outcome, 'http_status': status,
                         'finish_reason': choices[0].get('finish_reason'),
                         'response_sha256': hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()})
        if index or outcome not in {'INVALID_TOOL_ARGUMENTS', 'INVALID_TOOL_CALL'} or error or status is None or status >= 400:
            break
        request = deepcopy(payload)
        required_fields = sorted({field
            for tool in payload.get('tools') or []
            for field in ((tool.get('function') or {}).get('parameters') or {}).get('required', [])
            if isinstance(field, str)})
        request['messages'].append({'role': 'system', 'content':
            'The previous response did not satisfy the tool argument schema. Return exactly one call '
            'to the specified tool with a JSON object, all required fields and only allowed enum values. '
            'Required top-level argument fields: ' + json.dumps(required_fields) + '. '
            'Place these fields directly in the function arguments, without a wrapper object. '
            'Use the unchanged source data above. Do not invent missing information or alter quoted text.'})
    return (status, body, error, calls - 1), {
        'model_call_count': calls, 'retry_count': calls - 1,
        'input_tokens': inputs if complete else None, 'output_tokens': outputs if complete else None,
        'token_usage_complete': complete, 'format_attempts': attempts, 'format_retry_budget_blocked': blocked}

OLLAMA_FORCED_TOOL_CHOICE = "OLLAMA_FORCED_TOOL_CHOICE"
MAX_RETRIES_INFRA_ONLY = 1
REQUEST_TIMEOUT_SECONDS = 60
MAX_RATE_LIMIT_WAIT_SECONDS = 30.0
RATE_LIMIT_SPACING_SECONDS = 0.25
RATE_LIMIT_RECOVERY_WINDOW_SECONDS = 60.0
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_UNTIL = 0.0
_RATE_LIMIT_RECOVERY_UNTIL = 0.0
_RATE_LIMIT_NEXT_SLOT = 0.0


def _wait_for_rate_limit() -> None:
    """Coordinate later requests after 429; recheck extended cooldowns and pace release."""
    global _RATE_LIMIT_NEXT_SLOT
    admission_slot: float | None = None
    while True:
        now = time.monotonic()
        with _RATE_LIMIT_LOCK:
            if now < _RATE_LIMIT_UNTIL:
                if admission_slot is not None and admission_slot < _RATE_LIMIT_UNTIL:
                    admission_slot = None
                    _RATE_LIMIT_NEXT_SLOT = max(_RATE_LIMIT_NEXT_SLOT, _RATE_LIMIT_UNTIL)
                wait_until = _RATE_LIMIT_UNTIL
            elif now < _RATE_LIMIT_RECOVERY_UNTIL:
                if admission_slot is None:
                    admission_slot = max(now, _RATE_LIMIT_NEXT_SLOT)
                    _RATE_LIMIT_NEXT_SLOT = admission_slot + RATE_LIMIT_SPACING_SECONDS
                if admission_slot <= now:
                    return
                wait_until = admission_slot
            else:
                return
        time.sleep(max(0.0, wait_until - now))


def _record_rate_limit(delay: float | None) -> None:
    global _RATE_LIMIT_UNTIL, _RATE_LIMIT_RECOVERY_UNTIL, _RATE_LIMIT_NEXT_SLOT
    # A long/invalid Retry-After still opens a bounded cooldown; callers fail
    # visibly and a later independent request does not immediately hammer 429.
    wait = min(MAX_RATE_LIMIT_WAIT_SECONDS, delay if delay is not None else MAX_RATE_LIMIT_WAIT_SECONDS)
    with _RATE_LIMIT_LOCK:
        now = time.monotonic()
        _RATE_LIMIT_UNTIL = max(_RATE_LIMIT_UNTIL, now + wait)
        _RATE_LIMIT_RECOVERY_UNTIL = max(
            _RATE_LIMIT_RECOVERY_UNTIL, _RATE_LIMIT_UNTIL + RATE_LIMIT_RECOVERY_WINDOW_SECONDS)
        _RATE_LIMIT_NEXT_SLOT = max(_RATE_LIMIT_NEXT_SLOT, _RATE_LIMIT_UNTIL)


def _reset_rate_limit_state() -> None:
    """Test-only reset for the process-local cooldown."""
    global _RATE_LIMIT_UNTIL, _RATE_LIMIT_RECOVERY_UNTIL, _RATE_LIMIT_NEXT_SLOT
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_UNTIL = 0.0
        _RATE_LIMIT_RECOVERY_UNTIL = 0.0
        _RATE_LIMIT_NEXT_SLOT = 0.0


def _rate_limit_delay(response: Any) -> float | None:
    """Honor short Retry-After; fail visibly instead of ignoring a long cooldown."""
    headers = getattr(response, "headers", {})
    raw = headers.get("Retry-After") if hasattr(headers, "get") else None
    delay = 5.0
    if isinstance(raw, str):
        try:
            delay = float(raw)
        except ValueError:
            try:
                date = parsedate_to_datetime(raw)
                delay = (date - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                delay = 5.0
    if not 0 <= delay <= MAX_RATE_LIMIT_WAIT_SECONDS:
        return None
    return max(0.0, delay)


def endpoint() -> llm_config.LLMEndpoint:
    """Coordinate della chiamata, risolte **al momento della chiamata**.

    Erano due costanti di modulo: ``http://localhost:11434/v1/chat/completions``
    e ``gemma4:cloud``, senza header di autorizzazione. ``llm_config`` esisteva
    già con la configurazione corretta ma nessuno la importava, quindi la
    pipeline non poteva essere puntata altrove né autenticarsi. Risolvere qui, a
    ogni chiamata, evita anche che un import anticipato congeli la
    configurazione prima che i test la impostino.
    """
    return llm_config.resolve_endpoint()


def endpoint_url() -> str:
    return llm_config.resolve_endpoint(require_credentials=False).url


def model_name() -> str:
    return llm_config.model_name()


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_payload(tool_definition: dict, tool_name: str, messages: list[dict[str, str]], seed: int, max_tokens: int) -> dict[str, Any]:
    return {
        "model": model_name(), "messages": messages, "tools": [tool_definition],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "temperature": 0, "top_p": 1.0, "seed": seed, "max_tokens": max_tokens, "stream": False,
        # Nessuna catena di pensiero: non deve essere prodotta, non solo non
        # mostrata. ``events.assert_payload_is_publishable`` la rifiuterebbe
        # comunque a valle, ma un modello che ragiona ad alta voce consuma il
        # budget di token del tool call.
        "think": False,
    }


def _valid_response_envelope(body: Any) -> bool:
    """Check container types before exposing provider JSON to shared consumers.

    Missing tools, empty choices, names and argument content remain outcomes for
    the existing component classifiers. This boundary validates representation,
    never scientific content, and never turns a malformed envelope into a call.
    """
    if not isinstance(body, dict):
        return False
    if body.get("usage") is not None and not isinstance(body["usage"], dict):
        return False
    if body.get("choices") is None:
        return True
    if not isinstance(body["choices"], list):
        return False
    for choice in body["choices"]:
        if not isinstance(choice, dict):
            return False
        if choice.get("message") is None:
            continue
        message = choice["message"]
        if not isinstance(message, dict):
            return False
        if message.get("tool_calls") is None:
            continue
        calls = message["tool_calls"]
        if not isinstance(calls, list):
            return False
        for call in calls:
            if not isinstance(call, dict):
                return False
            if call.get("function") is not None and not isinstance(call["function"], dict):
                return False
    return True


def post_with_infra_retry(payload: dict) -> tuple[int | None, dict | None, str | None, int]:
    """Returns (status_code, response_json, network_error, retry_count). Retries only
    timeout / connection failure / HTTP 5xx -- never a semantic outcome."""
    retry_count = 0
    target = endpoint()
    _wait_for_rate_limit()
    for attempt in range(MAX_RETRIES_INFRA_ONLY + 1):
        budget = active_budget()
        if budget is not None:
            budget.before_transport(payload)
        try:
            response = requests.post(
                target.url, json=payload,
                headers=target.headers(llm_config.api_key()),
                timeout=target.timeout_seconds,
            )
            status = response.status_code
            try:
                body = response.json()
            except ValueError:
                body = {"raw_text": response.text}
            if budget is not None:
                budget.record_transport_usage(body)
            if status == 429:
                _record_rate_limit(_rate_limit_delay(response))
            if status >= 500 and attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                time.sleep(1.0)
                continue
            if not _valid_response_envelope(body):
                return status, None, "INVALID_RESPONSE_ENVELOPE" if status < 400 else None, retry_count
            return status, body, None, retry_count
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                continue
            return None, None, "TIMEOUT", retry_count
        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                time.sleep(1.0)
                continue
            return None, None, f"{type(exc).__name__}:{exc}", retry_count
    return None, None, "PROVIDER_ERROR", retry_count


def _sanitize_diagnostic(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_diagnostic(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_diagnostic(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"Bearer\s+\S+", "Bearer REDACTED", value)
    return value


def post_with_infra_retry_with_diagnostics(payload: dict) -> tuple[int | None, dict | None, str | None, int, dict[str, Any]]:
    """Parser-only transport call preserving sanitized response diagnostics."""
    retry_count = 0
    target = endpoint()
    _wait_for_rate_limit()
    safe_headers = {"content-type", "server", "date", "request-id", "x-request-id", "retry-after"}
    for attempt in range(MAX_RETRIES_INFRA_ONLY + 1):
        budget = active_budget()
        if budget is not None:
            budget.before_transport(payload)
        try:
            response = requests.post(
                target.url, json=payload,
                headers=target.headers(llm_config.api_key()),
                timeout=target.timeout_seconds,
            )
            try:
                body = response.json()
            except ValueError:
                body = {"raw_text": response.text}
            if budget is not None:
                budget.record_transport_usage(body)
            diagnostics = {
                "http_status": response.status_code,
                "response_headers": {k: v for k, v in response.headers.items() if k.lower() in safe_headers},
                "raw_response_body": _sanitize_diagnostic(body),
                "attempt_count": attempt + 1,
            }
            if response.status_code == 429:
                _record_rate_limit(_rate_limit_delay(response))
            if response.status_code >= 500 and attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                time.sleep(1.0)
                continue
            if not _valid_response_envelope(body):
                return (response.status_code, None,
                        "INVALID_RESPONSE_ENVELOPE" if response.status_code < 400 else None,
                        retry_count, diagnostics)
            return response.status_code, body, None, retry_count, diagnostics
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                continue
            return None, None, "TIMEOUT", retry_count, {"http_status": None, "response_headers": {}, "raw_response_body": None, "attempt_count": attempt + 1}
        except requests.exceptions.RequestException as exc:
            if attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                time.sleep(1.0)
                continue
            return None, None, f"{type(exc).__name__}:{exc}", retry_count, {"http_status": None, "response_headers": {}, "raw_response_body": None, "attempt_count": attempt + 1}
    return None, None, "PROVIDER_ERROR", retry_count, {"http_status": None, "response_headers": {}, "raw_response_body": None, "attempt_count": MAX_RETRIES_INFRA_ONLY + 1}


def transport_result(status_code: int | None, response_json: dict | None, network_error: str | None, expected_tool_name: str, argument_errors_fn) -> tuple[str, str | None, dict | None, list[str]]:
    """Shared transport-outcome classifier for any forced single-tool call."""
    if network_error == "TIMEOUT":
        return "TIMEOUT", None, None, ["REQUEST_TIMEOUT"]
    if network_error is not None:
        return "HTTP_ERROR", None, None, [network_error]
    if status_code is not None and status_code >= 400:
        return "HTTP_ERROR", None, None, [f"HTTP_{status_code}"]
    choices = (response_json or {}).get("choices") or []
    if not choices:
        return "NO_TOOL_CALL", None, None, ["EMPTY_CHOICES"]
    message = choices[0].get("message", {}) or {}
    finish_reason = choices[0].get("finish_reason")
    tool_calls = message.get("tool_calls") or []
    content = message.get("content")
    if not tool_calls:
        if content:
            recovered = _text_json_arguments(content, expected_tool_name)
            if recovered is not None:
                errors = argument_errors_fn(recovered)
                if errors:
                    return "INVALID_TOOL_ARGUMENTS", finish_reason, None, errors
                return "FORCED_TOOL_VALID", finish_reason, recovered, ["TEXT_JSON_RECOVERED"]
            return "TEXT_RESPONSE", finish_reason, None, []
        return "FORCED_TOOL_IGNORED", finish_reason, None, ["EMPTY_RESPONSE_DESPITE_FORCED_TOOL_CHOICE"]
    if len(tool_calls) != 1:
        return "MULTIPLE_TOOL_CALLS", finish_reason, None, []
    fn = tool_calls[0].get("function") or {}
    name = fn.get("name")
    if name != expected_tool_name:
        return "WRONG_TOOL_NAME", finish_reason, None, []
    raw_args = fn.get("arguments")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (TypeError, ValueError):
        return "INVALID_TOOL_ARGUMENTS", finish_reason, None, ["ARGUMENTS_NOT_JSON"]
    if not isinstance(args, dict):
        return "INVALID_TOOL_ARGUMENTS", finish_reason, None, ["ARGUMENTS_NOT_OBJECT"]
    errors = argument_errors_fn(args)
    if errors:
        return "INVALID_TOOL_ARGUMENTS", finish_reason, None, errors
    return "FORCED_TOOL_VALID", finish_reason, args, []


def _text_json_arguments(content: Any, expected_tool_name: str) -> dict[str, Any] | None:
    """Recover only a complete JSON object (optionally fenced), never prose fragments."""
    if not isinstance(content, str):
        return None
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    if set(payload) == {expected_tool_name}:
        payload = payload[expected_tool_name]
    return payload if isinstance(payload, dict) else None
