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
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from ..enrichment import transport as tr
from ..budget import active_budget
from . import prompt as pr

TRANSPORT_VERSION = "dossier-narrative-transport/1.8"
MAX_OUTPUT_TOKENS = 8192
MAX_CANDIDATES_PER_REQUEST = 40
MAX_REQUEST_CHARACTERS = 32000
MIN_CANDIDATES_PER_RECOVERY = 1

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
        elif key == 'narrative_summary' and not args[key].strip():
            errors.append(f"EMPTY_STRING:{key}")
    entries = args["candidate_narratives"]
    if not isinstance(entries, list):
        errors.append("candidate_narratives:NOT_ARRAY")
        return errors
    if not entries:
        errors.append("candidate_narratives:EMPTY_ARRAY")
    candidate_ids: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"candidate_narratives[{index}]:NOT_OBJECT")
            continue
        allowed = {"candidate_id", "text", "observation_narratives", "study_comparison"}
        if set(entry) - allowed:
            errors.append(f"candidate_narratives[{index}]:EXTRA_KEYS:{sorted(set(entry) - allowed)}")
        required_entry = {"candidate_id", "text"}
        if required_entry - set(entry):
            errors.append(f"candidate_narratives[{index}]:MISSING:{sorted(required_entry - set(entry))}")
            continue
        for key in {"candidate_id", "text"}:
            if key in {"candidate_id", "text"} and not isinstance(entry[key], str):
                errors.append(f"candidate_narratives[{index}].{key}:NOT_STRING")
            elif not entry[key].strip():
                errors.append(f"candidate_narratives[{index}].{key}:EMPTY_STRING")
        if isinstance(entry.get("candidate_id"), str):
            candidate_ids.append(entry["candidate_id"])
    duplicates = sorted({value for value in candidate_ids if candidate_ids.count(value) > 1})
    if duplicates:
        errors.append(f"candidate_narratives:DUPLICATE_CANDIDATE_ID:{duplicates}")
    from jsonschema import Draft7Validator
    schema_errors = list(Draft7Validator(pr.TOOL_SCHEMA).iter_errors(args))
    if schema_errors:
        errors.append('INVALID_NESTED_NARRATIVE_SHAPE')
        # Identify the schema field and rule, never echo response values into
        # retry instructions or logs. The legacy category remains available.
        for error in sorted(schema_errors, key=lambda item: tuple(map(str, item.path)))[:8]:
            path = '/'.join(str(part).replace('~', '~0').replace('/', '~1') for part in error.path)
            errors.append(f'SCHEMA_FIELD:/{path}:RULE:{error.validator}')
    return errors


def narrative_hash(narrative: dict[str, Any]) -> str:
    """Hash stabile della sola narrativa prodotta dal modello."""
    body = {k: narrative.get(k) for k in pr.REQUIRED_KEYS}
    encoded = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _bound_argument_errors(args: dict[str, Any], source: dict[str, Any]) -> list[str]:
    """Validate inventory and immutable supplied fields; never score free prose."""
    errors = _argument_errors(args)
    if errors or not source.get('candidates'):
        return errors
    candidates = source['candidates']
    entries = args['candidate_narratives']
    if [entry['candidate_id'] for entry in entries] != [row['candidate_id'] for row in candidates]:
        return ['REQUESTED_CANDIDATE_INVENTORY_MISMATCH']
    from .coverage import coverage_errors
    for candidate, entry in zip(candidates, entries):
        errors.extend(coverage_errors(candidate, entry))
    # Check the same view sent to the model. Historical projections do not have
    # this copy-only field; scientific observation prose remains the verifier's
    # responsibility. Reject mismatches rather than replacing model output.
    if source.get('documentary_contract_version'):
        from .model_view import model_view
        for index, (candidate, entry) in enumerate(zip(model_view(source)['candidates'], entries)):
            if 'branch_scope_text' in candidate and entry['text'] != candidate['branch_scope_text']:
                errors.append(f'BRANCH_SCOPE_TEXT_MISMATCH:{index}')
    return errors


def _narrative_id(case_id: str, input_hash: str, run_index: int) -> str:
    payload = json.dumps({"case_id": case_id, "input_hash": input_hash,
                          "run_index": run_index, "version": pr.NARRATOR_PROMPT_VERSION},
                         sort_keys=True)
    return "DN-" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _trim_only(args: dict[str, Any]) -> dict[str, Any]:
    """Solo trim degli spazi esterni. Nessuna altra normalizzazione."""
    trimmed = {k: (v.strip() if isinstance(v, str) else v) for k, v in args.items()}
    trimmed["candidate_narratives"] = []
    for e in args["candidate_narratives"]:
        item = deepcopy(e)
        item.update(candidate_id=e['candidate_id'].strip(), text=e['text'].strip())
        trimmed["candidate_narratives"].append(item)
    return trimmed


def _call_narrator_batch(case_id: str, narrator_input: dict[str, Any], run_index: int = 0) -> dict[str, Any]:
    """Invoca il modello. Non decide nulla sulla fedeltà della narrativa."""
    messages = [
        {"role": "system", "content": pr.SYSTEM_PROMPT},
        {"role": "user", "content": pr.build_user_message(narrator_input)},
    ]
    payload = tr.build_payload(TOOL_DEFINITION, pr.TOOL_NAME, messages,
                               seed=run_index, max_tokens=MAX_OUTPUT_TOKENS)
    started = time.perf_counter()
    attempts: list[dict[str, Any]] = []
    for attempt_number in (1, 2):
        status_code, response_json, network_error, retry_count = tr.post_with_infra_retry(payload)
        outcome, finish_reason, raw_args, reasons = tr.transport_result(
            status_code, response_json, network_error, pr.TOOL_NAME,
            lambda args: _bound_argument_errors(args, narrator_input))
        usage = (response_json or {}).get("usage") or {}
        attempts.append({
            "attempt": attempt_number,
            "status_code": status_code,
            "transport_result": outcome,
            "finish_reason": finish_reason,
            "reason_codes": reasons,
            "retry_count": retry_count,
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
        })
        retry_single_shape = (outcome == 'INVALID_TOOL_ARGUMENTS'
                              and len(narrator_input.get('candidates') or []) == 1)
        if attempt_number == 2 or (outcome != "FORCED_TOOL_IGNORED" and not retry_single_shape):
            break
        if retry_single_shape:
            # Ask for structural compliance only. Never repair scientific prose or
            # accept a malformed response; the next response is validated afresh.
            payload['messages'].append({
                'role': 'user',
                'content': ('The previous tool response did not satisfy the required structural contract. '
                            'Return the requested tool call with the exact required field types '
                            'and complete candidate and observation coverage. Copy each supplied '
                            'branch_scope_text exactly into its candidate text. Keep all claims '
                            'grounded in the supplied dossier. Structural errors: ' + '; '.join(reasons)),
            })
    latency_ms = round((time.perf_counter() - started) * 1000, 3)

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

    input_usage = [attempt["input_tokens"] for attempt in attempts]
    output_usage = [attempt["output_tokens"] for attempt in attempts]
    usage_known = all(type(value) is int for value in input_usage + output_usage)
    return {
        "case_id": case_id, "run_index": run_index,
        "model": tr.model_name(), "endpoint": tr.endpoint_url(),
        "delivery_transport": "OLLAMA_FORCED_TOOL_CHOICE_NARRATIVE",
        "prompt_version": pr.NARRATOR_PROMPT_VERSION,
        "transport_version": TRANSPORT_VERSION,
        "transport_result": outcome, "transport_reason_codes": reasons,
        "finish_reason": finish_reason,
        "attempts": attempts,
        "retry_result": (
            "FORCED_TOOL_IGNORED_RECOVERED" if len(attempts) == 2 and outcome == "FORCED_TOOL_VALID"
            and attempts[0]['transport_result'] == 'FORCED_TOOL_IGNORED'
            else "INVALID_TOOL_ARGUMENTS_RECOVERED" if len(attempts) == 2 and outcome == "FORCED_TOOL_VALID"
            else "FORCED_TOOL_IGNORED_FINAL" if len(attempts) == 2 and outcome == "FORCED_TOOL_IGNORED"
            else None
        ),
        "narrative": narrative,
        "narrator_input_hash": input_hash,
        "raw_response_hash": tr.sha(str(response_json)) if response_json is not None else None,
        "input_tokens": sum(input_usage) if all(type(value) is int for value in input_usage) else None,
        "output_tokens": sum(output_usage) if all(type(value) is int for value in output_usage) else None,
        "token_usage_complete": usage_known and not any(a["retry_count"] for a in attempts),
        "latency_ms": latency_ms, "retry_count": sum(a["retry_count"] for a in attempts), "status_code": status_code,
        "model_call_count": len(attempts) + sum(a["retry_count"] for a in attempts),
    }


def call_narrator(case_id: str, narrator_input: dict[str, Any], run_index: int = 0) -> dict[str, Any]:
    """Narrate every candidate in bounded requests; failed batches fail closed.

    Summary facts and limitations remain global.  The first batch supplies the
    global prose; candidate texts are assembled in order and the complete
    narrative is still checked against the original projection by the verifier.
    No candidate, support state or validated quotation is truncated.
    """
    candidates = narrator_input.get("candidates") or []
    def provision_request():
        budget = active_budget()
        if budget is not None:
            # Two empty-tool attempts, each with at most one infrastructure retry.
            # Discovered recovery requests are finite (at most a binary tree over
            # the supplied candidates). Explicit fixed operator caps never grow.
            budget.plan_remaining_calls(4)
    chunks = []
    chunk = []
    for candidate in candidates:
        proposed = chunk + [candidate]
        request_size = len(pr.SYSTEM_PROMPT) + len(pr.build_user_message({**narrator_input, 'candidates': proposed}))
        if chunk and (len(proposed) > MAX_CANDIDATES_PER_REQUEST or request_size > MAX_REQUEST_CHARACTERS):
            chunks.append(chunk)
            chunk = []
        chunk.append(candidate)
    if chunk:
        chunks.append(chunk)
    if len(candidates) <= 1:
        provision_request()
        return _call_narrator_batch(case_id, narrator_input, run_index)

    results = []
    accepted = []

    def request(chunk):
        provision_request()
        batch = {**narrator_input, "candidates": chunk}
        result = _call_narrator_batch(case_id, batch, run_index)
        results.append(result)
        if result.get("transport_result") == "FORCED_TOOL_VALID" and result.get("narrative"):
            accepted.append(result)
            return True
        outcome = result.get("transport_result")
        if (outcome in {"INVALID_TOOL_ARGUMENTS", "FORCED_TOOL_IGNORED"}
                and len(chunk) > MIN_CANDIDATES_PER_RECOVERY):
            # Replace a malformed transport with smaller independent requests.
            # Never rewrite, deduplicate, or semantically repair model prose.
            middle = len(chunk) // 2
            return request(chunk[:middle]) and request(chunk[middle:])
        return False

    for chunk in chunks:
        if not request(chunk):
            break

    combined = dict(results[-1])
    combined["batch_count"] = len(results)
    combined["accepted_batch_count"] = len(accepted)
    combined["structural_recovery_count"] = sum(
        r.get("transport_result") in {"INVALID_TOOL_ARGUMENTS", "FORCED_TOOL_IGNORED"} for r in results
    )
    combined["token_usage_complete"] = all(r.get("token_usage_complete", False) for r in results)
    combined["model_call_count"] = sum(r.get("model_call_count", 1) for r in results)
    combined["retry_count"] = sum(r.get("retry_count", 0) for r in results)
    combined["latency_ms"] = sum(r.get("latency_ms", 0) for r in results)
    for key in ("input_tokens", "output_tokens"):
        values = [r.get(key) for r in results]
        combined[key] = sum(values) if all(isinstance(v, int) for v in values) else None
    combined["attempts"] = [{**attempt, "batch": index + 1}
                            for index, r in enumerate(results) for attempt in r.get("attempts", [])]
    if combined.get("transport_result") != "FORCED_TOOL_VALID" or not combined.get("narrative"):
        combined["narrative"] = None
        return combined

    narrative = dict(accepted[0]["narrative"])
    narrative["candidate_narratives"] = [
        entry for result in accepted for entry in result["narrative"]["candidate_narratives"]
    ]
    narrative["narrative_hash"] = narrative_hash(narrative)
    combined["narrative"] = narrative
    combined["raw_response_hash"] = tr.sha(json.dumps([r.get("raw_response_hash") for r in results]))
    return combined


def call_dossier_narrator(case_id: str, narrator_input: dict[str, Any],
                          run_index: int = 0) -> dict[str, Any]:
    """Generate prose from the dossier; keep an independently checked fallback.

    Transport validity is not narrative acceptance. Stage 15 applies the
    deterministic verifier to the generated prose before presentation.
    """
    from .controlled import build_catalog, default_plan, render_plan

    catalog = build_catalog(narrator_input)
    fallback = render_plan(catalog, default_plan(catalog))
    fallback.update({'case_id': case_id, 'language': 'it',
                     'generation_origin': 'DETERMINISTIC_FALLBACK',
                     'narrator_input_hash': narrator_input.get('narrator_input_hash', '')})
    fallback['narrative_hash'] = narrative_hash(fallback)
    if not narrator_input.get('candidates'):
        return {'case_id': case_id, 'transport_result': 'NOT_EXECUTED',
                'narrative': None, 'deterministic_fallback': fallback,
                'model_call_count': 0, 'input_tokens': 0, 'output_tokens': 0,
                'generation_mode': 'DETERMINISTIC_FALLBACK'}
    try:
        result = call_narrator(case_id, narrator_input, run_index=run_index)
    except Exception as exc:  # post-dossier failure preserves the verified fallback
        from ..budget import CallBudgetExceeded

        return {'case_id': case_id, 'narrative': None, 'deterministic_fallback': fallback,
                'transport_result': ('CALL_BUDGET_EXCEEDED' if isinstance(exc, CallBudgetExceeded)
                                     else 'TRANSPORT_EXCEPTION'),
                'transport_reason_codes': [type(exc).__name__],
                'generation_mode': 'DETERMINISTIC_FALLBACK',
                'model_call_count': None, 'input_tokens': None, 'output_tokens': None,
                'token_usage_complete': False}
    narrative = result.get('narrative')
    if narrative is not None:
        narrative['generation_origin'] = 'MODEL_DOSSIER_NARRATION'
        narrative['dossier_narration_contract'] = {
            'version': 'dossier-narration/1.4',
            'input_hash': narrator_input.get('narrator_input_hash', ''),
        }
        narrative['canonical_sources'] = {
            candidate['candidate_id']: deepcopy(candidate.get('source_cards') or [])
            for candidate in narrator_input.get('candidates') or []
        }
        narrative['canonical_observations'] = {
            candidate['candidate_id']: deepcopy(candidate.get('narration_observations') or [])
            for candidate in narrator_input.get('candidates') or []
        }
    return {**result, 'deterministic_fallback': fallback,
            'generation_mode': 'MODEL_DOSSIER_NARRATION' if narrative else 'DETERMINISTIC_FALLBACK'}
