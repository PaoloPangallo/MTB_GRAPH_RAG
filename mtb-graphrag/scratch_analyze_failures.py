import json
from pathlib import Path
import re

results_dir = Path("backend/evaluation/results")
metrics = json.load(open("backend/evaluation/results/metrics_graphrag.json", encoding="utf-8"))

mismatches = [m for m in metrics if not m["escat_match"]]

output = []
output.append("=== QUALITATIVE ANALYSIS OF BORDERLINE CASES ===")
benchmark_results = json.load(open("backend/evaluation/results/benchmark_results.json", encoding="utf-8"))

for m in mismatches:
    case_id = m["case_id"]
    exp = m["expected_escat"]
    got = m["extracted_escat"]
    
    data = next((d for d in benchmark_results if d["case_id"] == case_id), None)
    if not data:
        continue
    
    # Estraiamo le evidenze trovate
    evidences = data.get("variant_data", {}).get("evidence_records", [])
    ev_summary = []
    for e in evidences:
        ev_summary.append(f"Level {e.get('evidence_level')} ({e.get('significance')} in {e.get('disease')})")
    
    # Estraiamo le frasi intorno a "ESCAT" dal report
    report = data.get("report", "")
    escat_context = re.findall(r'(.{0,50}ESCAT.{0,150})', report, re.IGNORECASE | re.DOTALL)
    
    output.append(f"\n--- {case_id} ---")
    output.append(f"Expected: {exp} | Extracted: {got}")
    output.append(f"Evidences in KB: {', '.join(ev_summary)}")
    output.append(f"Context in Report: {escat_context[0].strip().replace(chr(10), ' ') if escat_context else 'None'}")

with open(r"C:\Users\paolo\.gemini\antigravity-ide\brain\ddbd9d62-5f88-44fb-b10a-212387eda126\scratch\failures_details.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output))

print("Dumped to failures_details.txt")
