"""
Resistance Checker — Evidence(significance=Resistance) → CITED_IN → Publication.

SCELTA CLINICA (da argomentare in tesi):
La resistenza in oncologia molecolare è un fenomeno GENE-LEVEL e pathway-level,
non variante-specifico. Un paziente con EGFR L858R che progredisce sotto TKI
sviluppa T790M, C797S, amplificazione MET — nessuna è "una resistenza di L858R"
in senso stretto, ma del pathway EGFR sotto pressione terapeutica.

Per questo il Resistance Checker:
  1. cerca prima le resistenze della variante specifica
  2. se assenti, fa fallback gene-level FILTRATO:
     - esclude la variante driver stessa
     - esclude alterazioni driver alternative (delezioni, inserzioni,
       fusioni, amplificazioni) che NON sono resistenze acquisite ma
       varianti sensibilizzanti alternative
     - tiene solo mutazioni puntiformi con significance=Resistance
"""

from __future__ import annotations

from backend.pipeline.state import MTBState
from backend.pipeline.helpers import (
    run_cypher,
    get_disease_keywords,
    get_mp_keyword,
    is_acquired_resistance_variant,
)
from backend.pipeline.cypher import (
    CYPHER_RESISTANCE_POINT,
    CYPHER_RESISTANCE_MP,
    CYPHER_RESISTANCE_BIOMARKER,
    CYPHER_RESISTANCE_GENE,
    CYPHER_EXCLUDE_DRUGS,
)


def resistance_checker(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = get_disease_keywords(state["tumor_type"])

    records: list[dict] = []
    use_fallback = False

    if alt_type in ("point_mutation", "itd"):
        records = run_cypher(CYPHER_RESISTANCE_POINT, {
            "gene": state["gene"], "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    elif alt_type == "biomarker":
        v_upper = state["variant"].upper().strip()
        mp_name = "MSI High" if "MSI" in v_upper else ("TMB High" if "TMB" in v_upper else state["variant"])
        records = run_cypher(CYPHER_RESISTANCE_BIOMARKER, {
            "mp_name": mp_name,
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = get_mp_keyword(alt_type, state["variant"])
        records = run_cypher(CYPHER_RESISTANCE_MP, {
            "gene_keyword": state["gene"] or "",
            "mp_keyword":   mp_keyword,
            "disease_keywords": disease_kws,
        })

    # Fallback gene-level filtrato (scelta clinica documentata)
    if not records and state.get("gene"):
        gene_records = run_cypher(CYPHER_RESISTANCE_GENE, {
            "gene": state["gene"],
            "disease_keywords": disease_kws,
        })
        use_fallback = True

        filtered = []
        for r in gene_records:
            var_name = r.get("variant", "")
            # Esclude la variante driver stessa
            if var_name.lower() == state["variant"].lower():
                continue
            # Tiene solo mutazioni puntiformi di resistenza acquisita
            if not is_acquired_resistance_variant(var_name):
                continue
            filtered.append(r)
        records = filtered

    # Deduzione automatica della variante driver e calcolo dei farmaci inquinanti da escludere
    driver_var = state.get("driver_variant")
    if not driver_var:
        variant_upper = state["variant"].upper()
        gene_upper = (state.get("gene") or "").upper()
        if gene_upper == "EGFR" and variant_upper == "T790M":
            driver_var = "L858R"
        elif gene_upper == "ALK" and variant_upper == "G1202R":
            driver_var = "Fusion"
        elif gene_upper == "ABL1" and variant_upper == "T315I":
            driver_var = "BCR-ABL1 Fusion"
        elif gene_upper == "KIT" and variant_upper == "EXON 9 MUTATION":
            driver_var = "Exon 11 Mutation"

    exclude_drugs = []
    if driver_var and state.get("gene") and is_acquired_resistance_variant(state["variant"]):
        exclude_res = run_cypher(CYPHER_EXCLUDE_DRUGS, {
            "gene": state["gene"],
            "variant": state["variant"],
            "driver_variant": driver_var,
            "disease_keywords": disease_kws,
        })
        if exclude_res and exclude_res[0].get("exclude_drugs"):
            exclude_drugs = exclude_res[0]["exclude_drugs"]
            print(f"[Resistance Checker] Farmaci da escludere (pollution): {exclude_drugs}")

    # Filtra i farmaci inquinanti dai record
    if exclude_drugs:
        filtered = []
        for r in records:
            drug = r.get("drug_name")
            if drug and drug in exclude_drugs:
                print(f"[Resistance Checker] Escluso record per inquinamento (drug: {drug}, variante: {r.get('variant')})")
                continue
            filtered.append(r)
        records = filtered

    # Deduplica e raggruppa le resistenze trovate per variante, tenendo solo il livello migliore
    grouped_resistance = {}
    for r in records:
        var_name = r.get("variant")
        if not var_name:
            continue
        
        current_level = r.get("evidence_level", "B")
        if var_name not in grouped_resistance:
            grouped_resistance[var_name] = r
        else:
            existing_level = grouped_resistance[var_name].get("evidence_level", "B")
            # 'A' < 'B', quindi il minimo lessicografico è il livello migliore
            if current_level < existing_level:
                grouped_resistance[var_name] = r

    deduped_records = list(grouped_resistance.values())[:5]

    return {**state, "resistance_data": deduped_records}

