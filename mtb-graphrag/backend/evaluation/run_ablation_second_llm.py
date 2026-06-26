"""
run_ablation_second_llm.py — Studio di generalizzabilità con un secondo LLM (Qwen).

Esegue solo le condizioni vanilla e full_graphrag usando qwen3-coder-next
sui 30 casi clinici del benchmark e confronta le metriche.
"""

from __future__ import annotations

import os
# Imposta la variabile d'ambiente per il secondo LLM PRIMA di importare i moduli della pipeline
os.environ["LLM_PIPELINE"] = "qwen3-coder-next"
os.environ["LLM_JUDGE"] = "minimax-m2.5"
os.environ["OLLAMA_BASE_URL"] = "https://api.ollama.com"

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

# Configura UTF-8 per console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Assicuriamo che l'ambiente importi correttamente i moduli
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.pipeline.llm import llm, llm_judge
from backend.pipeline.state import MTBState
from backend.pipeline.graph import run_pipeline
from backend.pipeline.agents.judge import llm_as_judge
from backend.evaluation.compute_metrics import (
    extract_pmids_from_report,
    extract_escat_tier,
    check_pmids_exist_in_kb
)
from backend.evaluation.run_zeroshot import SYNTHESIZER_SYSTEM, build_zeroshot_context
from backend.evaluation.run_benchmark import csv_row_to_state

# ── Paths ──────────────────────────────────────────────────────
BENCHMARK_CSV = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR   = Path(__file__).resolve().parent / "results"

def retry_on_exception(func, *args, max_retries=5, initial_backoff=2.0, timeout=300, **kwargs):
    """Esegue una funzione riprovando in caso di eccezione o timeout con backoff esponenziale."""
    import concurrent.futures
    backoff = initial_backoff
    for attempt in range(max_retries):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(func, *args, **kwargs)
            val = future.result(timeout=timeout)
            executor.shutdown(wait=False)
            return val
        except Exception as e:
            executor.shutdown(wait=False)
            import traceback
            print(f"      [RETRY] Tentativo {attempt + 1}/{max_retries} fallito con errore o timeout: {e}")
            traceback.print_exc()
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff)
            backoff *= 2.0

TUMOR_MAP: dict[str, str] = {
    "NSCLC":               "Lung Adenocarcinoma",
    "Melanoma":            "Melanoma",
    "Breast Cancer HER2+": "Breast Cancer",
    "Breast Cancer HR+":   "Breast Cancer",
    "Ovarian Cancer":      "Ovarian Cancer",
    "CML":                 "Chronic Myeloid Leukemia",
    "Colorectal Cancer":   "Colorectal Cancer",
    "GIST":                "Gastrointestinal Stromal Tumor",
    "AML":                 "Acute Myeloid Leukemia",
    "Solid Tumor":         "Solid Tumor",
    "Gastric Cancer":      "Gastric Cancer",
    "Prostate Cancer":     "Prostate Cancer",
    "Cholangiocarcinoma":  "Cholangiocarcinoma",
    "Thyroid Cancer":      "Thyroid Cancer",
}

def run_vanilla_condition(gene: str, variant: str, tumor_type: str, alteration_type: str, therapy_line: str) -> str:
    """Esegue la condizione 0 (vanilla zero-shot)."""
    context = build_zeroshot_context(gene, variant, tumor_type, alteration_type, therapy_line)
    from langchain_core.messages import SystemMessage, HumanMessage
    response = llm.invoke([
        SystemMessage(content=SYNTHESIZER_SYSTEM),
        HumanMessage(content=context)
    ])
    return response.content

def run_full_graphrag_condition(row: dict) -> dict:
    """Esegue la condizione 4 (full GraphRAG pipeline)."""
    state = csv_row_to_state(row)
    final = run_pipeline(state)
    return {
        "report": final["report"],
        "escat_tier": final.get("escat_tier", ""),
        "pmid_rimossi_dal_testo": final.get("pmid_rimossi_dal_testo", [])
    }

def evaluate_report(
    case_id: str,
    report: str,
    expected_drug: str,
    expected_pmid: int | None,
    expected_escat: str,
    explicit_tier: str | None = None
) -> dict:
    """Calcola le metriche oggettive e soggettive (LLM-as-judge) per un report generato."""
    
    # 1. Drug Anchor Check
    drugs = [d.strip() for d in re.split(r'[+/,]', expected_drug)]
    drug_found = all(d.lower() in report.lower() for d in drugs if d) if drugs else False
    
    # 2. PMID extraction & coverage
    cited_pmids = extract_pmids_from_report(report)
    anchor_pmid_cited = expected_pmid in cited_pmids if expected_pmid else False
    
    # 3. PMID Hallucination Rate (verifica nel KG)
    valid_pmids = check_pmids_exist_in_kb(cited_pmids)
    hallucinated_pmids = cited_pmids - valid_pmids
    hallucination_rate = len(hallucinated_pmids) / len(cited_pmids) if cited_pmids else 0.0
    
    # 4. ESCAT Match
    extracted_tier = extract_escat_tier(report, explicit_tier)
    if expected_escat and expected_escat.lower() == "non determinato":
        escat_match = (extracted_tier is None)
    else:
        escat_match = (extracted_tier == expected_escat.upper()) if expected_escat else False
    
    return {
        "dac_drug_found": drug_found,
        "dac_anchor_pmid_cited": anchor_pmid_cited,
        "n_cited_pmids": len(cited_pmids),
        "n_hallucinated_pmids": len(hallucinated_pmids),
        "pmid_hallucination_rate": hallucination_rate,
        "extracted_escat": extracted_tier,
        "escat_match": escat_match,
        "cited_pmids_list": sorted(list(cited_pmids)),
        "hallucinated_pmids_list": sorted(list(hallucinated_pmids))
    }

def main():
    parser = argparse.ArgumentParser(description="Studio di generalizzabilità con secondo LLM (Qwen)")
    parser.add_argument("--case", type=str, default=None, help="Esegui solo un caso specifico (es. BENCH-004)")
    parser.add_argument("--fresh", action="store_true", help="Ricomincia l'esperimento cancellando i salvataggi parziali")
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Carica il benchmark
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        benchmark_rows = {row["case_id"]: row for row in reader}

    if args.case:
        if args.case not in benchmark_rows:
            print(f"Caso {args.case} non trovato.")
            sys.exit(1)
        cases_to_run = {args.case: benchmark_rows[args.case]}
        print(f"Esecuzione sul singolo caso: {args.case}")
    else:
        cases_to_run = benchmark_rows
        print(f"Esecuzione su tutti i {len(cases_to_run)} casi")

    # Condizioni per il secondo LLM
    conditions = ["vanilla", "full_graphrag"]
    
    # Dizionario per memorizzare i risultati per condizione
    condition_results = {cond: [] for cond in conditions}
    
    # Carica salvataggi parziali se presenti
    filename_map = {
        "vanilla": "ablation_second_llm_vanilla_results.json",
        "full_graphrag": "ablation_second_llm_graphrag_results.json"
    }
    
    for cond in conditions:
        filename = filename_map.get(cond)
        out_file = RESULTS_DIR / filename
        if out_file.exists() and not args.fresh and not args.case:
            try:
                with open(out_file, "r", encoding="utf-8") as f:
                    condition_results[cond] = json.load(f)
                print(f"Caricati {len(condition_results[cond])} casi parziali per la condizione '{cond}'.")
            except Exception as e:
                print(f"Impossibile caricare progressi parziali per '{cond}': {e}")

    # Loop sui casi
    for case_id, row in cases_to_run.items():
        gene = "MSI" if row["gene"] == "MMR" else ("TMB" if row["gene"] == "TMB" else row["gene"])
        variant = row["variant"]
        tumor_type = TUMOR_MAP.get(row["tumor"], row["tumor"])
        alteration_type = row["alteration_type"]
        therapy_line = "first-line"
        
        expected_drug = row["expected_drug"]
        expected_pmid = int(row["pmid"]) if row.get("pmid") and str(row.get("pmid")).isdigit() else None
        expected_escat = row.get("escat", "")

        print(f"\n{'-'*40}\nElaborazione Caso {case_id}: {gene} {variant} ({tumor_type}) [Second LLM: Qwen]\n{'-'*40}")

        # ── 0. VANILLA ──
        if not any(r["case_id"] == case_id for r in condition_results["vanilla"]):
            print("  -> Esecuzione Condizione: VANILLA...")
            report = retry_on_exception(run_vanilla_condition, gene, variant, tumor_type, alteration_type, therapy_line)
            metrics = evaluate_report(case_id, report, expected_drug, expected_pmid, expected_escat)
            judge = retry_on_exception(llm_as_judge, report, {"gene": gene, "variant": variant, "tumor_type": tumor_type})
            
            condition_results["vanilla"].append({
                "case_id": case_id,
                "report": report,
                **metrics,
                "judge_score": judge.get("score_totale"),
                "judge_detail": judge
            })
            with open(RESULTS_DIR / filename_map["vanilla"], "w", encoding="utf-8") as f:
                json.dump(condition_results["vanilla"], f, indent=2, ensure_ascii=False)

        # ── 1. FULL GRAPHRAG ──
        if not any(r["case_id"] == case_id for r in condition_results["full_graphrag"]):
            print("  -> Esecuzione Condizione: FULL GRAPHRAG...")
            res = retry_on_exception(run_full_graphrag_condition, benchmark_rows[case_id], timeout=300)
            report = res["report"]
            explicit_tier = res["escat_tier"]
                
            metrics = evaluate_report(case_id, report, expected_drug, expected_pmid, expected_escat, explicit_tier=explicit_tier)
            judge = retry_on_exception(llm_as_judge, report, {"gene": gene, "variant": variant, "tumor_type": tumor_type})
                
            condition_results["full_graphrag"].append({
                "case_id": case_id,
                "report": report,
                **metrics,
                "pmid_rimossi_dal_testo": res.get("pmid_rimossi_dal_testo", []),
                "judge_score": judge.get("score_totale"),
                "judge_detail": judge
            })
            with open(RESULTS_DIR / filename_map["full_graphrag"], "w", encoding="utf-8") as f:
                json.dump(condition_results["full_graphrag"], f, indent=2, ensure_ascii=False)

    # 3. Calcola medie aggregate per condizione
    print(f"\n{'═'*80}\n  STUDIO DI ABLAZIONE (QWEN) COMPLETATO\n{'═'*80}")
    
    summary_rows = []
    
    for cond in conditions:
        results = condition_results[cond]
        if not results:
            continue
            
        dac_list = [r["dac_drug_found"] for r in results]
        pmid_cov_list = [r["dac_anchor_pmid_cited"] for r in results]
        escat_match_list = [r["escat_match"] for r in results]
        
        # Filtra N/A sul tasso di allucinazione (casi senza PMID citati)
        hallucination_list = [r["pmid_hallucination_rate"] for r in results if r["pmid_hallucination_rate"] is not None]
        
        # PMID rimossi dal testo
        pmid_rimossi_list = [len(r.get("pmid_rimossi_dal_testo", [])) for r in results]
        sum_pmid_rimossi = sum(pmid_rimossi_list)
        mean_pmid_rimossi = sum_pmid_rimossi / len(pmid_rimossi_list) if pmid_rimossi_list else 0.0
        
        judge_scores = [r["judge_score"] for r in results if r["judge_score"] is not None]
        judge_compl = [r["judge_detail"].get("completezza") for r in results if r["judge_detail"] and r["judge_detail"].get("completezza") is not None]
        judge_util = [r["judge_detail"].get("utilita_clinica") for r in results if r["judge_detail"] and r["judge_detail"].get("utilita_clinica") is not None]
        judge_fed = [r["judge_detail"].get("fedelta_evidenze") for r in results if r["judge_detail"] and r["judge_detail"].get("fedelta_evidenze") is not None]
        judge_acc = [r["judge_detail"].get("accuratezza_clinica") for r in results if r["judge_detail"] and r["judge_detail"].get("accuratezza_clinica") is not None]

        mean_dac = sum(dac_list) / len(dac_list) if dac_list else 0.0
        mean_pmid_cov = sum(pmid_cov_list) / len(pmid_cov_list) if pmid_cov_list else 0.0
        mean_escat = sum(escat_match_list) / len(escat_match_list) if escat_match_list else 0.0
        mean_hallucination = sum(hallucination_list) / len(hallucination_list) if hallucination_list else 0.0
        
        mean_judge = sum(judge_scores) / len(judge_scores) if judge_scores else 0.0
        mean_compl = sum(judge_compl) / len(judge_compl) if judge_compl else 0.0
        mean_util = sum(judge_util) / len(judge_util) if judge_util else 0.0
        mean_fed = sum(judge_fed) / len(judge_fed) if judge_fed else 0.0
        mean_acc = sum(judge_acc) / len(judge_acc) if judge_acc else 0.0
        
        summary_row = {
            "condizione": cond,
            "drug_anchor_check": round(mean_dac, 3),
            "pmid_coverage_rate": round(mean_pmid_cov, 3),
            "pmid_hallucination_rate": round(mean_hallucination, 3),
            "escat_tier_match": round(mean_escat, 3),
            "pmid_rimossi_tot": sum_pmid_rimossi,
            "pmid_rimossi_medio": round(mean_pmid_rimossi, 3),
            "judge_score_totale": round(mean_judge, 3),
            "judge_completezza": round(mean_compl, 3),
            "judge_utilita_clinica": round(mean_util, 3),
            "judge_fedelta_evidenze": round(mean_fed, 3),
            "judge_accuratezza_clinica": round(mean_acc, 3)
        }
            
        summary_rows.append(summary_row)

    # 4. Stampa la tabella comparativa markdown in console
    print("\n### TABELLA RIASSUNTIVA COMPARATIVA (SECONDO LLM - QWEN)")
    print(
        f"{'Condizione':<16} | {'DAC':>6} | {'PMID Cov':>8} | {'PMID Hall':>9} | {'ESCAT':>6} | "
        f"{'Rimossi T/M':>11} | {'Judge Tot':>9} | {'Compl':>5} | {'Util':>5} | {'Fed':>5} | {'Acc':>5}"
    )
    print("-" * 105)
    for r in summary_rows:
        def fmt_p(v): return f"{v:.1%}" if isinstance(v, float) else str(v)
        def fmt_f(v): return f"{v:.2f}" if isinstance(v, float) else str(v)
        rem_str = f"{r['pmid_rimossi_tot']}/{r['pmid_rimossi_medio']:.1f}"
        print(
            f"{r['condizione']:<16} | {fmt_p(r['drug_anchor_check']):>6} | {fmt_p(r['pmid_coverage_rate']):>8} | "
            f"{fmt_p(r['pmid_hallucination_rate']):>9} | {fmt_p(r['escat_tier_match']):>6} | "
            f"{rem_str:>11} | {fmt_f(r['judge_score_totale']):>9} | {fmt_f(r['judge_completezza']):>5} | "
            f"{fmt_f(r['judge_utilita_clinica']):>5} | {fmt_f(r['judge_fedelta_evidenze']):>5} | "
            f"{fmt_f(r['judge_accuratezza_clinica']):>5}"
        )

    # 5. Salva la tabella in CSV
    csv_out = RESULTS_DIR / "ablation_second_llm_summary.csv"
    with open(csv_out, "w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "condizione", "drug_anchor_check", "pmid_coverage_rate", "pmid_hallucination_rate",
            "escat_tier_match", "pmid_rimossi_tot", "pmid_rimossi_medio", "judge_score_totale",
            "judge_completezza", "judge_utilita_clinica", "judge_fedelta_evidenze", "judge_accuratezza_clinica"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)
        
    print(f"\nTabella riepilogativa salvata con successo in: {csv_out}")

if __name__ == "__main__":
    main()
