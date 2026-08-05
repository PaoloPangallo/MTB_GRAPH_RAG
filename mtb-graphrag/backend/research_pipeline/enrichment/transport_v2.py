"""Transport-level checks for Paper Context Enricher v2.0 -- structural only
(section 3): single tool call, exact name, dict arguments, all five fields
present and string-typed, decision exactly QUOTE or ABSTAIN. Everything
semantic (source_unit_id existence, quote literalness, abstain+populated-
fields consistency, empty summary, etc.) is deferred to
PaperContextEnrichmentV2Validator -- never rejected here.

Reuses only the generic HTTP/retry/hashing primitives from transport.py
(shared with v1.0/v1.1); the outcome vocabulary and argument-shape checks
are new and specific to the v2.0 minimal contract.
"""
from __future__ import annotations

import json
from typing import Any

from .prompt_v2 import DECISIONS, TOOL_NAME, TOOL_SCHEMA

# TIMEOUT/HTTP_ERROR are not in the protocol's literal transport-outcome list (section 3)
# but are unavoidable at the network layer and are exactly what the infra-only retry
# policy (section 10) refers to -- included here for honest reporting, never used to
# justify a semantic retry.
OUTCOMES = {
    "V2_TRANSPORT_VALID", "NO_TOOL_CALL", "TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL",
    "WRONG_TOOL_NAME", "MULTIPLE_TOOL_CALLS", "MISSING_ARGUMENT", "WRONG_ARGUMENT_TYPE",
    "INVALID_DECISION", "INVALID_TOOL_ARGUMENTS", "TIMEOUT", "HTTP_ERROR",
}
VALID_OUTCOME = "V2_TRANSPORT_VALID"


def transport_result_v2(status_code: int | None, response_json: dict | None, network_error: str | None) -> tuple[str, str | None, dict | None, list[str]]:
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
            return "TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL", finish_reason, None, []
        return "NO_TOOL_CALL", finish_reason, None, []
    if len(tool_calls) != 1:
        return "MULTIPLE_TOOL_CALLS", finish_reason, None, []

    fn = tool_calls[0].get("function") or {}
    name = fn.get("name")
    if name != TOOL_NAME:
        return "WRONG_TOOL_NAME", finish_reason, None, []

    raw_args = fn.get("arguments")
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    except (TypeError, ValueError):
        return "INVALID_TOOL_ARGUMENTS", finish_reason, None, ["ARGUMENTS_NOT_JSON"]
    if not isinstance(args, dict):
        return "INVALID_TOOL_ARGUMENTS", finish_reason, None, ["ARGUMENTS_NOT_OBJECT"]

    required = set(TOOL_SCHEMA["properties"])
    missing = required - set(args)
    if missing:
        return "MISSING_ARGUMENT", finish_reason, None, [f"MISSING:{sorted(missing)}"]
    extra = set(args) - required
    if extra:
        return "INVALID_TOOL_ARGUMENTS", finish_reason, None, [f"EXTRA_KEYS:{sorted(extra)}"]

    non_string = sorted(key for key in required if not isinstance(args[key], str))
    if non_string:
        return "WRONG_ARGUMENT_TYPE", finish_reason, None, [f"NOT_STRING:{non_string}"]

    if args["decision"] not in DECISIONS:
        return "INVALID_DECISION", finish_reason, None, [f"DECISION_INVALID:{args['decision']}"]

    return VALID_OUTCOME, finish_reason, args, []
