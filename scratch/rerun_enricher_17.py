"""
rerun_enricher_17.py — Re-run mirato dei 17 casi enricher_only con query API corrette.

Modifica in-place ablation_enricher_results.json sostituendo solo i casi specificati,
poi ricalcola ablation_summary.csv.

Casi da ri-eseguire (16 con 0 trattamenti OncoKB + 1 con transient network failure):
  BENCH-005  BRCA1 / Ovarian Cancer          (Tipo B: alteration generic)
  BENCH-006  BCR-ABL1 / CML                  (Tipo C: fusion parser)
  BENCH-008  PIK3CA / Breast Cancer          (Tipo B: alteration generic)
  BENCH-009  KIT Exon 11 / GIST              (Tipo B: alteration generic atypical)
  BENCH-012  KRAS G12C / NSCLC               (Tipo D: transient network failure)
  BENCH-014  ABL1 T315I / CML                (Tipo A: tumor type synonym)
  BENCH-015  RET Fusion / NSCLC              (Tipo C: fusion single gene)
  BENCH-016  NTRK1 Fusion / Solid Tumor      (Tipo C: fusion single gene + tumor-agnostic)
  BENCH-017  MSI-High / Colorectal Cancer    (Tipo B: biomarker format)
  BENCH-019  KIT Exon 9 / GIST               (Tipo B: alteration generic atypical)
  BENCH-021  ERBB2 amp / Gastric Cancer      (Tipo A: tumor type synonym)
  BENCH-022  BRCA2 / Prostate Cancer         (Tipo B: alteration generic)
  BENCH-023  TMB-High / Solid Tumor          (Tipo B: biomarker format)
  BENCH-024  EGFR Exon 19 del / NSCLC        (Tipo B: alteration generic atypical)
  BENCH-025  IDH1 R132 / AML                 (Tipo B: incomplete protein change)
  BENCH-027  MET Exon 14 / NSCLC             (Tipo B: alteration generic atypical)
  BENCH-030  ERBB2 amp / Gastric Cancer      (Tipo A: tumor type synonym)
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1] / "mtb-graphrag"
sys.path.insert(0, str(ROOT))

from backend.pipeline.llm import llm, llm_judge
from backend.pipeline.agents.judge import llm_as_judge
from backend.evaluation.compute_metrics import (
    extract_pmids_from_report,
    extract_escat_tier,
    check_pmids_exist_in_kb,
)
from backend.evaluation.ablation_enricher import run_enricher_only

BENCHMARK_CSV = ROOT / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR   = ROOT / "backend" / "evaluation" / "results"
ENRICHER_JSON = RESULTS_DIR / "ablation_enricher_results.json"
SUMMARY_CSV   = RESULTS_DIR / "ablation_summary.csv"

# Stessi alias del runner originale
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

CASES_TO_RERUN = {
    "BENCH-005", "BENCH-006", "BENCH-008", "BENCH-009", "BENCH-012",
    "BENCH-014", "BENCH-015", "BENCH-016", "BENCH-017", "BENCH-019",
    "BENCH-021", "BENCH-022", "BENCH-023", "BENCH-024", "BENCH-025",
    "BENCH-027", "BENCH-030",
}


def retry(func, *args, max_retries=4, backoff=2.0, timeout=300, **kwargs):
    import concurrent.futures
    b = backoff
    for attempt in range(max_retries):
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(func, *args, **kwargs)
            val = future.result(timeout=timeout)
            executor.shutdown(wait=False)
            return val
        except Exception as e:
            executor.shutdown(wait=False)
            print(f"  [RETRY {attempt+1}/{max_retries}] {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(b)
            b *= 2.0


def evaluate_report(case_id, report, expected_drug, expected_pmid, expected_escat):
    drugs = [d.strip() for d in re.split(r"[+/,]", expected_drug)]
    drug_found = all(d.lower() in report.lower() for d in drugs if d) if drugs else False

    cited_pmids = extract_pmids_from_report(report)
    anchor_pmid_cited = expected_pmid in cited_pmids if expected_pmid else False

    valid_pmids = check_pmids_exist_in_kb(cited_pmids)
    hallucinated = cited_pmids - valid_pmids
    hallucination_rate = len(hallucinated) / len(cited_pmids) if cited_pmids else 0.0

    extracted_tier = extract_escat_tier(report, None)
    escat_match = (extracted_tier == expected_escat.upper()) if expected_escat else False

    return {
        "dac_drug_found":           drug_found,
        "dac_anchor_pmid_cited":    anchor_pmid_cited,
        "n_cited_pmids":            len(cited_pmids),
        "n_hallucinated_pmids":     len(hallucinated),
        "pmid_hallucination_rate":  hallucination_rate,
        "extracted_escat":          extracted_tier,
        "escat_match":              escat_match,
        "cited_pmids_list":         sorted(list(cited_pmids)),
        "hallucinated_pmids_list":  sorted(list(hallucinated)),
    }


def main():
    # ── Carica benchmark ──────────────────────────────────────────────
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        bench = {row["case_id"]: row for row in csv.DictReader(f)}

    # ── Carica risultati enricher esistenti ───────────────────────────
    if ENRICHER_JSON.exists():
        with open(ENRICHER_JSON, "r", encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []

    # Converti in dict per aggiornamento in-place
    results_map = {r["case_id"]: r for r in existing}

    # ── Re-run sui 17 casi ────────────────────────────────────────────
    for case_id in sorted(CASES_TO_RERUN):
        row = bench[case_id]
        gene = "MSI" if row["gene"] == "MMR" else ("TMB" if row["gene"] == "TMB" else row["gene"])
        variant       = row["variant"]
        tumor_type    = TUMOR_MAP.get(row["tumor"], row["tumor"])
        alteration_type = row["alteration_type"]
        therapy_line  = "first-line"
        expected_drug = row["expected_drug"]
        expected_pmid = int(row["pmid"]) if row.get("pmid") and str(row.get("pmid")).isdigit() else None
        expected_escat = row.get("escat", "")

        print(f"\n{'='*55}")
        print(f"  {case_id}: {gene} {variant} | {tumor_type}")
        print(f"  expected_drug: {expected_drug}")
        print(f"{'='*55}")

        try:
            report = retry(run_enricher_only, gene, variant, tumor_type, alteration_type, therapy_line)
            metrics = evaluate_report(case_id, report, expected_drug, expected_pmid, expected_escat)
            judge   = retry(llm_as_judge, report, {"gene": gene, "variant": variant, "tumor_type": tumor_type})

            entry = {
                "case_id":     case_id,
                "report":      report,
                **metrics,
                "judge_score": judge.get("score_totale"),
                "judge_detail": judge,
            }
            results_map[case_id] = entry

            # Salvataggio checkpoint dopo ogni caso
            ordered = [results_map[cid] for cid in sorted(results_map.keys())]
            with open(ENRICHER_JSON, "w", encoding="utf-8") as f:
                json.dump(ordered, f, indent=2, ensure_ascii=False)

            print(f"  DAC: {metrics['dac_drug_found']} | PMID halluc: {metrics['pmid_hallucination_rate']:.0%} | judge: {judge.get('score_totale')}")

        except Exception as e:
            print(f"  [ERROR] {case_id}: {e}")
            continue

    # ── Ricalcola ablation_summary.csv ───────────────────────────────
    print("\n\nRicalcolo ablation_summary.csv...")
    regen_summary()
    print("Fatto.")


def regen_summary():
    """Rilegge tutti e 5 i JSON dei risultati e riscrive ablation_summary.csv."""
    import statistics

    FILES = {
        "vanilla":       RESULTS_DIR / "ablation_vanilla_results.json",
        "websearch":     RESULTS_DIR / "ablation_websearch_results.json",
        "rag_testuale":  RESULTS_DIR / "ablation_rag_results.json",
        "enricher_only": RESULTS_DIR / "ablation_enricher_results.json",
        "full_graphrag": RESULTS_DIR / "ablation_graphrag_results.json",
    }

    rows = []
    for cond, path in FILES.items():
        if not path.exists():
            print(f"  [WARN] {path.name} non trovato, skip.")
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        n = len(data)
        if n == 0:
            continue

        dac          = sum(1 for r in data if r.get("dac_drug_found")) / n
        pmid_cov     = sum(1 for r in data if r.get("dac_anchor_pmid_cited")) / n
        halluc       = statistics.mean(r.get("pmid_hallucination_rate", 0) for r in data)
        escat_match  = sum(1 for r in data if r.get("escat_match")) / n
        judge_scores = [r["judge_score"] for r in data if r.get("judge_score") is not None]
        judge_mean   = statistics.mean(judge_scores) if judge_scores else None
        escat_present = sum(1 for r in data if r.get("extracted_escat") and r["extracted_escat"] != "N/A") / n

        rows.append({
            "condition":           cond,
            "n_cases":             n,
            "dac":                 f"{dac:.3f}",
            "pmid_coverage":       f"{pmid_cov:.3f}",
            "pmid_hallucination":  f"{halluc:.3f}",
            "escat_match":         f"{escat_match:.3f}",
            "escat_present":       f"{escat_present:.3f}",
            "judge_mean":          f"{judge_mean:.3f}" if judge_mean is not None else "N/A",
        })

    fieldnames = ["condition", "n_cases", "dac", "pmid_coverage",
                  "pmid_hallucination", "escat_match", "escat_present", "judge_mean"]
    with open(SUMMARY_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\n  ──────────────────────────────────────────────────────────")
    print(f"  {'Condizione':<16} {'DAC':>6} {'PMID_cov':>9} {'Halluc':>8} {'ESCAT':>7} {'Judge':>7}")
    print("  ──────────────────────────────────────────────────────────")
    for r in rows:
        print(f"  {r['condition']:<16} {r['dac']:>6} {r['pmid_coverage']:>9} "
              f"{r['pmid_hallucination']:>8} {r['escat_match']:>7} {r['judge_mean']:>7}")


if __name__ == "__main__":
    main()
