import runpy, pandas as pd, numpy as np
# carico definizioni dallo script ufficiale senza eseguirne il main
ns = runpy.run_path('05_sweep_budget_contesto.py', run_name='__lib__')
load_data=ns['load_data']; rank_all=ns['rank_all']; sweep_budget=ns['sweep_budget']
from sentence_transformers import SentenceTransformer
corpus=pd.read_pickle('rag_corpus.pkl'); emb=np.load('corpus_emb.npy')
texts=corpus['text'].tolist()
bench=pd.read_csv('benchmark_multihop_1k.csv')
print("corpus",len(texts),"emb",emb.shape,"bench",len(bench),flush=True)
m=SentenceTransformer(ns['EMB_MODEL_NAME'])
ranked=rank_all(texts,emb,bench,m)
sweep=sweep_budget(texts,bench,ranked)
sweep.to_csv('context_budget_sweep_1k.csv',index=False)
print(sweep.pivot(index='budget',columns='system',values='retr_recall').round(3).to_string(),flush=True)
print("SALVATO context_budget_sweep_1k.csv",flush=True)
