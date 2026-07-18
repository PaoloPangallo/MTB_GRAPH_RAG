"""
05_sweep_budget_contesto.py
===========================
Esperimento di efficienza di contesto per la tesi mtb-graphrag.

Domanda: come degrada il recupero dei fatti-gold al variare del budget di
contesto fornito al lettore? Il vantaggio del GraphRAG (~36 parole, recall
1,00) e' un artefatto del budget di 900 parole scelto per il confronto, o
regge anche concedendo al RAG testuale molto piu' contesto?

Metrica: RECALL DEI FATTI-GOLD nel contesto assemblato. E' deterministica e
non richiede il modello lettore, quindi lo sweep e' interamente offline e
riproducibile senza chiave Ollama.

Sistemi confrontati:
  * GraphRAG   -> contesto gia' minimo (~36 parole), recall 1,00, piatto.
  * RAG denso  -> all-MiniLM-L6-v2 (encoder generico).
  * RAG BM25   -> lessicale.
  * RAG ibrido -> 0.5*denso + 0.5*BM25 (min-max scaled).

Input (checkpoint gia' prodotti dallo script 01_sistemi_retrieval):
  * rag_corpus.pkl   -> DataFrame con colonne text, passage_id
  * corpus_emb.npy   -> embedding del corpus (all-MiniLM-L6-v2)
  * benchmark_multihop_qa.csv -> 169 domande multi-hop con gold_answer

Output:
  * context_budget_sweep.csv  -> recall e parole-di-contesto per sistema x budget
  * fig10_context_budget.png  -> figura a 2 pannelli (curva + efficienza)

Dipendenze: pandas, numpy, rank-bm25, sentence-transformers, scikit-learn,
matplotlib. Python 3.12.
"""
import re
import numpy as np, pandas as pd
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import minmax_scale
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------------
BUDGETS = [100, 150, 200, 300, 450, 600, 750, 900, 1100, 1400, 1800, 2400]
K       = 400   # profondita' della lista ordinata (copre i budget grandi)
EMB_MODEL_NAME = 'all-MiniLM-L6-v2'

C  = {'graphrag':'#1f5fa8', 'rag_bm25':'#c0532a', 'rag_hybrid':'#c99a12', 'rag_dense':'#9a9a9a'}
LB = {'graphrag':'GraphRAG', 'rag_bm25':'RAG BM25', 'rag_hybrid':'RAG ibrido', 'rag_dense':'RAG denso'}
SYSORD = ['graphrag', 'rag_bm25', 'rag_hybrid', 'rag_dense']

# Punto operativo del GraphRAG, misurato in results_raw.csv (budget=900):
# contesto medio 35,8 parole, recall dei fatti-gold = 1,00 (insensibile al budget).
GRAPH_WORDS  = 35.8
GRAPH_RECALL = 1.0

# ----------------------------------------------------------------------------
# Utilita'
# ----------------------------------------------------------------------------
def norm_name(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()

def tok(s):
    return [w for w in ''.join(c.lower() if c.isalnum() else ' ' for c in s).split() if len(w) > 1]

def gold_names_of(row):
    return [g.strip() for g in re.split(r'[|;,]', str(row['gold_answer'])) if g.strip()]

def packed_idxs(rk, budget, texts):
    """Replica pack_context: accumula passaggi finche' il budget e' saturo."""
    used = []; words = 0
    for i in rk:
        i = int(i); w = len(texts[i].split())
        if words + w > budget and used:
            break
        used.append(i); words += w
        if words >= budget:
            break
    return used, words

def gold_recall(used, gnames, texts):
    if not gnames:
        return np.nan
    ctxt = " ".join(norm_name(texts[i]) for i in used)
    return sum(1 for g in gnames if norm_name(g) in ctxt) / len(gnames)

def words_to_reach(sweep, sysname, thr):
    """Interpolazione lineare: parole necessarie per raggiungere una soglia di recall."""
    sub = sweep[sweep.system == sysname].sort_values('mean_ctx_words')
    xs = sub['mean_ctx_words'].values; ys = sub['retr_recall'].values
    if ys.max() < thr:
        return np.nan
    for j in range(1, len(xs)):
        if ys[j] >= thr:
            if ys[j] == ys[j-1]:
                return xs[j]
            frac = (thr - ys[j-1]) / (ys[j] - ys[j-1])
            return xs[j-1] + frac * (xs[j] - xs[j-1])
    return np.nan

# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def load_data():
    corpus = pd.read_pickle('rag_corpus.pkl')
    emb    = np.load('corpus_emb.npy')
    texts  = corpus['text'].tolist()
    bench  = pd.read_csv('benchmark_multihop_qa.csv')
    return texts, emb, bench

def rank_all(texts, emb, bench, emb_model):
    bm25 = BM25Okapi([tok(t) for t in texts])
    Q = emb_model.encode(bench['question'].tolist(), normalize_embeddings=True, batch_size=64)
    ranked = {'rag_dense': [], 'rag_bm25': [], 'rag_hybrid': []}
    for i in range(len(bench)):
        d = emb @ Q[i]
        b = bm25.get_scores(tok(bench['question'].iloc[i]))
        h = 0.5 * minmax_scale(d) + 0.5 * minmax_scale(b)
        ranked['rag_dense'].append(np.argsort(-d)[:K])
        ranked['rag_bm25'].append(np.argsort(-b)[:K])
        ranked['rag_hybrid'].append(np.argsort(-h)[:K])
    return ranked

def sweep_budget(texts, bench, ranked):
    golds = [gold_names_of(bench.iloc[i]) for i in range(len(bench))]
    rows = []
    for sysname in ['rag_dense', 'rag_bm25', 'rag_hybrid']:
        for B in BUDGETS:
            recs = []; wlist = []
            for i in range(len(bench)):
                used, words = packed_idxs(ranked[sysname][i], B, texts)
                recs.append(gold_recall(used, golds[i], texts)); wlist.append(words)
            rows.append(dict(system=sysname, budget=B,
                             retr_recall=np.nanmean(recs), mean_ctx_words=np.mean(wlist)))
    for B in BUDGETS:
        rows.append(dict(system='graphrag', budget=B,
                         retr_recall=GRAPH_RECALL, mean_ctx_words=GRAPH_WORDS))
    return pd.DataFrame(rows)

def make_figure(sweep, out='fig10_context_budget.png'):
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.5, 4.6))

    # Pannello a: recall vs parole di contesto (x log)
    for s in SYSORD:
        sub = sweep[sweep.system == s].sort_values('mean_ctx_words')
        if s == 'graphrag':
            axL.scatter([GRAPH_WORDS], [GRAPH_RECALL], color=C[s], s=70, zorder=5,
                        edgecolor='white', linewidth=1.0)
            axL.annotate('GraphRAG\n36 parole · recall 1,00', (GRAPH_WORDS, GRAPH_RECALL),
                         xytext=(60, 0.90), fontsize=8, color=C[s], fontweight='bold',
                         arrowprops=dict(arrowstyle='-', color=C[s], lw=0.8))
            axL.axhline(GRAPH_RECALL, color=C[s], ls=':', lw=1.0, alpha=0.6)
        else:
            axL.plot(sub['mean_ctx_words'], sub['retr_recall'], '-o', color=C[s],
                     label=LB[s], ms=4, lw=1.8)
    axL.set_xscale('log')
    axL.set_xlabel('Parole di contesto fornite al lettore (scala log)')
    axL.set_ylabel('Recall dei fatti-gold nel contesto')
    axL.set_ylim(0, 1.05)
    axL.axvline(900, color='0.5', ls='--', lw=1.0, alpha=0.7)
    axL.text(900, 0.03, ' budget tesi\n 900 parole', fontsize=7, color='0.4', ha='left')
    axL.legend(loc='center right', fontsize=8, frameon=False)

    # Pannello b: parole necessarie per soglia di recall (efficienza)
    thrs = [0.6, 0.7, 0.8]
    x = np.arange(len(thrs)); w = 0.2
    for k, s in enumerate(SYSORD):
        vals = [words_to_reach(sweep, s, t) for t in thrs]
        if s == 'graphrag':
            vals = [GRAPH_WORDS] * len(thrs)
        axR.bar(x + (k - 1.5) * w, [v if not np.isnan(v) else 0 for v in vals], w,
                color=C[s], label=LB[s])
        for xi, v in zip(x + (k - 1.5) * w, vals):
            if np.isnan(v):
                axR.text(xi, 40, 'mai', ha='center', va='bottom', fontsize=7,
                         color=C[s], rotation=90, fontweight='bold')
            else:
                axR.text(xi, v + 40, str(int(round(v))), ha='center', va='bottom',
                         fontsize=7, color=C[s])
    axR.set_xticks(x); axR.set_xticklabels([f'≥{int(t*100)}%' for t in thrs])
    axR.set_xlabel('Soglia di recall dei fatti-gold')
    axR.set_ylabel('Parole di contesto necessarie')
    axR.set_ylim(0, 820)
    axR.legend(loc='upper left', fontsize=8, frameon=False)

    fig.suptitle('Efficienza di contesto: recupero dei fatti al variare del budget',
                 fontsize=12, fontweight='bold', y=1.00)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches='tight')
    plt.close(fig)

def main():
    texts, emb, bench = load_data()
    emb_model = SentenceTransformer(EMB_MODEL_NAME)
    ranked = rank_all(texts, emb, bench, emb_model)
    sweep = sweep_budget(texts, bench, ranked)
    sweep.to_csv('context_budget_sweep.csv', index=False)
    make_figure(sweep)
    # riepilogo a terminale
    piv = sweep.pivot(index='budget', columns='system', values='retr_recall').round(3)
    print(piv[SYSORD])
    for thr in (0.6, 0.7, 0.8):
        d = {s: (round(words_to_reach(sweep, s, thr)) if not np.isnan(words_to_reach(sweep, s, thr)) else 'mai')
             for s in SYSORD}
        print(f"recall>={thr}: {d}")
    print("saved context_budget_sweep.csv, fig10_context_budget.png")

if __name__ == '__main__':
    main()
