import sys
import json
import shutil
from pathlib import Path

# Configura UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Path import backend
sys.path.append(str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))

from backend.evaluation.compute_metrics import (
    extract_pmids_from_report,
    check_pmids_exist_in_kb
)

RESULTS_DIR = Path(__file__).resolve().parents[1] / "mtb-graphrag" / "backend" / "evaluation" / "results"

# Lista di tutti i file JSON dei risultati da ricalcolare
json_files = [
    ("Gemma GraphRAG", RESULTS_DIR / "ablation_graphrag_results.json"),
    ("Gemma Vanilla", RESULTS_DIR / "ablation_vanilla_results.json"),
    ("Gemma Websearch", RESULTS_DIR / "ablation_websearch_results.json"),
    ("Gemma RAG Testuale", RESULTS_DIR / "ablation_rag_results.json"),
    ("Gemma Enricher Only", RESULTS_DIR / "ablation_enricher_results.json"),
    ("Qwen GraphRAG", RESULTS_DIR / "ablation_second_llm_graphrag_results.json"),
    ("Qwen Vanilla", RESULTS_DIR / "ablation_second_llm_vanilla_results.json"),
]

print("="*80)
print("RICALCOLO GENERALE DELLE METRICHE CON REGEX ALL-NUMBERS SU TUTTI I DATASET")
print("="*80)

for label, file_path in json_files:
    if not file_path.exists():
        print(f"File non trovato: {file_path.name}")
        continue
        
    # Backup
    shutil.copy2(file_path, file_path.with_suffix(".json.bak"))
    
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    casi_cambiati = 0
    tot_pmid_vecchi = 0
    tot_pmid_nuovi = 0
    tot_hall_vecchi = 0
    tot_hall_nuovi = 0
    
    for r in data:
        case_id = r["case_id"]
        report = r["report"]
        
        vecchi_pmid = set(r.get("cited_pmids_list", []))
        vecchi_hall = set(r.get("hallucinated_pmids_list", []))
        
        # Ricalcolo
        nuovi_pmid = extract_pmids_from_report(report)
        nuovi_validi = check_pmids_exist_in_kb(nuovi_pmid)
        nuovi_hall = nuovi_pmid - nuovi_validi
        nuovo_rate = len(nuovi_hall) / len(nuovi_pmid) if nuovi_pmid else 0.0
        
        tot_pmid_vecchi += len(vecchi_pmid)
        tot_pmid_nuovi += len(nuovi_pmid)
        tot_hall_vecchi += len(vecchi_hall)
        tot_hall_nuovi += len(nuovi_hall)
        
        if nuovi_pmid != vecchi_pmid or nuovi_hall != vecchi_hall:
            casi_cambiati += 1
            # Stampiamo solo per capire cosa cambia (per non intasare l'output mostriamo solo i primi o i più significativi)
            print(f"[{label}] Caso {case_id} CAMBIATO:")
            print(f"  PMID vecchi:         {sorted(list(vecchi_pmid))}")
            print(f"  PMID nuovi:          {sorted(list(nuovi_pmid))}")
            print(f"  Allucinazioni vecchie: {sorted(list(vecchi_hall))}")
            print(f"  Allucinazioni nuove:   {sorted(list(nuovi_hall))}")
            
        # Aggiorna record
        r["cited_pmids_list"] = sorted(list(nuovi_pmid))
        r["hallucinated_pmids_list"] = sorted(list(nuovi_hall))
        r["n_cited_pmids"] = len(nuovi_pmid)
        r["n_hallucinated_pmids"] = len(nuovi_hall)
        r["pmid_hallucination_rate"] = nuovo_rate
        
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    print(f"File {file_path.name} AGGIORNATO. Casi modificati: {casi_cambiati}/{len(data)}")
    print(f"  PMID totali: vecchi = {tot_pmid_vecchi}, nuovi = {tot_pmid_nuovi}")
    print(f"  Allucinati totali: vecchi = {tot_hall_vecchi}, nuovi = {tot_hall_nuovi}")
    print("-" * 80)
