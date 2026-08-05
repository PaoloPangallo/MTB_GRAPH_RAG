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
import time
from typing import Any

import requests

OLLAMA_FORCED_TOOL_CHOICE = "OLLAMA_FORCED_TOOL_CHOICE"
OPENAI_COMPAT_ENDPOINT = "http://localhost:11434/v1/chat/completions"
MODEL = "gemma4:cloud"
MAX_RETRIES_INFRA_ONLY = 1
REQUEST_TIMEOUT_SECONDS = 60


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def build_payload(tool_definition: dict, tool_name: str, messages: list[dict[str, str]], seed: int, max_tokens: int) -> dict[str, Any]:
    return {
        "model": MODEL, "messages": messages, "tools": [tool_definition],
        "tool_choice": {"type": "function", "function": {"name": tool_name}},
        "temperature": 0, "top_p": 1.0, "seed": seed, "max_tokens": max_tokens, "stream": False,
    }


def post_with_infra_retry(payload: dict) -> tuple[int | None, dict | None, str | None, int]:
    """Returns (status_code, response_json, network_error, retry_count). Retries only
    timeout / connection failure / HTTP 5xx -- never a semantic outcome."""
    retry_count = 0
    for attempt in range(MAX_RETRIES_INFRA_ONLY + 1):
        try:
            response = requests.post(OPENAI_COMPAT_ENDPOINT, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            status = response.status_code
            try:
                body = response.json()
            except ValueError:
                body = {"raw_text": response.text}
            if status >= 500 and attempt < MAX_RETRIES_INFRA_ONLY:
                retry_count += 1
                time.sleep(1.0)
                continue
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
