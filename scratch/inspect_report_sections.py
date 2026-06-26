import json
import re
from pathlib import Path

# Let's extract what was in the context for these cases.
# We can do this by running a script to parse the output results and get the PMIDs that OncoKB actually returned.
# OncoKB returned PMIDs are stored in the context, but wait, the context is not saved, but the results JSON has the report itself,
# and also we can re-evaluate the PMIDs. Wait, are the OncoKB PMIDs listed in the report under "5. Lista finale dei PMID verificati"?
# Let's check!

results_path = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results\ablation_enricher_results.json")
with open(results_path, "r", encoding="utf-8") as f:
    data = json.load(f)

for case_id in ["BENCH-001", "BENCH-004", "BENCH-005"]:
    record = next(r for r in data if r["case_id"] == case_id)
    report = record.get("report", "")
    print(f"=== CASE {case_id} ===")
    
    # Let's extract the "PMID verificati" section of the report text to see what was listed there
    match = re.search(r"(?:PMID Verificati|PMID verificati nel Knowledge Graph|Lista finale dei PMID verificati)(.*)", report, re.DOTALL | re.IGNORECASE)
    if match:
        print("--- Section 'PMID Verificati' in Report: ---")
        print(match.group(1).strip()[:400])
    else:
        print("--- Could not find verified PMIDs section in report ---")
    
    print("\n" + "="*60 + "\n")
