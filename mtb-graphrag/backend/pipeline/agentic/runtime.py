"""Planner agentico con strumenti allow-listed e ledger scritto durante l'esecuzione."""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger


logger = logging.getLogger(__name__)

Tool = Callable[[dict[str, Any]], dict[str, Any]]

# Categorie sanitizzate del motivo di fallback: mai il testo grezzo
# dell'eccezione, che potrebbe contenere dettagli interni o segreti.
FallbackReason = str  # "timeout" | "invalid_json" | "service_unavailable" | "budget_exhausted" | "other"

_FALLBACK_MESSAGES: dict[FallbackReason, str] = {
    "timeout": "Fallback sicuro: timeout del planner.",
    "invalid_json": "Fallback sicuro: risposta del planner non conforme al formato JSON.",
    "service_unavailable": "Fallback sicuro: servizio del planner non disponibile.",
    "budget_exhausted": "Fallback sicuro: budget di tempo del planner esaurito.",
    "other": "Fallback sicuro: il planner ha proposto uno strumento non consentito o un errore non classificato.",
}

# Categorie sanitizzate per un fallimento di tool call: mai str(exc) nel
# ledger o nelle limitations restituite dall'API — i dettagli tecnici
# completi restano solo nei log server-side (senza token/segreti).
ToolFailureCategory = str  # "timeout" | "invalid_response" | "service_unavailable" | "data_error" | "other"

_TOOL_FAILURE_MESSAGES: dict[ToolFailureCategory, str] = {
    "timeout": "timeout durante l'esecuzione dello strumento",
    "invalid_response": "risposta dello strumento non conforme al formato atteso",
    "service_unavailable": "servizio esterno non disponibile durante l'esecuzione dello strumento",
    "data_error": "dati insufficienti o non validi per completare lo strumento",
    "other": "errore non classificato durante l'esecuzione dello strumento",
}


def _categorize_tool_exception(exc: Exception) -> ToolFailureCategory:
    if isinstance(exc, (TimeoutError, FuturesTimeoutError)):
        return "timeout"
    if isinstance(exc, (ConnectionError, OSError)):
        return "service_unavailable"
    if isinstance(exc, (json.JSONDecodeError, ValueError, TypeError)):
        return "invalid_response"
    if isinstance(exc, (KeyError, IndexError, AttributeError)):
        return "data_error"
    return "other"


PLANNER_SYSTEM = """Sei il planner di raccolta evidenze per un Molecular Tumor Board.
Scegli UN solo prossimo strumento dalla lista consentita. Puoi cambiare piano dopo
ogni osservazione. Non formulare raccomandazioni terapeutiche e non inventare dati.
Termina quando le evidenze necessarie sono state raccolte o quando gli strumenti
disponibili non possono ridurre l'incertezza.

Restituisci esclusivamente JSON valido:
{"tool": "nome_strumento", "rationale": "motivazione breve"}
"""


def _planner_timeout_seconds() -> int:
    try:
        return max(1, int(os.getenv("PLANNER_TIMEOUT_SECONDS", "20")))
    except ValueError:
        return 20


def _planner_max_retries() -> int:
    try:
        return max(0, int(os.getenv("PLANNER_MAX_RETRIES", "1")))
    except ValueError:
        return 1


def _planner_total_budget_seconds() -> int:
    try:
        return max(1, int(os.getenv("PLANNER_TOTAL_BUDGET_SECONDS", "30")))
    except ValueError:
        return 30


@dataclass
class AgenticCollectionResult:
    state: dict[str, Any]
    run_id: str
    events: list[dict[str, Any]]
    tool_path: list[str]
    planning_mode: str
    ledger_valid: bool
    errors: list[str]
    fallback_reason: FallbackReason | None = None
    planner_attempts: int = 0
    planner_elapsed_ms: int = 0
    tool_call_timings: list[dict[str, Any]] = field(default_factory=list)


def _default_tools() -> dict[str, Tool]:
    from backend.pipeline.agents.complexity_check import complexity_check
    from backend.pipeline.agents.oncokb_enricher import oncokb_enricher
    from backend.pipeline.agents.resistance_checker import resistance_checker
    from backend.pipeline.agents.target_identifier import target_identifier
    from backend.pipeline.agents.trial_matcher import trial_matcher
    from backend.pipeline.agents.variant_interpreter import variant_interpreter_low

    return {
        "assess_complexity": complexity_check,
        "interpret_variant": variant_interpreter_low,
        "identify_targets": target_identifier,
        "match_trials": trial_matcher,
        "check_resistance": resistance_checker,
        "enrich_oncokb": oncokb_enricher,
    }


def _allowed_tools(state: dict[str, Any], completed: set[str]) -> list[str]:
    allowed: list[str] = []
    if "assess_complexity" not in completed:
        allowed.append("assess_complexity")
    if "interpret_variant" not in completed:
        allowed.append("interpret_variant")
    if "interpret_variant" in completed:
        if "identify_targets" not in completed:
            allowed.append("identify_targets")
        if "check_resistance" not in completed:
            allowed.append("check_resistance")
        if "identify_targets" in completed and "match_trials" not in completed:
            allowed.append("match_trials")
        if state.get("enrich_with_oncokb") and "enrich_oncokb" not in completed:
            allowed.append("enrich_oncokb")
        allowed.append("finish")
    return allowed


def _state_summary(state: dict[str, Any], completed: set[str]) -> dict[str, Any]:
    return {
        "case": {
            "gene": state.get("gene"),
            "variant": state.get("variant"),
            "tumor_type": state.get("tumor_type"),
            "alteration_type": state.get("alteration_type"),
            "therapy_line": state.get("therapy_line"),
            "disease_stage": state.get("disease_stage"),
            "disease_setting": state.get("disease_setting"),
            "prior_therapies": state.get("prior_therapies", []),
            "prior_response": state.get("prior_response"),
            "ecog_status": state.get("ecog_status"),
            "cns_metastases": state.get("cns_metastases"),
            "co_alterations": state.get("co_alterations", []),
            "jurisdiction": state.get("jurisdiction"),
            "mtb_goal": state.get("mtb_goal"),
        },
        "complexity": state.get("complexity"),
        "completed_tools": sorted(completed),
        "observations": {
            "evidence_records": len(state.get("variant_data", {}).get("evidence_records", [])),
            "drug_candidates": len(state.get("drug_candidates", [])),
            "trial_candidates": len(state.get("trial_candidates", [])),
            "resistance_records": len(state.get("resistance_data", [])),
            "oncokb_records": len(state.get("oncokb_enrichment", [])),
        },
    }


def _parse_decision(content: Any) -> tuple[str, str]:
    text = str(content).strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        candidate = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if candidate:
            text = candidate.group(0)
    parsed = json.loads(text)
    return str(parsed["tool"]), str(parsed.get("rationale", ""))


def _fallback_tool(allowed: list[str]) -> str:
    safe_order = (
        "assess_complexity",
        "interpret_variant",
        "identify_targets",
        "check_resistance",
        "match_trials",
        "enrich_oncokb",
        "finish",
    )
    return next(tool for tool in safe_order if tool in allowed)


def _invoke_planner_with_timeout(planner_llm: Any, messages: list[tuple[str, str]], timeout_seconds: int) -> Any:
    """Invoca il planner con un timeout. Il meccanismo di interruzione affidabile
    è il timeout configurato sul client stesso (vedi ``backend.pipeline.llm.build_llm``);
    questo executor è solo una misura difensiva aggiuntiva e non deve MAI attendere
    il thread bloccato dopo lo scadere del timeout — un thread Python non può
    terminare in sicurezza una richiesta di rete in corso, quindi lo si abbandona
    con ``shutdown(wait=False)`` invece di bloccare l'esecuzione su di esso."""
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(planner_llm.invoke, messages)
        return future.result(timeout=timeout_seconds)
    finally:
        executor.shutdown(wait=False)


def _attempt_planner_call(
    state: dict[str, Any],
    completed: set[str],
    allowed: list[str],
    planner_llm: Any,
    timeout_seconds: int,
) -> tuple[tuple[str, str] | None, FallbackReason | None]:
    """Un solo tentativo di ottenere una decisione valida dal planner.
    Restituisce ``(decisione, None)`` in caso di successo oppure
    ``(None, categoria_sanitizzata)`` in caso di fallimento — mai il testo
    grezzo dell'eccezione."""
    prompt = json.dumps({
        "stato": _state_summary(state, completed),
        "strumenti_consentiti": allowed,
    }, ensure_ascii=False, sort_keys=True)
    messages = [("system", PLANNER_SYSTEM), ("human", prompt)]
    try:
        response = _invoke_planner_with_timeout(planner_llm, messages, timeout_seconds)
    except FuturesTimeoutError:
        return None, "timeout"
    except Exception:
        return None, "service_unavailable"
    try:
        tool, rationale = _parse_decision(response.content)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None, "invalid_json"
    if tool not in allowed:
        return None, "other"
    return (tool, rationale), None


def _observation(tool: str, state: dict[str, Any]) -> dict[str, Any]:
    if tool == "assess_complexity":
        return {"complexity": state.get("complexity")}
    if tool == "interpret_variant":
        return {
            "escat_tier": state.get("escat_tier"),
            "evidence_records": state.get("variant_data", {}).get("evidence_records", []),
        }
    if tool == "identify_targets":
        return {"drug_candidates": state.get("drug_candidates", [])}
    if tool == "match_trials":
        return {"trial_candidates": state.get("trial_candidates", [])}
    if tool == "check_resistance":
        return {"resistance_data": state.get("resistance_data", [])}
    if tool == "enrich_oncokb":
        return {"oncokb_enrichment": state.get("oncokb_enrichment", [])}
    return {}


def run_agentic_collection(
    initial_state: dict[str, Any],
    *,
    ledger: EventLedger | None = None,
    planner_llm: Any | None = None,
    tool_registry: dict[str, Tool] | None = None,
    max_steps: int = 8,
) -> AgenticCollectionResult:
    """Esegue un ciclo plan→tool→observe limitato e completamente auditabile.

    Il planner LLM può fallire una sola volta per l'intera run: dopo la prima
    transizione a ``safe_fallback`` non viene più richiamato — gli step
    successivi usano direttamente l'ordine tipizzato sicuro, senza ulteriori
    chiamate LLM e senza moltiplicare i tentativi/timeout per ogni step.
    """
    if planner_llm is None:
        from backend.pipeline.llm import build_llm
        planner_llm = build_llm(timeout=_planner_timeout_seconds())
    tools = tool_registry or _default_tools()
    event_ledger = ledger or EventLedger()
    run_id = str(uuid4())
    state = dict(initial_state)
    completed: set[str] = set()
    tool_path: list[str] = []
    errors: list[str] = []
    tool_call_timings: list[dict[str, Any]] = []

    planning_mode = "llm_dynamic"
    fallback_locked = False
    fallback_reason: FallbackReason | None = None
    planner_attempts = 0
    planner_elapsed_ms = 0
    budget_remaining_ms = _planner_total_budget_seconds() * 1000
    timeout_seconds = _planner_timeout_seconds()
    max_attempts = 1 + _planner_max_retries()

    event_ledger.append(run_id, "run_started", "controller", {
        "case": _state_summary(state, completed)["case"],
        "max_steps": max_steps,
    })

    for step in range(1, max_steps + 1):
        allowed = _allowed_tools(state, completed)
        if not allowed:
            errors.append("Nessuno strumento consentito disponibile.")
            break

        if fallback_locked:
            tool = _fallback_tool(allowed)
            rationale = _FALLBACK_MESSAGES.get(fallback_reason, _FALLBACK_MESSAGES["other"])
        else:
            decision: tuple[str, str] | None = None
            for _attempt in range(max_attempts):
                if budget_remaining_ms <= 0:
                    fallback_reason = fallback_reason or "budget_exhausted"
                    break
                planner_attempts += 1
                started = perf_counter()
                decision, category = _attempt_planner_call(
                    state, completed, allowed, planner_llm, timeout_seconds,
                )
                elapsed = int((perf_counter() - started) * 1000)
                planner_elapsed_ms += elapsed
                budget_remaining_ms -= elapsed
                if decision is not None:
                    break
                fallback_reason = fallback_reason or category

            if decision is not None:
                tool, rationale = decision
            else:
                fallback_locked = True
                planning_mode = "safe_fallback"
                fallback_reason = fallback_reason or "other"
                tool = _fallback_tool(allowed)
                rationale = _FALLBACK_MESSAGES.get(fallback_reason, _FALLBACK_MESSAGES["other"])
                event_ledger.append(run_id, "planner_fallback_triggered", "controller", {
                    "step": step,
                    "reason_category": fallback_reason,
                    "rationale": rationale,
                    "attempts": planner_attempts,
                    "elapsed_ms": planner_elapsed_ms,
                })

        event_ledger.append(run_id, "plan_decision", "llm_planner" if not fallback_locked else "controller", {
            "step": step,
            "selected_tool": tool,
            "allowed_tools": allowed,
            "rationale": rationale,
            "fallback": fallback_locked,
        })

        if tool == "finish":
            event_ledger.append(run_id, "collection_finished", "controller", {
                "step": step,
                "completed_tools": sorted(completed),
            })
            break

        event_ledger.append(run_id, "tool_started", tool, {"step": step})
        tool_started = perf_counter()
        try:
            state = tools[tool](state)
            completed.add(tool)
            tool_path.append(tool)
            tool_call_timings.append({
                "tool": tool,
                "sequence": len(tool_path),
                "elapsed_ms": int((perf_counter() - tool_started) * 1000),
                "status": "completed",
            })
            event_ledger.append(run_id, "tool_completed", tool, {
                "step": step,
                "observation": _observation(tool, state),
            })
        except Exception as exc:
            category = _categorize_tool_exception(exc)
            logger.exception("Tool '%s' failed during agentic collection (category=%s)", tool, category)
            message = f"{tool}: {_TOOL_FAILURE_MESSAGES[category]}"
            errors.append(message)
            tool_call_timings.append({
                "tool": tool,
                "sequence": len(tool_path) + 1,
                "elapsed_ms": int((perf_counter() - tool_started) * 1000),
                "status": "failed",
            })
            event_ledger.append(run_id, "tool_failed", tool, {
                "step": step,
                "error_category": category,
            })
            break
    else:
        errors.append(f"Raggiunto il limite di {max_steps} passi.")

    event_ledger.append(run_id, "run_completed", "controller", {
        "completed_tools": tool_path,
        "errors": errors,
    })
    events = event_ledger.events(run_id)
    return AgenticCollectionResult(
        state=state,
        run_id=run_id,
        events=events,
        tool_path=tool_path,
        planning_mode=planning_mode,
        ledger_valid=event_ledger.verify_chain(run_id),
        errors=errors,
        fallback_reason=fallback_reason if planning_mode == "safe_fallback" else None,
        planner_attempts=planner_attempts,
        planner_elapsed_ms=planner_elapsed_ms,
        tool_call_timings=tool_call_timings,
    )
