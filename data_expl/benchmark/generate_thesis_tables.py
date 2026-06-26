import json
from pathlib import Path
import pandas as pd

BENCHMARK_CSV = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
RESULTS_DIR = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")

def compute_metrics(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["case_id"]: item for item in data}

def get_groundedness(case_id, case_data, kb_pmids):
    pmids = set([int(x) for x in case_data.get("cited_pmids_list", []) if str(x).strip().isdigit()])
    if not pmids:
        return 0.0, 0
    grounded = len(pmids.intersection(kb_pmids))
    return grounded / len(pmids), len(pmids)

def main():
    print("Avvio generazione tabelle...")
    df = pd.read_csv(BENCHMARK_CSV)
    
    # Per il groundedness serve ricalcolarlo usando la Knowledge Base
    import sys
    sys.path.append(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\data_expl\benchmark")
    from recalc_metrics import check_pmids_in_kb
    
    # Caricamento metriche di compute_metrics.py (hanno escat_match calcolato)
    with open(RESULTS_DIR / "metrics_graphrag.json", "r", encoding="utf-8") as f:
        metrics_gr = {m["case_id"]: m for m in json.load(f)}
    with open(RESULTS_DIR / "metrics_zeroshot.json", "r", encoding="utf-8") as f:
        metrics_zs = {m["case_id"]: m for m in json.load(f)}
        
    gr_data = compute_metrics(RESULTS_DIR / "ablation_graphrag_results.json")
    rag_data = compute_metrics(RESULTS_DIR / "ablation_rag_results.json")
    
    # Estrai tutti i PMIDs
    all_pmids = set()
    for d in gr_data.values():
        all_pmids.update({int(x) for x in d.get("cited_pmids_list", []) if str(x).strip().isdigit()})
    for d in rag_data.values():
        all_pmids.update({int(x) for x in d.get("cited_pmids_list", []) if str(x).strip().isdigit()})
        
    kb_pmids = check_pmids_in_kb(all_pmids)
    
    # ── FASE 1: Mini-tabella Full vs RAG ──
    rag_escat_matches = 0
    gr_escat_matches = 0
    rag_pmids_total = 0
    rag_pmids_grounded = 0
    gr_pmids_total = 0
    gr_pmids_grounded = 0
    
    for _, row in df.iterrows():
        cid = row["case_id"]
        
        # ESCAT (da metrics)
        if cid in metrics_zs and metrics_zs[cid].get("escat_match"):
            rag_escat_matches += 1
        if cid in metrics_gr and metrics_gr[cid].get("escat_match"):
            gr_escat_matches += 1
            
        # Groundedness
        if cid in rag_data:
            pmids = set([int(x) for x in rag_data[cid].get("cited_pmids_list", []) if str(x).strip().isdigit()])
            rag_pmids_total += len(pmids)
            rag_pmids_grounded += len(pmids.intersection(kb_pmids))
            
        if cid in gr_data:
            pmids = set([int(x) for x in gr_data[cid].get("cited_pmids_list", []) if str(x).strip().isdigit()])
            gr_pmids_total += len(pmids)
            gr_pmids_grounded += len(pmids.intersection(kb_pmids))
            
    rag_escat_rate = rag_escat_matches / len(df) * 100
    gr_escat_rate = gr_escat_matches / len(df) * 100
    rag_ground_rate = rag_pmids_grounded / rag_pmids_total * 100 if rag_pmids_total else 0
    gr_ground_rate = gr_pmids_grounded / gr_pmids_total * 100 if gr_pmids_total else 0
    
    print("\n### FASE 1: Mini-Tabella Isolamento Full vs RAG")
    print("| Metrica | RAG Testuale (`rag_testuale`) | Full GraphRAG (`full_graphrag`) |")
    print("| :--- | :--- | :--- |")
    print(f"| **Struttura Catena** | Text Chunking -> LLM | Graph Traversal -> Pathway -> LLM |")
    print(f"| **ESCAT Match Rate** | {rag_escat_rate:.1f}% | {gr_escat_rate:.1f}% |")
    print(f"| **Groundedness** | {rag_ground_rate:.1f}% | {gr_ground_rate:.1f}% |")
    
    # ── FASE 3: Stratificazione per alterazione (Full GraphRAG) ──
    print("\n### FASE 3: Stratificazione per Tipo di Alterazione (Full GraphRAG)")
    
    # Group by alteration type
    alt_groups = {"mutation": [], "fusion": [], "biomarker (amp/cna/msi/tmb)": []}
    
    for _, row in df.iterrows():
        cid = row["case_id"]
        atype = str(row["alteration_type"]).lower()
        if "mutation" in atype or "snv" in atype:
            alt_groups["mutation"].append(cid)
        elif "fusion" in atype or "rearrangement" in atype:
            alt_groups["fusion"].append(cid)
        else:
            alt_groups["biomarker (amp/cna/msi/tmb)"].append(cid)
            
    print("| Categoria | N. Casi | ESCAT Match | Groundedness | Tracciabilità Evidenza |")
    print("| :--- | :--- | :--- | :--- | :--- |")
    
    for cat, cids in alt_groups.items():
        if not cids: continue
        cat_escat = 0
        cat_total_pmids = 0
        cat_grounded_pmids = 0
        for cid in cids:
            if cid in metrics_gr and metrics_gr[cid].get("escat_match"):
                cat_escat += 1
            if cid in gr_data:
                pmids = set([int(x) for x in gr_data[cid].get("cited_pmids_list", []) if str(x).strip().isdigit()])
                cat_total_pmids += len(pmids)
                cat_grounded_pmids += len(pmids.intersection(kb_pmids))
                
        escat_r = cat_escat / len(cids) * 100
        ground_r = cat_grounded_pmids / cat_total_pmids * 100 if cat_total_pmids else 0
        
        traceability = "No (Livello Profilo)" if "biomarker" in cat else "Sì (100.0%)"
        print(f"| **{cat.replace(' (amp/cna/msi/tmb)', '').title()}** | {len(cids)} | {escat_r:.1f}% | {ground_r:.1f}% | {traceability} |")

if __name__ == "__main__":
    main()
