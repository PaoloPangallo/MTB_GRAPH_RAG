"""
test_oncokb_queries3.py — Test finale per i casi ancora irrisolti.
"""
import sys
import requests
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))
from backend.pipeline.llm import ONCOKB_TOKEN

ONCOKB_BASE = "https://www.oncokb.org/api/v1/annotate"
HEADERS = {"accept": "application/json", "Authorization": f"Bearer {ONCOKB_TOKEN}"}

def q(endpoint, params):
    r = requests.get(f"{ONCOKB_BASE}/{endpoint}", params=params, headers=HEADERS, timeout=10)
    r.raise_for_status()
    data = r.json()
    t = data.get("treatments", [])
    l12 = [x for x in t if x.get("level") in ("LEVEL_1", "LEVEL_2")]
    drugs = " | ".join(", ".join(d["drugName"] for d in x.get("drugs",[])) for x in l12)
    return f"{len(l12)} L1/2 | {drugs or 'none'}"

print("=" * 70)

# BRCA1 / Ovarian Cancer (expected: Olaparib)
print("\nBENCH-005 BRCA1 / Ovarian Cancer")
for alt in ["Oncogenic Mutations", "Truncating Mutations", "K1630fs", "5382insC"]:
    print(f"  alt='{alt}':", q("mutations/byProteinChange", {"hugoSymbol": "BRCA1", "alteration": alt, "tumorType": "Ovarian Cancer"}))

# BRCA2 / Prostate Cancer (expected: Olaparib)
print("\nBENCH-022 BRCA2 / Prostate Cancer")
for alt, tumor in [("Oncogenic Mutations", "Prostate Cancer"), ("Truncating Mutations", "Prostate Cancer"),
                   ("Oncogenic Mutations", "Prostate Adenocarcinoma"), ("Truncating Mutations", "Castration-Resistant Prostate Cancer")]:
    print(f"  alt='{alt}' tumor='{tumor}':", q("mutations/byProteinChange", {"hugoSymbol": "BRCA2", "alteration": alt, "tumorType": tumor}))

# BCR-ABL1 / CML (expected: Imatinib)
print("\nBENCH-006 BCR-ABL1 / CML")
for alt in ["BCR-ABL1 Fusion", "BCR-ABL", "BCR-ABL1", "p210"]:
    print(f"  ABL1 alt='{alt}':", q("mutations/byProteinChange", {"hugoSymbol": "ABL1", "alteration": alt, "tumorType": "CML"}))
# Try structuralVariants with CML
print("  structuralVariants BCR/ABL1 CML:", q("structuralVariants", {"hugoSymbolA": "BCR", "hugoSymbolB": "ABL1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "CML"}))
print("  structuralVariants BCR/ABL1 no tumor:", q("structuralVariants", {"hugoSymbolA": "BCR", "hugoSymbolB": "ABL1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true"}))

# NTRK1 Fusion / Solid Tumor (expected: Larotrectinib)
print("\nBENCH-016 NTRK1 Fusion / Solid Tumor")
print("  sv A=NTRK1 B=NTRK1:", q("structuralVariants", {"hugoSymbolA": "NTRK1", "hugoSymbolB": "NTRK1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true", "tumorType": "Solid Tumor"}))
print("  sv A=NTRK1 B=NTRK1 no tumor:", q("structuralVariants", {"hugoSymbolA": "NTRK1", "hugoSymbolB": "NTRK1", "structuralVariantType": "FUSION", "isFunctionalFusion": "true"}))
print("  byProteinChange Fusion Solid Tumor:", q("mutations/byProteinChange", {"hugoSymbol": "NTRK1", "alteration": "Fusion", "tumorType": "Solid Tumor"}))
print("  byProteinChange Fusion no tumor:", q("mutations/byProteinChange", {"hugoSymbol": "NTRK1", "alteration": "Fusion"}))

# ERBB2 Amplification / Gastric (expected: Trastuzumab / T-DXd)
print("\nBENCH-021/030 ERBB2 CNA / Gastric")
for tumor in ["Gastric Cancer", "Stomach Cancer", "Gastroesophageal Adenocarcinoma",
              "Gastroesophageal Junction Adenocarcinoma", "Esophagogastric Adenocarcinoma",
              "Esophagogastric Cancer", "Gastric Adenocarcinoma", "HER2-positive Gastric Cancer"]:
    res = q("copyNumberAlterations", {"hugoSymbol": "ERBB2", "copyNameAlterationType": "AMPLIFICATION", "tumorType": tumor})
    if "0 L1/2" not in res:
        print(f"  *** FOUND: tumor='{tumor}':", res)
    else:
        print(f"  tumor='{tumor}':", res)

# TMB-High / Solid Tumor (expected: Pembrolizumab)
print("\nBENCH-023 TMB-High / Solid Tumor")
for alt, tumor in [("TMB-H", ""), ("TMB-H", "All Solid Tumors"), ("Tumor Mutational Burden-High", "Solid Tumor"),
                   ("High", "Solid Tumor"), ("TMB", "Solid Tumor"), ("TMB-High", "")]:
    params = {"alteration": alt}
    if tumor:
        params["tumorType"] = tumor
    print(f"  alt='{alt}' tumor='{tumor}':", q("mutations/byProteinChange", params))

# PIK3CA / Breast Cancer (expected: Alpelisib+Fulvestrant)
print("\nBENCH-008 PIK3CA / Breast Cancer")
for alt in ["Oncogenic Mutations", "Gain-of-function Mutations", "Mutation"]:
    for tumor in ["Breast Cancer", "Breast Cancer (HR+)", "Invasive Breast Carcinoma"]:
        res = q("mutations/byProteinChange", {"hugoSymbol": "PIK3CA", "alteration": alt, "tumorType": tumor})
        if "0 L1/2" not in res:
            print(f"  *** FOUND alt='{alt}' tumor='{tumor}':", res)

# KIT / GIST (expected: Imatinib for Exon 11, Sunitinib for Exon 9)
print("\nBENCH-009 KIT Exon 11 / GIST")
for alt in ["Oncogenic Mutations", "Exon 11 mutations", "Exon 11 deletion", "Exon 11"]:
    print(f"  alt='{alt}':", q("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": alt, "tumorType": "Gastrointestinal Stromal Tumor"}))

print("\nBENCH-019 KIT Exon 9 / GIST")
for alt in ["Oncogenic Mutations", "Exon 9 mutations", "Exon 9 insertion", "Exon 9"]:
    print(f"  alt='{alt}':", q("mutations/byProteinChange", {"hugoSymbol": "KIT", "alteration": alt, "tumorType": "Gastrointestinal Stromal Tumor"}))
