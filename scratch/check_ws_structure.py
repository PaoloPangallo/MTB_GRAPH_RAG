"""
check_ws_structure.py — Ispeziona la struttura reale del JSON websearch
"""
import sys, json
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")

with open(RESULTS_DIR / "ablation_websearch_results.json", "r", encoding="utf-8") as f:
    ws = json.load(f)

print(f"Totale casi websearch: {len(ws)}")
r0 = ws[0]
print(f"\nChiavi del record: {list(r0.keys())}")

web_detail = r0.get("web_pmid_detail", {})
print(f"\nChiavi web_pmid_detail: {list(web_detail.keys())}")
print(f"n_cited_pmids: {web_detail.get('n_cited_pmids')}")
print(f"n_exists_pmids: {web_detail.get('n_exists_pmids')}")
print(f"n_relevant_pmids: {web_detail.get('n_relevant_pmids')}")
print(f"pmid_relevant_rate: {web_detail.get('pmid_relevant_rate')}")
print(f"Lunghezza 'details': {len(web_detail.get('details', []))}")
if web_detail.get('details'):
    print(f"Chiavi primo detail: {list(web_detail['details'][0].keys())}")
    print(f"Primo detail: {web_detail['details'][0]}")

# Conta fallback su tutti i casi
print("\n--- Conteggio fallback via campo 'motivazione' ---")
total = 0
fallback_by_motive = 0
pertinent_true = 0
pertinent_false = 0
cases_with_fallback = []

for r in ws:
    details = r.get("web_pmid_detail", {}).get("details", [])
    case_fallback = 0
    for p in details:
        total += 1
        m = (p.get("motivazione") or "").lower()
        if "fallback" in m or "errore fallback" in m:
            fallback_by_motive += 1
            case_fallback += 1
        if p.get("pertinente"):
            pertinent_true += 1
        else:
            pertinent_false += 1
    if case_fallback > 0:
        cases_with_fallback.append((r["case_id"], case_fallback))

print(f"PMID totali con detail: {total}")
print(f"PMID pertinent=True: {pertinent_true}")
print(f"PMID pertinent=False: {pertinent_false}")
print(f"PMID con motivazione 'fallback': {fallback_by_motive}")
print(f"Casi con almeno un fallback: {len(cases_with_fallback)}")
for cid, n in cases_with_fallback:
    print(f"  {cid}: {n} fallback")
