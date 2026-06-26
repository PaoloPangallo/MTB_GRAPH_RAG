"""
test_oncokb_queries.py — Testa le query OncoKB per i 16 casi che restituiscono zero trattamenti
per trovare il formato corretto da usare nell'enricher.
"""
import sys
import json
import requests
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))
from backend.pipeline.llm import ONCOKB_TOKEN

ONCOKB_BASE = "https://www.oncokb.org/api/v1/annotate"
HEADERS = {
    "accept": "application/json",
    "Authorization": f"Bearer {ONCOKB_TOKEN}",
}

def query(endpoint, params):
    try:
        r = requests.get(f"{ONCOKB_BASE}/{endpoint}", params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        treatments = data.get("treatments", [])
        level1_2 = [t for t in treatments if t.get("level") in ("LEVEL_1", "LEVEL_2")]
        return f"OK | {len(treatments)} treatments total | {len(level1_2)} LEVEL_1/2"
    except Exception as e:
        return f"ERROR: {e}"

print("=" * 70)
print("TEST ONCOKB QUERY FORMATS")
print("=" * 70)

# ── ATYPICAL cases ─────────────────────────────────────────────────────────
print("\n--- ATYPICAL ---")

# BENCH-009: KIT Exon 11 Mutation / GIST / expected: Imatinib
case = "BENCH-009 KIT Exon 11 / GIST"
print(f"\n{case}")
print("  [a] variant='Exon 11 Mutation':", query("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": "Exon 11 Mutation", "tumorType": "Gastrointestinal Stromal Tumor"}))
print("  [b] variant='Exon11'          :", query("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": "Exon11", "tumorType": "Gastrointestinal Stromal Tumor"}))
print("  [c] variant='V560D' (example) :", query("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": "V560D", "tumorType": "Gastrointestinal Stromal Tumor"}))

# BENCH-019: KIT Exon 9 Mutation / GIST / expected: Sunitinib
case = "BENCH-019 KIT Exon 9 / GIST"
print(f"\n{case}")
print("  [a] variant='Exon 9 Mutation':", query("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": "Exon 9 Mutation", "tumorType": "Gastrointestinal Stromal Tumor"}))
print("  [b] variant='A502_Y503dup'   :", query("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": "A502_Y503dup", "tumorType": "Gastrointestinal Stromal Tumor"}))

# BENCH-024: EGFR Exon 19 Deletion / NSCLC / expected: Osimertinib
case = "BENCH-024 EGFR Exon 19 Deletion / NSCLC"
print(f"\n{case}")
print("  [a] variant='Exon 19 Deletion'      :", query("mutations/byProteinChange", {"hugoSymbol": "EGFR", "alteration": "Exon 19 Deletion", "tumorType": "Lung Adenocarcinoma"}))
print("  [b] variant='Exon 19 deletion'      :", query("mutations/byProteinChange", {"hugoSymbol": "EGFR", "alteration": "Exon 19 deletion", "tumorType": "Lung Adenocarcinoma"}))
print("  [c] variant='DEL19'                 :", query("mutations/byProteinChange", {"hugoSymbol": "EGFR", "alteration": "DEL19", "tumorType": "Lung Adenocarcinoma"}))
print("  [d] variant='L747_P753delinsS'      :", query("mutations/byProteinChange", {"hugoSymbol": "EGFR", "alteration": "L747_P753delinsS", "tumorType": "Lung Adenocarcinoma"}))
print("  [e] variant='EGFR act mut'          :", query("mutations/byProteinChange", {"hugoSymbol": "EGFR", "alteration": "EGFR act mut", "tumorType": "Lung Adenocarcinoma"}))

# BENCH-027: MET Exon 14 Skipping / NSCLC / expected: Capmatinib
case = "BENCH-027 MET Exon 14 Skipping / NSCLC"
print(f"\n{case}")
print("  [a] variant='Exon 14 Skipping'      :", query("mutations/byProteinChange", {"hugoSymbol": "MET", "alteration": "Exon 14 Skipping", "tumorType": "Lung Adenocarcinoma"}))
print("  [b] variant='Exon 14 skipping'      :", query("mutations/byProteinChange", {"hugoSymbol": "MET", "alteration": "Exon 14 skipping", "tumorType": "Lung Adenocarcinoma"}))
print("  [c] variant='Exon 14 skipping mutation':", query("mutations/byProteinChange", {"hugoSymbol": "MET", "alteration": "Exon 14 skipping mutation", "tumorType": "Lung Adenocarcinoma"}))
print("  [d] variant='METex14'               :", query("mutations/byProteinChange", {"hugoSymbol": "MET", "alteration": "METex14", "tumorType": "Lung Adenocarcinoma"}))

# ── BIOMARKER cases ────────────────────────────────────────────────────────
print("\n--- BIOMARKER ---")

# BENCH-017: MSI-High / Colorectal Cancer / expected: Pembrolizumab
case = "BENCH-017 MSI-High / Colorectal"
print(f"\n{case}")
print("  [a] no hugoSymbol, alt='MSI-High'   :", query("mutations/byProteinChange", {"alteration": "MSI-High", "tumorType": "Colorectal Cancer"}))
print("  [b] no hugoSymbol, alt='MSI-H'      :", query("mutations/byProteinChange", {"alteration": "MSI-H", "tumorType": "Colorectal Cancer"}))
print("  [c] tumorType=None, alt='MSI-H'     :", query("mutations/byProteinChange", {"alteration": "MSI-H"}))
print("  [d] hugoSymbol=MSH2, alt='MSI-H'   :", query("mutations/byProteinChange", {"hugoSymbol": "MSH2", "alteration": "MSI-H", "tumorType": "Colorectal Cancer"}))

# BENCH-023: TMB-High / Solid Tumor / expected: Pembrolizumab
case = "BENCH-023 TMB-High / Solid Tumor"
print(f"\n{case}")
print("  [a] no hugoSymbol, alt='TMB-High'   :", query("mutations/byProteinChange", {"alteration": "TMB-High", "tumorType": "Solid Tumor"}))
print("  [b] no hugoSymbol, alt='TMB-H'      :", query("mutations/byProteinChange", {"alteration": "TMB-H", "tumorType": "Solid Tumor"}))
print("  [c] no hugoSymbol, alt='High TMB'   :", query("mutations/byProteinChange", {"alteration": "High TMB", "tumorType": "Solid Tumor"}))

# ── FUSION single-gene cases ────────────────────────────────────────────────
print("\n--- FUSION single gene ---")

# BENCH-006: ABL1 BCR-ABL1 Fusion / CML / expected: Imatinib
case = "BENCH-006 BCR-ABL1 / CML"
print(f"\n{case}")
print("  [a] structuralVariants A=BCR B=ABL1 :", query("structuralVariants", {"hugoSymbolA": "BCR", "hugoSymbolB": "ABL1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Chronic Myeloid Leukemia"}))
print("  [b] byProteinChange BCR-ABL1        :", query("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": "BCR-ABL1 Fusion", "tumorType": "Chronic Myeloid Leukemia"}))

# BENCH-016: NTRK1 Fusion / Solid Tumor / expected: Larotrectinib
case = "BENCH-016 NTRK1 Fusion / Solid Tumor"
print(f"\n{case}")
print("  [a] structuralVariants A=NTRK1 B='' :", query("structuralVariants", {"hugoSymbolA": "NTRK1", "hugoSymbolB": "NTRK1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Solid Tumor"}))
print("  [b] A=LMNA B=NTRK1                  :", query("structuralVariants", {"hugoSymbolA": "LMNA", "hugoSymbolB": "NTRK1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Solid Tumor"}))
