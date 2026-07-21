import json
import time
import requests
import re
from pathlib import Path
from dotenv import load_dotenv
import os
from neo4j import GraphDatabase

# ── Paths ─────────────────────────────────────────────────────
RESULTS_DIR = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")
OUT_MD = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\data_expl\benchmark\results\citation_metrics_recalc.md")
OUT_MD.parent.mkdir(parents=True, exist_ok=True)

CONDITIONS = {
    "vanilla": "ablation_vanilla_results.json",
    "websearch": "ablation_websearch_results.json",
    "rag_testuale": "ablation_rag_results.json",
    "enricher_only": "ablation_enricher_results.json",
    "full_graphrag": "ablation_graphrag_results.json"
}

# ── Neo4j ─────────────────────────────────────────────────────
_env_path = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\.env")
load_dotenv(_env_path)
# La password Neo4j arriva esclusivamente dall'ambiente: nessun valore di ripiego,
# perche' un default scritto nel codice finirebbe nella cronologia Git.
import sys as _sys
from pathlib import Path as _Path

for _root in _Path(__file__).resolve().parents:
    if (_root / "utility" / "credentials.py").is_file():
        _sys.path.insert(0, str(_root))
        break
from utility.credentials import require_env

_NEO4J_PASSWORD = require_env("NEO4J_PASSWORD")
_drv = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", _NEO4J_PASSWORD))

def check_pmids_in_kb(pmids: set[int]) -> set[int]:
    if not pmids:
        return set()
    query = """
    MATCH (p:Publication)
    WHERE p.pmid IN $pmids
    RETURN p.pmid AS pmid
    """
    try:
        with _drv.session() as session:
            res = session.run(query, {"pmids": list(pmids)})
            return {int(r["pmid"]) for r in res if r.get("pmid")}
    except Exception as e:
        print(f"[ERRORE NEO4J] {e}")
        return set()

# ── NCBI ──────────────────────────────────────────────────────
_ncbi_cache = {}
ncbi_unchecked = set()

def check_pmids_in_ncbi(pmids: set[int]) -> set[int]:
    """Verifica l'esistenza su PubMed via NCBI E-utilities, con rate limit."""
    found = set()
    to_check = []
    
    for p in pmids:
        if p in _ncbi_cache:
            if _ncbi_cache[p]:
                found.add(p)
        else:
            to_check.append(p)
            
    if not to_check:
        return found
        
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
                            _ncbi_cache[p_int] = True
                            found.add(p_int)
                        else:
                            _ncbi_cache[p_int] = False
                for p in batch:
                    if p not in _ncbi_cache:
                        _ncbi_cache[p] = False
            else:
                print(f"[NCBI ERROR] Status {resp.status_code} per batch {batch}")
                ncbi_unchecked.update(batch)
        except Exception as e:
            print(f"[NCBI EXCEPTION] {e} per batch {batch}")
            ncbi_unchecked.update(batch)
            
    return found

# ── Elaborazione ──────────────────────────────────────────────
results = {}
all_pmids_ever = set()
special_cases_log = {}

for cond_name, filename in CONDITIONS.items():
    filepath = RESULTS_DIR / filename
    if not filepath.exists():
        print(f"[WARN] File mancante: {filename}")
        continue
        
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    total_cited = 0
    
    for case in data:
        # BUG 3 FIX: check if the key exists at all in the first place
        if "cited_pmids_list" not in case:
            print(f"[ERROR] 'cited_pmids_list' mancante nel file {filename} caso {case.get('case_id')}.")
            import sys
            sys.exit(1)
            
        # BUG 1 FIX: Normalizza i PMID ad interi
        raw_pmids = case.get("cited_pmids_list", [])
        pmids = {int(x) for x in raw_pmids if str(x).strip().isdigit()}
        
        all_pmids_ever.update(pmids)
        total_cited += len(pmids)
        
        # BUG 2 FIX: special_cases_log definito a livello globale
        if cond_name == "full_graphrag" and case.get("case_id") in ["BENCH-017", "BENCH-023"]:
            special_cases_log[case.get("case_id")] = pmids
            
    results[cond_name] = {
        "cases": data,
        "total_cited": total_cited
    }

print(f"Pre-caching di {len(all_pmids_ever)} PMIDs univoci da NCBI e Neo4j...")
ncbi_valid = check_pmids_in_ncbi(all_pmids_ever)
kb_valid = check_pmids_in_kb(all_pmids_ever)
print(f"Fatto. Validi NCBI: {len(ncbi_valid)}. Validi KB: {len(kb_valid)}. Non verificati NCBI: {len(ncbi_unchecked)}")

# Calcolo finale
for cond, meta in results.items():
    ncbi_count = 0
    kb_count = 0
    unchecked_count = 0
    
    for case in meta["cases"]:
        raw_pmids = case.get("cited_pmids_list", [])
        pmids = {int(x) for x in raw_pmids if str(x).strip().isdigit()}
        
        for p in pmids:
            if p in ncbi_unchecked:
                unchecked_count += 1
            elif p in ncbi_valid: 
                ncbi_count += 1
            
            if p in kb_valid: 
                kb_count += 1
            
    meta["ncbi_found"] = ncbi_count
    meta["kb_found"] = kb_count
    meta["ncbi_unchecked"] = unchecked_count
    
    # BUG 4 FIX: exclude unchecked from denominator
    verified_total = meta["total_cited"] - unchecked_count
    
    meta["fabrication_rate"] = 1 - (ncbi_count / verified_total) if verified_total > 0 else 0
    meta["groundedness"] = kb_count / meta["total_cited"] if meta["total_cited"] > 0 else 0

# Special logs
special_txt = ""
if "full_graphrag" in results:
    special_txt = "### Casi biomarker speciali (full_graphrag)\n"
    for cid, pmids in special_cases_log.items():
        kb_c = sum(1 for p in pmids if p in kb_valid)
        special_txt += f"- **{cid}**: {len(pmids)} PMID citati, di cui {kb_c} collegati nel grafo.\n"

# ── Generazione Report ────────────────────────────────────────

report = f"""# Ricalcolo delle metriche di citazione per l'ablation study

> Report generato automaticamente.
> Ground truth ESTERNO: PubMed (via NCBI E-utilities).
> Ground truth INTERNO: Grafo Neo4j (GraphRAGTesi).

## Tabella 1: Fabrication Rate (Ground Truth Esterno)

*Metrica KB-indipendente: confrontabile alla pari tra tutte le condizioni. Indica quanti PMID citati non esistono affatto in letteratura.*
*Nota: i PMID che hanno subito timeout NCBI non sono contati nel denominatore.*

| Condizione | PMID Totali Citati | Non verificabili (Rete) | Esistenti su PubMed (NCBI) | Fabbricati (Inventati) | Fabrication Rate |
|------------|-------------------|-------------------------|----------------------------|------------------------|------------------|
"""

for cond in CONDITIONS.keys():
    if cond not in results: continue
    m = results[cond]
    verified_tot = m["total_cited"] - m["ncbi_unchecked"]
    fab = verified_tot - m["ncbi_found"]
    rate = f"{m['fabrication_rate']*100:.1f}%"
    report += f"| {cond} | {m['total_cited']} | {m['ncbi_unchecked']} | {m['ncbi_found']} | {fab} | **{rate}** |\n"

report += """
## Tabella 2: KB-Groundedness (Ground Truth Interno)

*Metrica KB-dipendente. Indica la frazione di PMID citati che deriva effettivamente dai nodi Publication presenti nel grafo. Il confronto leale è solo tra `full_graphrag` e `rag_testuale`.*

| Condizione | PMID Totali Citati | Tracciabili nel KG Neo4j | KB-Groundedness | Note |
|------------|-------------------|--------------------------|-----------------|------|
"""

for cond in CONDITIONS.keys():
    if cond not in results: continue
    m = results[cond]
    note = "Confronto leale" if cond in ["full_graphrag", "rag_testuale"] else "no-KB, riferimento"
    rate = f"{m['groundedness']*100:.1f}%"
    report += f"| {cond} | {m['total_cited']} | {m['kb_found']} | **{rate}** | {note} |\n"

report += f"\n{special_txt}"

with open(OUT_MD, "w", encoding="utf-8") as f:
    f.write(report)

print(f"Report generato con successo in: {OUT_MD}")

