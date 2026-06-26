import json
from pathlib import Path

results_path = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results\ablation_enricher_results.json")
with open(results_path, "r", encoding="utf-8") as f:
    data = json.load(f)

# Let's inspect BENCH-001, BENCH-005, and BENCH-004
cases = ["BENCH-001", "BENCH-004", "BENCH-005"]
for case_id in cases:
    record = next(r for r in data if r["case_id"] == case_id)
    print(f"=== {case_id} ===")
    print(f"Cited PMIDs: {record.get('cited_pmids_list')}")
    print(f"Hallucinated PMIDs: {record.get('hallucinated_pmids_list')}")
    print("\n--- REPORT snippet (References/PMIDs mentioned) ---")
    
    # Let's find lines with PMIDs or references in the report
    report = record.get("report", "")
    lines = report.split("\n")
    for line in lines:
        if "PMID" in line or "pmid" in line or "[" in line or "References" in line:
            print(f"  {line.strip()}")
    print("\n" + "="*50 + "\n")
