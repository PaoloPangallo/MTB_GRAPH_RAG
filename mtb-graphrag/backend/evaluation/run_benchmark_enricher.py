import json
import csv
from pathlib import Path
from backend.pipeline.graph import run_pipeline

BENCHMARK_CSV = Path(__file__).resolve().parents[1] / "benchmark" / "benchmark_papers_summary_30_v2.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

TUMOR_MAP = {
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

def main():
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cases_meta = {r["case_id"]: r for r in reader}

    gap_cases = ["BENCH-013", "BENCH-017", "BENCH-030"]
    
    results = []
    output_json = RESULTS_DIR / "enricher_results.json"
    
    # Load existing if any
    if output_json.exists():
        with open(output_json, "r", encoding="utf-8") as f:
            results = json.load(f)
            
    already_done = {r["case_id"] for r in results}

    for case_id in gap_cases:
        if case_id in already_done:
            print(f"Skipping {case_id}, already done.")
            continue
            
        row = cases_meta[case_id]
        print(f"Running Enricher per {case_id}...")
        tumor = TUMOR_MAP.get(row["tumor"], row["tumor"])
        state = {
            "gene":               row["gene"] if row["gene"] not in ("MMR", "TMB") else "",
            "variant":            row["variant"],
            "tumor_type":         tumor,
            "alteration_type":    row["alteration_type"],
            "therapy_line":       "first-line",
            "enrich_with_oncokb": True,  # <-- ABILITIAMO L'ENRICHER
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
        
        final = run_pipeline(state)
        
        res = {
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
            "report":        final["report"],
            "oncokb_enrichment": final["oncokb_enrichment"]
        }
        results.append(res)
        
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    print("Completato enricher.")

if __name__ == "__main__":
    main()
