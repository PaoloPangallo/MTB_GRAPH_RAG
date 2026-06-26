"""
Graph Assembly — Costruisce il StateGraph LangGraph e lo compila.

Questo è l'unico modulo che conosce tutti gli agenti e li assembla
nel grafo agentico. Espone:
  - build_graph()  : restituisce il grafo compilato
  - run_pipeline() : wrapper che invoca il grafo su un MTBState
"""

from __future__ import annotations

from langgraph.graph import StateGraph, START, END

from backend.pipeline.state import MTBState
from backend.pipeline.agents.complexity_check import complexity_check, route_by_complexity
from backend.pipeline.agents.variant_interpreter import (
    variant_interpreter_low,
    variant_interpreter_moderate,
    variant_interpreter_high,
)
from backend.pipeline.agents.target_identifier import target_identifier, route_after_target
from backend.pipeline.agents.trial_matcher import trial_matcher
from backend.pipeline.agents.resistance_checker import resistance_checker
from backend.pipeline.agents.synthesizer import synthesizer
from backend.pipeline.agents.oncokb_enricher import oncokb_enricher


def build_graph() -> StateGraph:
    g = StateGraph(MTBState)

    g.add_node("complexity_check",             complexity_check)
    g.add_node("variant_interpreter_low",      variant_interpreter_low)
    g.add_node("variant_interpreter_moderate", variant_interpreter_moderate)
    g.add_node("variant_interpreter_high",     variant_interpreter_high)
    g.add_node("target_identifier",            target_identifier)
    g.add_node("trial_matcher",                trial_matcher)
    g.add_node("resistance_checker",           resistance_checker)
    g.add_node("synthesizer",                  synthesizer)
    g.add_node("oncokb_enricher",              oncokb_enricher)

    g.add_edge(START, "complexity_check")

    g.add_conditional_edges(
        "complexity_check", route_by_complexity,
        {
            "variant_interpreter_low":      "variant_interpreter_low",
            "variant_interpreter_moderate": "variant_interpreter_moderate",
            "variant_interpreter_high":     "variant_interpreter_high",
        },
    )

    # Flusso Low → diretto al Synthesizer
    g.add_edge("variant_interpreter_low", "synthesizer")

    # Flusso Moderate + High convergono su target_identifier
    g.add_edge("variant_interpreter_moderate", "target_identifier")
    g.add_edge("variant_interpreter_high",     "target_identifier")

    g.add_conditional_edges(
        "target_identifier", route_after_target,
        {
            "trial_matcher":      "trial_matcher",
            "resistance_checker": "resistance_checker",
        },
    )

    g.add_edge("trial_matcher",      "resistance_checker")
    g.add_edge("resistance_checker", "synthesizer")

    # Synthesizer → OncoKB Enricher (sempre, ma l'Enricher è no-op se flag=False)
    g.add_edge("synthesizer",    "oncokb_enricher")
    g.add_edge("oncokb_enricher", END)

    return g.compile()


def run_pipeline(state: MTBState) -> MTBState:
    """Wrapper: costruisce il grafo ed esegue la pipeline su un caso MTB."""
    pipeline = build_graph()
    return pipeline.invoke(state)
