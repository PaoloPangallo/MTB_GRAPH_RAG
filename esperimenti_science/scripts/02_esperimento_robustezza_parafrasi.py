"""
02_esperimento_robustezza_parafrasi.py
======================================
Esperimento 1.1 - Robustezza alla riformulazione clinica.

Rigenera le metriche di robustezza confrontando:
  * GraphRAG con router a parole chiave (route_pattern)  vs
  * GraphRAG con router semantico a intenti (etichette LLM)
  * RAG denso / BM25 / ibrido
sulle domande ORIGINALI e sulle loro PARAFRASI cliniche.

Input:
  benchmark_multihop_qa.csv              (169 domande originali)
  benchmark_multihop_qa_paraphrased.csv  (169 parafrasi, col. 'question', 'question_original', 'lex_jaccard')

Le etichette d'intento delle parafrasi sono prodotte da un classificatore LLM
(route_llm). Il router non vede mai gold ne' corpus: classifica solo l'intento
della domanda -> confronto equo.

Output:
  results_paraphrase_keywordrouter.csv
  results_paraphrase_graphrag_routed.csv
  robustezza_parafrasi_summary.csv
"""
import pandas as pd, numpy as np
from importlib import import_module
S = import_module("01_sistemi_retrieval")
G, corpus, emb, texts, pids = S.load_checkpoints()
# ... (riassegna i globali del modulo S: G, corpus, emb, texts, pids, indici, bm25, emb_model)

BENCH      = pd.read_csv("benchmark_multihop_qa.csv")
BENCH_PARA = pd.read_csv("benchmark_multihop_qa_paraphrased.csv")

QTYPE2ROUTE = {
    "drug_to_gene_cdx":"DRUG_TO_GENE_CDX", "gene_to_trialdrug":"GENE_TO_TRIALDRUG",
    "variant_to_drug":"VARIANT_TO_DRUG", "gene_to_disease":"GENE_TO_DISEASE",
    "gene_to_drug":"GENE_TO_DRUG", "gene_evidence_trial_bridge":"GENE_EVIDENCE_TRIAL_BRIDGE",
    "gene_to_cdx":"GENE_TO_CDX",
}

def run_condition(bench, use_router):
    """use_router in {'keyword','semantic'}. Ritorna DataFrame per-domanda."""
    rows=[]
    for _,r in bench.iterrows():
        q=r["question"]
        if use_router=="keyword":
            ctx,vis,_=S.graph_retrieve(q)                       # route_pattern interno
        else:
            intent=S.route_llm(q)                               # etichetta LLM
            ctx,vis,_=S.graph_retrieve_routed(q,intent)
        pred=S.reader_answer(q,ctx)
        sc=S.score_answer(pred, str(r["gold_answer"]).split("|"))
        rows.append(dict(qid=r["qid"], hop_count=r["hop_count"],
                         f1=sc["f1"], exact=sc["exact"], ctx_words=len(ctx.split()), pred=pred))
    return pd.DataFrame(rows)

if __name__=="__main__":
    kw  = run_condition(BENCH_PARA, "keyword");  kw.to_csv("results_paraphrase_keywordrouter.csv", index=False)
    sem = run_condition(BENCH_PARA, "semantic"); sem.to_csv("results_paraphrase_graphrag_routed.csv", index=False)
    print("F1 keyword-router (parafrasi):", round(kw.f1.mean(),3))
    print("F1 semantic-router (parafrasi):", round(sem.f1.mean(),3))
