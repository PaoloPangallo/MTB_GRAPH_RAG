"""
Variant Interpreter — Branching per alteration_type:
  point_mutation / itd → percorso classico Gene→Variant→MP→Evidence
  tutti gli altri      → ricerca su MolecularProfile.name
"""

from __future__ import annotations

from backend.pipeline.state import MTBState
from backend.pipeline.helpers import run_cypher, get_disease_keywords, get_mp_keyword
from backend.pipeline.mappings import ONCOKB_TO_KB
from backend.pipeline.cypher import (
    CYPHER_VARIANT_POINT,
    CYPHER_VARIANT_MP,
    CYPHER_VARIANT_BIOMARKER,
)


from langchain_core.messages import SystemMessage
from backend.pipeline.llm import llm

INTERPRETER_SYSTEM = """Sei un oncologo computazionale esperto. Il tuo compito è classificare il livello ESCAT (ESMO Scale for Clinical Actionability of molecular Targets) globale per il paziente in base alle evidenze cliniche fornite.

Definizioni dei Tier ESCAT:
- Tier I: Target pronto per l'uso clinico.
  - I-A: Terapia mirata specifica approvata e raccomandata come standard di cura per la specifica mutazione nello stesso tumore del paziente (evidenza da trial di fase III randomizzati).
  - I-B: Terapia mirata specifica approvata e raccomandata per la specifica mutazione nello stesso tumore del paziente, ma basata su trial di fase II o coorti non randomizzate.
  - I-C: Terapia approvata con indicazione tumor-agnostic (indipendente dall'istologia, es. NTRK fusions, MSI-High, TMB-High) per tumori solidi avanzati.
- Tier II: Target terapeutico potenziale.
  - II-A: Evidenza di attività clinica promettente nello stesso tipo di tumore, ma priva di approvazione regolatoria formale per questo setting.
  - II-B: Evidenza di risposta clinica solo in altri tipi di tumore (off-label) o basata su studi retrospettivi preliminari nello stesso tumore.
- Tier III-IV o non determinato: Evidenze scarse o precliniche.

Dati del paziente:
- Gene: {gene}
- Variante: {variant}
- Tumore: {tumor}

Evidenze estratte dal Knowledge Graph:
{evidences}

Assegna il livello ESCAT globale più appropriato tra: "I-A", "I-B", "I-C", "II", "II-B", "non determinato".
REGOLA CRITICA 1: Se il Livello dell'evidenza in KB è "A" (o "1", "LEVEL_1") e il "Match istologico" è "SÌ", DEVI assegnare TASSATIVAMENTE il Tier "I-A".
REGOLA CRITICA 2: Se il Livello dell'evidenza in KB è "B" (o "2", "LEVEL_2") e il "Match istologico" è "SÌ", DEVI assegnare TASSATIVAMENTE il Tier "I-B".
REGOLA CRITICA 3: Se il campo "Match istologico" è "NO", il tier deve essere declassato (Livello A/B in tumore diverso → II-B; mai I-A o I-B off-label).
REGOLA CRITICA 4: Se la Significatività è "Resistance", assegna sempre "non determinato".
Restituisci SOLO ed ESCLUSIVAMENTE la sigla del Tier (es. "I-A", "I-C" o "non determinato"), senza preamboli, spiegazioni o punteggiatura."""

def _is_same_tumor(evidence_disease: str, patient_tumor: str) -> bool:
    """Confronto semantico tra tumore dell'evidenza e tumore del paziente basato sulle keyword della KB."""
    if not evidence_disease or not patient_tumor:
        return False
    ev = evidence_disease.lower().strip()
    pt = patient_tumor.lower().strip()
    if ev == pt or ev in pt or pt in ev:
        return True
        
    from backend.pipeline.helpers import get_disease_keywords
    keywords = get_disease_keywords(patient_tumor)
    
    if keywords == [""]:
        return True
        
    for kw in keywords:
        if kw and kw in ev:
            return True
            
    if "solid tumor" in ev:
        return True
        
    return False

def _variant_interpreter_core(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = get_disease_keywords(state["tumor_type"])

    if alt_type in ("point_mutation", "itd"):
        records = run_cypher(CYPHER_VARIANT_POINT, {
            "gene":       state["gene"],
            "variant":    state["variant"],
            "disease_keywords": disease_kws,
        })

    elif alt_type == "biomarker":
        # Traduce il nome variante nel nome esatto del MolecularProfile nel KB in modo robusto
        v_upper = state["variant"].upper().strip()
        if "MSI" in v_upper:
            mp_name = "MSI High"
        elif "TMB" in v_upper:
            mp_name = "TMB High"
        else:
            variant_normalized = state["variant"].replace("-High", " High").replace("-H", " High")
            mp_name = ONCOKB_TO_KB.get(state["variant"], variant_normalized)
        records = run_cypher(CYPHER_VARIANT_BIOMARKER, {
            "mp_name": mp_name,
            "disease_keywords": disease_kws,
        })

    else:
        # fusion, cna, atypical
        mp_keyword   = get_mp_keyword(alt_type, state["variant"])
        gene_keyword = state["gene"] or ""
        records = run_cypher(CYPHER_VARIANT_MP, {
            "gene_keyword": gene_keyword,
            "mp_keyword":   mp_keyword,
            "disease_keywords": disease_kws,
        })

    escat_tier = "non determinato"
    if records:
        evidences_str = "\n".join(
            f"- Significatività: {r['significance']} | "
            f"Livello: {r['evidence_level']} | "
            f"Tumore evidenza: {r['disease']} | "
            f"Match istologico: {'SÌ' if _is_same_tumor(r['disease'], state['tumor_type']) else 'NO (tumore diverso)'} | "
            f"PMID: {r['pmid']}"
            for r in records
        )
        
        prompt = INTERPRETER_SYSTEM.format(
            gene=state["gene"],
            variant=state["variant"],
            tumor=state["tumor_type"],
            evidences=evidences_str
        )
        
        try:
            response = llm.invoke([SystemMessage(content=prompt)])
            extracted = response.content.strip().upper()
            
            # Normalizza varianti comuni che l'LLM produce
            extracted = extracted.replace('"', '').replace("'", "").strip()
            valid_tiers = {"I-A", "I-B", "I-C", "II-A", "II-B", "NON DETERMINATO"}
            
            if extracted in valid_tiers:
                escat_tier = extracted if extracted != "II-A" else "II"
            else:
                # Fallback intelligente basato su resistenza + match tumore
                first = records[0]
                if "resistance" in first.get("significance", "").lower():
                    escat_tier = "non determinato"
                elif _is_same_tumor(first.get("disease", ""), state["tumor_type"]):
                    escat_tier = {"A": "I-A", "B": "I-B", "C": "II-A", "D": "II-B"}.get(
                        first["evidence_level"], "non determinato")
                else:
                    # Off-label: declassa di un livello
                    escat_tier = {"A": "II-A", "B": "II-B", "C": "non determinato"}.get(
                        first["evidence_level"], "non determinato")
        except Exception:
            escat_tier = "non determinato"

    return {
        **state,
        "variant_data": {"evidence_records": records, "top_evidence_level": records[0]["evidence_level"] if records else None},
        "escat_tier": escat_tier,
    }


def variant_interpreter_low(state: MTBState)      -> MTBState: return _variant_interpreter_core(state)
def variant_interpreter_moderate(state: MTBState) -> MTBState: return _variant_interpreter_core(state)
def variant_interpreter_high(state: MTBState)     -> MTBState: return _variant_interpreter_core(state)
