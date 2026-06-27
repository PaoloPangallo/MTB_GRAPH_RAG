import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "mtb-graphrag"))

from backend.evaluation.ablation_rag import RAGRetriever

def verify_chunk():
    print("Inizializzo l'indice per ALK...")
    retriever = RAGRetriever.get_instance("ALK")
    
    print(f"\nIndice creato. Totale chunk: {len(retriever.chunks)}")
    
    found_chunks = []
    for chunk in retriever.chunks:
        chunk_lower = chunk.lower()
        if "g1202r" in chunk_lower and "lorlatinib" in chunk_lower:
            found_chunks.append(chunk)
            
    if found_chunks:
        print("\n[ESITO: PRESENTE] Il RAG aveva questi chunk nella sua knowledge base, ma non li ha estratti nel top-15:")
        for idx, c in enumerate(found_chunks, 1):
            print(f"  {idx}) {c}")
    else:
        print("\n[ESITO: ASSENTE] Il RAG NON conteneva nessun chunk che associasse G1202R a Lorlatinib.")

if __name__ == "__main__":
    verify_chunk()
