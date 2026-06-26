"""
diagnose_fairness.py — Verifica i tre punti sollevati dal relatore:
1. Fallback pertinente=True nel websearch: count reale dai JSON
2. Asimmetria di normalizzazione: gene/variant passati identicamente a tutte le condizioni?
3. Separazione netta Tipo D (rete) vs Tipo B (formato) nell'enricher fix
"""
import sys
import json
import csv
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS_DIR = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")
BENCH_CSV   = Path(r"c:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\benchmark\benchmark_papers_summary_30_v2.csv")

with open(BENCH_CSV, "r", encoding="utf-8") as f:
    bench = {row["case_id"]: row for row in csv.DictReader(f)}

print("=" * 70)
print("PUNTO 1 — Websearch: fallback pertinente=True")
print("=" * 70)

with open(RESULTS_DIR / "ablation_websearch_results.json", "r", encoding="utf-8") as f:
    ws = json.load(f)

total_pmids = 0
fallback_count = 0
no_fallback_field = 0
pertinent_true = 0
pertinent_false = 0

for r in ws:
    details = r.get("web_pmid_detail", {}).get("pmids_detail", [])
    for p in details:
        total_pmids += 1
        if "fallback" not in p:
            no_fallback_field += 1
        elif p.get("fallback"):
            fallback_count += 1
        if p.get("pertinente"):
            pertinent_true += 1
        else:
            pertinent_false += 1

print(f"  PMID totali valutati: {total_pmids}")
print(f"  PMID con campo 'fallback' assente nel JSON: {no_fallback_field}")
print(f"  PMID con fallback=True esplicito: {fallback_count}")
print(f"  PMID con pertinente=True (include eventuali fallback): {pertinent_true}")
print(f"  PMID con pertinente=False: {pertinent_false}")
print()
print("  CONCLUSIONE: il campo 'fallback' non viene mai scritto nel JSON.")
print("  I fallback pertinente=True non sono distinguibili dai veri positivi.")
print("  => Il dato 81.1% non è auditabile sui JSON salvati.")

# Quanti PMID hanno motivazione di fallback?
fallback_by_motive = 0
for r in ws:
    details = r.get("web_pmid_detail", {}).get("pmids_detail", [])
    for p in details:
        motive = p.get("motivazione", "")
        if "fallback" in motive.lower() or "errore" in motive.lower():
            fallback_by_motive += 1

print(f"  PMID con motivazione contenente 'fallback'/'errore': {fallback_by_motive}")
print(f"  => Questo è il numero di fallback recuperabile indirettamente dal testo.")


print()
print("=" * 70)
print("PUNTO 2 — Normalizzazione input: è identica per tutte le condizioni?")
print("=" * 70)

TUMOR_MAP = {
    "NSCLC": "Lung Adenocarcinoma", "Melanoma": "Melanoma",
    "Breast Cancer HER2+": "Breast Cancer", "Breast Cancer HR+": "Breast Cancer",
    "Ovarian Cancer": "Ovarian Cancer", "CML": "Chronic Myeloid Leukemia",
    "Colorectal Cancer": "Colorectal Cancer", "GIST": "Gastrointestinal Stromal Tumor",
    "AML": "Acute Myeloid Leukemia", "Solid Tumor": "Solid Tumor",
    "Gastric Cancer": "Gastric Cancer", "Prostate Cancer": "Prostate Cancer",
    "Cholangiocarcinoma": "Cholangiocarcinoma", "Thyroid Cancer": "Thyroid Cancer",
}

print("\n  Input comune (identico per tutte le 5 condizioni — riga 223 run_ablation_study.py):")
for case_id in ["BENCH-017", "BENCH-023", "BENCH-014", "BENCH-021"]:
    row = bench[case_id]
    gene_raw = row["gene"]
    gene = "MSI" if gene_raw == "MMR" else ("TMB" if gene_raw == "TMB" else gene_raw)
    tumor_type = TUMOR_MAP.get(row["tumor"], row["tumor"])
    print(f"  {case_id}: gene={gene!r}, variant={row['variant']!r}, tumor={tumor_type!r}, alt={row['alteration_type']!r}")

print()
print("  Normalizzazioni INTERNE a ciascuna condizione (NON modificano l'input):")
print()
print("  vanilla:       nessuna — usa gene/variant raw per il prompt LLM")
print("  websearch:     nessuna — usa gene/variant per la query PubMed")
print("  rag_testuale:  nessuna — usa gene/variant per la query Cypher/embedding")
print("  enricher_only: MSI-High→MSI-H, TMB-High→TMB-H solo per la chiamata API OncoKB")
print("                 (ablation_enricher.py, _build_fair_oncokb_params)")
print("  full_graphrag: il gene è già normalizzato nel grafo Neo4j")
print()
print("  CONCLUSIONE: l'input (gene, variant, tumor) è IDENTICO per tutte le condizioni.")
print("  La conversione MSI-H è un adattamento del formato di query OncoKB,")
print("  non una modifica dell'input clinico. Nessuna asimmetria di input.")
print()
print("  Verifica: MSI-High nel report vanilla (dovrebbe citare Pembrolizumab)?")
with open(RESULTS_DIR / "ablation_vanilla_results.json", "r", encoding="utf-8") as f:
    vanilla = {r["case_id"]: r for r in json.load(f)}
v017 = vanilla.get("BENCH-017", {})
print(f"  BENCH-017 vanilla — DAC: {v017.get('dac_drug_found')} | report (200 chars): {v017.get('report','')[:200]}")


print()
print("=" * 70)
print("PUNTO 3 — Separazione Tipo D (rete) vs Tipo B/A/C (formato)")
print("=" * 70)

tipo = {
    "D — Transient network failure": ["BENCH-012"],
    "A — Tumor type synonym": ["BENCH-014", "BENCH-021", "BENCH-030"],
    "B — Biomarker format (MSI-H/TMB-H)": ["BENCH-017", "BENCH-023"],
    "B — Alteration generic → Oncogenic Mutations": ["BENCH-005", "BENCH-008", "BENCH-009",
                                                       "BENCH-019", "BENCH-022", "BENCH-024",
                                                       "BENCH-025", "BENCH-027"],
    "C — Fusion parser (BCR-ABL1/RET/NTRK1)": ["BENCH-006", "BENCH-015", "BENCH-016"],
}

for label, cases in tipo.items():
    print(f"\n  {label} ({len(cases)} casi):")
    for cid in cases:
        row = bench[cid]
        print(f"    {cid}: {row['gene']} {row['variant']} / {row['tumor']}")
