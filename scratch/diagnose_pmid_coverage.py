"""
diagnose_pmid_coverage.py — Analizza perché full_graphrag ha PMID coverage 63.3%.
Mostra quali 11 casi NON citano il PMID anchor e perché.
"""
import sys
import json
import csv
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))
from backend.evaluation.compute_metrics import extract_pmids_from_report, check_pmids_exist_in_kb

RESULTS_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")
BENCH_CSV   = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")

# Carica benchmark
with open(BENCH_CSV, "r", encoding="utf-8") as f:
    bench = {row["case_id"]: row for row in csv.DictReader(f)}

# Carica risultati graphrag
with open(RESULTS_DIR / "ablation_graphrag_results.json", "r", encoding="utf-8") as f:
    graphrag = json.load(f)

print("=" * 72)
print("FULL_GRAPHRAG — Diagnosi PMID Coverage (63.3%)")
print("=" * 72)

hit = []
miss_pmid_not_in_report = []
miss_pmid_not_in_kg = []

for r in graphrag:
    case_id = r["case_id"]
    row = bench.get(case_id, {})
    expected_pmid_raw = row.get("pmid", "")
    report = r.get("report", "")
    
    if not expected_pmid_raw or not str(expected_pmid_raw).strip().isdigit():
        print(f"  {case_id}: NO expected PMID nel benchmark")
        continue
    
    expected_pmid = int(expected_pmid_raw)
    cited_pmids = extract_pmids_from_report(report)
    
    # Controlla se il PMID esiste nel KG
    in_kg = check_pmids_exist_in_kb({expected_pmid})
    pmid_in_kg = expected_pmid in in_kg
    
    # Controlla se è citato nel report
    pmid_cited = expected_pmid in cited_pmids
    
    if pmid_cited:
        hit.append(case_id)
    elif not pmid_in_kg:
        miss_pmid_not_in_kg.append((case_id, expected_pmid, row.get("gene"), row.get("variant")))
    else:
        # PMID è nel KG ma non è stato citato nel report
        miss_pmid_not_in_report.append((case_id, expected_pmid, row.get("gene"), row.get("variant")))

print(f"\nCasi con anchor PMID citato: {len(hit)}/30 ({len(hit)/30:.1%})")
print(f"  {sorted(hit)}")

print(f"\nCasi MISS — PMID nel KG ma NON citato nel report: {len(miss_pmid_not_in_report)}")
for cid, pmid, gene, var in miss_pmid_not_in_report:
    r = next(x for x in graphrag if x["case_id"] == cid)
    cited = extract_pmids_from_report(r.get("report",""))
    print(f"  {cid}: expected PMID={pmid} ({gene} {var}) | PMIDs nel report: {sorted(cited)}")

print(f"\nCasi MISS — PMID NON presente nel KG (non indicizzato): {len(miss_pmid_not_in_kg)}")
for cid, pmid, gene, var in miss_pmid_not_in_kg:
    r = next(x for x in graphrag if x["case_id"] == cid)
    cited = extract_pmids_from_report(r.get("report",""))
    print(f"  {cid}: expected PMID={pmid} ({gene} {var}) | PMIDs nel report: {sorted(cited)}")

print("\n\n--- RIEPILOGO DIAGNOSTICO ---")
print(f"  PMID coverage = {len(hit)}/30 = {len(hit)/30:.1%}")
print(f"  Di cui miss per PMID non nel KG: {len(miss_pmid_not_in_kg)}")
print(f"  Di cui miss per PMID nel KG ma non citato: {len(miss_pmid_not_in_report)}")

# Diagnosi: check se anche enricher ha il PMID nel KG
if miss_pmid_not_in_report:
    print(f"\n  Diagnosi per i {len(miss_pmid_not_in_report)} casi 'nel KG ma non citati':")
    print("  Il report del graphrag cita altri PMID, ma non quello del benchmark.")
    print("  Possibile causa: il nodo CITED_IN esiste per la variante ma punta")
    print("  a pubblicazioni diverse da quella del benchmark (che usa il PMID")
    print("  della linea guida clinica, non necessariamente quello dei trial).")
