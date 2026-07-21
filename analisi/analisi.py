"""
GraphRAG MTB v3 — Pipeline Agentica per Molecular Tumor Board
=============================================================
Struttura:   LangGraph StateGraph
KB:          Neo4j — 9 nodi · 11 relazioni · 30/30 casi verificati
LLM:         Gemma 4 31B (pipeline) · MiniMax M2.7 (LLM-as-judge)
Runtime:     Ollama Cloud (gratuito, no GPU richiesta)

Modifiche rispetto alla v2:
  1. LLM: ChatAnthropic → ChatOllama (Gemma 4 31B via Ollama Cloud)
  2. State: aggiunto campo alteration_type
  3. Variant Interpreter: branching per alteration_type
       point_mutation / itd → Gene→Variant→MP→Evidence (percorso classico)
       fusion / cna / atypical / biomarker → MolecularProfile.name CONTAINS
  4. Dizionario KB↔OncoKB per biomarker (TMB High↔TMB-H, MSI High↔MSI-H)
  5. Pre-query Complexity Check adattata per alteration_type non point_mutation
  6. OncoKB Enricher: nodo opzionale post-report (human-in-the-loop)
  7. Complexity Check: considera alteration_type nel routing

Gap KB documentati:
  BENCH-030: Trastuzumab deruxtecan — nessuna evidenza su gastrico nel KB
  BENCH-027: MET Exon 14 — copertura limitata (3 evidenze)
  BENCH-017: MSI High — copertura limitata (2 evidenze A, solo CRC)
"""

from __future__ import annotations

import os
import sys

# Configure standard output to use UTF-8 to prevent UnicodeEncodeError on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests
from typing import Any, Literal
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, START, END
from neo4j import GraphDatabase

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# 0. CONFIGURAZIONE
# ─────────────────────────────────────────────

NEO4J_URI      = "bolt://localhost:7687"
NEO4J_USER     = "neo4j"
# La password Neo4j arriva esclusivamente dall'ambiente: nessun valore di ripiego,
# perche' un default scritto nel codice finirebbe nella cronologia Git.
import sys as _sys
from pathlib import Path as _Path

for _root in _Path(__file__).resolve().parents:
    if (_root / "utility" / "credentials.py").is_file():
        _sys.path.insert(0, str(_root))
        break
from utility.credentials import require_env

NEO4J_PASSWORD = require_env("NEO4J_PASSWORD")


# Ollama Cloud — modelli gratuiti, no GPU
OLLAMA_BASE_URL   = "https://api.ollama.com"   # endpoint Ollama Cloud
OLLAMA_API_KEY    = os.getenv("OLLAMA_API_KEY", "")  # da variabile ambiente

LLM_PIPELINE  = "gemma4:31b-cloud"       # agenti della pipeline
LLM_JUDGE     = "gemma4:31b-cloud"       # LLM-as-judge per valutazione (fallback)
TEMPERATURE   = 0.0                      # determinismo per uso clinico

ONCOKB_TOKEN  = os.getenv("ONCOKB_TOKEN", "")  # token OncoKB API

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

llm = ChatOllama(
    model=LLM_PIPELINE,
    base_url=OLLAMA_BASE_URL,
    api_key=OLLAMA_API_KEY,
    temperature=TEMPERATURE,
)

llm_judge = ChatOllama(
    model=LLM_JUDGE,
    base_url=OLLAMA_BASE_URL,
    api_key=OLLAMA_API_KEY,
    temperature=TEMPERATURE,
)

# ─────────────────────────────────────────────
# 1. DIZIONARIO KB ↔ OncoKB
#    I nomi dei biomarker differiscono tra KB e API
# ─────────────────────────────────────────────

KB_TO_ONCOKB = {
    "TMB High":  "TMB-H",
    "MSI High":  "MSI-H",
}

ONCOKB_TO_KB = {v: k for k, v in KB_TO_ONCOKB.items()}

# ─────────────────────────────────────────────
# 2. STATE
# ─────────────────────────────────────────────

AlterationType = Literal[
    "point_mutation", "fusion", "cna", "itd", "atypical", "biomarker"
]

class MTBState(TypedDict):
    # Input clinico
    gene:               str                    # HUGO symbol (null per biomarker)
    variant:            str                    # protein change, Fusion, MSI-High
    tumor_type:         str                    # nome tumore o codice OncoTree
    alteration_type:    AlterationType         # determina logica di query e endpoint OncoKB
    therapy_line:       str                    # first-line | second-line | later-line
    enrich_with_oncokb: bool                   # attiva OncoKB Enricher (human-in-the-loop)

    # Routing
    complexity:         Literal["low", "moderate", "high"]

    # Output intermedi
    variant_data:       dict[str, Any]         # evidenze A/B + ESCAT tier
    drug_candidates:    list[dict[str, Any]]   # drug + companion diagnostic
    trial_candidates:   list[dict[str, Any]]   # trial clinici eleggibili
    resistance_data:    list[dict[str, Any]]   # evidenze di resistenza + pubblicazioni
    oncokb_enrichment:  list[dict[str, Any]]   # trattamenti OncoKB live (solo se Enricher attivo)

    # Output finale
    report:             str
    cited_pmids:        list[int]
    escat_tier:         str


# ─────────────────────────────────────────────
# 3. HELPER
# ─────────────────────────────────────────────

def run_cypher(query: str, params: dict | None = None) -> list[dict]:
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]


def _get_disease_keywords(tumor_type: str) -> list[str]:
    """Mappa il tipo di tumore in ingresso a una lista di parole chiave per la ricerca gerarchica/sinonimi nel KB."""
    t = tumor_type.lower()
    if "solid tumor" in t or t in ("cancer", "solid", "all"):
        return [""]  # stringa vuota fa sì che CONTAINS sia sempre vero
    
    keywords = []
    # Tumore del polmone
    if "lung" in t or "nsclc" in t or "bronchial" in t:
        keywords.extend(["lung", "nsclc", "bronchial"])
    # Tumore del colon-retto
    elif "colorectal" in t or "crc" in t or "colon" in t or "rectal" in t or "anus" in t:
        keywords.extend(["colorectal", "colon", "rectal", "anus"])
    # Tumore della mammella
    elif "breast" in t:
        keywords.append("breast")
    # Tumore dell'ovaio
    elif "ovarian" in t or "ovary" in t:
        keywords.extend(["ovarian", "ovary"])
    # Leucemia mieloide cronica / acuta
    elif "cml" in t or "chronic myeloid" in t:
        keywords.extend(["myeloid", "leukemia", "cml"])
    elif "aml" in t or "acute myeloid" in t:
        keywords.extend(["myeloid", "leukemia", "aml"])
    # GIST
    elif "gist" in t or "gastrointestinal" in t:
        keywords.extend(["gist", "gastrointestinal stromal"])
    # Tumore gastrico
    elif "gastric" in t or "stomach" in t:
        keywords.extend(["gastric", "stomach", "gastroesophageal"])
    # Melanoma
    elif "melanoma" in t:
        keywords.append("melanoma")
    # Cholangiocarcinoma
    elif "cholangiocarcinoma" in t or "biliary" in t:
        keywords.extend(["cholangiocarcinoma", "biliary"])
    # Tiroide
    elif "thyroid" in t:
        keywords.append("thyroid")
    # Prostata
    elif "prostate" in t:
        keywords.append("prostate")
    else:
        # Fallback sulle parole singole del tipo tumorale
        keywords.extend([w for w in t.split() if len(w) > 2])
        if not keywords:
            keywords.append(t)
            
    return keywords


# ─────────────────────────────────────────────
# 4. COMPLEXITY CHECK
#    Pre-query al KB adattata per alteration_type
#    Considera tipo variante nel routing
# ─────────────────────────────────────────────

CYPHER_PRE_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
WITH count(e) AS n_evidence,
     collect(DISTINCT e.significance) AS significances
OPTIONAL MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g2:Gene {hugo_symbol: $gene})
WHERE ANY(c IN ct.conditions WHERE ANY(kw IN $disease_keywords WHERE toLower(c) CONTAINS kw))
WITH n_evidence, significances, count(ct) AS n_trials
RETURN n_evidence, significances, n_trials
"""

CYPHER_PRE_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
WHERE e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
WITH count(e) AS n_evidence,
     collect(DISTINCT e.significance) AS significances
RETURN n_evidence, significances, 0 AS n_trials
"""

def _get_mp_keyword(alteration_type: str, variant: str) -> str:
    """Restituisce la keyword da cercare nel MolecularProfile.name."""
    if alteration_type == "fusion":
        return "fusion"
    if alteration_type == "cna":
        return "amplif" if "amplif" in variant.lower() else "deletion"
    if alteration_type == "itd":
        return "itd"
    if alteration_type == "biomarker":
        return variant.split("-")[0].strip()  # "MSI-High" → "MSI"
    if alteration_type == "atypical":
        # Estrae "exon 14", "exon 19" ecc. dal nome variante
        words = variant.lower().split()
        for i, w in enumerate(words):
            if w == "exon" and i + 1 < len(words):
                return f"exon {words[i+1]}"
        return variant.split()[0]
    return variant

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
    disease_kws = _get_disease_keywords(state["tumor_type"])

    # Pre-query adattata per tipo di variante
    if alt_type == "point_mutation":
        kb_data = run_cypher(CYPHER_PRE_POINT, {
            "gene": state["gene"],
            "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = _get_mp_keyword(alt_type, state["variant"])
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


# ─────────────────────────────────────────────
# 5. VARIANT INTERPRETER
#    Branching per alteration_type:
#    point_mutation/itd → percorso classico Gene→Variant→MP→Evidence
#    tutti gli altri    → ricerca su MolecularProfile.name
# ─────────────────────────────────────────────

# Query percorso classico (point_mutation, itd)
CYPHER_VARIANT_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(mp:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:CITED_IN]->(p:Publication)
WHERE e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
RETURN e.evidence_level     AS evidence_level,
       e.significance       AS significance,
       e.disease            AS disease,
       p.pmid               AS pmid,
       p.citation_text      AS citation_text,
       mp.name              AS molecular_profile
ORDER BY e.evidence_level ASC, size(mp.name) ASC
LIMIT 15
"""

# Query percorso MolecularProfile (fusion, cna, atypical, biomarker)
CYPHER_VARIANT_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
     -[:CITED_IN]->(p:Publication)
WHERE e.evidence_level IN ['A', 'B']
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
RETURN e.evidence_level     AS evidence_level,
       e.significance       AS significance,
       e.disease            AS disease,
       p.pmid               AS pmid,
       p.citation_text      AS citation_text,
       mp.name              AS molecular_profile
ORDER BY e.evidence_level ASC, size(mp.name) ASC
LIMIT 15
"""

# Query biomarker senza gene (MSI High, TMB High)
CYPHER_VARIANT_BIOMARKER = """
MATCH (mp:MolecularProfile)
WHERE mp.name = $mp_name
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
     -[:CITED_IN]->(p:Publication)
WHERE e.evidence_level IN ['A', 'B']
RETURN e.evidence_level     AS evidence_level,
       e.significance       AS significance,
       e.disease            AS disease,
       p.pmid               AS pmid,
       p.citation_text      AS citation_text,
       mp.name              AS molecular_profile
ORDER BY e.evidence_level ASC
LIMIT 15
"""

def _variant_interpreter_core(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = _get_disease_keywords(state["tumor_type"])

    if alt_type in ("point_mutation", "itd"):
        records = run_cypher(CYPHER_VARIANT_POINT, {
            "gene":       state["gene"],
            "variant":    state["variant"],
            "disease_keywords": disease_kws,
        })

    elif alt_type == "biomarker":
        # Traduce il nome variante nel nome esatto del MolecularProfile nel KB
        # es. "MSI-High" → "MSI High", "TMB-High" → "TMB High"
        variant_normalized = state["variant"].replace("-High", " High").replace("-H", " High")
        mp_name = ONCOKB_TO_KB.get(state["variant"], variant_normalized)
        records = run_cypher(CYPHER_VARIANT_BIOMARKER, {"mp_name": mp_name})

    else:
        # fusion, cna, atypical
        mp_keyword   = _get_mp_keyword(alt_type, state["variant"])
        gene_keyword = state["gene"] or ""
        records = run_cypher(CYPHER_VARIANT_MP, {
            "gene_keyword": gene_keyword,
            "mp_keyword":   mp_keyword,
            "disease_keywords": disease_kws,
        })

    escat_map = {"A": "I-A", "B": "II-B"}
    top_level = records[0]["evidence_level"] if records else None
    return {
        **state,
        "variant_data": {"evidence_records": records, "top_evidence_level": top_level},
        "escat_tier":   escat_map.get(top_level, "non determinato"),
    }

def variant_interpreter_low(state)      -> MTBState: return _variant_interpreter_core(state)
def variant_interpreter_moderate(state) -> MTBState: return _variant_interpreter_core(state)
def variant_interpreter_high(state)     -> MTBState: return _variant_interpreter_core(state)


# ─────────────────────────────────────────────
# 6. TARGET IDENTIFIER
#    Evidence(Sensitivity/Response) → Drug → HAS_COMPANION_DIAGNOSTIC
#    Adattato per alteration_type
# ─────────────────────────────────────────────

CYPHER_TARGET_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_level IN ['A', 'B']
  AND e.significance = 'Sensitivity/Response'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN d.drug_name       AS drug_name,
       d.approved        AS approved,
       cd.device_name    AS companion_diagnostic,
       cd.platform_type  AS cd_platform,
       e.evidence_level  AS evidence_level
ORDER BY e.evidence_level ASC
"""

CYPHER_TARGET_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
         -[:TARGETS_DRUG]->(d:Drug)
WHERE e.evidence_level IN ['A', 'B']
  AND e.significance = 'Sensitivity/Response'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
OPTIONAL MATCH (d)-[:HAS_COMPANION_DIAGNOSTIC]->(cd:CompanionDiagnostic)
RETURN d.drug_name       AS drug_name,
       d.approved        AS approved,
       cd.device_name    AS companion_diagnostic,
       cd.platform_type  AS cd_platform,
       e.evidence_level  AS evidence_level
ORDER BY e.evidence_level ASC, size(mp.name) ASC
"""

def target_identifier(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = _get_disease_keywords(state["tumor_type"])

    if alt_type in ("point_mutation", "itd"):
        records = run_cypher(CYPHER_TARGET_POINT, {
            "gene": state["gene"], "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = _get_mp_keyword(alt_type, state["variant"])
        records = run_cypher(CYPHER_TARGET_MP, {
            "gene_keyword": state["gene"] or "",
            "mp_keyword":   mp_keyword,
            "disease_keywords": disease_kws,
        })

    return {**state, "drug_candidates": records}


def route_after_target(state: MTBState) -> str:
    return "trial_matcher" if state["complexity"] == "high" else "resistance_checker"


# ─────────────────────────────────────────────
# 7. TRIAL MATCHER  (solo High)
#    ClinicalTrial → ASSOCIATED_GENE + DIAGNOSES_GENE → Disease
# ─────────────────────────────────────────────

CYPHER_TRIALS = """
MATCH (ct:ClinicalTrial)-[:ASSOCIATED_GENE]->(g:Gene {hugo_symbol: $gene})
WHERE ANY(c IN ct.conditions WHERE ANY(kw IN $disease_keywords WHERE toLower(c) CONTAINS kw))
   OR ANY(k IN ct.keywords   WHERE ANY(kw IN $disease_keywords WHERE toLower(k) CONTAINS kw))
OPTIONAL MATCH (ct)-[:TESTS_DRUG]->(d:Drug)
WHERE d.drug_name IN $drug_names
RETURN ct.nct_id     AS nct_id,
       ct.title      AS title,
       ct.phase      AS phase,
       ct.status     AS status,
       d.drug_name   AS drug_tested
ORDER BY ct.phase DESC
LIMIT 5
"""

def trial_matcher(state: MTBState) -> MTBState:
    gene       = state.get("gene") or ""
    drug_names = list({r["drug_name"] for r in state.get("drug_candidates", [])})
    disease_kws = _get_disease_keywords(state["tumor_type"])
    records    = run_cypher(CYPHER_TRIALS, {
        "gene":       gene,
        "disease_keywords": disease_kws,
        "drug_names": drug_names,
    })
    return {**state, "trial_candidates": records}


# ─────────────────────────────────────────────
# 8. RESISTANCE CHECKER  (Moderate + High)
#    Evidence(significance=Resistance) → CITED_IN → Publication
#
#    SCELTA CLINICA (da argomentare in tesi):
#    La resistenza in oncologia molecolare è un fenomeno GENE-LEVEL e
#    pathway-level, non variante-specifico. Un paziente con EGFR L858R che
#    progredisce sotto TKI sviluppa T790M, C797S, amplificazione MET — nessuna
#    è "una resistenza di L858R" in senso stretto, ma del pathway EGFR sotto
#    pressione terapeutica. Per questo il Resistance Checker:
#      1. cerca prima le resistenze della variante specifica
#      2. se assenti, fa fallback gene-level FILTRATO:
#         - esclude la variante driver stessa
#         - esclude alterazioni driver alternative (delezioni, inserzioni,
#           fusioni, amplificazioni) che NON sono resistenze acquisite ma
#           varianti sensibilizzanti alternative
#         - tiene solo mutazioni puntiformi con significance=Resistance
# ─────────────────────────────────────────────

CYPHER_RESISTANCE_POINT = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant {variant_name: $variant})
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B']
RETURN v.variant_name        AS variant,
       e.evidence_level      AS evidence_level,
       e.disease             AS disease,
       e.evidence_statement  AS statement,
       p.pmid                AS pmid,
       p.citation_text       AS citation_text
ORDER BY e.evidence_level ASC
LIMIT 5
"""

CYPHER_RESISTANCE_MP = """
MATCH (mp:MolecularProfile)
WHERE toLower(mp.name) CONTAINS toLower($gene_keyword)
  AND toLower(mp.name) CONTAINS toLower($mp_keyword)
MATCH (mp)-[:HAS_EVIDENCE]->(e:Evidence)
         -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B']
RETURN mp.name               AS variant,
       e.evidence_level      AS evidence_level,
       e.disease             AS disease,
       e.evidence_statement  AS statement,
       p.pmid                AS pmid,
       p.citation_text       AS citation_text
ORDER BY e.evidence_level ASC
LIMIT 5
"""

CYPHER_RESISTANCE_GENE = """
MATCH (g:Gene {hugo_symbol: $gene})
      -[:HAS_VARIANT]->(v:Variant)
      -[:IN_MOLECULAR_PROFILE]->(:MolecularProfile)
      -[:HAS_EVIDENCE]->(e:Evidence)
      -[:CITED_IN]->(p:Publication)
WHERE e.significance = 'Resistance'
  AND ANY(kw IN $disease_keywords WHERE toLower(e.disease) CONTAINS kw)
  AND e.evidence_level IN ['A', 'B']
OPTIONAL MATCH (e)-[:TARGETS_DRUG]->(d:Drug)
RETURN DISTINCT v.variant_name AS variant,
                e.evidence_level AS evidence_level,
                e.disease        AS disease,
                e.evidence_statement AS statement,
                p.pmid           AS pmid,
                p.citation_text  AS citation_text,
                d.drug_name      AS drug_name
ORDER BY e.evidence_level ASC, v.variant_name ASC
LIMIT 15
"""


def _is_acquired_resistance_variant(var_name: str) -> bool:
    """True se la variante è una mutazione puntiforme di resistenza acquisita
    (es. T790M, C797S, F317L), False se è una alterazione driver alternativa
    (delezione, inserzione, fusione, amplificazione, exon skipping)."""
    import re
    v = var_name.strip()
    # Esclude esplicitamente alterazioni driver alternative
    exclude_keywords = (
        "deletion", "insertion", "fusion", "amplification", "skipping",
        "exon", "duplication", "itd", "del", "ins", "mutation", "rearrangement"
    )
    if any(kw in v.lower() for kw in exclude_keywords):
        return False
    # Mutazione puntiforme classica: lettera + numero + lettera (es. T790M)
    # oppure lettera + numero + lettera multipla (es. L747S, G719X)
    return bool(re.match(r'^[A-Za-z]\d{1,4}[A-Za-z*]+$', v))


def resistance_checker(state: MTBState) -> MTBState:
    alt_type = state["alteration_type"]
    disease_kws = _get_disease_keywords(state["tumor_type"])

    records = []
    use_fallback = False

    if alt_type in ("point_mutation", "itd"):
        records = run_cypher(CYPHER_RESISTANCE_POINT, {
            "gene": state["gene"], "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = _get_mp_keyword(alt_type, state["variant"])
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
            if not _is_acquired_resistance_variant(var_name):
                continue
            filtered.append(r)

        records = filtered[:5]

    return {**state, "resistance_data": records}


# ─────────────────────────────────────────────
# 9. SYNTHESIZER
#    Verifica PMID su nodi Publication via CITED_IN
# ─────────────────────────────────────────────

CYPHER_VERIFY_PMIDS = """
MATCH (e:Evidence)-[:CITED_IN]->(p:Publication)
WHERE p.pmid IN $pmids
  AND e.evidence_level IN ['A', 'B']
RETURN DISTINCT p.pmid          AS pmid,
                p.citation_text AS citation_text
"""

SYNTHESIZER_SYSTEM = """Sei un assistente clinico esperto per Molecular Tumor Board.
Produci un report strutturato e conciso in italiano.
IMPORTANTE:
- Collega ESPLICITAMENTE ogni singola raccomandazione terapeutica, ciascun livello ESCAT e ciascun meccanismo di resistenza al relativo PMID di supporto direttamente inline nel testo (es. "Osimertinib è raccomandato come prima linea [PMID: 37937763]").
- Non limitarti a elencare i PMID alla fine del paragrafo o in fondo al report: ogni singola affermazione terapeutica o clinica nel corpo del report deve essere immediatamente seguita dal suo rispettivo PMID di supporto tra parentesi quadre.
- Se un farmaco ha associata una companion diagnostic (CDx), riportala insieme al farmaco con la relativa citazione.
- Usa SOLO i PMID verificati forniti nel contesto dell'input. Non inventare citazioni esterne.

Struttura obbligatoria:
1. Variante e classificazione ESCAT (con citazioni inline [PMID: XXXXX])
2. Terapia raccomandata (per ciascun farmaco e companion diagnostic, includere la spiegazione dell'evidenza clinica e la citazione inline [PMID: XXXXX])
3. Profilo di resistenza (descrivere le mutazioni di resistenza come T790M o C797S e come impattano le terapie, indicando esplicitamente i PMID di supporto inline [PMID: XXXXX])
4. Trial clinici eleggibili (se presenti nel contesto, con NCT ID)
5. Lista finale dei PMID verificati nel Knowledge Graph
"""

def synthesizer(state: MTBState) -> MTBState:
    raw_pmids: list[int] = []
    for r in state.get("variant_data", {}).get("evidence_records", []):
        if r.get("pmid"):
            raw_pmids.append(int(r["pmid"]))
    for r in state.get("resistance_data", []):
        if r.get("pmid"):
            raw_pmids.append(int(r["pmid"]))

    verified     = run_cypher(CYPHER_VERIFY_PMIDS, {"pmids": list(set(raw_pmids))})
    verified_map = {r["pmid"]: r["citation_text"] for r in verified}

    ctx = [
        f"=== VARIANTE ===\n"
        f"Gene: {state['gene']} | Variante: {state['variant']} | "
        f"Tipo: {state['alteration_type']} | Tumore: {state['tumor_type']} | "
        f"Linea: {state['therapy_line']}\nESCAT Tier: {state.get('escat_tier', 'N/D')}",

        "=== EVIDENZE CLINICHE (A/B) ===\n" + "\n".join(
            f"- {r['significance']} | {r['evidence_level']} | "
            f"{r['disease']} | PMID: {r['pmid']} ({r.get('citation_text', '')})"
            for r in state.get("variant_data", {}).get("evidence_records", [])
        ),
    ]

    if state.get("drug_candidates"):
        ctx.append("=== DRUG CANDIDATI ===\n" + "\n".join(
            f"- {r['drug_name']} (approvato: {r['approved']})"
            + (f" | CompDiag: {r['companion_diagnostic']}" if r.get("companion_diagnostic") else "")
            + f" | Livello: {r['evidence_level']}"
            for r in state["drug_candidates"]
        ))

    if state.get("resistance_data"):
        ctx.append("=== PROFILO DI RESISTENZA ===\n" + "\n".join(
            f"- Variante: {r.get('variant', state['variant'])} | Livello: {r['evidence_level']} | PMID: {r['pmid']} ({r.get('citation_text', '')})\n"
            f"  {r['statement'][:300]}..."
            for r in state["resistance_data"]
        ))

    if state.get("trial_candidates"):
        ctx.append("=== TRIAL CLINICI ===\n" + "\n".join(
            f"- {r['nct_id']} | {r['title']} | Fase {r['phase']} | {r['status']}"
            for r in state["trial_candidates"]
        ))

    ctx.append(
        "=== PMID VERIFICATI NEL KNOWLEDGE GRAPH ===\n" + (
            "\n".join(f"- {pmid}: {text}" for pmid, text in verified_map.items())
            if verified_map else "(nessuno verificato)"
        )
    )

    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content="\n\n".join(ctx)),
    ])

    return {**state, "report": response.content, "cited_pmids": list(verified_map.keys())}


# ─────────────────────────────────────────────
# 10. ONCOKB ENRICHER  (opzionale, human-in-the-loop)
#     Si attiva solo se enrich_with_oncokb=True
#     Endpoint diverso per alteration_type
# ─────────────────────────────────────────────

ONCOKB_BASE = "https://www.oncokb.org/api/v1/annotate"

def _oncokb_request(endpoint: str, params: dict) -> dict | None:
    headers = {
        "accept": "application/json",
        "Authorization": f"Bearer {ONCOKB_TOKEN}",
    }
    try:
        r = requests.get(f"{ONCOKB_BASE}/{endpoint}", params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[OncoKB Enricher] Errore chiamata API: {e}")
        return None

def _build_oncokb_params(state: MTBState) -> tuple[str, dict]:
    """Restituisce (endpoint, params) in base ad alteration_type."""
    alt_type   = state["alteration_type"]
    gene       = state.get("gene") or ""
    variant    = state["variant"]
    tumor_type = state["tumor_type"]

    if alt_type in ("point_mutation", "itd", "atypical"):
        alteration = "ITD" if alt_type == "itd" else variant
        return "mutations/byProteinChange", {
            "hugoSymbol": gene,
            "alteration": alteration,
            "tumorType":  tumor_type,
        }

    elif alt_type == "fusion":
        # Es. "EML4-ALK Fusion" → hugoSymbolA=EML4, hugoSymbolB=ALK
        parts = gene.split("-") if "-" in gene else [gene, ""]
        return "structuralVariants", {
            "hugoSymbolA":          parts[0],
            "hugoSymbolB":          parts[1] if len(parts) > 1 else gene,
            "structuralVariantType": "FUSION",
            "isFunctionalFusion":    "true",
            "tumorType":             tumor_type,
        }

    elif alt_type == "cna":
        cna_type = "AMPLIFICATION" if "amplif" in variant.lower() else "DELETION"
        return "copyNumberAlterations", {
            "hugoSymbol":            gene,
            "copyNameAlterationType": cna_type,
            "tumorType":             tumor_type,
        }

    elif alt_type == "biomarker":
        # MSI-High o TMB-High — nessun gene richiesto
        oncokb_alt = KB_TO_ONCOKB.get(variant, variant)
        return "mutations/byProteinChange", {
            "alteration": oncokb_alt,
            "tumorType":  tumor_type,
        }

    return "mutations/byProteinChange", {
        "hugoSymbol": gene,
        "alteration": variant,
        "tumorType":  tumor_type,
    }

def oncokb_enricher(state: MTBState) -> MTBState:
    """Nodo opzionale — si attiva solo se enrich_with_oncokb=True."""
    if not state.get("enrich_with_oncokb"):
        return {**state, "oncokb_enrichment": []}

    endpoint, params = _build_oncokb_params(state)
    data = _oncokb_request(endpoint, params)

    if not data or "treatments" not in data:
        return {**state, "oncokb_enrichment": []}

    # Farmaci già nel report base
    existing_drugs = {r["drug_name"].upper() for r in state.get("drug_candidates", [])}

    # Filtra LEVEL_1 e LEVEL_2 non già presenti nel report
    new_treatments = []
    for t in data.get("treatments", []):
        if t.get("level") not in ("LEVEL_1", "LEVEL_2"):
            continue
        drug_names = [d["drugName"].upper() for d in t.get("drugs", [])]
        if all(d in existing_drugs for d in drug_names):
            continue  # già nel report base
        new_treatments.append({
            "drugs":       [d["drugName"] for d in t.get("drugs", [])],
            "level":       t.get("level"),
            "fda_level":   t.get("fdaLevel"),
            "cancer_type": t.get("levelAssociatedCancerType", {}).get("name", ""),
            "pmids":       t.get("pmids", []),
            "description": t.get("description", "")[:400],
        })

    return {**state, "oncokb_enrichment": new_treatments}


# ─────────────────────────────────────────────
# 11. GRAFO LANGGRAPH
# ─────────────────────────────────────────────

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

    # Flusso Low
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


# ─────────────────────────────────────────────
# 12. LLM-AS-JUDGE  (valutazione separata)
#     Usa MiniMax M2.7 — modello diverso dalla pipeline
# ─────────────────────────────────────────────

JUDGE_SYSTEM = """Sei un valutatore esperto di sistemi AI per oncologia clinica.
Valuta il report MTB fornito secondo questi criteri (punteggio 1-5 per ciascuno):

1. COMPLETEZZA: il report copre variante, terapia, resistenze e trial in modo esaustivo?
2. ACCURATEZZA: le informazioni cliniche sono corrette e coerenti con le evidenze citate?
3. CITAZIONI: i PMID citati sono pertinenti e verificabili?
4. UTILITÀ CLINICA: il report è actionable per un oncologo al board?
5. STRUTTURA: il report segue la struttura obbligatoria in modo chiaro?

Restituisci un JSON con questa struttura:
{
  "completezza": <1-5>,
  "accuratezza": <1-5>,
  "citazioni": <1-5>,
  "utilita_clinica": <1-5>,
  "struttura": <1-5>,
  "score_totale": <media dei 5>,
  "motivazione": "<spiegazione sintetica>"
}
"""

def llm_as_judge(report: str, case_info: dict) -> dict:
    """Valuta un report MTB con MiniMax M2.7."""
    user_msg = (
        f"Caso: {case_info.get('gene')} {case_info.get('variant')} / "
        f"{case_info.get('tumor_type')}\n\n"
        f"Report da valutare:\n{report}"
    )
    response = llm_judge.invoke([
        SystemMessage(content=JUDGE_SYSTEM),
        HumanMessage(content=user_msg),
    ])
    import json, re
    try:
        clean = re.sub(r"```json|```", "", response.content).strip()
        return json.loads(clean)
    except Exception:
        return {"raw_response": response.content, "error": "parsing fallito"}


# ─────────────────────────────────────────────
# 13. ENTRY POINT — BENCH-001
# ─────────────────────────────────────────────

if __name__ == "__main__":
    pipeline = build_graph()

    # BENCH-001: EGFR L858R / NSCLC / prima linea
    bench_001: MTBState = {
        "gene":               "EGFR",
        "variant":            "L858R",
        "tumor_type":         "Lung Adenocarcinoma",
        "alteration_type":    "point_mutation",
        "therapy_line":       "first-line",
        "enrich_with_oncokb": False,
        # placeholder — sovrascritti dagli agenti
        "complexity":         "low",
        "variant_data":       {},
        "drug_candidates":    [],
        "trial_candidates":   [],
        "resistance_data":    [],
        "oncokb_enrichment":  [],
        "report":             "",
        "cited_pmids":        [],
        "escat_tier":         "",
    }

    final = pipeline.invoke(bench_001)

    print("═" * 60)
    print("Drug candidates:", final['drug_candidates'])
    print("Resistance data:", final['resistance_data'])
    print("═" * 60)
    print(f"Complessità    : {final['complexity']}")
    print(f"ESCAT Tier     : {final['escat_tier']}")
    print(f"PMID citati    : {final['cited_pmids']}")
    print(f"OncoKB (nuovi) : {len(final.get('oncokb_enrichment', []))} trattamenti")
    print("═" * 60)
    print(final["report"])

    # Valutazione con LLM-as-judge
    print("\n" + "═" * 60)
    print("VALUTAZIONE LLM-AS-JUDGE (Gemma 4 31B)")
    print("═" * 60)
    score = llm_as_judge(final["report"], bench_001)
    import json
    print(json.dumps(score, indent=2, ensure_ascii=False))