"""
Run Benchmark — Esecuzione sistematica dei 30 casi del benchmark.

Chiama direttamente pipeline/graph.py (no overhead HTTP).
Uso:
  python -m backend.evaluation.run_benchmark                  # tutti i 30 casi
  python -m backend.evaluation.run_benchmark --case BENCH-001  # singolo caso
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

# Configure standard output to use UTF-8 to prevent UnicodeEncodeError on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from backend.pipeline.state import MTBState
from backend.pipeline.graph import run_pipeline
from backend.pipeline.agents.judge import llm_as_judge


# ── Path ───────────────────────────────────────────────────
BENCHMARK_CSV = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR   = Path(__file__).resolve().parent / "results"


# ── Mapping CSV → MTBState ─────────────────────────────────

# Mapping dei nomi di tumore dal CSV ai nomi OncoTree-compatibili
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


def csv_row_to_state(row: dict) -> MTBState:
    """Converte una riga del CSV benchmark in MTBState."""
    tumor = TUMOR_MAP.get(row["tumor"], row["tumor"])
    return {
        "gene":               row["gene"] if row["gene"] not in ("MMR", "TMB") else "",
        "variant":            row["variant"],
        "tumor_type":         tumor,
        "alteration_type":    row["alteration_type"],
        "therapy_line":       "first-line",
        "enrich_with_oncokb": False,
        # placeholder — sovrascritti dagli agenti
        "complexity":         "low",
        "variant_data":       {},
        "drug_candidates":    [],
        "trial_candidates":   [],
        "resistance_data":    [],
        "oncokb_enrichment":  [],
        "report":             "",
        "cited_pmids":        [],
        "escat_tier":         "",
    }


def run_single(case_id: str, row: dict) -> dict:
    """Esegue pipeline + judge per un singolo caso."""
    print(f"\n{'═' * 60}")
    print(f"  {case_id}: {row['gene']} {row['variant']} / {row['tumor']}")
    print(f"{'═' * 60}")

    state = csv_row_to_state(row)
    final = run_pipeline(state)

    print(f"  Complessità : {final['complexity']}")
    print(f"  ESCAT Tier  : {final['escat_tier']}")
    print(f"  PMID citati : {len(final['cited_pmids'])}")
    print(f"  Drug cand.  : {len(final['drug_candidates'])}")
    print(f"  Resistance  : {len(final['resistance_data'])}")

    # Valutazione LLM-as-judge
    score = llm_as_judge(final["report"], {
        "gene": row["gene"],
        "variant": row["variant"],
        "tumor_type": state["tumor_type"],
    })

    print(f"  Judge score : {score.get('score_totale', 'N/A')}")

    return {
        "case_id":       case_id,
        "gene":          row["gene"],
        "variant":       row["variant"],
        "tumor":         row["tumor"],
        "expected_drug": row["expected_drug"],
        "complexity":    final["complexity"],
        "escat_tier":    final["escat_tier"],
        "n_pmids":       len(final["cited_pmids"]),
        "n_drugs":       len(final["drug_candidates"]),
        "n_resistance":  len(final["resistance_data"]),
        "n_trials":      len(final.get("trial_candidates", [])),
        "judge_score":   score.get("score_totale"),
        "judge_detail":  score,
        "report":        final["report"],
    }


def main():
    import time
    parser = argparse.ArgumentParser(description="Run MTB GraphRAG Benchmark")
    parser.add_argument("--case", type=str, default=None, help="Singolo caso (es. BENCH-001)")
    parser.add_argument("--fresh", action="store_true", help="Ricomincia il benchmark da zero (cancella progressi precedenti)")
    args = parser.parse_args()

    # Leggi benchmark CSV
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = {row["case_id"]: row for row in reader}

    if args.case:
        if args.case not in rows:
            print(f"Caso {args.case} non trovato nel benchmark.")
            sys.exit(1)
        cases = {args.case: rows[args.case]}
    else:
        cases = rows

    # Crea directory risultati
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    output_json = RESULTS_DIR / "benchmark_results.json"
    results = []

    if output_json.exists() and not args.fresh and not args.case:
        try:
            with open(output_json, "r", encoding="utf-8") as f:
                results = json.load(f)
            print(f"Caricati {len(results)} casi già completati dal file esistente.")
        except Exception as e:
            print(f"Impossibile caricare risultati parziali: {e}. Ricomincio da zero.")
            results = []

    already_done = {r["case_id"] for r in results}

    for case_id, row in cases.items():
        if case_id in already_done and not args.case:
            print(f"Caso {case_id} già completato. Salto.")
            continue

        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = run_single(case_id, row)
                break
            except Exception as e:
                print(f"\n[ATTENZIONE] Errore al tentativo {attempt + 1} per {case_id}: {e}")
                if attempt < max_retries - 1:
                    print("Attesa di 10 secondi prima del prossimo tentativo per bypassare limiti di connessione...")
                    time.sleep(10)
                else:
                    print(f"Superato il numero massimo di tentativi per {case_id}. Questo caso viene saltato.")

        if result:
            # Rimuove eventuale vecchio record dello stesso caso se presente (es. se rieseguito con --case)
            results = [r for r in results if r["case_id"] != case_id]
            results.append(result)

            # Salva subito il JSON dopo ogni caso completato
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            # Salva anche il CSV riepilogativo aggiornato ad ogni passo
            output_csv = RESULTS_DIR / "benchmark_summary.csv"
            with open(output_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "case_id", "gene", "variant", "tumor", "expected_drug",
                    "complexity", "escat_tier", "n_pmids", "n_drugs",
                    "n_resistance", "n_trials", "judge_score",
                ])
                writer.writeheader()
                for r in results:
                    writer.writerow({k: r[k] for k in writer.fieldnames})

    print(f"\n{'═' * 60}")
    print(f"  Benchmark completato: {len(results)} casi in totale")
    print(f"  Risultati salvati in: {RESULTS_DIR}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
