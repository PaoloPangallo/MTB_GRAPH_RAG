"""
Complexity Check — Pre-query al KB + valutazione LLM della complessità del caso.
Determina il routing: low | moderate | high.
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from backend.pipeline.state import MTBState
from backend.pipeline.llm import llm
from backend.pipeline.helpers import run_cypher, get_disease_keywords, get_mp_keyword
from backend.pipeline.cypher import CYPHER_PRE_POINT, CYPHER_PRE_MP, CYPHER_PRE_BIOMARKER


COMPLEXITY_SYSTEM = """Sei un assistente clinico esperto in oncologia molecolare.
Ti vengono forniti dati strutturati dal Knowledge Graph su un caso MTB.
Restituisci SOLO una delle parole: low | moderate | high

Criteri:
- low:      evidenze dirette A/B, nessuna resistenza nota, nessun trial rilevante,
            prima linea, variante puntiforme con evidenza diretta
- moderate: drug matching non immediato, companion diagnostic richiesto,
            OR resistenza presente nelle evidenze, OR fusione/CNA/atypical
- high:     trial clinici attivi rilevanti, profilo di resistenza acquisita,
            OR terapia di seconda linea o successiva, OR biomarker tumor-agnostico
"""


def complexity_check(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = get_disease_keywords(state["tumor_type"])

    # Pre-query adattata per tipo di variante
    if alt_type == "point_mutation":
        kb_data = run_cypher(CYPHER_PRE_POINT, {
            "gene": state["gene"],
            "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    elif alt_type == "biomarker":
        v_upper = state["variant"].upper().strip()
        mp_name = "MSI High" if "MSI" in v_upper else ("TMB High" if "TMB" in v_upper else state["variant"])
        kb_data = run_cypher(CYPHER_PRE_BIOMARKER, {
            "mp_name": mp_name,
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = get_mp_keyword(alt_type, state["variant"])
        kb_data = run_cypher(CYPHER_PRE_MP, {
            "gene": state["gene"] or "",
            "mp_keyword": mp_keyword,
            "disease_keywords": disease_kws,
        })

    kb = kb_data[0] if kb_data else {"n_evidence": 0, "significances": [], "n_trials": 0}

    user_msg = (
        f"Gene: {state['gene']} | Variante: {state['variant']}\n"
        f"Tipo alterazione: {alt_type}\n"
        f"Tumore: {state['tumor_type']} | Linea: {state['therapy_line']}\n"
        f"--- Dati KB ---\n"
        f"Evidenze A/B: {kb.get('n_evidence', 0)}\n"
        f"Significance: {kb.get('significances', [])}\n"
        f"Trial attivi: {kb.get('n_trials', 0)}"
    )

    response   = llm.invoke([SystemMessage(content=COMPLEXITY_SYSTEM), HumanMessage(content=user_msg)])
    complexity = response.content.strip().lower()

    # Sanity check — alcuni tipi forzano il tier minimo
    if alt_type in ("biomarker",) and complexity == "low":
        complexity = "high"  # biomarker tumor-agnostici sono sempre almeno High
    if state["therapy_line"] in ("second-line", "later-line") and complexity == "low":
        complexity = "moderate"

    # EGFR cases have critical resistance profiles (e.g. T790M, C797S) and must be at least Moderate to run Resistance Checker
    if state.get("gene") == "EGFR" and complexity == "low":
        complexity = "moderate"

    assert complexity in ("low", "moderate", "high"), f"Valore inatteso: {complexity}"
    return {**state, "complexity": complexity}


def route_by_complexity(state: MTBState) -> str:
    return f"variant_interpreter_{state['complexity']}"
