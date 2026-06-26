"""
test_enricher_fix.py — Smoke test del nuovo ablation_enricher su 3 casi campione.
Uno per tipo di fix: Tipo A (tumor alias), Tipo B (fallback Oncogenic Mutations), Tipo C (fusion).
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))
from backend.evaluation.ablation_enricher import run_enricher_only

tests = [
    # (case_id, gene, variant, tumor_type (già mappato da TUMOR_MAP), alteration_type, expected_drug)
    ("BENCH-014 [Tipo A: tumor alias]",
     "ABL1", "T315I", "Chronic Myeloid Leukemia", "point_mutation", "Ponatinib"),

    ("BENCH-005 [Tipo B: Oncogenic Mutations fallback]",
     "BRCA1", "Mutation", "Ovarian Cancer", "point_mutation", "Olaparib"),

    ("BENCH-006 [Tipo C: fusion BCR-ABL1]",
     "ABL1", "BCR-ABL1 Fusion", "Chronic Myeloid Leukemia", "fusion", "Imatinib"),

    ("BENCH-015 [Tipo C: fusion self RET]",
     "RET", "Fusion", "Lung Adenocarcinoma", "fusion", "Selpercatinib"),

    ("BENCH-017 [Tipo B: biomarker MSI-H]",
     "MSI", "MSI-High", "Colorectal Cancer", "biomarker", "Pembrolizumab"),
]

print("=" * 70)
print("SMOKE TEST — ablation_enricher v2")
print("=" * 70)

for label, gene, variant, tumor, alt_type, expected in tests:
    print(f"\n--- {label} ---")
    print(f"  gene={gene} | variant={variant} | tumor={tumor} | alt={alt_type}")
    print(f"  expected_drug: {expected}")
    try:
        report = run_enricher_only(gene, variant, tumor, alt_type, "first-line")
        found = expected.lower() in report.lower()
        lines = report.strip().split("\n")
        print(f"  report (prime 3 righe): {' / '.join(l.strip() for l in lines[:3] if l.strip())}")
        print(f"  >>> DAC ({expected}): {'PASS' if found else 'FAIL'}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n" + "=" * 70)
print("Test completati.")
