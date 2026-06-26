"""
Funzioni helper pure e utility per l'accesso al Knowledge Graph.

Espone:
  - run_cypher(query, params)          : esegue query Cypher su Neo4j
  - get_disease_keywords(tumor_type)   : mappa tumore → keywords per ricerca gerarchica
  - get_mp_keyword(alteration_type, variant) : keyword per MolecularProfile.name
  - is_acquired_resistance_variant(var_name) : filtro strutturale per resistenze acquisite
"""

from __future__ import annotations

import re

from backend.pipeline.llm import driver


# ── Accesso Neo4j ──────────────────────────────────────────

def run_cypher(query: str, params: dict | None = None) -> list[dict]:
    """Esegue una query Cypher e restituisce i record come lista di dict."""
    with driver.session() as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]


# ── Mapping tumore → keywords di ricerca ───────────────────

def get_disease_keywords(tumor_type: str) -> list[str]:
    """Mappa il tipo di tumore in ingresso a una lista di parole chiave
    per la ricerca gerarchica/sinonimi nel KB."""
    t = tumor_type.lower()
    if "solid tumor" in t or t in ("cancer", "solid", "all"):
        return [""]  # stringa vuota fa sì che CONTAINS sia sempre vero

    keywords: list[str] = []
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


# ── Keyword per MolecularProfile ───────────────────────────

def get_mp_keyword(alteration_type: str, variant: str) -> str:
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


# ── Filtro strutturale per resistenze acquisite ────────────

def is_acquired_resistance_variant(var_name: str) -> bool:
    """True se la variante è una mutazione puntiforme di resistenza acquisita
    (es. T790M, C797S, F317L), False se è una alterazione driver alternativa
    (delezione, inserzione, fusione, amplificazione, exon skipping)."""
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


# ── PMID clickable formatter ────────────────────────────────
def make_pmids_clickable(report_text: str) -> str:
    """Trasforma i PMID nel report in link cliccabili a PubMed, evitando parentesi quadre doppie."""
    if not report_text:
        return ""
    pattern = r'\[?\bPMID[:\s]*(\d{5,9})\b\]?'
    
    def repl(match):
        pmid = match.group(1)
        full_match = match.group(0)
        end_idx = match.end()
        after = report_text[end_idx:end_idx+5]
        if after.strip().startswith('('):
            return full_match
        return f"[PMID: {pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid})"

    return re.sub(pattern, repl, report_text, flags=re.IGNORECASE)

