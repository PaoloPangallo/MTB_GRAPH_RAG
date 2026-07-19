#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
08_profondita_salti.py — Strand E: scaling della profondità dei salti (deep-hop).

Misura, in funzione della profondità della catena di ragionamento (1..8 salti),
due metriche di recupero deterministiche e offline:

  (a) recall del fatto TERMINALE  : il nome dell'entità-obiettivo finale compare
                                     nel contesto recuperato?
  (b) chain-recall (completezza)  : quale frazione dei nomi-ponte intermedi
                                     compare nel contesto recuperato?

Confronta 4 sistemi: GraphRAG (traversata tipizzata) e tre RAG testuali/densi
(BM25, ibrido, denso MiniLM). Router = oracolo (ogni sistema riceve la domanda
gia' instradata sulla spina corretta), cosi' la profondita' e' l'unica variabile.

DESIGN: una singola "spina" tipizzata (Gene ->Variant ->MolecularProfile ->Evidence
->Drug ->CompanionDiagnostic ->Gene' ->Variant' ->MolecularProfile') viene ancorata
a ciascun gene che possiede un cammino canonico completo a profondita' 8, e
troncata a profondita' crescenti. Usando lo STESSO gene-ancora ad ogni profondita'
si isola l'effetto della profondita' dal confondimento con la scelta del gene.
La profondita' 3 (terminale = Evidence, priva di attributo 'name') e' esclusa.

Riproducibile: SEED=20240517, nessuna rete, nessun LLM. Legge i checkpoint:
  kb_graph.gpickle, rag_corpus.pkl, corpus_emb.npy, benchmark_deep_hops.csv
Produce: deep_hops_sweep.csv, fig13_profondita_salti.png, deep_hops_fanout.png
"""
import os, re, json, pickle
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from rank_bm25 import BM25Okapi
from sklearn.preprocessing import minmax_scale
from sentence_transformers import SentenceTransformer

SEED = 20240517
BUDGET_WORDS = 900
TOPK = 400
DEPTHS = [1, 2, 4, 5, 6, 7, 8]           # hop 3 (Evidence, senza nome) escluso
rng = np.random.default_rng(SEED)

# --- Spina tipizzata (relazione, direzione) e tipo-obiettivo di ogni salto ---
SPINE = [('HAS_VARIANT', '+'), ('IN_MOLECULAR_PROFILE', '+'), ('HAS_EVIDENCE', '+'),
         ('TARGETS_DRUG', '+'), ('HAS_COMPANION_DIAGNOSTIC', '+'), ('DIAGNOSES_GENE', '+'),
         ('HAS_VARIANT', '+'), ('IN_MOLECULAR_PROFILE', '+')]
STEP_TGT_TYPE = ['Variant', 'MolecularProfile', 'Evidence', 'Drug',
                 'CompanionDiagnostic', 'Gene', 'Variant', 'MolecularProfile']

# Connettivi italiani per la serializzazione dei cammini GraphRAG
REL_VERB = {
    ('HAS_VARIANT', '+'): "presenta la variante",
    ('IN_MOLECULAR_PROFILE', '+'): "nel profilo molecolare",
    ('HAS_EVIDENCE', '+'): "con evidenza clinica",
    ('TARGETS_DRUG', '+'): "che supporta il farmaco",
    ('HAS_COMPANION_DIAGNOSTIC', '+'): "rilevato dal test diagnostico",
    ('DIAGNOSES_GENE', '+'): "che diagnostica il gene",
}

# ---------------------------------------------------------------- helpers
def norm_name(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()

def tok(s):
    return [w for w in ''.join(c.lower() if c.isalnum() else ' ' for c in s).split() if len(w) > 1]


def main():
    # ----------------------------------------------------------- load KB
    print("[1/6] Carico il grafo di conoscenza...")
    G = nx.read_gpickle('kb_graph.gpickle') if hasattr(nx, 'read_gpickle') \
        else pickle.load(open('kb_graph.gpickle', 'rb'))

    def nm(n):
        return G.nodes[n].get('name')

    def ntype(n):
        dd = G.nodes[n]; return dd.get('type') or dd.get('label') or '?'

    # adiacenza tipizzata: nodo -> relazione -> {vicini}
    from collections import defaultdict
    out_adj = defaultdict(lambda: defaultdict(set))
    in_adj = defaultdict(lambda: defaultdict(set))
    for u, v, d in G.edges(data=True):
        r = d.get('rel')
        out_adj[u][r].add(v)
        in_adj[v][r].add(u)

    gene_nodes = [n for n in G.nodes if ntype(n) == 'Gene']
    print(f"      nodi={G.number_of_nodes()} archi={G.number_of_edges()} geni={len(gene_nodes)}")

    # ----------------------------------------------------------- corpus + RAG
    print("[2/6] Carico corpus ed indici RAG...")
    cdf = pickle.load(open('rag_corpus.pkl', 'rb'))
    texts = cdf['text'].tolist()
    bm25 = BM25Okapi([tok(t) for t in texts])
    emb_corpus = np.load('corpus_emb.npy')            # MiniLM 384d, normalizzato
    mini = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

    # ----------------------------------------------------------- benchmark
    print("[3/6] Carico il benchmark annidato...")
    bdf = pd.read_csv('benchmark_deep_hops.csv')
    print(f"      {len(bdf)} domande, {bdf.anchor_id.nunique()} ancore, profondita' {sorted(bdf.depth.unique())}")

    # ricodifica embedding delle domande (deterministico)
    q_texts = bdf['question'].tolist()
    q_emb = mini.encode(q_texts, normalize_embeddings=True, batch_size=128, show_progress_bar=False)

    # ----------------------------------------------------- GraphRAG traversal
    def enum_paths(anchor, k, cap=4000):
        paths_k = [(anchor,)]
        for i in range(k):
            rel, dr = SPINE[i]; adj = out_adj if dr == '+' else in_adj
            nxt = []
            for pth in paths_k:
                for t in adj[pth[-1]].get(rel, ()):
                    if t in pth:
                        continue
                    nxt.append(pth + (t,))
                    if len(nxt) >= cap:
                        break
                if len(nxt) >= cap:
                    break
            paths_k = nxt
            if not paths_k:
                return []
        return paths_k

    def serialize_path(pth):
        parts = [f"Il gene {nm(pth[0])}"]
        for i in range(1, len(pth)):
            rel, dr = SPINE[i - 1]
            label = nm(pth[i]) or "(evidenza)"
            parts.append(f"{REL_VERB.get((rel, dr), '->')} {label}")
        return " ".join(parts) + "."

    def graph_ctx_deep(anchor, k, budget=BUDGET_WORDS):
        pk = enum_paths(anchor, k)
        seen, strs = set(), []
        for pth in sorted(pk):
            s = serialize_path(pth)
            if s not in seen:
                seen.add(s); strs.append(s)
        ctx, words = [], 0
        for s in strs:
            w = len(s.split())
            if words + w > budget and ctx:
                break
            ctx.append(s); words += w
        return ctx, len(pk)

    # ------------------------------------------------------------- RAG ctx
    def rag_ctx(qi, system, budget=BUDGET_WORDS):
        q = q_texts[qi]
        bscores = bm25.get_scores(tok(q))
        if system == 'rag_bm25':
            order = np.argsort(-bscores)[:TOPK]
        else:
            dscores = emb_corpus @ q_emb[qi]
            if system == 'rag_dense':
                order = np.argsort(-dscores)[:TOPK]
            else:  # hybrid
                order = np.argsort(-(0.5 * minmax_scale(dscores) + 0.5 * minmax_scale(bscores)))[:TOPK]
        ctx, words = [], 0
        for i in order:
            t = texts[int(i)]; w = len(t.split())
            if words + w > budget and ctx:
                break
            ctx.append(t); words += w
            if words >= budget:
                break
        return ctx

    def contains(name_str, blob):
        n = norm_name(name_str)
        return bool(n) and n in blob

    # -------------------------------------------------- valutazione completa
    print("[4/6] Valuto GraphRAG e i 3 sistemi RAG (recall terminale + chain-recall)...")
    def eval_all():
        cols = {}
        # GraphRAG
        gt, gc = [], []
        for _, r in bdf.iterrows():
            ctx, _ = graph_ctx_deep(r.anchor_id, int(r.depth))
            blob = " ".join(norm_name(x) for x in ctx)
            gt.append(1.0 if contains(r.gold_terminal, blob) else 0.0)
            br = json.loads(r.bridge_chain)
            gc.append(sum(contains(b, blob) for b in br) / len(br) if br else np.nan)
        cols['graphrag'] = (gt, gc)
        # RAG systems
        for s in ['rag_bm25', 'rag_hybrid', 'rag_dense']:
            tt, cc = [], []
            for qi, (_, r) in enumerate(bdf.iterrows()):
                ctx = rag_ctx(qi, s)
                blob = " ".join(norm_name(x) for x in ctx)
                tt.append(1.0 if contains(r.gold_terminal, blob) else 0.0)
                br = json.loads(r.bridge_chain)
                cc.append(sum(contains(b, blob) for b in br) / len(br) if br else np.nan)
            cols[s] = (tt, cc)
        return cols

    cols = eval_all()
    for s, (t, c) in cols.items():
        bdf[f'{s}_term'] = t
        bdf[f'{s}_chain'] = c

    # ------------------------------------------------------ sweep long-format
    rows = []
    for depth in DEPTHS:
        sub = bdf[bdf.depth == depth]
        for s in ['graphrag', 'rag_bm25', 'rag_hybrid', 'rag_dense']:
            term = sub[f'{s}_term'].mean()
            chain = sub[f'{s}_chain'].mean()
            rows.append(dict(system=s, depth=depth,
                             terminal_recall=round(float(term), 4),
                             chain_recall=(round(float(chain), 4) if not np.isnan(chain) else np.nan),
                             n_questions=len(sub)))
    sweep = pd.DataFrame(rows)
    sweep.to_csv('deep_hops_sweep.csv', index=False)
    print("      -> deep_hops_sweep.csv")

    # ------------------------------------------------ figura fan-out covariata
    print("[5/6] Figura covariata fan-out...")
    def name_witness_rows(u, v):
        un, vn = norm_name(nm(u) or ''), norm_name(nm(v) or '')
        if not un or not vn:
            return set()
        return {i for i in range(len(texts)) if un in norm_name(texts[i]) and vn in norm_name(texts[i])}

    # cammino canonico per ancora (DFS deterministico seed-shuffled)
    def succ(n, i):
        rel, dr = SPINE[i]; adj = out_adj if dr == '+' else in_adj
        return sorted(adj[n].get(rel, set()))

    def canonical_path(anchor):
        cache = {}
        def shuf(lst):
            key = tuple(lst)
            if key not in cache:
                idx = rng.permutation(len(lst)); cache[key] = [lst[j] for j in idx]
            return cache[key]
        def dfs(node, path, depth):
            if depth == 8:
                return path
            for nx_ in shuf(succ(node, depth)):
                if nx_ in path:
                    continue
                r = dfs(nx_, path + [nx_], depth + 1)
                if r:
                    return r
            return None
        return dfs(anchor, [anchor], 0)

    anchor_ids = sorted(bdf.anchor_id.unique())
    paths = {}
    for a in anchor_ids:
        p = canonical_path(a)
        if p:
            paths[a] = p
    cum = {k: [] for k in DEPTHS}
    for g, p in paths.items():
        needed = set()
        for hop in range(1, 9):
            w = name_witness_rows(p[hop - 1], p[hop])
            if w:
                needed.add(min(w))
            if hop in cum:
                cum[hop].append(len(needed))
    med = [np.median(cum[k]) for k in DEPTHS]
    mx = [np.max(cum[k]) for k in DEPTHS]
    fig, ax = plt.subplots(figsize=(5.2, 3.4))
    ax.plot(DEPTHS, med, 'o-', color='#1f5fa8', lw=1.8, label='mediana')
    ax.fill_between(DEPTHS, med, mx, color='#1f5fa8', alpha=0.12, label='fino al massimo')
    ax.set_xlabel('Profondita\' della catena (numero di salti)')
    ax.set_ylabel('Passaggi distinti\nche testimoniano la catena')
    ax.set_title('Quanti passaggi separati deve unire il RAG', fontsize=9)
    ax.set_xticks(DEPTHS); ax.legend(frameon=False, fontsize=7)
    fig.tight_layout(); fig.savefig('deep_hops_fanout.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    print("      -> deep_hops_fanout.png")

    # ------------------------------------------------------- figura principale
    print("[6/6] Figura principale a doppio pannello...")
    C = {'graphrag': '#1f5fa8', 'rag_bm25': '#c0532a', 'rag_hybrid': '#c99a12', 'rag_dense': '#9a9a9a'}
    LB = {'graphrag': 'GraphRAG', 'rag_bm25': 'RAG BM25', 'rag_hybrid': 'RAG ibrido', 'rag_dense': 'RAG denso'}
    sysord = ['graphrag', 'rag_bm25', 'rag_hybrid', 'rag_dense']
    OFF = {'a': {'graphrag': 0.0, 'rag_bm25': -0.045, 'rag_hybrid': 0.045, 'rag_dense': -0.02},
           'b': {'graphrag': 0.0, 'rag_bm25': 0.03, 'rag_hybrid': -0.055, 'rag_dense': 0.0}}
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.9))

    def panel(ax, col, title, letter, depths_filter=None):
        for s in sysord:
            d = sweep[sweep.system == s]
            if depths_filter is not None:
                d = d[d.depth.isin(depths_filter)]
            d = d.dropna(subset=[col])
            lw = 2.4 if s == 'graphrag' else 1.5
            z = 5 if s == 'graphrag' else 3
            ax.plot(d.depth, d[col], 'o-', color=C[s], lw=lw, ms=5 if s == 'graphrag' else 4, zorder=z)
            if len(d):
                xl, yl = d.depth.iloc[-1], d[col].iloc[-1]
                ax.annotate(LB[s], xy=(xl, yl), xytext=(6, OFF[letter][s] * 90),
                            textcoords='offset points', fontsize=6.8, color=C[s], va='center',
                            fontweight='bold' if s == 'graphrag' else 'normal')
        ax.set_xlabel('Profondita\' della catena (numero di salti)')
        ax.set_ylabel(title)
        ax.set_xticks([1, 2, 4, 5, 6, 7, 8]); ax.set_ylim(-0.03, 1.05); ax.set_xlim(0.7, 9.8)
        ax.text(-0.12, 1.03, letter, transform=ax.transAxes, fontsize=12, fontweight='bold', va='top')

    panel(axes[0], 'terminal_recall', 'Recall del fatto terminale', 'a')
    panel(axes[1], 'chain_recall', 'Chain-recall (completezza catena)', 'b', depths_filter=[2, 4, 5, 6, 7, 8])
    fig.suptitle('Scaling della profondita\' dei salti: recall terminale e completezza della catena',
                 fontsize=10, y=1.02)
    fig.tight_layout(); fig.savefig('fig13_profondita_salti.png', dpi=160, bbox_inches='tight')
    plt.close(fig)
    print("      -> fig13_profondita_salti.png")

    print("\n=== SWEEP ===")
    print(sweep.to_string(index=False))
    print("\nFatto.")


if __name__ == '__main__':
    main()
