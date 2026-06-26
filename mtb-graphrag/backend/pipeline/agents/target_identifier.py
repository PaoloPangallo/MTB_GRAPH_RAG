"""
Target Identifier — Evidence(Sensitivity/Response) → Drug → HAS_COMPANION_DIAGNOSTIC.
Adattato per alteration_type.
"""

from __future__ import annotations

from backend.pipeline.state import MTBState
from backend.pipeline.helpers import run_cypher, get_disease_keywords, get_mp_keyword
from backend.pipeline.cypher import CYPHER_TARGET_POINT, CYPHER_TARGET_MP, CYPHER_TARGET_BIOMARKER


def target_identifier(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = get_disease_keywords(state["tumor_type"])

    if alt_type in ("point_mutation", "itd"):
        records = run_cypher(CYPHER_TARGET_POINT, {
            "gene": state["gene"], "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    elif alt_type == "biomarker":
        v_upper = state["variant"].upper().strip()
        mp_name = "MSI High" if "MSI" in v_upper else ("TMB High" if "TMB" in v_upper else state["variant"])
        records = run_cypher(CYPHER_TARGET_BIOMARKER, {
            "mp_name": mp_name,
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = get_mp_keyword(alt_type, state["variant"])
        records = run_cypher(CYPHER_TARGET_MP, {
            "gene_keyword": state["gene"] or "",
            "mp_keyword":   mp_keyword,
            "disease_keywords": disease_kws,
        })

    # Raggruppa e deduplica per drug_name
    grouped = {}
    for r in records:
        name = r.get("drug_name")
        if not name:
            continue
        
        approved = r.get("approved", False)
        cd = r.get("companion_diagnostic")
        plat = r.get("cd_platform")
        ev_level = r.get("evidence_level")
        
        if name not in grouped:
            grouped[name] = {
                "drug_name": name,
                "approved": approved,
                "companion_diagnostics": set(),
                "cd_platforms": set(),
                "evidence_levels": set()
            }
        
        if approved:
            grouped[name]["approved"] = True
        if cd:
            grouped[name]["companion_diagnostics"].add(cd)
        if plat:
            grouped[name]["cd_platforms"].add(plat)
        if ev_level:
            grouped[name]["evidence_levels"].add(ev_level)

    deduped_records = []
    for name, info in grouped.items():
        # Il livello migliore è il minimo lessicografico (A < B < C...)
        best_level = min(info["evidence_levels"]) if info["evidence_levels"] else "B"
        cd_str = ", ".join(sorted(info["companion_diagnostics"])) if info["companion_diagnostics"] else None
        plat_str = ", ".join(sorted(info["cd_platforms"])) if info["cd_platforms"] else None
        
        deduped_records.append({
            "drug_name": name,
            "approved": info["approved"],
            "companion_diagnostic": cd_str,
            "cd_platform": plat_str,
            "evidence_level": best_level
        })

    # Ordina per livello di evidenza e poi nome farmaco
    deduped_records.sort(key=lambda x: (x["evidence_level"], x["drug_name"]))

    return {**state, "drug_candidates": deduped_records}


def route_after_target(state: MTBState) -> str:
    # Abilitato trial_matcher sia per moderate che per high per coprire i casi clinici rilevanti (es. EGFR L858R)
    return "trial_matcher" if state["complexity"] in ("moderate", "high") else "resistance_checker"

