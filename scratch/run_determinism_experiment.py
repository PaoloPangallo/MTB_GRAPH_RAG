import sys
import os
import re
import csv
import json
import time
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from langchain_ollama import ChatOllama
import backend.pipeline.llm as pipeline_llm

def set_llm_temperature(temp: float):
    pipeline_llm.llm = ChatOllama(
        model=pipeline_llm.LLM_PIPELINE,
        base_url=pipeline_llm.OLLAMA_BASE_URL,
        api_key=pipeline_llm.OLLAMA_API_KEY,
        temperature=temp,
        timeout=60,
    )
    pipeline_llm.llm_judge = ChatOllama(
        model=pipeline_llm.LLM_JUDGE,
        base_url=pipeline_llm.OLLAMA_BASE_URL,
        api_key=pipeline_llm.OLLAMA_API_KEY,
        temperature=temp,
        timeout=60,
    )

from backend.pipeline.graph import run_pipeline
from backend.evaluation.run_benchmark import csv_row_to_state

# File paths
BENCHMARK_CSV = PROJECT_ROOT / "mtb-graphrag" / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"
OUTPUT_JSON = PROJECT_ROOT / "scratch" / "determinism_raw_runs.json"

def main():
    print("====================================================")
    print("  ESPERIMENTO DI RIPRODUCIBILITA (RQ2)")
    print("====================================================")
    print(f"Benchmark CSV: {BENCHMARK_CSV}")
    print(f"Output JSON:   {OUTPUT_JSON}")
    
    # 1. Carica il benchmark
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        benchmark_rows = {row["case_id"]: row for row in reader}
    
    case_ids = sorted(list(benchmark_rows.keys()))
    print(f"Caricati {len(case_ids)} casi di benchmark.")
    
    # 2. Test anti-cache
    first_case_id = case_ids[0]
    first_row = benchmark_rows[first_case_id]
    
    print("\n--- FASE 1: TEST ANTI-CACHE PRELIMINARE ---")
    print(f"Esecuzione di {first_case_id} a temperatura 0.0...")
    set_llm_temperature(0.0)
    state_00 = csv_row_to_state(first_row)
    res_00 = run_pipeline(state_00)
    report_00 = res_00.get("report", "")
    
    print(f"Esecuzione di {first_case_id} a temperatura 0.8...")
    set_llm_temperature(0.8)
    state_08 = csv_row_to_state(first_row)
    res_08 = run_pipeline(state_08)
    report_08 = res_08.get("report", "")
    
    # Ripristina temp standard
    set_llm_temperature(0.0)
    
    len_00 = len(report_00)
    len_08 = len(report_08)
    print(f"Report a temp 0.0: {len_00} caratteri.")
    print(f"Report a temp 0.8: {len_08} caratteri.")
    
    if report_00 == report_08:
        print("\n[ERRORE CRITICO] Gli output a 0.0 e 0.8 sono identici al 100%.")
        print("La cache è attiva ed interferisce. L'esperimento è INVALIDATO.")
        sys.exit(1)
    else:
        print("\n[OK] I report a 0.0 e 0.8 differiscono. La cache non interferisce.")
    
    # 3. Inizializza file JSON per salvataggio progressivo
    all_runs = []
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                all_runs = json.load(f)
            print(f"Trovato file esistente con {len(all_runs)} record. Saranno integrati.")
        except Exception:
            print("Impossibile caricare file esistente. Ricomincio da zero.")
            all_runs = []

    # Helper per salvare progressivamente
    def save_progress():
        temp_file = OUTPUT_JSON.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(all_runs, f, indent=2, ensure_ascii=False)
        if OUTPUT_JSON.exists():
            os.remove(OUTPUT_JSON)
        os.rename(temp_file, OUTPUT_JSON)

    # 4. Fase Dry-Run (BENCH-001)
    print("\n--- FASE 2: DRY-RUN SU BENCH-001 ---")
    dry_run_case = "BENCH-001"
    dry_row = benchmark_rows[dry_run_case]
    
    bench_001_runs = [r for r in all_runs if r["case_id"] == dry_run_case]
    if len(bench_001_runs) < 5:
        print(f"Esecuzione di {dry_run_case} (5 run) per il dry-run...")
        for run_idx in range(len(bench_001_runs) + 1, 6):
            print(f"  -> Run {run_idx}/5 per {dry_run_case}...")
            start_time = time.time()
            try:
                state = csv_row_to_state(dry_row)
                final = run_pipeline(state)
                
                cited_pmids = sorted(list(set(final.get("cited_pmids", []))))
                drug_candidates = sorted(list(set([
                    d["drug_name"].strip() for d in final.get("drug_candidates", []) if d.get("drug_name")
                ])))
                
                run_record = {
                    "case_id": dry_run_case,
                    "run_index": run_idx,
                    "complexity": final.get("complexity", ""),
                    "escat_tier": final.get("escat_tier", ""),
                    "cited_pmids": cited_pmids,
                    "drug_candidates": drug_candidates,
                    "duration_seconds": round(time.time() - start_time, 2)
                }
                print(f"    Raw Result: {run_record}")
                all_runs.append(run_record)
                save_progress()
            except Exception as e:
                print(f"    [ERRORE] Esecuzione fallita per {dry_run_case} run {run_idx}: {e}")
                run_record = {
                    "case_id": dry_run_case,
                    "run_index": run_idx,
                    "complexity": "ERROR",
                    "escat_tier": "ERROR",
                    "cited_pmids": [],
                    "drug_candidates": [],
                    "error": str(e),
                    "duration_seconds": round(time.time() - start_time, 2)
                }
                print(f"    Raw Result: {run_record}")
                all_runs.append(run_record)
                save_progress()
    else:
        print(f"Dry-run per {dry_run_case} già presente con {len(bench_001_runs)} run.")
    
    bench_001_runs = [r for r in all_runs if r["case_id"] == dry_run_case]
    print(f"Verifica record dry-run salvati (totale {len(bench_001_runs)}):")
    valid = True
    for r in bench_001_runs:
        print(f"  Run {r['run_index']}: complexity={r['complexity']}, escat_tier={r['escat_tier']}, pmids_len={len(r['cited_pmids'])}, drugs_len={len(r['drug_candidates'])}")
        if r['complexity'] == "ERROR" or not r['complexity']:
            valid = False
    
    if not valid:
        print("[ERRORE DRY-RUN] Alcuni run del dry-run presentano errori o sono vuoti.")
        print("Continuo con il batch completo come da regole di robustezza dell'esperimento.")
    else:
        print("[OK] Dry-run superato con successo.")

    # 5. Batch completo per i restanti casi
    print("\n--- FASE 3: BATCH COMPLETO SU TUTTI I CASI ---")
    for case_id in case_ids:
        row = benchmark_rows[case_id]
        existing = [r for r in all_runs if r["case_id"] == case_id]
        if len(existing) >= 5:
            print(f"Caso {case_id} già completato con {len(existing)} run. Salto.")
            continue
            
        print(f"\nEsecuzione caso {case_id} (attualmente ha {len(existing)}/5 run completati)...")
        for run_idx in range(len(existing) + 1, 6):
            print(f"  -> Run {run_idx}/5 per {case_id}...")
            start_time = time.time()
            try:
                state = csv_row_to_state(row)
                final = run_pipeline(state)
                
                cited_pmids = sorted(list(set(final.get("cited_pmids", []))))
                drug_candidates = sorted(list(set([
                    d["drug_name"].strip() for d in final.get("drug_candidates", []) if d.get("drug_name")
                ])))
                
                run_record = {
                    "case_id": case_id,
                    "run_index": run_idx,
                    "complexity": final.get("complexity", ""),
                    "escat_tier": final.get("escat_tier", ""),
                    "cited_pmids": cited_pmids,
                    "drug_candidates": drug_candidates,
                    "duration_seconds": round(time.time() - start_time, 2)
                }
                print(f"    Raw Result: {run_record}")
                all_runs.append(run_record)
                save_progress()
            except Exception as e:
                print(f"    [ERRORE] Esecuzione fallita per {case_id} run {run_idx}: {e}")
                run_record = {
                    "case_id": case_id,
                    "run_index": run_idx,
                    "complexity": "ERROR",
                    "escat_tier": "ERROR",
                    "cited_pmids": [],
                    "drug_candidates": [],
                    "error": str(e),
                    "duration_seconds": round(time.time() - start_time, 2)
                }
                print(f"    Raw Result: {run_record}")
                all_runs.append(run_record)
                save_progress()

    print("\n====================================================")
    print("  BATCH COMPLETATO. CALCOLO STATISTICHE DI STABILITÀ")
    print("====================================================")
    
    # 6. Analisi dei dati
    grouped_runs = {}
    for r in all_runs:
        cid = r["case_id"]
        if cid not in grouped_runs:
            grouped_runs[cid] = []
        grouped_runs[cid].append(r)
        
    stability_data = []
    
    escat_stables = 0
    pmids_stables = 0
    drugs_stables = 0
    complexity_stables = 0
    total_analyzed = 0
    
    unstable_cases = []
    
    for cid in sorted(grouped_runs.keys()):
        runs = sorted(grouped_runs[cid], key=lambda x: x["run_index"])
        
        complexities = [r["complexity"] for r in runs]
        escat_tiers = [r["escat_tier"] for r in runs]
        pmids_sets = [tuple(r["cited_pmids"]) for r in runs]
        drugs_sets = [tuple(r["drug_candidates"]) for r in runs]
        
        comp_stable = len(set(complexities)) == 1
        escat_stable = len(set(escat_tiers)) == 1
        pmids_stable = len(set(pmids_sets)) == 1
        drugs_stable = len(set(drugs_sets)) == 1
        
        if comp_stable: complexity_stables += 1
        if escat_stable: escat_stables += 1
        if pmids_stable: pmids_stables += 1
        if drugs_stable: drugs_stables += 1
        total_analyzed += 1
        
        case_unstable = not (comp_stable and escat_stable and pmids_stable and drugs_stable)
        if case_unstable:
            details = []
            if not comp_stable:
                details.append(f"complexity: {complexities}")
            if not escat_stable:
                details.append(f"tier: {escat_tiers}")
            if not pmids_stable:
                details.append(f"pmids vary across runs: {[r['cited_pmids'] for r in runs]}")
            if not drugs_stable:
                details.append(f"drugs vary across runs: {[r['drug_candidates'] for r in runs]}")
            unstable_cases.append(f"{cid}: {', '.join(details)}")
            
        stability_data.append({
            "case_id": cid,
            "complexity_stable": comp_stable,
            "escat_stable": escat_stable,
            "pmids_stable": pmids_stable,
            "drugs_stable": drugs_stable,
            "complexities": complexities,
            "escat_tiers": escat_tiers
        })
        
    # Percentuali
    pct_complexity = (complexity_stables / total_analyzed * 100) if total_analyzed > 0 else 0
    pct_escat = (escat_stables / total_analyzed * 100) if total_analyzed > 0 else 0
    pct_pmids = (pmids_stables / total_analyzed * 100) if total_analyzed > 0 else 0
    pct_drugs = (drugs_stables / total_analyzed * 100) if total_analyzed > 0 else 0
    
    print("\n--- RISULTATI AGGREGATI ---")
    print(f"Totale casi analizzati: {total_analyzed}")
    print(f"% casi con complexity_stable=True: {pct_complexity:.1f}%")
    print(f"% casi con escat_stable=True:      {pct_escat:.1f}%")
    print(f"% casi con pmids_stable=True:      {pct_pmids:.1f}%")
    print(f"% casi con drugs_stable=True:      {pct_drugs:.1f}%")
    
    print("\n--- CASI CON INSTABILITÀ ---")
    if unstable_cases:
        for uc in unstable_cases:
            print(f"  - {uc}")
    else:
        print("  Nessuno. Tutti i casi sono stabili al 100%.")

    # Salva report riepilogativo di analisi in JSON
    analysis_report = {
        "summary": {
            "total_cases": total_analyzed,
            "pct_complexity_stable": round(pct_complexity, 2),
            "pct_escat_stable": round(pct_escat, 2),
            "pct_pmids_stable": round(pct_pmids, 2),
            "pct_drugs_stable": round(pct_drugs, 2)
        },
        "unstable_cases_list": unstable_cases,
        "stability_details": stability_data
    }
    
    with open(PROJECT_ROOT / "scratch" / "determinism_analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis_report, f, indent=2, ensure_ascii=False)
        
    print("\nFinito!")

if __name__ == "__main__":
    main()
