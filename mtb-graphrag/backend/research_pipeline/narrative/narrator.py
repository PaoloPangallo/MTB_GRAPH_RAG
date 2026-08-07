"""Dossier Narrator — chiamata al modello e classificazione del trasporto.

Riusa le primitive generiche di ``enrichment/transport.py`` (tool call forzata,
retry solo infrastrutturale, hashing della risposta): non duplica il trasporto e
non introduce logica di decisione.

Tutti i metadati — ``narrative_id``, hash, modello, versioni, timestamp — sono
aggiunti **localmente** dopo un trasporto valido. Il modello non li produce.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

from ..enrichment import transport as tr
from . import prompt as pr

TRANSPORT_VERSION = "dossier-narrative-transport/1.0"

#: Esiti del trasporto. ``FORCED_TOOL_VALID`` significa soltanto che la forma è
#: corretta: la fedeltà è decisa dal Narrative Verifier, non qui.
TRANSPORT_OUTCOMES: tuple[str, ...] = (
    "FORCED_TOOL_VALID", "NO_TOOL_CALL", "TEXT_RESPONSE", "FORCED_TOOL_IGNORED",
    "MULTIPLE_TOOL_CALLS", "WRONG_TOOL_NAME", "INVALID_TOOL_ARGUMENTS",
    "TIMEOUT", "HTTP_ERROR",
)

TOOL_DEFINITION: dict = {
    "type": "function",
    "function": {
        "name": pr.TOOL_NAME,
        "description": "Emette la narrativa leggibile di un dossier gia' deciso.",
        "parameters": pr.TOOL_SCHEMA,
    },
}


def _argument_errors(args: dict[str, Any]) -> list[str]:
    """Controlli **strutturali** soltanto. La semantica è del verifier.

    Come per l'enricher v2, le chiavi extra sono rifiutate: il modello non può
    introdurre un campo che il contratto non prevede.
    """
    errors: list[str] = []
    required = set(pr.REQUIRED_KEYS)
    missing = required - set(args)
    if missing:
        errors.append(f"MISSING:{sorted(missing)}")
    extra = set(args) - required
    if extra:
        errors.append(f"EXTRA_KEYS:{sorted(extra)}")
    if errors:
        return errors

    for key in ("narrative_summary", "limitations_summary", "closing_note"):
        if not isinstance(args[key], str):
            errors.append(f"NOT_STRING:{key}")
    entries = args["candidate_narratives"]
    if not isinstance(entries, list):
        errors.append("candidate_narratives:NOT_ARRAY")
        return errors
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"candidate_narratives[{index}]:NOT_OBJECT")
            continue
        allowed = {"candidate_id", "text"}
        if set(entry) - allowed:
            errors.append(f"candidate_narratives[{index}]:EXTRA_KEYS:{sorted(set(entry) - allowed)}")
        if allowed - set(entry):
            errors.append(f"candidate_narratives[{index}]:MISSING:{sorted(allowed - set(entry))}")
            continue
        for key in allowed:
            if not isinstance(entry[key], str):
                errors.append(f"candidate_narratives[{index}].{key}:NOT_STRING")
    return errors


def narrative_hash(narrative: dict[str, Any]) -> str:
    """Hash stabile della sola narrativa prodotta dal modello."""
    body = {k: narrative.get(k) for k in pr.REQUIRED_KEYS}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _narrative_id(case_id: str, input_hash: str, run_index: int) -> str:
    payload = json.dumps({"case_id": case_id, "input_hash": input_hash,
                          "run_index": run_index, "version": pr.NARRATOR_PROMPT_VERSION},
                         sort_keys=True)
    return "DN-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _trim_only(args: dict[str, Any]) -> dict[str, Any]:
    """Solo trim degli spazi esterni. Nessuna altra normalizzazione."""
    trimmed = {k: (v.strip() if isinstance(v, str) else v) for k, v in args.items()}
    trimmed["candidate_narratives"] = [
        {"candidate_id": e["candidate_id"].strip(), "text": e["text"].strip()}
        for e in args["candidate_narratives"]
    ]
    return trimmed


def call_narrator(case_id: str, narrator_input: dict[str, Any], run_index: int = 0) -> dict[str, Any]:
    """Invoca il modello. Non decide nulla sulla fedeltà della narrativa."""
    messages = [
        {"role": "system", "content": pr.SYSTEM_PROMPT},
        {"role": "user", "content": pr.build_user_message(narrator_input)},
    ]
    payload = tr.build_payload(TOOL_DEFINITION, pr.TOOL_NAME, messages,
                               seed=run_index, max_tokens=2048)
    started = time.perf_counter()
    status_code, response_json, network_error, retry_count = tr.post_with_infra_retry(payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    outcome, finish_reason, raw_args, reasons = tr.transport_result(
        status_code, response_json, network_error, pr.TOOL_NAME, _argument_errors)

    input_hash = narrator_input.get("narrator_input_hash", "")
    narrative = None
    if raw_args is not None:
        args = _trim_only(raw_args)
        narrative = {
            "narrative_id": _narrative_id(case_id, input_hash, run_index),
            "case_id": case_id,
            **{k: args[k] for k in pr.REQUIRED_KEYS},
            "language": pr.NARRATIVE_LANGUAGE,
            "model": tr.model_name(),
            "prompt_version": pr.NARRATOR_PROMPT_VERSION,
            "transport_version": TRANSPORT_VERSION,
            "narrator_input_hash": input_hash,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        narrative["narrative_hash"] = narrative_hash(narrative)

    usage = (response_json or {}).get("usage") or {}
    return {
        "case_id": case_id, "run_index": run_index,
        "model": tr.model_name(), "endpoint": tr.endpoint_url(),
        "delivery_transport": "OLLAMA_FORCED_TOOL_CHOICE_NARRATIVE",
        "prompt_version": pr.NARRATOR_PROMPT_VERSION,
        "transport_version": TRANSPORT_VERSION,
        "transport_result": outcome, "transport_reason_codes": reasons,
        "finish_reason": finish_reason,
        "narrative": narrative,
        "narrator_input_hash": input_hash,
        "raw_response_hash": tr.sha(str(response_json)) if response_json is not None else None,
        "input_tokens": usage.get("prompt_tokens"),
        "output_tokens": usage.get("completion_tokens"),
        "latency_ms": latency_ms, "retry_count": retry_count, "status_code": status_code,
    }
