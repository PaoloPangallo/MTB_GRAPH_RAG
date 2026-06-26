import sys
import os
from pathlib import Path

# Configura ambiente per secondo LLM
os.environ["LLM_PIPELINE"] = "qwen3-coder-next"
os.environ["OLLAMA_BASE_URL"] = "https://api.ollama.com"

# Path import backend
sys.path.append(str(Path(__file__).resolve().parents[1] / "mtb-graphrag"))

from backend.pipeline.graph import run_pipeline
from backend.evaluation.run_benchmark import csv_row_to_state
import csv

BENCHMARK_CSV = Path(__file__).resolve().parents[1] / "mtb-graphrag" / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"

# Carichiamo il benchmark per trovare BENCH-021
with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    benchmark_rows = {row["case_id"]: row for row in reader}

row = benchmark_rows.get("BENCH-025")
if not row:
    print("Caso BENCH-025 non trovato nel CSV!")
    sys.exit(1)

print("="*60)
print("ESECUZIONE INTEGRATION TEST SU BENCH-025 (GraphRAG + Filtro)")
print("="*60)

state = csv_row_to_state(row)
print(f"Input: Gene={state.get('gene')}, Variant={state.get('variant')}, Tumor={state.get('tumor_type')}")

# Esegui la pipeline
final_state = run_pipeline(state)

print("\n--- REPORT GENERATO E FILTRATO ---")
print(final_state["report"])
print("\n--- STATISTICHE FILTRO ---")
print(f"Cited PMIDs (verificati nel KG): {final_state.get('cited_pmids')}")
print(f"PMID rimossi dal testo (non verificati): {final_state.get('pmid_rimossi_dal_testo')}")
print("="*60)
