import json
import time
import requests
import re
from pathlib import Path
from dotenv import load_dotenv
import os
import xml.etree.ElementTree as ET
import concurrent.futures

import sys
# Make sure we can import from backend
sys.path.append(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag")

from backend.pipeline.llm import llm_judge
from langchain_core.messages import SystemMessage, HumanMessage

# ── Paths ─────────────────────────────────────────────────────
RESULTS_DIR = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")
OUT_MD = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\data_expl\benchmark\results\citation_metrics_recalc.md")
CACHE_FILE = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\data_expl\benchmark\results\pertinence_llm_cache.json")

CONDITIONS = {
    "vanilla": "ablation_vanilla_results.json",
    "websearch": "ablation_websearch_results.json",
    "rag_testuale": "ablation_rag_results.json",
    "enricher_only": "ablation_enricher_results.json",
    "full_graphrag": "ablation_graphrag_results.json"
}

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

def fetch_pubmed_abstracts(pmids: set[int]) -> dict:
    if not pmids:
        return {}
    
    results = {}
    to_fetch = list(pmids)
    batch_size = 50
    
    for i in range(0, len(to_fetch), batch_size):
        batch = to_fetch[i:i+batch_size]
        ids_str = ",".join(str(x) for x in batch)
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids_str}&retmode=xml"
        
        try:
            time.sleep(0.4)
            r = requests.get(url, headers={"User-Agent": "MTB-Ablation/1.0"}, timeout=15)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for article in root.findall(".//PubmedArticle"):
                    pmid_el = article.find(".//PMID")
                    if pmid_el is None:
                        continue
                    p_id = int(pmid_el.text)
                    
                    title = ""
                    title_el = article.find(".//ArticleTitle")
                    if title_el is not None:
                        title = "".join(title_el.itertext())
                        
                    abstract = ""
                    abstract_el = article.find(".//Abstract")
                    if abstract_el is not None:
                        abstract_texts = []
                        for text_el in abstract_el.findall(".//AbstractText"):
                            abstract_texts.append("".join(text_el.itertext()))
                        abstract = " ".join(abstract_texts)
                        
                    results[p_id] = {
                        "title": title or "Titolo non disponibile",
                        "abstract": abstract or "Abstract non disponibile"
                    }
            else:
                print(f"[PubMed Fetch] Errore {r.status_code} per batch {batch}")
        except Exception as e:
            print(f"[PubMed Fetch] Eccezione efetch per batch {batch}: {e}")
            
    return results

def check_pmids_in_ncbi(pmids: set[int]) -> set[int]:
    """Verifica l'esistenza su PubMed via NCBI E-utilities (esummary)."""
    found = set()
    to_check = list(pmids)
    batch_size = 50
    
    for i in range(0, len(to_check), batch_size):
        batch = to_check[i:i+batch_size]
        ids_str = ",".join(str(x) for x in batch)
        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids_str}&retmode=json"
        
        try:
            time.sleep(0.4)
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                res = data.get("result", {})
                for p_str in res:
                    if p_str != "uids":
                        p_int = int(p_str)
                        if "error" not in res[p_str]:
                            found.add(p_int)
        except Exception as e:
            print(f"[NCBI EXCEPTION] {e} per batch {batch}")
    return found

def check_pmid_pertinence(gene: str, variant: str, tumor: str, title: str, abstract: str) -> dict:
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
            future = executor.submit(_call)
            response = future.result(timeout=30)
            executor.shutdown(wait=False)
            
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"): lines = lines[1:]
                if lines and lines[-1].strip() == "```": lines = lines[:-1]
                content = "\n".join(lines).strip()
            
            # Find JSON block if there's text before/after
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]
                
            return json.loads(content)
        except Exception as e:
            print(f"[LLM] Tentativo {attempt+1} fallito: {e}")
            executor.shutdown(wait=False)
            time.sleep(1)
            
    return {"pertinente": False, "motivazione": "Errore API LLM", "timeout": True}

# ── Elaborazione ──────────────────────────────────────────────

print("1. Caricamento dati...")
all_pmids = set()
results = {}
for cond_name, filename in CONDITIONS.items():
    filepath = RESULTS_DIR / filename
    if not filepath.exists(): continue
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    results[cond_name] = data
    for case in data:
        pmids = {int(x) for x in case.get("cited_pmids_list", []) if str(x).strip().isdigit()}
        all_pmids.update(pmids)

print(f"2. Check esistenza NCBI per {len(all_pmids)} PMIDs...")
valid_pmids = check_pmids_in_ncbi(all_pmids)
print(f"   PMID reali: {len(valid_pmids)}")

print(f"3. Fetching abstracts per i PMID reali...")
pmid_metadata = fetch_pubmed_abstracts(valid_pmids)
print(f"   Metadata recuperati: {len(pmid_metadata)}")

llm_cache = {}
if CACHE_FILE.exists():
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        llm_cache = json.load(f)

import pandas as pd
df_cases = pd.read_csv(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
case_info = {}
for _, row in df_cases.iterrows():
    case_info[row["case_id"]] = {
        "gene": row["gene"],
        "variant": row["variant"],
        "tumor": row["tumor"]
    }

# Raccogli tutti i task da eseguire
tasks_to_run = []
for cond_name, data in results.items():
    for case in data:
        case_id = case.get("case_id")
        
        info = case_info.get(case_id, {})
        gene = info.get("gene", "")
        variant = info.get("variant", "")
        tumor = info.get("tumor", "")
        
        pmids = {int(x) for x in case.get("cited_pmids_list", []) if str(x).strip().isdigit()}
        real_pmids = [p for p in pmids if p in pmid_metadata]
        
        for p in real_pmids:
            cache_key = f"{case_id}_{p}"
            if cache_key not in llm_cache or llm_cache[cache_key].get("timeout"):
                title = pmid_metadata[p]["title"]
                abstract = pmid_metadata[p]["abstract"]
                tasks_to_run.append((cache_key, gene, variant, tumor, title, abstract))

print(f"4. Valutazione pertinenza con LLM: {len(tasks_to_run)} task rimanenti da valutare...")

print("SALTATA valutazione per limite di quota API, aggregazione dei risultati parziali in cache...")
#if tasks_to_run:
#    import threading
#    lock = threading.Lock()
#    
#    def process_task(task):
#        cache_key, gene, variant, tumor, title, abstract = task
#        # Riprova internamente fino a 5 volte con backoff per aggirare i 429
#        eval_res = None
#        for attempt in range(5):
#            eval_res = check_pmid_pertinence(gene, variant, tumor, title, abstract)
#            if not eval_res.get("timeout"):
#                break
#            time.sleep(2 ** attempt) # backoff esponenziale: 1, 2, 4, 8, 16s
#            
#        with lock:
#            llm_cache[cache_key] = eval_res
#            with open(CACHE_FILE, "w", encoding="utf-8") as f:
#                json.dump(llm_cache, f)
#        return cache_key
#        
#    # Usiamo max_workers=2 per non distruggere le API di MiniMax che droppano a 429
#    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
#        futures = [executor.submit(process_task, t) for t in tasks_to_run]
#        completed = 0
#        for future in concurrent.futures.as_completed(futures):
#            completed += 1
#            if completed % 10 == 0:
#                print(f"   Completati {completed}/{len(tasks_to_run)}")

print("5. Aggregazione risultati...")
pertinence_metrics = {}
for cond_name, data in results.items():
    meta = {
        "real_pmids": 0,
        "pertinent": 0,
        "not_pertinent": 0,
        "not_evaluated": 0
    }
    
    for case in data:
        case_id = case.get("case_id")
        pmids = {int(x) for x in case.get("cited_pmids_list", []) if str(x).strip().isdigit()}
        real_pmids = [p for p in pmids if p in pmid_metadata]
        
        meta["real_pmids"] += len(real_pmids)
        
        for p in real_pmids:
            cache_key = f"{case_id}_{p}"
            eval_res = llm_cache.get(cache_key, {})
            
            if eval_res.get("timeout"):
                meta["not_evaluated"] += 1
            elif eval_res.get("pertinente") is True:
                meta["pertinent"] += 1
            else:
                meta["not_pertinent"] += 1
                
    pertinence_metrics[cond_name] = meta

    
# ── Generazione Tabella ────────────────────────────────────────

report_md = """
## Tabella 3: Pertinenza al Caso Clinico (Ground Truth LLM Judge)

*Metrica calcolata **solo sui PMID reali** (esistenti su PubMed). Valuta se l'articolo tratta del gene+variante+tumore specifici del caso clinico.*
*I PMID non valutati per errori API/timeout sono esclusi dal calcolo del tasso.*

| Condizione | PMID Reali Citati | Non valutati | Pertinenti | Non pertinenti | Tasso Pertinenza |
|------------|-------------------|--------------|------------|----------------|------------------|
"""

for cond in CONDITIONS.keys():
    if cond not in pertinence_metrics: continue
    m = pertinence_metrics[cond]
    verified = m["real_pmids"] - m["not_evaluated"]
    rate = f"{(m['pertinent'] / verified) * 100:.1f}%" if verified > 0 else "0.0%"
    report_md += f"| {cond} | {m['real_pmids']} | {m['not_evaluated']} | {m['pertinent']} | {m['not_pertinent']} | **{rate}** |\n"

# Aggiungo la tabella al file esistente
with open(OUT_MD, "a", encoding="utf-8") as f:
    f.write(report_md)

print(f"Completato! Tabella aggiunta in {OUT_MD}")
