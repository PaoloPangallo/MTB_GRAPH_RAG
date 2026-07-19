"""Planner agentico con strumenti allow-listed e ledger scritto durante l'esecuzione."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger


Tool = Callable[[dict[str, Any]], dict[str, Any]]


PLANNER_SYSTEM = """Sei il planner di raccolta evidenze per un Molecular Tumor Board.
Scegli UN solo prossimo strumento dalla lista consentita. Puoi cambiare piano dopo
ogni osservazione. Non formulare raccomandazioni terapeutiche e non inventare dati.
Termina quando le evidenze necessarie sono state raccolte o quando gli strumenti
disponibili non possono ridurre l'incertezza.

Restituisci esclusivamente JSON valido:
{"tool": "nome_strumento", "rationale": "motivazione breve"}
"""


@dataclass
class AgenticCollectionResult:
    state: dict[str, Any]
    run_id: str
    events: list[dict[str, Any]]
    tool_path: list[str]
    planning_mode: str
    ledger_valid: bool
    errors: list[str]


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


def _choose_tool(
    state: dict[str, Any],
    completed: set[str],
    allowed: list[str],
    planner_llm: Any,
) -> tuple[str, str, bool]:
    prompt = json.dumps({
        "stato": _state_summary(state, completed),
        "strumenti_consentiti": allowed,
    }, ensure_ascii=False, sort_keys=True)
    try:
        response = planner_llm.invoke([
            ("system", PLANNER_SYSTEM),
            ("human", prompt),
        ])
        tool, rationale = _parse_decision(response.content)
        if tool not in allowed:
            raise ValueError(f"Strumento non consentito: {tool}")
        return tool, rationale, False
    except Exception as exc:
        fallback = _fallback_tool(allowed)
        return fallback, f"Fallback sicuro dopo errore del planner: {exc}", True


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
    """Esegue un ciclo plan→tool→observe limitato e completamente auditabile."""
    if planner_llm is None:
        from backend.pipeline.llm import llm
        planner_llm = llm
    tools = tool_registry or _default_tools()
    event_ledger = ledger or EventLedger()
    run_id = str(uuid4())
    state = dict(initial_state)
    completed: set[str] = set()
    tool_path: list[str] = []
    errors: list[str] = []
    used_fallback = False

    event_ledger.append(run_id, "run_started", "controller", {
        "case": _state_summary(state, completed)["case"],
        "max_steps": max_steps,
    })

    for step in range(1, max_steps + 1):
        allowed = _allowed_tools(state, completed)
        if not allowed:
            errors.append("Nessuno strumento consentito disponibile.")
            break
        tool, rationale, fallback = _choose_tool(
            state,
            completed,
            allowed,
            planner_llm,
        )
        used_fallback = used_fallback or fallback
        event_ledger.append(run_id, "plan_decision", "llm_planner", {
            "step": step,
            "selected_tool": tool,
            "allowed_tools": allowed,
            "rationale": rationale,
            "fallback": fallback,
        })

        if tool == "finish":
            event_ledger.append(run_id, "collection_finished", "controller", {
                "step": step,
                "completed_tools": sorted(completed),
            })
            break

        event_ledger.append(run_id, "tool_started", tool, {"step": step})
        try:
            state = tools[tool](state)
            completed.add(tool)
            tool_path.append(tool)
            event_ledger.append(run_id, "tool_completed", tool, {
                "step": step,
                "observation": _observation(tool, state),
            })
        except Exception as exc:
            message = f"{tool}: {exc}"
            errors.append(message)
            event_ledger.append(run_id, "tool_failed", tool, {
                "step": step,
                "error": str(exc),
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
        planning_mode="safe_fallback" if used_fallback else "llm_dynamic",
        ledger_valid=event_ledger.verify_chain(run_id),
        errors=errors,
    )
