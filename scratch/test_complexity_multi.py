import sys
import csv
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from langchain_core.messages import HumanMessage, SystemMessage
from backend.pipeline.llm import llm
from backend.pipeline.helpers import get_disease_keywords, get_mp_keyword, run_cypher
from backend.pipeline.cypher import CYPHER_PRE_MP, CYPHER_PRE_POINT
from backend.pipeline.agents.complexity_check import COMPLEXITY_SYSTEM
from backend.evaluation.run_benchmark import csv_row_to_state

BENCHMARK_CSV = PROJECT_ROOT / "mtb-graphrag" / "backend" / "benchmark" / "benchmark_papers_summary_30_v2.csv"

def get_user_msg(case_id, row):
    state = csv_row_to_state(row)
    alt_type = state["alteration_type"]
    disease_kws = get_disease_keywords(state["tumor_type"])
    
    if alt_type == "point_mutation":
        kb_data = run_cypher(CYPHER_PRE_POINT, {
            "gene": state["gene"],
            "variant": state["variant"],
            "disease_keywords": disease_kws,
        })
    else:
        mp_keyword = get_mp_keyword(alt_type, state["variant"])
        kb_data = run_cypher(CYPHER_PRE_MP, {
            "gene": state["gene"] or "",
            "mp_keyword": mp_keyword,
            "disease_keywords": disease_kws,
        })
        
    kb = kb_data[0] if kb_data else {"n_evidence": 0, "significances": [], "n_trials": 0}
    
    return (
        f"Gene: {state['gene']} | Variante: {state['variant']}\n"
        f"Tipo alterazione: {alt_type}\n"
        f"Tumore: {state['tumor_type']} | Linea: {state['therapy_line']}\n"
        f"--- Dati KB ---\n"
        f"Evidenze A/B: {kb.get('n_evidence', 0)}\n"
        f"Significance: {kb.get('significances', [])}\n"
        f"Trial attivi: {kb.get('n_trials', 0)}"
    )

def main():
    with open(BENCHMARK_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        benchmark_rows = {row["case_id"]: row for row in reader}
        
    for case_id in ["BENCH-010", "BENCH-029"]:
        print(f"\n=====================================")
        print(f"  TEST ISOLATO PER {case_id} (30 ITERAZIONI)")
        print(f"=====================================")
        
        row = benchmark_rows[case_id]
        user_msg = get_user_msg(case_id, row)
        print("INPUT:")
        print(user_msg)
        print("-------------------------------------")
        
        results = []
        for i in range(1, 31):
            try:
                response = llm.invoke([SystemMessage(content=COMPLEXITY_SYSTEM), HumanMessage(content=user_msg)])
                complexity = response.content.strip().lower()
                print(f"  Run {i:2d}/30: {complexity}")
                results.append(complexity)
            except Exception as e:
                print(f"  Run {i:2d}/30 ERROR: {e}")
                results.append("ERROR")
                
        print("\n--- RISULTATI ---")
        print(f"Risultati: {results}")
        print(f"Unici: {list(set(results))}")
        print(f"Frequenze: {{val: results.count(val) for val in set(results)}}")

if __name__ == "__main__":
    main()
