"""Bounded model planning; canonical facts are realized locally, never rewritten."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from ..enrichment import transport as tr
from .controlled import build_catalog, default_plan, render_plan, validate_plan
from .narrator import narrative_hash

PROMPT_VERSION = "controlled-narrative-planner/2.0"
TRANSPORT_VERSION = "controlled-narrative-transport/1.0"
TOOL_NAME = "emit_narrative_plan"
MAX_ENTRIES = 40
MIN_RECOVERY_ENTRIES = 10
SYSTEM_PROMPT = (
    "Organizza osservazioni documentali e controlli separati, senza un giudizio globale di supporto o validita clinica. Non produci testo clinico. "
    "Per ogni fact_id fornito scegli solo concise o detailed. Mantieni tutti gli ID "
    "nell'ordine fornito, una volta ciascuno. Non aggiungere fatti, campi o ID. "
    "Le due varianti preservano gli stessi fatti canonici; scegli detailed per una "
    "spiegazione piu' esplicita, concise per ridurre la ripetizione. "
    "Rispondi esclusivamente chiamando emit_narrative_plan."
)


def _tool(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": TOOL_NAME,
        "description": "Seleziona formulazioni autorizzate senza modificare i fatti.",
        "parameters": {"type": "object", "additionalProperties": False,
            "properties": {"entries": {"type": "array", "minItems": len(entries),
                "maxItems": len(entries), "items": {"type": "object",
                    "additionalProperties": False,
                    "properties": {"fact_id": {"type": "string", "enum": [e["fact_id"] for e in entries]},
                                   "variant": {"type": "string", "enum": ["concise", "detailed"]}},
                    "required": ["fact_id", "variant"]}}}, "required": ["entries"]}}}


def _batch_errors(args: dict[str, Any], expected: list[str]) -> list[str]:
    if set(args) != {"entries"} or not isinstance(args.get("entries"), list):
        return ["PLAN_SHAPE_INVALID"]
    ids = []
    for entry in args["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"fact_id", "variant"}:
            return ["PLAN_ENTRY_INVALID"]
        if not isinstance(entry["fact_id"], str) or entry["variant"] not in ("concise", "detailed"):
            return ["PLAN_VALUE_INVALID"]
        ids.append(entry["fact_id"])
    return [] if ids == expected else ["PLAN_COVERAGE_OR_ORDER_INVALID"]


def _realized(case_id: str, source: dict[str, Any], catalog: dict[str, Any],
              plan: dict[str, Any], origin: str) -> dict[str, Any]:
    narrative = render_plan(catalog, plan)
    narrative.update({"case_id": case_id, "language": "it", "generation_origin": origin,
                      "narrator_input_hash": source.get("narrator_input_hash", ""),
                      "prompt_version": PROMPT_VERSION, "transport_version": TRANSPORT_VERSION,
                      "model": tr.model_name() if origin == "MODEL_PLAN" else None,
                      "timestamp": datetime.now(timezone.utc).isoformat()})
    narrative["narrative_hash"] = narrative_hash(narrative)
    return narrative


def call_controlled_narrator(case_id: str, narrator_input: dict[str, Any],
                            run_index: int = 0) -> dict[str, Any]:
    """Never expose partial plans; deterministic fallback is a separate artifact."""
    started = time.perf_counter()
    catalog = build_catalog(narrator_input)
    attempts: list[dict[str, Any]] = []
    selected: list[dict[str, str]] = []
    last_outcome = "NOT_EXECUTED"

    def request(entries: list[dict[str, Any]]) -> bool:
        nonlocal last_outcome
        expected = [e["fact_id"] for e in entries]
        payload = tr.build_payload(_tool(entries), TOOL_NAME, [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"entries": [
                {"fact_id": e["fact_id"], "branch": e["branch"]} for e in entries]},
                ensure_ascii=False, separators=(",", ":"))}], seed=run_index, max_tokens=4096)
        code, response, error, retries = tr.post_with_infra_retry(payload)
        outcome, finish, args, reasons = tr.transport_result(
            code, response, error, TOOL_NAME, lambda value: _batch_errors(value, expected))
        usage = (response or {}).get("usage") or {}
        attempts.append({"attempt": len(attempts) + 1, "entry_count": len(entries),
                         "status_code": code, "transport_result": outcome,
                         "finish_reason": finish, "reason_codes": reasons, "retry_count": retries,
                         "input_tokens": usage.get("prompt_tokens"),
                         "output_tokens": usage.get("completion_tokens"),
                         "raw_response_hash": tr.sha(json.dumps(response, sort_keys=True))})
        last_outcome = outcome
        if outcome == "FORCED_TOOL_VALID" and args is not None:
            selected.extend(args["entries"])
            return True
        if outcome in {"INVALID_TOOL_ARGUMENTS", "FORCED_TOOL_IGNORED", "TEXT_RESPONSE", "NO_TOOL_CALL"} and len(entries) > MIN_RECOVERY_ENTRIES:
            middle = len(entries) // 2
            return request(entries[:middle]) and request(entries[middle:])
        return False

    entries = catalog["entries"]
    complete = bool(entries)
    for offset in range(0, len(entries), MAX_ENTRIES):
        if not request(entries[offset:offset + MAX_ENTRIES]):
            complete = False
            break
    plan = {"catalog_hash": catalog["catalog_hash"], "entries": selected}
    complete = complete and not validate_plan(catalog, plan)
    narrative = _realized(case_id, narrator_input, catalog, plan, "MODEL_PLAN") if complete else None
    fallback = None if complete else _realized(
        case_id, narrator_input, catalog, default_plan(catalog), "DETERMINISTIC_FALLBACK")

    def usage_sum(key: str) -> int | None:
        values = [a[key] for a in attempts]
        return sum(values) if all(type(v) is int for v in values) else None

    return {"case_id": case_id, "model": tr.model_name(), "endpoint": tr.endpoint_url(),
            "prompt_version": PROMPT_VERSION, "transport_version": TRANSPORT_VERSION,
            "delivery_transport": "OLLAMA_FORCED_TOOL_CHOICE_CONTROLLED_PLAN",
            "transport_result": "FORCED_TOOL_VALID" if complete else last_outcome,
            "transport_reason_codes": [] if complete else ["MODEL_PLAN_UNAVAILABLE"],
            "narrative": narrative, "deterministic_fallback": fallback,
            "model_plan_valid": complete, "generation_mode": "MODEL_PLAN" if complete else "DETERMINISTIC_FALLBACK",
            "narrator_input_hash": narrator_input.get("narrator_input_hash", ""),
            "catalog_hash": catalog["catalog_hash"], "attempts": attempts,
            "model_call_count": sum(1 + a["retry_count"] for a in attempts),
            "retry_count": sum(a["retry_count"] for a in attempts),
            "input_tokens": usage_sum("input_tokens"), "output_tokens": usage_sum("output_tokens"),
            "token_usage_complete": all(type(a[k]) is int for a in attempts for k in ("input_tokens", "output_tokens")) and not any(a["retry_count"] for a in attempts),
            "latency_ms": round((time.perf_counter() - started) * 1000, 3)}
