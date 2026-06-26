"""
ablation_websearch.py — Condizione 1: Zero-shot + Ricerca Web (PubMed).

Utilizza le API NCBI E-utilities per cercare articoli su PubMed e arricchire il contesto.
Calcola anche le metriche specifiche:
- pmid_exists: il PMID citato nel report esiste davvero su PubMed?
- pmid_relevant: il PMID citato è pertinente (giudicato su titolo+abstract da LLM-as-judge)?
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
import requests
from langchain_core.messages import SystemMessage, HumanMessage

from backend.pipeline.llm import llm, llm_judge
from backend.pipeline.agents.synthesizer import SYNTHESIZER_SYSTEM

PERTINENCE_SYSTEM_PROMPT = """Sei un oncologo clinico esperto membro di un Molecular Tumor Board.
Valuta se un articolo scientifico (identificato da titolo e abstract) è clinicamente e biologicamente pertinente per un dato caso clinico (Gene, Variante, Tipo di Tumore).
Un articolo è pertinente se tratta della variante specifica, della sensibilità/resistenza ai farmaci per questo gene/variante, o della biologia oncologica ad esso correlata nello stesso tumore o in tumori solidi correlati.
Non è pertinente se tratta di geni diversi, varianti non correlate, o malattie non oncologiche.

Rispondi rigorosamente in formato JSON con due chiavi:
- "pertinente": true se l'articolo è pertinente, false altrimenti.
- "motivazione": una breve frase in italiano (max 15 parole) che spiega la decisione.

Esempio di output:
{
  "pertinente": true,
  "motivazione": "Lo studio analizza l'efficacia di Osimertinib in pazienti con EGFR L858R."
}
"""

def extract_pmids_from_report(report_text: str) -> list[str]:
    """Estrae tutti i numeri di PMID citati nel report."""
    if not report_text:
        return []
    matches = re.findall(r'\b(?:PMID|pmid)[:\s]*(\d{5,9})\b', report_text)
    seen = set()
    unique_pmids = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_pmids.append(m)
    return unique_pmids

def search_pubmed(query: str, max_results: int = 5) -> list[str]:
    """Cerca su PubMed utilizzando NCBI esearch e restituisce una lista di PMIDs."""
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "MTB-Ablation/1.0"}, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"[PubMed Search] Errore esearch per query '{query}': {e}")
        return []

def fetch_pubmed_abstracts(pmids: list[str]) -> dict[str, dict]:
    """Recupera titolo, abstract, rivista e anno per un elenco di PMID usando NCBI efetch XML."""
    if not pmids:
        return {}
    ids_str = ",".join(pmids)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml"
    print(f"    [PubMed Fetch] Invio HTTP GET a NCBI efetch per {len(pmids)} PMIDs...")
    try:
        r = requests.get(url, headers={"User-Agent": "MTB-Ablation/1.0"}, timeout=15)
        print(f"    [PubMed Fetch] Ricevuto status {r.status_code}. Parsing XML in corso...")
        r.raise_for_status()
        root = ET.fromstring(r.content)
        print("    [PubMed Fetch] XML parsing completato con successo.")
        results = {}
        for article in root.findall(".//PubmedArticle"):
            pmid_el = article.find(".//PMID")
            if pmid_el is None:
                continue
            pmid = pmid_el.text
            
            # Titolo
            title = ""
            title_el = article.find(".//ArticleTitle")
            if title_el is not None:
                title = "".join(title_el.itertext())
                
            # Abstract
            abstract = ""
            abstract_el = article.find(".//Abstract")
            if abstract_el is not None:
                abstract_texts = []
                for text_el in abstract_el.findall(".//AbstractText"):
                    abstract_texts.append("".join(text_el.itertext()))
                abstract = " ".join(abstract_texts)
                
            # Rivista
            journal = ""
            journal_el = article.find(".//Journal/Title")
            if journal_el is not None:
                journal = journal_el.text
            elif article.find(".//Journal/ISOAbbreviation") is not None:
                journal = article.find(".//Journal/ISOAbbreviation").text
                
            # Anno
            year = ""
            year_el = article.find(".//JournalIssue/PubDate/Year")
            if year_el is not None:
                year = year_el.text
            else:
                medline_date_el = article.find(".//JournalIssue/PubDate/MedlineDate")
                if medline_date_el is not None:
                    m = re.search(r'\b(19|20)\d{2}\b', medline_date_el.text)
                    if m:
                        year = m.group(0)
                        
            results[pmid] = {
                "title": title or "Titolo non disponibile",
                "abstract": abstract or "Abstract non disponibile",
                "journal": journal or "N/D",
                "year": year or "N/D"
            }
        return results
    except Exception as e:
        print(f"[PubMed Fetch] Errore efetch per PMIDs {pmids}: {e}")
        return {}

def check_pmid_pertinence(gene: str, variant: str, tumor: str, title: str, abstract: str) -> dict:
    """Giudica se l'articolo è pertinente al caso clinico basandosi su titolo e abstract."""
    import concurrent.futures
    prompt = (
        f"Caso clinico:\n"
        f"- Gene: {gene or 'N/D'}\n"
        f"- Variante: {variant}\n"
        f"- Tumore: {tumor}\n\n"
        f"Articolo Scientifico:\n"
        f"- Titolo: \"{title}\"\n"
        f"- Abstract: \"{abstract}\"\n"
    )
    
    def _call():
        return llm_judge.invoke([
            SystemMessage(content=PERTINENCE_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ])
        
    for attempt in range(3):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            print(f"      [LLM Pertinence] Invoco llm_judge (Tentativo {attempt+1}/3) per valutare pertinenza: \"{title[:50]}...\"")
            future = executor.submit(_call)
            response = future.result(timeout=30)
            executor.shutdown(wait=False)
            print("      [LLM Pertinence] Valutazione pertinenza ricevuta.")
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            return json.loads(content)
        except Exception as e:
            executor.shutdown(wait=False)
            print(f"      [LLM Pertinence] Errore/Timeout al tentativo {attempt+1}: {e}")
            if attempt == 2:
                print(f"[LLM Pertinence] Fallito dopo 3 tentativi. Fallback a pertinente.")
                return {"pertinente": True, "motivazione": "Errore fallback: assunto pertinente."}
            time.sleep(2)


def run_websearch(gene: str, variant: str, tumor_type: str, alteration_type: str, therapy_line: str) -> str:
    """Esegue la ricerca PubMed, crea il contesto testuale e genera il report."""
    query = f"{gene} {variant} {tumor_type}"
    print(f"  [WebSearch] Eseguo query su PubMed: '{query}'...")
    
    pmids = search_pubmed(query, max_results=5)
    
    if pmids:
        print(f"  [WebSearch] Trovati {len(pmids)} PMIDs. Recupero abstract...")
        articles = fetch_pubmed_abstracts(pmids)
    else:
        articles = {}
        print("  [WebSearch] Nessun PMID trovato.")
        
    # Costruisci il contesto
    ctx = [
        f"=== VARIANTE ===\n"
        f"Gene: {gene} | Variante: {variant} | "
        f"Tipo: {alteration_type} | Tumore: {tumor_type} | "
        f"Linea: {therapy_line}\n"
    ]
    
    if articles:
        search_results = []
        for pmid, art in articles.items():
            search_results.append(
                f"- Articolo (PMID: {pmid}): \"{art['title']}\"\n"
                f"  Rivista: {art['journal']} | Anno: {art['year']}\n"
                f"  Abstract: {art['abstract']}"
            )
        ctx.append("=== RISULTATI DI RICERCA WEB (PUBMED) ===\n" + "\n\n".join(search_results))
    else:
        ctx.append("=== RISULTATI DI RICERCA WEB (PUBMED) ===\nNessun articolo trovato su PubMed per questo caso.")
        
    ctx.append(
        "=== NOTA ===\nUsa le tue conoscenze mediche integrate dai risultati di ricerca PubMed forniti "
        "per scrivere il report. Assicurati di associare ciascun PMID di supporto inline [PMID: XXXXXX]."
    )
    
    # Esegue l'LLM con il prompt scaffold identico
    print("  [WebSearch] Invoco LLM (ChatOllama) per la generazione del report...")
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content="\n\n".join(ctx))
    ])
    print("  [WebSearch] Generazione del report completata da LLM.")
    
    return response.content

def evaluate_websearch_pmids(report_text: str, case_info: dict) -> dict:
    """Valuta tutti i PMID estratti dal report per esistenza e pertinenza su PubMed."""
    cited_pmids = extract_pmids_from_report(report_text)
    if not cited_pmids:
        return {
            "n_cited_pmids": 0,
            "n_exists_pmids": 0,
            "n_relevant_pmids": 0,
            "pmid_exists_rate": 0.0,
            "pmid_relevant_rate": 0.0,
            "details": []
        }
        
    # Verifica esistenza e raccogli abstract
    details_map = fetch_pubmed_abstracts(cited_pmids)
    
    n_exists = 0
    n_relevant = 0
    details = []
    
    for pmid in cited_pmids:
        exists = pmid in details_map
        relevant = False
        motivazione = "N/A"
        title = None
        
        if exists:
            n_exists += 1
            art = details_map[pmid]
            title = art["title"]
            # Giudizio pertinenza
            judgement = check_pmid_pertinence(
                gene=case_info.get("gene", ""),
                variant=case_info.get("variant", ""),
                tumor=case_info.get("tumor_type", ""),
                title=art["title"],
                abstract=art["abstract"]
            )
            relevant = judgement.get("pertinente", False)
            motivazione = judgement.get("motivazione", "")
            if relevant:
                n_relevant += 1
        else:
            motivazione = "Il PMID non esiste nel database PubMed/NCBI."
            
        details.append({
            "pmid": pmid,
            "esiste": exists,
            "pertinente": relevant,
            "titolo": title,
            "motivazione": motivazione
        })
        
    return {
        "n_cited_pmids": len(cited_pmids),
        "n_exists_pmids": n_exists,
        "n_relevant_pmids": n_relevant,
        "pmid_exists_rate": round(n_exists / len(cited_pmids), 3),
        "pmid_relevant_rate": round(n_relevant / len(cited_pmids), 3) if n_exists > 0 else 0.0,
        "details": details
    }
