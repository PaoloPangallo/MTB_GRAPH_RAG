import sys
import json
from pathlib import Path

ROOT = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag")
sys.path.insert(0, str(ROOT))

from backend.evaluation.ablation_enricher import _build_fair_oncokb_params, _extract_level1_2
from backend.pipeline.agents.oncokb_enricher import _oncokb_request

results_path = ROOT / "backend" / "evaluation" / "results" / "ablation_enricher_results.json"
with open(results_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Benchmark rows to get tumor aliases
BENCHMARK_CSV = ROOT / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"
import csv
with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
    bench = {row["case_id"]: row for row in csv.DictReader(f)}

TUMOR_MAP = {
    "NSCLC": "Lung Adenocarcinoma", "Melanoma": "Melanoma",
    "Breast Cancer HER2+": "Breast Cancer", "Breast Cancer HR+": "Breast Cancer",
    "Ovarian Cancer": "Ovarian Cancer", "CML": "Chronic Myeloid Leukemia",
    "Colorectal Cancer": "Colorectal Cancer", "GIST": "Gastrointestinal Stromal Tumor",
    "AML": "Acute Myeloid Leukemia", "Solid Tumor": "Solid Tumor",
    "Gastric Cancer": "Gastric Cancer", "Prostate Cancer": "Prostate Cancer",
    "Cholangiocarcinoma": "Cholangiocarcinoma", "Thyroid Cancer": "Thyroid Cancer",
}

print(f"{'Case ID':<10} | {'Cited count':<12} | {'Not in local KG':<15} | {'Not in OncoKB API context':<25}")
print("-" * 75)

total_cited = 0
total_not_in_kg = 0
total_not_in_oncokb = 0

for r in data:
    case_id = r["case_id"]
    row = bench[case_id]
    gene = "MSI" if row["gene"] == "MMR" else ("TMB" if row["gene"] == "TMB" else row["gene"])
    variant = row["variant"]
    tumor_type = TUMOR_MAP.get(row["tumor"], row["tumor"])
    alteration_type = row["alteration_type"]
    
    # Query OncoKB to find what PMIDs were returned
    endpoint, params = _build_fair_oncokb_params(gene, variant, tumor_type, alteration_type)
    okb_data = _oncokb_request(endpoint, params)
    treatments = _extract_level1_2(okb_data)
    
    # Fallback if primary is empty and generic
    if not treatments and alteration_type in ("point_mutation", "atypical") and gene:
        # Check generic
        from backend.evaluation.ablation_enricher import _is_generic_alteration
        if _is_generic_alteration(variant):
            fb_params = {
                "hugoSymbol": gene,
                "alteration": "Oncogenic Mutations",
                "tumorType": tumor_type,
            }
            fb_data = _oncokb_request("mutations/byProteinChange", fb_params)
            treatments = _extract_level1_2(fb_data)
            
    oncokb_pmids = set()
    for t in treatments:
        oncokb_pmids.update(int(p) for p in t["pmids"])
        
    cited = set(int(p) for p in r.get("cited_pmids_list", []))
    hallucinated_by_metric = set(int(p) for p in r.get("hallucinated_pmids_list", []))
    
    not_in_oncokb = cited - oncokb_pmids
    
    print(f"{case_id:<10} | {len(cited):<12} | {len(hallucinated_by_metric):<15} | {len(not_in_oncokb):<25} ({list(not_in_oncokb)})")
    
    total_cited += len(cited)
    total_not_in_kg += len(hallucinated_by_metric)
    total_not_in_oncokb += len(not_in_oncokb)

print("-" * 75)
print(f"TOTAL      | {total_cited:<12} | {total_not_in_kg:<15} | {total_not_in_oncokb:<25}")
