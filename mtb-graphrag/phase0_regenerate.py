import json
from pathlib import Path
import re
from backend.evaluation.run_ablation_study import run_full_graphrag_condition, extract_pmids_from_report

BENCHMARK_CSV = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
RESULTS_DIR = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")
ABLATION_JSON = RESULTS_DIR / "ablation_graphrag_results.json"

def run_phase0():
    print("Avvio Fase 0: Rigenerazione casi biomarker BENCH-017 e BENCH-023...")
    
    # Caricamento CSV per avere lo state
    import csv
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        benchmark_rows = {row["case_id"]: row for row in reader}

    # Carica JSON ablation
    with open(ABLATION_JSON, "r", encoding="utf-8") as f:
        ablation_data = json.load(f)

    for target_case in ["BENCH-017", "BENCH-023"]:
        print(f"Rigenerazione di {target_case}...")
        row = benchmark_rows.get(target_case)
        if not row:
            print(f"Case {target_case} non trovato nel CSV.")
            continue
            
        final_state = run_full_graphrag_condition(row)
        report = final_state["report"]
        
        # Aggiorna il JSON dell'ablation (solo i campi puliti scelti prima)
        pmids = list(extract_pmids_from_report(report))
        
        # Cerca il dizionario da aggiornare
        found = False
        for case in ablation_data:
            if case["case_id"] == target_case:
                case["report"] = report
                case["cited_pmids_list"] = pmids
                found = True
                break
                
        if not found:
            ablation_data.append({
                "case_id": target_case,
                "report": report,
                "cited_pmids_list": pmids
            })
            
        print(f"[{target_case}] Rigenerato con successo.")

    # Salva il file pulito
    with open(ABLATION_JSON, "w", encoding="utf-8") as f:
        json.dump(ablation_data, f, indent=2, ensure_ascii=False)
    print("File ablation_graphrag_results.json aggiornato.")

if __name__ == "__main__":
    run_phase0()
