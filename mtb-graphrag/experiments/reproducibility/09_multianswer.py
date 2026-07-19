#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
09_multianswer.py — Strand F: aggregazione multi-risposta (recall a livello di insieme).

Molte domande cliniche reali NON hanno una risposta singola ma un INSIEME:
«quali sono TUTTE le varianti note del gene X?», «TUTTI i farmaci con evidenza
per X?». Qui la metrica non e' se una risposta compare, ma quale FRAZIONE
dell'insieme-gold viene recuperata (recall a livello di insieme), con precisione
e F1, stratificate per AMPIEZZA dell'insieme (cardinalita' del gold-set).

Quattro template di aggregazione, ciascuno ancorato a una catena tipizzata:
  gene_to_variants  : Gene -HAS_VARIANT-> Variant
  gene_to_drugs     : Gene ->Variant ->MolecularProfile ->Evidence ->Drug
  gene_to_diseases  : Gene ->Variant ->MolecularProfile ->Evidence ->Disease
  gene_to_cdx       : Gene ->...->Drug ->CompanionDiagnostic

Confronta 4 sistemi: GraphRAG (enumerazione esaustiva del vicinato tipizzato) e
tre RAG (BM25, ibrido 0.5/0.5, denso MiniLM). Router = oracolo. Il gold-set e'
l'insieme completo dei nodi del tipo-obiettivo raggiungibili lungo la catena;
l'ampiezza (set_size) e' una covariata, non un filtro (si tengono set_size>=2).

Metrica name-in-text: per GraphRAG l'insieme restituito e' l'enumerazione
impacchettata nel budget; per i RAG e' l'insieme delle entita' del tipo-obiettivo
i cui nomi compaiono nei passaggi recuperati (campo 'entities' del corpus).

Riproducibile: SEED=20240517, nessuna rete, nessun LLM. Legge i checkpoint:
  kb_graph.gpickle, rag_corpus.pkl, corpus_emb.npy
Produce: benchmark_multianswer.csv, multianswer_sweep.csv,
         multianswer_setsize.png, fig14_multianswer.png
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
rng = np.random.default_rng(SEED)

# --- Template di aggregazione: catena (relazione, direzione) + tipo-obiettivo ---
TEMPLATES = {
    'gene_to_variants': {
        'chain': [('HAS_VARIANT', '+')],
        'tgt': 'Variant',
        'q': "Quali sono tutte le varianti note del gene {g}?",
        'desc': "le varianti note",
    },
    'gene_to_drugs': {
        'chain': [('HAS_VARIANT', '+'), ('IN_MOLECULAR_PROFILE', '+'),
                  ('HAS_EVIDENCE', '+'), ('TARGETS_DRUG', '+')],
        'tgt': 'Drug',
        'q': "Quali sono tutti i farmaci supportati da evidenza clinica per le alterazioni del gene {g}?",
        'desc': "i farmaci con evidenza clinica",
    },
    'gene_to_diseases': {
        'chain': [('HAS_VARIANT', '+'), ('IN_MOLECULAR_PROFILE', '+'),
                  ('HAS_EVIDENCE', '+'), ('HAS_DISEASE', '+')],
        'tgt': 'Disease',
        'q': "Quali sono tutte le malattie associate ad alterazioni del gene {g} con evidenza clinica?",
        'desc': "le malattie associate",
    },
    'gene_to_cdx': {
        'chain': [('HAS_VARIANT', '+'), ('IN_MOLECULAR_PROFILE', '+'),
                  ('HAS_EVIDENCE', '+'), ('TARGETS_DRUG', '+'),
                  ('HAS_COMPANION_DIAGNOSTIC', '+')],
        'tgt': 'CompanionDiagnostic',
        'q': "Quali sono tutti i test diagnostici di accompagnamento per i farmaci indicati per il gene {g}?",
        'desc': "i test diagnostici di accompagnamento",
    },
}
TORDER = ['gene_to_variants', 'gene_to_drugs', 'gene_to_diseases', 'gene_to_cdx']

SYSORD = ['graphrag', 'rag_bm25', 'rag_hybrid', 'rag_dense']
C = {'graphrag': '#1f5fa8', 'rag_bm25': '#c0532a', 'rag_hybrid': '#c99a12', 'rag_dense': '#9a9a9a'}
LB = {'graphrag': 'GraphRAG', 'rag_bm25': 'RAG BM25', 'rag_hybrid': 'RAG ibrido', 'rag_dense': 'RAG denso'}
TLB = {'gene_to_variants': 'varianti', 'gene_to_drugs': 'farmaci',
       'gene_to_diseases': 'malattie', 'gene_to_cdx': 'test dx'}
BINORDER = ['2', '3-4', '5-8', '9+']


def norm_name(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()


def tok(s):
    return [w for w in ''.join(c.lower() if c.isalnum() else ' ' for c in s).split() if len(w) > 1]


def width_bin(s):
    if s == 2: return '2'
    if s <= 4: return '3-4'
    if s <= 8: return '5-8'
    return '9+'


def main():
    # ----------------------------------------------------------- load KB
    print("[1/7] Carico il grafo di conoscenza...")
    G = nx.read_gpickle('kb_graph.gpickle') if hasattr(nx, 'read_gpickle') \
        else pickle.load(open('kb_graph.gpickle', 'rb'))

    def nm(n):
        return G.nodes[n].get('name')

    def ntype(n):
        dd = G.nodes[n]
        return dd.get('type') or dd.get('label') or '?'

    # adiacenza tipizzata per relazione
    from collections import defaultdict
    out_adj = defaultdict(lambda: defaultdict(set))
    in_adj = defaultdict(lambda: defaultdict(set))
    for u, v, d in G.edges(data=True):
        r = d.get('rel')
        out_adj[u][r].add(v)
        in_adj[v][r].add(u)

    gene_nodes = [n for n in G.nodes if ntype(n) == 'Gene']
    print(f"      grafo: {G.number_of_nodes()} nodi / {G.number_of_edges()} archi; {len(gene_nodes)} geni")

    # ----------------------------------------------------------- traversata
    def reach(anchor, chain):
        cur = {anchor}
        for rel, dr in chain:
            adj = out_adj if dr == '+' else in_adj
            nxt = set()
            for n in cur:
                nxt |= adj[n].get(rel, set())
            cur = nxt
        return cur

    def gold_set(anchor, template):
        tgt = TEMPLATES[template]['tgt']
        mem = {x for x in reach(anchor, TEMPLATES[template]['chain'])
               if ntype(x) == tgt and nm(x)}
        byname = {}
        for x in mem:
            byname.setdefault(norm_name(nm(x)), nm(x))
        return sorted(byname.values())

    # ----------------------------------------------------------- benchmark
    print("[2/7] Costruisco il benchmark multi-risposta (set_size>=2)...")
    rows = []
    for template in TORDER:
        for g in gene_nodes:
            gname = nm(g)
            if not gname or 'other biomarker' in gname.lower():
                continue
            gs = gold_set(g, template)
            if len(gs) >= 2:
                rows.append({
                    'anchor_gene': gname, 'anchor_id': g, 'template': template,
                    'gold_set': json.dumps(gs, ensure_ascii=False),
                    'set_size': len(gs),
                    'question': TEMPLATES[template]['q'].format(g=gname),
                })
    mdf = pd.DataFrame(rows).sort_values(['template', 'set_size']).reset_index(drop=True)
    mdf.to_csv('benchmark_multianswer.csv', index=False)
    print(f"      {len(mdf)} domande; per template: {mdf.groupby('template').size().to_dict()}")

    # ----------------------------------------------------------- corpus RAG
    print("[3/7] Carico corpus e indici RAG...")
    with open('rag_corpus.pkl', 'rb') as f:
        cdf = pickle.load(f)
    if not isinstance(cdf, pd.DataFrame):
        cdf = pd.DataFrame(cdf)
    texts = cdf['text'].tolist()
    ent_col = cdf['entities'].tolist()
    emb_mini = np.load('corpus_emb.npy')
    bm25_base = BM25Okapi([tok(t) for t in texts])
    mini = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    q_texts = mdf['question'].tolist()
    q_emb = mini.encode(q_texts, normalize_embeddings=True, batch_size=128, show_progress_bar=False)
    print(f"      corpus: {len(texts)} passaggi; emb {emb_mini.shape}")

    # ----------------------------------------------------------- GraphRAG agg
    def agg_members(anchor, template):
        mem = {x for x in reach(anchor, TEMPLATES[template]['chain'])
               if ntype(x) == TEMPLATES[template]['tgt'] and nm(x)}
        byname = {}
        for x in mem:
            byname.setdefault(norm_name(nm(x)), nm(x))
        return sorted(byname.values())

    def graph_packed(anchor, template, gname, budget=BUDGET_WORDS):
        mem = agg_members(anchor, template)
        head = f"Per il gene {gname}, {TEMPLATES[template]['desc']} comprendono: "
        words = len(head.split())
        packed = []
        for name in mem:
            w = len(name.split()) + 1
            if words + w > budget and packed:
                break
            packed.append(name); words += w
        return mem, packed

    # ----------------------------------------------------------- RAG retrieval
    def rag_rows(qi, system, budget=BUDGET_WORDS):
        q = q_texts[qi]
        bscores = bm25_base.get_scores(tok(q))
        if system == 'rag_bm25':
            order = np.argsort(-bscores)[:TOPK]
        else:
            dscores = emb_mini @ q_emb[qi]
            if system == 'rag_dense':
                order = np.argsort(-dscores)[:TOPK]
            else:
                order = np.argsort(-(0.5 * minmax_scale(dscores) + 0.5 * minmax_scale(bscores)))[:TOPK]
        picked = []; words = 0
        for i in order:
            t = texts[int(i)]; w = len(t.split())
            if words + w > budget and picked:
                break
            picked.append(int(i)); words += w
            if words >= budget:
                break
        return picked

    def returned_set_rag(picked, template):
        tgt = TEMPLATES[template]['tgt']; got = {}
        for i in picked:
            for e in ent_col[i]:
                if e in G.nodes and ntype(e) == tgt:
                    nn = nm(e)
                    if nn:
                        got.setdefault(norm_name(nn), nn)
        return set(got.keys())

    def prf(gold_norm, ret_norm):
        if not ret_norm:
            return 0.0, 0.0, 0.0
        inter = len(gold_norm & ret_norm)
        rec = inter / len(gold_norm); prec = inter / len(ret_norm)
        f1 = 0.0 if rec + prec == 0 else 2 * rec * prec / (rec + prec)
        return rec, prec, f1

    # ----------------------------------------------------------- sweep
    print("[4/7] Sweep a livello di insieme (4 sistemi x %d domande)..." % len(mdf))
    out = []
    for qi, (_, r) in enumerate(mdf.iterrows()):
        gold_norm = {norm_name(x) for x in json.loads(r.gold_set)}
        _, packed = graph_packed(r.anchor_id, r.template, r.anchor_gene)
        gp_norm = {norm_name(x) for x in packed}
        rec, prec, f1 = prf(gold_norm, gp_norm)
        out.append((r.anchor_gene, r.template, r.set_size, 'graphrag', rec, prec, f1))
        for system in ['rag_bm25', 'rag_hybrid', 'rag_dense']:
            ret = returned_set_rag(rag_rows(qi, system), r.template)
            rec, prec, f1 = prf(gold_norm, ret)
            out.append((r.anchor_gene, r.template, r.set_size, system, rec, prec, f1))
    res = pd.DataFrame(out, columns=['anchor_gene', 'template', 'set_size', 'system',
                                     'recall', 'precision', 'f1'])
    res['set_size_bin'] = res.set_size.apply(width_bin)

    # ----------------------------------------------------------- aggregato long
    print("[5/7] Aggrego e salvo multianswer_sweep.csv...")
    agg = (res.groupby(['system', 'template', 'set_size_bin'])
              .agg(recall=('recall', 'mean'), precision=('precision', 'mean'),
                   f1=('f1', 'mean'), n=('recall', 'size')).reset_index())
    agg.to_csv('multianswer_sweep.csv', index=False)
    rec_piv = res.groupby(['system', 'set_size_bin']).recall.mean().unstack()[BINORDER]
    f1_piv = res.groupby(['system', 'set_size_bin']).f1.mean().unstack()[BINORDER]
    prec_piv = res.groupby(['system', 'set_size_bin']).precision.mean().unstack()[BINORDER]
    f1t = res.groupby(['system', 'template']).f1.mean().unstack()
    print("      recall per bin:\n", rec_piv.reindex(SYSORD).round(3).to_string())

    # ----------------------------------------------------------- fig setsize
    print("[6/7] Istogramma delle ampiezze...")
    CT = {'gene_to_variants': '#1f5fa8', 'gene_to_drugs': '#c0532a',
          'gene_to_diseases': '#c99a12', 'gene_to_cdx': '#4a9a6a'}
    LBT = {'gene_to_variants': 'gene → varianti', 'gene_to_drugs': 'gene → farmaci',
           'gene_to_diseases': 'gene → malattie', 'gene_to_cdx': 'gene → test diagnostici'}
    fig, ax = plt.subplots(figsize=(6.2, 3.6)); bins = np.arange(2, 26, 1)
    for t in TORDER:
        d = mdf[mdf.template == t].set_size.clip(upper=25)
        ax.hist(d, bins=bins, histtype='step', lw=1.8, color=CT[t], label=LBT[t])
    ax.set_xlabel("Ampiezza dell'insieme-risposta (cardinalità del gold-set)")
    ax.set_ylabel('Numero di domande')
    ax.set_title('Distribuzione dell\'ampiezza multi-risposta (troncata a 25)', fontsize=9)
    ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout(); fig.savefig('multianswer_setsize.png', dpi=150, bbox_inches='tight')
    plt.close(fig)

    # ----------------------------------------------------------- fig14
    print("[7/7] Figura multi-pannello fig14_multianswer.png...")
    xpos = np.arange(len(BINORDER))
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.7)); lw_focal = 2.6
    META_GREY = '#6b6b6b'

    ax = axes[0]
    for s in SYSORD:
        foc = s == 'graphrag'
        ax.plot(xpos, rec_piv.loc[s].values, marker='o', ms=5 if foc else 4,
                lw=lw_focal if foc else 1.5, color=C[s], zorder=5 if foc else 3,
                alpha=1.0 if foc else 0.85)
    ax.set_xticks(xpos); ax.set_xticklabels(BINORDER)
    ax.set_xlabel("Ampiezza dell'insieme-risposta"); ax.set_ylabel('Recall a livello di insieme')
    ax.set_ylim(-0.03, 1.05); ax.margins(x=0.08)
    ax.text(0.02, 0.02, 'più alto = migliore', transform=ax.transAxes, fontsize=6,
            style='italic', color=META_GREY)
    yoff = {'graphrag': 0, 'rag_bm25': 6, 'rag_hybrid': -6, 'rag_dense': 0}
    for s in SYSORD:
        y = rec_piv.loc[s].values[-1]
        ax.annotate(LB[s], xy=(xpos[-1], y), xytext=(4, yoff[s]), textcoords='offset points',
                    va='center', fontsize=6.5, color=C[s],
                    fontweight='bold' if s == 'graphrag' else 'normal')

    ax = axes[1]; bw = 0.19
    for i, s in enumerate(SYSORD):
        vals = [f1t.loc[s, t] for t in TORDER]
        ax.bar(np.arange(len(TORDER)) + (i - 1.5) * bw, vals, bw, color=C[s],
               label=LB[s], edgecolor='white', linewidth=0.4)
    ax.set_xticks(np.arange(len(TORDER))); ax.set_xticklabels([TLB[t] for t in TORDER])
    ax.set_xlabel('Template di aggregazione'); ax.set_ylabel('F1 a livello di insieme')
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, fontsize=6.2, ncol=2, loc='upper center',
              columnspacing=1.0, handlelength=1.2)

    ax = axes[2]
    for s in SYSORD:
        foc = s == 'graphrag'
        ax.plot(xpos, prec_piv.loc[s].values, marker='s', ms=5 if foc else 4,
                lw=lw_focal if foc else 1.5, color=C[s], zorder=5 if foc else 3,
                alpha=1.0 if foc else 0.85)
    ax.set_xticks(xpos); ax.set_xticklabels(BINORDER)
    ax.set_xlabel("Ampiezza dell'insieme-risposta"); ax.set_ylabel('Precisione a livello di insieme')
    ax.set_ylim(-0.03, 1.05); ax.margins(x=0.08)
    for s in ['graphrag', 'rag_bm25']:
        y = prec_piv.loc[s].values[-1]
        ax.annotate(LB[s], xy=(xpos[-1], y), xytext=(4, 0), textcoords='offset points',
                    va='center', fontsize=6.5, color=C[s],
                    fontweight='bold' if s == 'graphrag' else 'normal')

    for L, ax in zip('abc', axes):
        ax.text(-0.14, 1.04, L, transform=ax.transAxes, fontsize=12, fontweight='bold', va='bottom')
    fig.tight_layout(); fig.savefig('fig14_multianswer.png', dpi=200, bbox_inches='tight')
    plt.close(fig)

    print("FATTO. Output: benchmark_multianswer.csv, multianswer_sweep.csv, "
          "multianswer_setsize.png, fig14_multianswer.png")
    return mdf, res, agg


if __name__ == '__main__':
    main()
