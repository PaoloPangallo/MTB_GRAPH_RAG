"""
Estrae i report del full GraphRAG per i 7 casi con PMID fuori KB.
Legge da: ablation_graphrag_results.json (il full GraphRAG dall'ablation)
         e benchmark_results.json (risultati benchmark originali)
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RESULTS_DIR = Path(r"C:\Users\paolo\Desktop\IspezioneDatasetTesi\mtb-graphrag\backend\evaluation\results")

TARGET_CASES = ["BENCH-006", "BENCH-013", "BENCH-014", "BENCH-017", "BENCH-023", "BENCH-024", "BENCH-030"]

# Try multiple result files
files_to_check = [
    ("ablation_graphrag_results.json", "Ablation GraphRAG (full)"),
    ("benchmark_results.json", "Benchmark results"),
]

for filename, label in files_to_check:
    fpath = RESULTS_DIR / filename
    if not fpath.exists():
        print(f"[SKIP] {filename} non trovato")
        continue

    with open(fpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n{'═' * 80}")
    print(f"  FILE: {filename} ({label})")
    print(f"  Casi totali nel file: {len(data)}")
    print(f"{'═' * 80}")

    # Find target cases
    for case_id in TARGET_CASES:
        match = [c for c in data if c.get("case_id") == case_id]
        if not match:
            print(f"\n--- {case_id}: NON PRESENTE nel file ---")
            continue

        c = match[0]
        print(f"\n{'─' * 80}")
        print(f"  {case_id}")
        print(f"  Gene: {c.get('gene', 'N/A')} | Variant: {c.get('variant', 'N/A')} | Tumor: {c.get('tumor', c.get('tumor_type', 'N/A'))}")
        print(f"  Expected Drug: {c.get('expected_drug', 'N/A')}")
        print(f"  ESCAT Tier (output): {c.get('escat_tier', 'N/A')}")
        print(f"{'─' * 80}")

        report = c.get("report", "")
        if report:
            # Print full report
            print(f"  REPORT ({len(report)} chars):")
            print("  " + "─" * 40)
            for line in report.split("\n"):
                print(f"  {line}")
            print("  " + "─" * 40)
        else:
            print("  REPORT: (vuoto)")

        # Print any other relevant fields
        for key in sorted(c.keys()):
            if key not in ("case_id", "gene", "variant", "tumor", "tumor_type",
                           "expected_drug", "escat_tier", "report", "pmid"):
                val = c[key]
                if isinstance(val, str) and len(val) > 200:
                    val = val[:200] + "..."
                print(f"  {key}: {val}")
