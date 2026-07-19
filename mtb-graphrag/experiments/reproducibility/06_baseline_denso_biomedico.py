"""
06_baseline_denso_biomedico.py
==============================
Esperimento "baseline denso biomedico" per la tesi mtb-graphrag (Priorità 1).

Domanda di ricerca
------------------
Il RAG denso con encoder GENERICO (all-MiniLM-L6-v2) resta bloccato a una
recall dei fatti-gold molto bassa (0,14 -> 0,39 su tutto lo sweep di budget),
molto sotto BM25/ibrido e lontanissimo dal tetto del GraphRAG (1,00). La
domanda: il divario e' colpa dell'ENCODER (vocabolario generico, non
biomedico) o e' un limite strutturale del retrieval dense su questo corpus?

Per rispondere si sostituisce l'encoder generico con encoder di DOMINIO e si
ripete la STESSA metrica (recall dei fatti-gold, deterministica, offline):

  * RAG denso generico   -> all-MiniLM-L6-v2                (incumbent, 384-dim)
  * RAG denso biomedico  -> pritamdeka/S-PubMedBert-MS-MARCO(768-dim, retrieval-tuned)
  * RAG denso biomedico  -> microsoft/BiomedNLP-BiomedBERT  (raw MLM, mean-pool)
                            [opzionale: separa "dominio" da "tuning retrieval"]

Confronto con i sistemi gia' misurati nello sweep (context_budget_sweep.csv):
GraphRAG (1,00 piatto), BM25, ibrido.

Metrica: RECALL DEI FATTI-GOLD nel contesto assemblato, identica allo
script 05_sweep_budget_contesto.py. Nessun lettore, nessuna chiave Ollama.

Input (checkpoint gia' prodotti):
  * rag_corpus.pkl              -> DataFrame con colonne text, passage_id
  * corpus_emb.npy              -> embedding all-MiniLM-L6-v2 (incumbent)
  * benchmark_multihop_qa.csv   -> 169 domande multi-hop con gold_answer
  * context_budget_sweep.csv    -> sweep gia' calcolato per graphrag/bm25/ibrido/denso-minilm

Output:
  * biomedical_dense_sweep.csv  -> recall per (sistema x budget), 5 sistemi
  * fig11_biomedical_dense.png  -> figura a 2 pannelli (curva + barre a budget 900)

Dipendenze: pandas, numpy, sentence-transformers, transformers, torch,
matplotlib. Python 3.12. Gli embedding del corpus vengono ricalcolati se non
sono gia' su disco (operazione lenta su CPU: ~35-85 min a modello).
"""
import os, re, time
import numpy as np, pandas as pd
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------------
BUDGETS = [100, 150, 200, 300, 450, 600, 750, 900, 1100, 1400, 1800, 2400]
K       = 400
GRAPH_WORDS, GRAPH_RECALL = 35.8, 1.0   # punto operativo GraphRAG (results_raw.csv)

EMB_MINILM   = 'corpus_emb.npy'                       # incumbent generico
EMB_MSMARCO  = 'corpus_emb_pubmedbert_msmarco.npy'    # biomedico retrieval-tuned
EMB_RAW      = 'corpus_emb_pubmedbert_raw.npy'        # biomedico MLM grezzo (opzionale)
MODEL_MSMARCO = 'pritamdeka/S-PubMedBert-MS-MARCO'
MODEL_RAW     = 'microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext'

C  = {'graphrag':'#1f5fa8', 'rag_bm25':'#c0532a', 'rag_hybrid':'#c99a12',
      'rag_dense_minilm':'#9a9a9a', 'rag_dense_biomed':'#4a9e6f',
      'rag_dense_biomed_raw':'#b07fd0'}
LB = {'graphrag':'GraphRAG', 'rag_bm25':'RAG BM25', 'rag_hybrid':'RAG ibrido',
      'rag_dense_minilm':'RAG denso (all-MiniLM)',
      'rag_dense_biomed':'RAG denso (PubMedBERT-MS)',
      'rag_dense_biomed_raw':'RAG denso (PubMedBERT grezzo)'}

# ----------------------------------------------------------------------------
# Metrica (identica a 05_sweep_budget_contesto.py)
# ----------------------------------------------------------------------------
def norm_name(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()

def gold_names_of(row):
    return [g.strip() for g in re.split(r'[|;,]', str(row['gold_answer'])) if g.strip()]

def packed_idxs(rk, budget, texts):
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

def l2norm(M):
    n = np.linalg.norm(M, axis=1, keepdims=True); n[n == 0] = 1
    return (M / n).astype(np.float32)

# ----------------------------------------------------------------------------
# Codifica del corpus (ricalcolata solo se manca il .npy)
# ----------------------------------------------------------------------------
def encode_corpus_st(texts, model_name, out_path, max_seq=256, batch=128):
    """Encoder sentence-transformers (S-PubMedBert-MS-MARCO)."""
    if os.path.exists(out_path):
        return np.load(out_path)
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(model_name); m.max_seq_length = max_seq
    embs = []; t0 = time.time()
    for s in range(0, len(texts), 2000):
        chunk = texts[s:s+2000]
        v = m.encode(chunk, normalize_embeddings=True, batch_size=batch)
        embs.append(np.asarray(v, dtype=np.float32))
        print(f"[{s+len(chunk)}/{len(texts)}] {int(time.time()-t0)}s", flush=True)
    E = np.vstack(embs); np.save(out_path, E)
    return E

def encode_corpus_raw(texts, model_name, out_path, max_seq=256, batch=128):
    """Encoder MLM grezzo con mean-pooling (BiomedBERT abstract-fulltext)."""
    if os.path.exists(out_path):
        return np.load(out_path)
    import torch
    from transformers import AutoTokenizer, AutoModel
    torch.set_num_threads(8)
    tok = AutoTokenizer.from_pretrained(model_name)
    mdl = AutoModel.from_pretrained(model_name); mdl.eval()
    def meanpool(out, mask):
        m = mask.unsqueeze(-1).float()
        return (out.last_hidden_state * m).sum(1) / m.sum(1).clamp(min=1e-9)
    embs = []; t0 = time.time()
    with torch.no_grad():
        for s in range(0, len(texts), batch):
            b = texts[s:s+batch]
            enc = tok(b, padding=True, truncation=True, max_length=max_seq, return_tensors='pt')
            v = meanpool(mdl(**enc), enc['attention_mask'])
            v = torch.nn.functional.normalize(v, p=2, dim=1)
            embs.append(v.cpu().numpy().astype(np.float32))
    E = np.vstack(embs); np.save(out_path, E)
    return E

# ----------------------------------------------------------------------------
# Liste ordinate + sweep per un sistema denso
# ----------------------------------------------------------------------------
def dense_sweep(sysname, emb, Q, texts, golds, bench):
    embn = l2norm(emb)
    ranked = [np.argsort(-(embn @ Q[i]))[:K] for i in range(len(bench))]
    rows = []
    for B in BUDGETS:
        recs = []; wl = []
        for i in range(len(bench)):
            used, words = packed_idxs(ranked[i], B, texts)
            recs.append(gold_recall(used, golds[i], texts)); wl.append(words)
        rows.append(dict(system=sysname, budget=B,
                         retr_recall=np.nanmean(recs), mean_ctx_words=np.mean(wl)))
    return pd.DataFrame(rows)

def words_to_reach(df, sysname, thr):
    sub = df[df.system == sysname].sort_values('mean_ctx_words')
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
# Figura
# ----------------------------------------------------------------------------
def make_figure(full, out='fig11_biomedical_dense.png', with_raw=False):
    sysord = ['graphrag','rag_bm25','rag_hybrid','rag_dense_minilm','rag_dense_biomed']
    if with_raw:
        sysord.append('rag_dense_biomed_raw')
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(11.8, 4.7))

    for s in sysord:
        sub = full[full.system == s].sort_values('mean_ctx_words')
        if s == 'graphrag':
            axL.scatter([GRAPH_WORDS], [GRAPH_RECALL], color=C[s], s=75, zorder=6,
                        edgecolor='white', linewidth=1.0)
            axL.annotate('GraphRAG\n36 parole · recall 1,00', (GRAPH_WORDS, GRAPH_RECALL),
                         xytext=(70, 0.905), fontsize=8, color=C[s], fontweight='bold',
                         arrowprops=dict(arrowstyle='-', color=C[s], lw=0.8))
            axL.axhline(GRAPH_RECALL, color=C[s], ls=':', lw=1.0, alpha=0.6)
        else:
            lw = 2.2 if s == 'rag_dense_biomed' else 1.7
            axL.plot(sub['mean_ctx_words'], sub['retr_recall'], '-o', color=C[s],
                     label=LB[s], ms=4, lw=lw)
    axL.set_xscale('log')
    axL.set_xlabel('Parole di contesto fornite al lettore (scala log)')
    axL.set_ylabel('Recall dei fatti-gold nel contesto')
    axL.set_ylim(0, 1.05)
    axL.axvline(900, color='0.5', ls='--', lw=1.0, alpha=0.7)
    axL.text(920, 0.90, 'budget tesi\n900 parole', fontsize=7, color='0.4', ha='left')
    axL.legend(loc='lower right', fontsize=7.5, frameon=False)

    b900 = full[full.budget == 900].set_index('system')['retr_recall']
    bars = ['graphrag','rag_bm25','rag_hybrid','rag_dense_biomed','rag_dense_minilm']
    if with_raw:
        bars.insert(4, 'rag_dense_biomed_raw')
    vals = [b900[s] for s in bars]; xpos = np.arange(len(bars)); cols = [C[s] for s in bars]
    axR.bar(xpos, vals, color=cols, width=0.66)
    for xi, v in zip(xpos, vals):
        axR.text(xi, v + 0.015, f'{v:.3f}'.replace('.', ','), ha='center', va='bottom', fontsize=8)
    axR.annotate('', xy=(3, b900['rag_dense_biomed']), xytext=(len(bars)-1, b900['rag_dense_minilm']),
                 arrowprops=dict(arrowstyle='->', color='#4a9e6f', lw=1.6))
    lbls = {'graphrag':'GraphRAG','rag_bm25':'BM25','rag_hybrid':'ibrido',
            'rag_dense_biomed':'denso\nPubMedBERT','rag_dense_minilm':'denso\nall-MiniLM',
            'rag_dense_biomed_raw':'denso\nPubMedBERT\ngrezzo'}
    axR.set_xticks(xpos); axR.set_xticklabels([lbls[s] for s in bars], fontsize=7.5)
    axR.set_ylabel('Recall dei fatti-gold (budget 900 parole)')
    axR.set_ylim(0, 1.08)

    fig.suptitle('Encoder biomedico vs generico: quanto recupera il RAG denso',
                 fontsize=12, fontweight='bold', y=1.00)
    fig.tight_layout()
    fig.savefig(out, dpi=300, bbox_inches='tight')
    plt.close(fig)

# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def main():
    corpus = pd.read_pickle('rag_corpus.pkl')
    texts  = corpus['text'].tolist()
    bench  = pd.read_csv('benchmark_multihop_qa.csv')
    golds  = [gold_names_of(bench.iloc[i]) for i in range(len(bench))]
    queries = bench['question'].tolist()

    # sweep incumbent gia' calcolato (graphrag/bm25/ibrido/denso-minilm)
    inc = pd.read_csv('context_budget_sweep.csv')
    allm = inc[inc.system == 'rag_dense'].copy(); allm['system'] = 'rag_dense_minilm'
    others = inc[inc.system != 'rag_dense'].copy()

    # --- encoder biomedico retrieval-tuned ---
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(MODEL_MSMARCO); m.max_seq_length = 256
    emb_bio = encode_corpus_st(texts, MODEL_MSMARCO, EMB_MSMARCO)
    Qbio = np.asarray(m.encode(queries, normalize_embeddings=True, batch_size=64), dtype=np.float32)
    sweep_bio = dense_sweep('rag_dense_biomed', emb_bio, Qbio, texts, golds, bench)

    parts = [others, allm, sweep_bio]

    # --- encoder biomedico MLM grezzo (opzionale, se il .npy esiste) ---
    with_raw = os.path.exists(EMB_RAW)
    if with_raw:
        import torch
        from transformers import AutoTokenizer, AutoModel
        tok = AutoTokenizer.from_pretrained(MODEL_RAW)
        mdl = AutoModel.from_pretrained(MODEL_RAW); mdl.eval()
        def meanpool(out, mask):
            mm = mask.unsqueeze(-1).float()
            return (out.last_hidden_state * mm).sum(1) / mm.sum(1).clamp(min=1e-9)
        with torch.no_grad():
            enc = tok(queries, padding=True, truncation=True, max_length=256, return_tensors='pt')
            Qraw = torch.nn.functional.normalize(meanpool(mdl(**enc), enc['attention_mask']), p=2, dim=1)
            Qraw = Qraw.cpu().numpy().astype(np.float32)
        emb_raw = np.load(EMB_RAW)
        sweep_raw = dense_sweep('rag_dense_biomed_raw', emb_raw, Qraw, texts, golds, bench)
        parts.append(sweep_raw)

    full = pd.concat(parts, ignore_index=True)
    full.to_csv('biomedical_dense_sweep.csv', index=False)
    make_figure(full, with_raw=with_raw)

    piv = full.pivot(index='budget', columns='system', values='retr_recall').round(3)
    print(piv.to_string())

if __name__ == '__main__':
    main()
