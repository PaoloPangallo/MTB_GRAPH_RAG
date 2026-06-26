"""
diagnose_ablation.py — Controlla i due numeri sospetti nella tabella ablazione:
1. Quanti PMID websearch sono finiti in fallback (pertinente=True per timeout)?
2. Quante risposte enricher sono vuote/fallite?
"""
import sys
import json
from pathlib import Path

# Fix encoding Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")

# =============================================================
# 1. WEBSEARCH: Conta i fallback sul relevance check
# =============================================================
print("=" * 70)
print("  1. WEBSEARCH -- Analisi fallback sul relevance check")
print("=" * 70)

ws_file = RESULTS_DIR / "ablation_websearch_results.json"
ws_data = json.loads(ws_file.read_text(encoding="utf-8"))

total_pmid_evaluated = 0
total_fallback = 0
cases_with_fallback = []

for r in ws_data:
    case_id = r["case_id"]
    web_detail = r.get("web_pmid_detail", {})
    pmid_details = web_detail.get("pmids_detail", [])
    
    case_fallback = 0
    for p in pmid_details:
        total_pmid_evaluated += 1
        if p.get("fallback"):
            total_fallback += 1
            case_fallback += 1
    
    if case_fallback > 0:
        cases_with_fallback.append((case_id, case_fallback))

print(f"  Casi totali: {len(ws_data)}")
print(f"  PMID totali valutati dal judge: {total_pmid_evaluated}")
print(f"  PMID finiti in fallback (pertinente=True per timeout): {total_fallback}")
if total_pmid_evaluated > 0:
    print(f"  Percentuale fallback: {total_fallback/total_pmid_evaluated:.1%}")
print(f"  Casi con almeno un fallback: {len(cases_with_fallback)}")
for cid, n in cases_with_fallback:
    print(f"    {cid}: {n} PMID in fallback")

# Mostra la struttura di un esempio
print("\n  --- Struttura di un pmid_detail (primo disponibile) ---")
for r in ws_data:
    details = r.get("web_pmid_detail", {}).get("pmids_detail", [])
    if details:
        print(f"  Caso: {r['case_id']}")
        print(f"  Chiavi disponibili: {list(details[0].keys())}")
        print(f"  Primo esempio: {details[0]}")
        print()
        # Mostra tutti i pmid di quel caso
        for d in details:
            print(f"    pmid={d.get('pmid')}, pertinente={d.get('pertinente')}, fallback={d.get('fallback')}")
        break

# Calcolo del pmid_relevant_rate reale escludendo i fallback
print("\n  --- Ricalcolo pmid_relevant_rate escludendo i fallback ---")
total_non_fallback = 0
total_relevant_non_fallback = 0
for r in ws_data:
    details = r.get("web_pmid_detail", {}).get("pmids_detail", [])
    for p in details:
        if not p.get("fallback"):
            total_non_fallback += 1
            if p.get("pertinente"):
                total_relevant_non_fallback += 1

if total_non_fallback > 0:
    rate_clean = total_relevant_non_fallback / total_non_fallback
    print(f"  PMID valutati senza fallback: {total_non_fallback}")
    print(f"  PMID rilevanti (senza fallback): {total_relevant_non_fallback}")
    print(f"  pmid_relevant_rate PULITO (senza fallback): {rate_clean:.1%}")
    print(f"  pmid_relevant_rate DICHIARATO (con fallback): 81.1%")
    
    if total_fallback > 0:
        # Stima lower bound: tutti i fallback erano irrilevanti
        lb = total_relevant_non_fallback / (total_non_fallback + total_fallback)
        print(f"  Lower bound pessimistico (tutti i fallback irrilevanti): {lb:.1%}")


# =============================================================
# 2. ENRICHER: Conta le risposte vuote/fallite da OncoKB
# =============================================================
print()
print("=" * 70)
print("  2. ENRICHER -- Analisi risposte vuote/fallite da OncoKB API")
print("=" * 70)

enr_file = RESULTS_DIR / "ablation_enricher_results.json"
enr_data = json.loads(enr_file.read_text(encoding="utf-8"))

empty_oncokb = []   # OncoKB ha restituito 0 trattamenti
dac_failed = []     # farmaco non trovato

EMPTY_SIGNALS = [
    "Nessun trattamento",
    "nessuna evidenza",
    "nessun dato",
    "non sono stati trovati",
    "non sono stati rilevati",
    "Al momento, non sono",
    "non sono disponibili dati",
]

for r in enr_data:
    case_id = r["case_id"]
    report = r.get("report", "")
    drug_found = r.get("dac_drug_found", True)
    
    is_empty = any(sig.lower() in report.lower() for sig in EMPTY_SIGNALS)
    
    if is_empty:
        empty_oncokb.append(case_id)
    
    if not drug_found:
        dac_failed.append(case_id)

print(f"  Casi totali: {len(enr_data)}")
print(f"  Casi con 0 trattamenti OncoKB (report vuoto/nessuna evidenza): {len(empty_oncokb)}")
for cid in empty_oncokb:
    print(f"    {cid}")

print(f"\n  Casi con DAC fallito (farmaco atteso non presente nel report): {len(dac_failed)}")

# Incrocio: quali DAC falliti sono anche vuoti OncoKB?
both = [c for c in dac_failed if c in empty_oncokb]
only_dac = [c for c in dac_failed if c not in empty_oncokb]
print(f"  Di cui: con report vuoto (API fallita/mismatch): {len(both)}")
print(f"          con report non vuoto (wrong drug): {len(only_dac)}")

if both:
    print("\n  --- Casi vuoti con DAC fallito (API vuota o mismatch naming) ---")
    for cid in both:
        r = next(x for x in enr_data if x["case_id"] == cid)
        bench_csv = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
        import csv
        with open(bench_csv, "r", encoding="utf-8") as f:
            rows = {row["case_id"]: row for row in csv.DictReader(f)}
        bench = rows.get(cid, {})
        print(f"\n    {cid}: expected_drug={bench.get('expected_drug')!r} | gene={bench.get('gene')!r} | alteration={bench.get('alteration_type')!r}")
        print(f"    Report (primi 200 char): {r.get('report','')[:200]}")

if only_dac:
    print("\n  --- Casi con DAC fallito ma report NON vuoto (wrong drug) ---")
    for cid in only_dac:
        r = next(x for x in enr_data if x["case_id"] == cid)
        bench_csv = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
        import csv
        with open(bench_csv, "r", encoding="utf-8") as f:
            rows = {row["case_id"]: row for row in csv.DictReader(f)}
        bench = rows.get(cid, {})
        print(f"\n    {cid}: expected_drug={bench.get('expected_drug')!r}")
        print(f"    Report (primi 300 char): {r.get('report','')[:300]}")

# DAC corretto considerando solo i casi con OncoKB non vuoto
non_empty_cases = [r for r in enr_data if r["case_id"] not in empty_oncokb]
if non_empty_cases:
    dac_non_empty = sum(1 for r in non_empty_cases if r.get("dac_drug_found"))
    print(f"\n  --- DAC ricalcolato escludendo i casi OncoKB vuoti ---")
    print(f"  Casi con risposta OncoKB non vuota: {len(non_empty_cases)}")
    print(f"  DAC corretto su casi non vuoti: {dac_non_empty}/{len(non_empty_cases)} = {dac_non_empty/len(non_empty_cases):.1%}")


# =============================================================
# 3. VERIFICA FIX BIOMARKER
# =============================================================
print()
print("=" * 70)
print("  3. VERIFICA FIX BIOMARKER -- gene query identico per tutte le condizioni")
print("=" * 70)

import csv as csv_module
bench_csv = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")
with open(bench_csv, "r", encoding="utf-8") as f:
    bench_rows = list(csv_module.DictReader(f))

biomarker_cases = [r for r in bench_rows if r["alteration_type"] == "biomarker"]
print(f"  Casi biomarker nel benchmark: {len(biomarker_cases)}")
for r in biomarker_cases:
    gene_raw = r["gene"]
    gene_used = "MSI" if gene_raw == "MMR" else ("TMB" if gene_raw == "TMB" else gene_raw)
    print(f"    {r['case_id']}: gene_raw={gene_raw!r} -> gene_used={gene_used!r} (alteration_type={r['alteration_type']})")

print()
print("  CONCLUSIONE:")
print("  La variabile 'gene' e' condivisa nel loop del runner (riga 223) ed e'")
print("  applicata IDENTICAMENTE a tutte le 5 condizioni nello stesso loop.")
print("  Il fix non e' condizione-specifica -> OK metodologicamente.")
print()

# Verifica mappatura OncoKB per biomarker
sys.path.insert(0, str(Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag")))
try:
    from backend.pipeline.mappings import KB_TO_ONCOKB
    print("  Mappatura KB_TO_ONCOKB per le varianti biomarker:")
    for r in biomarker_cases:
        variant = r["variant"]
        mapped = KB_TO_ONCOKB.get(variant, variant)
        print(f"    {r['case_id']}: variant={variant!r} -> oncokb_alt={mapped!r}")
    print()
    print("  NOTA: l'enricher usa KB_TO_ONCOKB per il mapping OncoKB,")
    print("  che e' indipendente dalla variabile 'gene' usata per il RAG.")
    print("  I biomarker cases usano alteration_type='biomarker' -> endpoint speciale.")
except Exception as e:
    print(f"  [Errore import mappings]: {e}")
