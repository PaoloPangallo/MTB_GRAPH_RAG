"""
test_oncokb_queries2.py — Testa i casi rimanenti non ancora testati.
Include: BENCH-005, 008, 012, 014, 015, 021, 022, 025, 030
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

def query(endpoint, params, label=""):
    try:
        r = requests.get(f"{ONCOKB_BASE}/{endpoint}", params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        treatments = data.get("treatments", [])
        level1_2 = [t for t in treatments if t.get("level") in ("LEVEL_1", "LEVEL_2")]
        drugs_found = [", ".join(d["drugName"] for d in t.get("drugs", [])) for t in level1_2]
        drugs_str = " | ".join(drugs_found) if drugs_found else "none"
        return f"OK | {len(treatments)} total | {len(level1_2)} L1/2 | drugs: {drugs_str}"
    except Exception as e:
        return f"ERROR: {e}"

print("=" * 80)
print("TEST ONCOKB - CASI RIMANENTI")
print("=" * 80)

# ─────────────────────────────────────────────────────────────────────────────
# POINT_MUTATION cases that returned empty
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- POINT_MUTATION cases ---")

# BENCH-005: BRCA1 Mutation / Ovarian Cancer / expected: Olaparib
print("\nBENCH-005 BRCA1 / Ovarian Cancer (expected: Olaparib)")
print("  [a] alt='Mutation':", query("mutations/byProteinChange", {"hugoSymbol": "BRCA1", "alteration": "Mutation", "tumorType": "Ovarian Cancer"}))
print("  [b] alt='any':", query("mutations/byProteinChange", {"hugoSymbol": "BRCA1", "alteration": "any", "tumorType": "Ovarian Cancer"}))
print("  [c] no alt:", query("mutations/byProteinChange", {"hugoSymbol": "BRCA1", "tumorType": "Ovarian Cancer"}))

# BENCH-008: PIK3CA Mutation / Breast Cancer HR+ / expected: Alpelisib+Fulvestrant
print("\nBENCH-008 PIK3CA / Breast Cancer (expected: Alpelisib+Fulvestrant)")
print("  [a] alt='Mutation'  tumor='Breast Cancer':", query("mutations/byProteinChange", {"hugoSymbol": "PIK3CA", "alteration": "Mutation", "tumorType": "Breast Cancer"}))
print("  [b] alt='E545K' (example) tumor='Breast Cancer':", query("mutations/byProteinChange", {"hugoSymbol": "PIK3CA", "alteration": "E545K", "tumorType": "Breast Cancer"}))
print("  [c] alt='Mutation' tumor='Breast Cancer (ER+)':", query("mutations/byProteinChange", {"hugoSymbol": "PIK3CA", "alteration": "Mutation", "tumorType": "Breast Cancer (ER+)"}))

# BENCH-012: KRAS G12C / NSCLC / expected: Sotorasib
print("\nBENCH-012 KRAS G12C / NSCLC (expected: Sotorasib)")
print("  [a] tumor='Lung Adenocarcinoma':", query("mutations/byProteinChange", {"hugoSymbol": "KRAS", "alteration": "G12C", "tumorType": "Lung Adenocarcinoma"}))
print("  [b] tumor='Non-Small Cell Lung Cancer':", query("mutations/byProteinChange", {"hugoSymbol": "KRAS", "alteration": "G12C", "tumorType": "Non-Small Cell Lung Cancer"}))
print("  [c] tumor='NSCLC':", query("mutations/byProteinChange", {"hugoSymbol": "KRAS", "alteration": "G12C", "tumorType": "NSCLC"}))

# BENCH-014: ABL1 T315I / CML / expected: Ponatinib
print("\nBENCH-014 ABL1 T315I / CML (expected: Ponatinib)")
print("  [a] tumor='Chronic Myeloid Leukemia':", query("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": "T315I", "tumorType": "Chronic Myeloid Leukemia"}))
print("  [b] tumor='CML':", query("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": "T315I", "tumorType": "CML"}))
print("  [c] no tumor:", query("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": "T315I"}))

# BENCH-022: BRCA2 Mutation / Prostate Cancer / expected: Olaparib
print("\nBENCH-022 BRCA2 / Prostate Cancer (expected: Olaparib)")
print("  [a] alt='Mutation':", query("mutations/byProteinChange", {"hugoSymbol": "BRCA2", "alteration": "Mutation", "tumorType": "Prostate Cancer"}))
print("  [b] alt='any':", query("mutations/byProteinChange", {"hugoSymbol": "BRCA2", "alteration": "any", "tumorType": "Prostate Cancer"}))

# BENCH-025: IDH1 R132 / AML / expected: Ivosidenib
print("\nBENCH-025 IDH1 R132 / AML (expected: Ivosidenib)")
print("  [a] alt='R132' tumor='Acute Myeloid Leukemia':", query("mutations/byProteinChange", {"hugoSymbol": "IDH1", "alteration": "R132", "tumorType": "Acute Myeloid Leukemia"}))
print("  [b] alt='R132H' tumor='Acute Myeloid Leukemia':", query("mutations/byProteinChange", {"hugoSymbol": "IDH1", "alteration": "R132H", "tumorType": "Acute Myeloid Leukemia"}))
print("  [c] alt='R132' tumor='AML':", query("mutations/byProteinChange", {"hugoSymbol": "IDH1", "alteration": "R132", "tumorType": "AML"}))
print("  [d] alt='Oncogenic Mutations':", query("mutations/byProteinChange", {"hugoSymbol": "IDH1", "alteration": "Oncogenic Mutations", "tumorType": "Acute Myeloid Leukemia"}))

# ─────────────────────────────────────────────────────────────────────────────
# FUSION remaining
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- FUSION remaining ---")

# BENCH-015: RET Fusion / NSCLC / expected: Selpercatinib
print("\nBENCH-015 RET Fusion / NSCLC (expected: Selpercatinib)")
print("  [a] structuralVariants A=RET B=RET:", query("structuralVariants", {"hugoSymbolA": "RET", "hugoSymbolB": "RET", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Lung Adenocarcinoma"}))
print("  [b] structuralVariants A=RET B=KIF5B:", query("structuralVariants", {"hugoSymbolA": "KIF5B", "hugoSymbolB": "RET", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Lung Adenocarcinoma"}))
print("  [c] byProteinChange alt='Fusion':", query("mutations/byProteinChange", {"hugoSymbol": "RET", "alteration": "Fusion", "tumorType": "Lung Adenocarcinoma"}))
print("  [d] NSCLC:", query("structuralVariants", {"hugoSymbolA": "KIF5B", "hugoSymbolB": "RET", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Non-Small Cell Lung Cancer"}))

# ─────────────────────────────────────────────────────────────────────────────
# CNA remaining
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- CNA remaining ---")

# BENCH-021: ERBB2 Amplification / Gastric Cancer / expected: Trastuzumab
print("\nBENCH-021 ERBB2 Amplification / Gastric Cancer (expected: Trastuzumab)")
print("  [a] tumor='Gastric Cancer':", query("copyNumberAlterations", {"hugoSymbol": "ERBB2", "copyNameAlterationType": "AMPLIFICATION", "tumorType": "Gastric Cancer"}))
print("  [b] tumor='Stomach Cancer':", query("copyNumberAlterations", {"hugoSymbol": "ERBB2", "copyNameAlterationType": "AMPLIFICATION", "tumorType": "Stomach Cancer"}))
print("  [c] L1/2/3:", "checking with all levels")
r = requests.get(f"{ONCOKB_BASE}/copyNumberAlterations", params={"hugoSymbol": "ERBB2", "copyNameAlterationType": "AMPLIFICATION", "tumorType": "Gastric Cancer"}, headers=HEADERS, timeout=10)
data = r.json()
treatments = data.get("treatments", [])
for t in treatments:
    print(f"     level={t.get('level')} | tumor={t.get('levelAssociatedCancerType', {}).get('name')} | drugs={[d['drugName'] for d in t.get('drugs', [])]}")
if not treatments:
    print("     (0 treatments)")

# BENCH-030: ERBB2 Amplification / Gastric Cancer / expected: Trastuzumab deruxtecan
print("\nBENCH-030 ERBB2 Amplification / Gastric (expected: Trastuzumab deruxtecan)")
print("  [a] same as BENCH-021:")
# same query - the expected drug is different (T-DXd vs Trastuzumab), which means the
# DAC failure here is about naming, not API failure

# ─────────────────────────────────────────────────────────────────────────────
# MET Exon 14 additional formats
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- MET Exon 14 additional formats ---")
print("\nBENCH-027 MET Exon 14 Skipping / NSCLC (expected: Capmatinib)")
for fmt in ["X14_splice", "Exon 14 splice site mutation", "splice", "D1010N", "T1010I", "del D1010"]:
    print(f"  alt='{fmt}':", query("mutations/byProteinChange", {"hugoSymbol": "MET", "alteration": fmt, "tumorType": "Lung Adenocarcinoma"}))

# ─────────────────────────────────────────────────────────────────────────────
# BCR-ABL1 additional formats
# ─────────────────────────────────────────────────────────────────────────────
print("\n--- BCR-ABL1 additional formats ---")
print("\nBENCH-006 BCR-ABL1 / CML (expected: Imatinib)")
for fmt in [("BCR", "ABL1"), ("ABL1", "BCR"), ("BCR-ABL1", "")]:
    a, b = fmt
    print(f"  A={a!r} B={b!r}:", query("structuralVariants", {"hugoSymbolA": a, "hugoSymbolB": b, "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Chronic Myeloid Leukemia"}))
# Try simple point mutation approach
print("  byProteinChange ABL1 alt='BCR-ABL1':", query("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": "BCR-ABL1", "tumorType": "Chronic Myeloid Leukemia"}))
print("  byProteinChange ABL1 alt='BCR-ABL':", query("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": "BCR-ABL", "tumorType": "Chronic Myeloid Leukemia"}))
