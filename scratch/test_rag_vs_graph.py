import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from backend.evaluation.ablation_rag import run_rag_testuale, RAGRetriever
from backend.pipeline.graph import run_pipeline

def run_test(case_num, gene, variant, tumor_type, alteration_type, therapy_line):
    print(f"\n{'='*80}")
    print(f" CASO {case_num}: {gene} {variant} in {tumor_type}")
    print(f"{'='*80}")

    # 1. Recupero Chunk RAG Testuale
    print("\n--- [RAG TESTUALE] CHUNK RECUPERATI ---")
    retriever = RAGRetriever.get_instance(gene)
    query = f"Variant {variant} in gene {gene} for tumor {tumor_type}. What are the evidence levels, significances, and targeted drugs?"
    chunks = retriever.retrieve(query, top_k=15)
    for i, c in enumerate(chunks, 1):
        print(f"  Chunk {i}: {c}")

    # 2. Esecuzione RAG Testuale
    print("\n--- [RAG TESTUALE] REPORT ---")
    try:
        rag_report = run_rag_testuale(gene, variant, tumor_type, alteration_type, therapy_line)
        print(rag_report)
    except Exception as e:
        print(f"Error in RAG Testuale: {e}")
        rag_report = "ERROR"

    # 3. Esecuzione Full GraphRAG
    print("\n--- [FULL GRAPHRAG] STATO & REPORT ---")
    state = {
        "gene": gene,
        "variant": variant,
        "tumor_type": tumor_type,
        "alteration_type": alteration_type,
        "therapy_line": therapy_line
    }
    try:
        final_state = run_pipeline(state)
        graph_drugs = final_state.get("drug_candidates", [])
        graph_report = final_state.get("report", "")
        print("\nFarmaci Candidati (Grafo):", graph_drugs)
        print("\nReport Grafo:")
        print(graph_report)
    except Exception as e:
        print(f"Error in Full GraphRAG: {e}")
        graph_drugs = []
        graph_report = "ERROR"
    
    # Save to file for easy reading
    out = {
        "gene": gene, "variant": variant,
        "rag_chunks": chunks,
        "rag_report": rag_report,
        "graph_drugs": graph_drugs,
        "graph_report": graph_report
    }
    with open(PROJECT_ROOT / f"scratch/rag_vs_graph_case_{case_num}.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

def main():
    run_test(1, "EGFR", "T790M", "NSCLC", "point_mutation", "second-line")
    run_test(2, "ALK", "G1202R", "NSCLC", "point_mutation", "second-line")

if __name__ == "__main__":
    main()
