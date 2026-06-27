import sys
import csv
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from langchain_core.messages import HumanMessage, SystemMessage
from backend.pipeline.llm import llm
from backend.pipeline.helpers import get_disease_keywords, get_mp_keyword, run_cypher
from backend.pipeline.cypher import CYPHER_PRE_MP
from backend.pipeline.agents.complexity_check import COMPLEXITY_SYSTEM
from backend.evaluation.run_benchmark import csv_row_to_state

BENCHMARK_CSV = PROJECT_ROOT / "mtb-graphrag" / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"

def main():
    print("=== TEST ISOLATO COMPLETTO PER BENCH-010 ===")
    
    # 1. Carica il caso BENCH-010 dal benchmark
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["case_id"] == "BENCH-010":
                bench_row = row
                break
                
    state = csv_row_to_state(bench_row)
    alt_type = state["alteration_type"]
    disease_kws = get_disease_keywords(state["tumor_type"])
    mp_keyword = get_mp_keyword(alt_type, state["variant"])
    
    # Esegui la query per comporre l'input dell'LLM
    kb_data = run_cypher(CYPHER_PRE_MP, {
        "gene": state["gene"] or "",
        "mp_keyword": mp_keyword,
        "disease_keywords": disease_kws,
    })
    kb = kb_data[0] if kb_data else {"n_evidence": 0, "significances": [], "n_trials": 0}
    
    user_msg = (
        f"Gene: {state['gene']} | Variante: {state['variant']}\n"
        f"Tipo alterazione: {alt_type}\n"
        f"Tumore: {state['tumor_type']} | Linea: {state['therapy_line']}\n"
        f"--- Dati KB ---\n"
        f"Evidenze A/B: {kb.get('n_evidence', 0)}\n"
        f"Significance: {kb.get('significances', [])}\n"
        f"Trial attivi: {kb.get('n_trials', 0)}"
    )
    
    print("\n--- INPUT LLM FISSO ---")
    print(user_msg)
    print("-----------------------\n")
    
    print("Esecuzione di 10 chiamate consecutive all'LLM...")
    results = []
    for i in range(1, 11):
        try:
            response = llm.invoke([SystemMessage(content=COMPLEXITY_SYSTEM), HumanMessage(content=user_msg)])
            complexity = response.content.strip().lower()
            print(f"  Chiamata {i:2d}/10: {complexity}")
            results.append(complexity)
        except Exception as e:
            print(f"  Chiamata {i:2d}/10 Fallita: {e}")
            results.append("ERROR")
            
    print("\n--- RIEPILOGO OUTPUT ---")
    print(f"Risultati ottenuti: {results}")
    print(f"Valori unici: {list(set(results))}")
    if len(set(results)) > 1:
        print("La singola chiamata LLM ha dato risultati DIVERSI (Non-determinismo confermato).")
    else:
        print("La singola chiamata LLM ha dato sempre lo stesso risultato.")

if __name__ == "__main__":
    main()
