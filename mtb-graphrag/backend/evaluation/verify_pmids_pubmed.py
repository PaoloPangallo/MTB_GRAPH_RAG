"""
Verify PMIDs PubMed — Convalida l'esistenza e la pertinenza dei PMID citati dallo zero-shot.
Interroga in batch le API NCBI E-utilities ed utilizza MiniMax per giudicare la pertinenza.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
import requests
from langchain_core.messages import SystemMessage, HumanMessage

# Per evitare problemi di codifica in console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline.llm import llm_judge

# ── Path ───────────────────────────────────────────────────
ZEROSHOT_RESULTS_JSON = Path(__file__).resolve().parent / "results" / "zeroshot_results.json"
OUTPUT_JSON           = Path(__file__).resolve().parent / "results" / "zeroshot_pmid_verification.json"

PERTINENCE_SYSTEM_PROMPT = """Sei un oncologo clinico esperto membro di un Molecular Tumor Board.
Valuta se un articolo scientifico (identificato dal suo titolo) è clinicamente e biologicamente pertinente per un dato caso clinico (Gene, Variante, Tipo di Tumore).
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
    # Trova sia PMID: 123456 sia pmid:123456
    matches = re.findall(r'\b(?:PMID|pmid)[:\s]*(\d{6,9})\b', report_text)
    # Rimuovi duplicati mantenendo l'ordine
    seen = set()
    unique_pmids = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            unique_pmids.append(m)
    return unique_pmids

def fetch_ncbi_summaries(pmids: list[str]) -> dict[str, dict]:
    """Interroga NCBI E-utilities esummary per ottenere i dettagli degli articoli in batch."""
    if not pmids:
        return {}
    
    ids_str = ",".join(pmids)
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
    
    print(f"Interrogazione NCBI per {len(pmids)} PMID...")
    try:
        # Aggiungiamo un header user-agent amichevole per evitare blocchi
        headers = {"User-Agent": "MTB-GraphRAG-ThesisVerifier/1.0 (mailto:paolo@example.com)"}
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {})
    except Exception as e:
        print(f"Errore nella richiesta NCBI: {e}")
        return {}

def check_pertinence(gene: str, variant: str, tumor: str, title: str) -> dict:
    """Usa MiniMax per giudicare se il titolo dell'articolo è pertinente al caso."""
    prompt = (
        f"Caso clinico:\n"
        f"- Gene: {gene or 'N/D'}\n"
        f"- Variante: {variant}\n"
        f"- Tumore: {tumor}\n\n"
        f"Titolo dell'articolo:\n"
        f"\"{title}\"\n"
    )
    
    try:
        response = llm_judge.invoke([
            SystemMessage(content=PERTINENCE_SYSTEM_PROMPT),
            HumanMessage(content=prompt)
        ])
        content = response.content.strip()
        
        # Pulisce eventuali blocchi di codice markdown ```json ... ```
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        return json.loads(content)
    except Exception as e:
        print(f"Errore durante la valutazione LLM del titolo '{title}': {e}")
        return {"pertinente": True, "motivazione": "Errore fallback: assunto pertinente."}

def main():
    if not ZEROSHOT_RESULTS_JSON.exists():
        print(f"File non trovato: {ZEROSHOT_RESULTS_JSON}")
        sys.exit(1)
        
    print(f"Caricamento risultati zero-shot da: {ZEROSHOT_RESULTS_JSON}")
    with open(ZEROSHOT_RESULTS_JSON, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    # 1. Estrarre tutti i PMID da tutti i casi
    case_pmids: dict[str, list[str]] = {}
    all_pmids_set: set[str] = set()
    
    for c in cases:
        case_id = c["case_id"]
        report = c.get("report", "")
        pmids = extract_pmids_from_report(report)
        case_pmids[case_id] = pmids
        all_pmids_set.update(pmids)
        
    all_pmids = sorted(list(all_pmids_set))
    print(f"Trovati {len(all_pmids)} PMID unici citati nei report zero-shot.")
    
    if not all_pmids:
        print("Nessun PMID trovato nei report zero-shot.")
        sys.exit(0)
        
    # 2. Query NCBI in batch
    ncbi_results = fetch_ncbi_summaries(all_pmids)
    
    # 3. Classificare ogni PMID (esistenza)
    pmid_registry: dict[str, dict] = {}
    for pmid in all_pmids:
        summary = ncbi_results.get(pmid)
        if not summary or "error" in summary:
            pmid_registry[pmid] = {
                "esiste": False,
                "titolo": None,
                "pertinenza_cache": {} # mappa case_id -> dict
            }
        else:
            pmid_registry[pmid] = {
                "esiste": True,
                "titolo": summary.get("title", "Titolo non disponibile"),
                "pertinenza_cache": {}
            }
            
    # 4. Valutazione di pertinenza caso per caso
    print("\nInizio valutazione di pertinenza via LLM (MiniMax)...")
    verification_results = []
    
    total_cited = 0
    total_hallucinated = 0 # non esiste OR non pertinente
    total_non_existent = 0
    total_not_pertinent = 0
    
    for c in cases:
        case_id = c["case_id"]
        gene = c.get("gene", "")
        variant = c.get("variant", "")
        tumor = c.get("tumor_type", c.get("tumor", ""))
        
        pmids_cited = case_pmids.get(case_id, [])
        pmid_details = []
        
        print(f"\nAnalisi {case_id} ({gene} {variant}) — Citati: {len(pmids_cited)} PMID")
        
        for pmid in pmids_cited:
            total_cited += 1
            reg = pmid_registry[pmid]
            
            if not reg["esiste"]:
                total_non_existent += 1
                total_hallucinated += 1
                pmid_details.append({
                    "pmid": pmid,
                    "esiste": False,
                    "pertinente": False,
                    "motivazione": "Il PMID non esiste nel database PubMed/NCBI."
                })
                print(f"  - PMID {pmid}: NON ESISTE")
            else:
                title = reg["titolo"]
                # Caching per evitare di chiamare l'LLM più volte per lo stesso PMID sullo stesso caso (se ci fossero duplicati)
                # O tra casi diversi se hanno la stessa combinazione gene/variante/tumore
                cache_key = f"{gene}_{variant}_{tumor}"
                if cache_key in reg["pertinenza_cache"]:
                    judgement = reg["pertinenza_cache"][cache_key]
                else:
                    # Chiamata LLM
                    judgement = check_pertinence(gene, variant, tumor, title)
                    reg["pertinenza_cache"][cache_key] = judgement
                    # Delay per non saturare Ollama/LLM API
                    time.sleep(0.1)
                
                is_pertinent = judgement["pertinente"]
                mot = judgement["motivazione"]
                
                if not is_pertinent:
                    total_not_pertinent += 1
                    total_hallucinated += 1
                    print(f"  - PMID {pmid}: ESISTE MA NON PERTINENTE (Titolo: \"{title[:50]}...\")")
                else:
                    print(f"  - PMID {pmid}: OK (PERTINENTE) (Titolo: \"{title[:50]}...\")")
                    
                pmid_details.append({
                    "pmid": pmid,
                    "esiste": True,
                    "titolo": title,
                    "pertinente": is_pertinent,
                    "motivazione": mot
                })
                
        verification_results.append({
            "case_id": case_id,
            "gene": gene,
            "variant": variant,
            "tumor": tumor,
            "expected_drug": c.get("expected_drug", ""),
            "pmids_cited": pmids_cited,
            "pmid_details": pmid_details
        })
        
    # 5. Calcolo statistiche
    hallucination_rate = (total_hallucinated / total_cited * 100) if total_cited > 0 else 0.0
    non_existent_rate = (total_non_existent / total_cited * 100) if total_cited > 0 else 0.0
    not_pertinent_rate = (total_not_pertinent / total_cited * 100) if total_cited > 0 else 0.0
    
    summary_stats = {
        "totale_casi_valutati": len(cases),
        "totale_pmid_citati": total_cited,
        "totale_pmid_inesistenti": total_non_existent,
        "totale_pmid_non_pertinenti": total_not_pertinent,
        "totale_pmid_allucinati": total_hallucinated,
        "tasso_allucinazione_percento": round(hallucination_rate, 2),
        "tasso_inesistenza_percento": round(non_existent_rate, 2),
        "tasso_non_pertinenza_percento": round(not_pertinent_rate, 2),
    }
    
    output_data = {
        "statistiche": summary_stats,
        "dettagli_casi": verification_results
    }
    
    # Salva su file
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    print(f"\n{'═' * 60}")
    print("  VERIFICA PMID COMPLETATA E SALVATA")
    print(f"  File salvato in: {OUTPUT_JSON}")
    print(f"  PMID Citati Totali: {total_cited}")
    print(f"  PMID Inesistenti   : {total_non_existent} ({summary_stats['tasso_inesistenza_percento']}%)")
    print(f"  PMID Non Pertinenti: {total_not_pertinent} ({summary_stats['tasso_non_pertinenza_percento']}%)")
    print(f"  Tasso Allucinazione Complessivo: {summary_stats['tasso_allucinazione_percento']}%")
    print(f"{'═' * 60}")

if __name__ == "__main__":
    main()
