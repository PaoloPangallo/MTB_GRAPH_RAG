"""
07_robustezza_rumore_kb.py
==========================
Esperimento aggiuntivo (strand D) per la tesi mtb-graphrag:
ROBUSTEZZA AL RUMORE DELLA KNOWLEDGE BASE.

Domanda
-------
Se la knowledge base viene contaminata con *falsi fatti plausibili*, quale
architettura di retrieval degrada di meno? Si confrontano GraphRAG e i tre
sistemi RAG testuali (BM25, ibrido, denso all-MiniLM-L6-v2).

Principio di equità (critico)
-----------------------------
GraphRAG attraversa archi tipizzati del grafo; il RAG consuma passaggi di
testo. Iniettare rumore SOLO nel corpus renderebbe GraphRAG immune per
costruzione (risultato banale). Qui il rumore è ACCOPPIATO: ogni falso fatto
è simultaneamente
  (1) un arco tipizzato spurio nel grafo   -> visto da GraphRAG
  (2) un passaggio distrattore nel corpus  -> visto dal RAG
nello stesso identico formato dei fatti veri. I due sistemi affrontano quindi
lo stesso identico avversario.

Costruzione del rumore
----------------------
Per le relazioni di ultimo salto che determinano la risposta gold
(TARGETS_DRUG, HAS_DISEASE, DIAGNOSES_GENE, TESTS_DRUG): per ogni nodo
sorgente con k archi veri di tipo R si aggiungono round(rho*k) archi spuri
verso target dello stesso tipo ma non realmente collegati, campionati dallo
stesso vocabolario dei target reali (massima plausibilità). Ogni arco spurio
genera un passaggio distrattore che nomina l'ancora della query (gene,
variante, farmaco) così da competere davvero nel retrieval testuale.
I livelli sono ANNIDATI: l'ordine dei falsi a rho=4 è fisso e il livello rho
prende i primi round(rho*k) per ogni sorgente -> curve monotone e comparabili.

Livelli di rumore:  rho in {0, 0.25, 0.5, 1.0, 2.0, 4.0}
Seed fisso:         20240517

Metrica
-------
* Recall del fatto gold: frazione di risposte gold il cui nome compare nel
  contesto assemblato a budget 900 parole (stessa metrica deterministica e
  offline delle strand B e C, nessuna chiamata a Ollama).
* Contaminazione del contesto: frazione di contenuto spurio nel contesto
  assemblato. Per GraphRAG = frazione di path serializzati che usano >=1 arco
  spurio; per il RAG = frazione di passaggi del budget marcati is_noise.
  La precisione del contesto riportata in figura è 1 - contaminazione.

Router
------
Si usa il router-oracolo (qtype del benchmark -> intento) per isolare
l'effetto del RUMORE dall'errore di instradamento; a rho=0 GraphRAG riproduce
esattamente recall 1.000, e i sistemi RAG le baseline delle strand B/C
(BM25 0.835, ibrido 0.825, denso 0.293).

Checkpoint richiesti (già prodotti dalla pipeline principale):
  kb_graph.gpickle   nx.MultiDiGraph, 43.005 nodi / 55.544 archi
  rag_corpus.pkl     DataFrame, 20.679 passaggi (col: passage_id,text,src_type,entities)
  corpus_emb.npy     embedding all-MiniLM-L6-v2 dei passaggi (20.679 x 384, normalizzati)
  benchmark_multihop_qa.csv   169 domande (col: question, gold_answer, qtype)

Output:
  noise_facts.csv        i falsi fatti generati (a rho=4, con rank di attivazione)
  kb_noise_sweep.csv     system x rho x recall x contamination x precision
  fig12_kb_noise.png     curve di degradazione (2 pannelli)

Dipendenze: networkx, pandas, numpy, sentence-transformers, rank-bm25,
scikit-learn, matplotlib. Python 3.12. Nessuna chiave, nessuna rete a runtime
(il modello all-MiniLM viene scaricato da HuggingFace solo la prima volta).
"""
import os, re, time, pickle, random
from collections import defaultdict, Counter
import numpy as np, pandas as pd, networkx as nx
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import minmax_scale

# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------
SEED          = 20240517
RHOS          = [0, 0.25, 0.5, 1.0, 2.0, 4.0]
BUDGET_WORDS  = 900
TOPK          = 400
REL4          = ['TARGETS_DRUG', 'HAS_DISEASE', 'DIAGNOSES_GENE', 'TESTS_DRUG']
DENSE_MODEL   = 'sentence-transformers/all-MiniLM-L6-v2'

C  = {'graphrag':'#1f5fa8','rag_bm25':'#c0532a','rag_hybrid':'#c99a12','rag_dense':'#9a9a9a'}
LB = {'graphrag':'GraphRAG','rag_bm25':'RAG BM25','rag_hybrid':'RAG ibrido','rag_dense':'RAG denso'}
SYSORD = ['graphrag','rag_bm25','rag_hybrid','rag_dense']

# ---------------------------------------------------------------------------
# Utilità
# ---------------------------------------------------------------------------
def norm_name(s): return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()
def tok(s):       return [w for w in ''.join(c.lower() if c.isalnum() else ' ' for c in s).split() if len(w) > 1]

# ---------------------------------------------------------------------------
# Caricamento checkpoint
# ---------------------------------------------------------------------------
def load_checkpoints():
    with open("kb_graph.gpickle", "rb") as f:
        G = pickle.load(f)
    corpus   = pd.read_pickle("rag_corpus.pkl")
    emb_mini = np.load("corpus_emb.npy")
    bench    = pd.read_csv("benchmark_multihop_qa.csv")
    return G, corpus, emb_mini, bench

# ---------------------------------------------------------------------------
# Machinery del grafo (fedele a 01_sistemi_retrieval.py)
# ---------------------------------------------------------------------------
def build_graph_helpers(G):
    def name(nid):
        d = G.nodes[nid]; return d.get('name') or d.get('nct_id') or d.get('pmid') or str(nid)
    # indice alias SOLO su name (il campo 'aliases' introduce collisioni con parole
    # italiane comuni, es. "per" -> gene PER1, e va escluso)
    alias2nodes = defaultdict(list)
    for n, d in G.nodes(data=True):
        a = norm_name(d.get('name', ''))
        if a: alias2nodes[a].append(n)
    gene_variants = defaultdict(dict); gene_of_variant = {}
    for u, v, d in G.edges(data=True):
        if d.get('rel') == 'HAS_VARIANT':
            gene_variants[u][norm_name(name(v))] = v; gene_of_variant[v] = u
    return name, alias2nodes, gene_variants, gene_of_variant

_VARIANT_TRIGGERS = ('variante', 'mutazione', 'mutation', 'variant')

ROUTES = {
 'GENE_TO_DRUG': ('Gene',[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')]),
 'GENE_TO_DISEASE':('Gene',[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('HAS_DISEASE','>')]),
 'GENE_TO_CDX':('Gene',[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>'),('HAS_COMPANION_DIAGNOSTIC','>')]),
 'GENE_TO_TRIALDRUG':('Gene',[('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')]),
 'VARIANT_TO_DRUG':('Variant',[('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')]),
 'DRUG_TO_GENE_CDX':('Drug',[('HAS_COMPANION_DIAGNOSTIC','>'),('DIAGNOSES_GENE','>')]),
 'GENE_EVIDENCE_TRIAL_BRIDGE':('BRIDGE',None),
}
QT2INT = {'gene_to_drug':'GENE_TO_DRUG','gene_to_disease':'GENE_TO_DISEASE','gene_to_cdx':'GENE_TO_CDX',
          'gene_to_trialdrug':'GENE_TO_TRIALDRUG','variant_to_drug':'VARIANT_TO_DRUG',
          'drug_to_gene_cdx':'DRUG_TO_GENE_CDX','gene_evidence_trial_bridge':'GENE_EVIDENCE_TRIAL_BRIDGE'}

def make_engine(G, name, alias2nodes, gene_variants, gene_of_variant):
    def link_entities(q):
        toks = norm_name(q).split(); found = []
        for L in (3, 2, 1):
            for i in range(len(toks)-L+1):
                cand = ' '.join(toks[i:i+L])
                if cand in alias2nodes and len(cand) > 2:
                    for nid in alias2nodes[cand]:
                        found.append((cand, nid, G.nodes[nid]['label']))
        seen = set(); out = []
        for c, n, l in found:
            if n not in seen: seen.add(n); out.append((c, n, l))
        return out
    def link_entities2(q):
        base = link_entities(q)
        genes_linked = [n for _, n, l in base if l == 'Gene']
        ql = norm_name(q)
        if any(t in ql for t in _VARIANT_TRIGGERS) and genes_linked:
            g = genes_linked[0]; gn = norm_name(name(g)); after = ql.split(gn, 1)[-1].strip()
            vnodes = []
            for vname_norm, vnode in gene_variants[g].items():
                if vname_norm and vname_norm in after: vnodes.append((len(vname_norm), vnode))
            vnodes.sort(reverse=True)
            if vnodes:
                best = [vn for _, vn in vnodes]
                return [(gn, g, 'Gene')] + [(norm_name(name(vn)), vn, 'Variant') for vn in best[:3]]
            return [(gn, g, 'Gene')]
        return base
    def follow_tagged(start, steps):
        frontier = [([start], False)]
        for rel, d in steps:
            nf = []
            for path, nz in frontier:
                node = path[-1]
                if d == '>':
                    for _, v, dt in G.out_edges(node, data=True):
                        if dt.get('rel') == rel: nf.append((path+[v], nz or dt.get('noise', False)))
                else:
                    for u, _, dt in G.in_edges(node, data=True):
                        if dt.get('rel') == rel: nf.append((path+[u], nz or dt.get('noise', False)))
            frontier = nf
        return frontier
    def serialize(pn, pr):
        labels = [G.nodes[n]['label'] for n in pn]; nmv = [name(n) for n in pn]
        rels = [r for r, _ in pr]; leaf = labels[-1]; start = labels[0]
        def var_q(vnode):
            gg = gene_of_variant.get(vnode); return f"{name(gg)} {name(vnode)}" if gg else name(vnode)
        if start=='Variant' and leaf=='Drug': return f"La variante {var_q(pn[0])} è collegata, tramite evidenza clinica documentata, al farmaco {nmv[-1]}."
        if start=='Variant' and leaf=='Disease': return f"La variante {var_q(pn[0])} presenta evidenza clinica nella malattia {nmv[-1]}."
        if start=='Gene' and leaf=='Drug' and 'HAS_EVIDENCE' in rels: return f"Il gene {nmv[0]} è collegato, tramite evidenza clinica documentata, al farmaco {nmv[-1]}."
        if start in ('Gene','Variant') and leaf=='Disease': return f"Il {start.lower()} {nmv[0]} presenta evidenza clinica nella malattia {nmv[-1]}."
        if start=='Drug' and leaf=='Gene' and 'DIAGNOSES_GENE' in rels: return f"Il farmaco {nmv[0]} ha un test diagnostico di accompagnamento che rileva il gene {nmv[-1]}."
        if start=='Gene' and leaf=='Drug' and 'TESTS_DRUG' in rels: return f"Il gene {nmv[0]} è associato a un trial clinico che testa il farmaco {nmv[-1]}."
        if leaf=='CompanionDiagnostic': return f"Il gene {nmv[0]} è collegato, tramite farmaco con evidenza clinica, al test diagnostico {nmv[-1]}."
        parts = [nmv[0]]
        for i, (rel, d) in enumerate(pr):
            rl = rel.lower().replace('_', ' '); parts.append(f"—{rl}→" if d=='>' else f"←{rl}—"); parts.append(nmv[i+1])
        return " ".join(parts)
    def pack_graph(facts, budget):
        clean_seen = {}; order = []
        for s, nz in facts:
            if s not in clean_seen: clean_seen[s] = (not nz); order.append(s)
            else: clean_seen[s] = clean_seen[s] or (not nz)
        ctx = []; words = 0; n_noise = 0; n_tot = 0
        for s in order:
            w = len(s.split())
            if words+w > budget and ctx: break
            ctx.append(s); words += w; n_tot += 1
            if not clean_seen[s]: n_noise += 1
        return ctx, n_noise, n_tot
    def graph_retrieve(q, intent, budget=BUDGET_WORDS):
        links = link_entities2(q)
        if not links: return [], 0, 0
        start_pref, steps = ROUTES[intent]
        if start_pref == 'BRIDGE':
            gene = [n for _, n, l in links if l == 'Gene']
            if not gene: return [], 0, 0
            g = gene[0]
            ev = follow_tagged(g, [('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')])
            tr = follow_tagged(g, [('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')])
            ev_any = defaultdict(bool); tr_any = defaultdict(bool)
            for p, nz in ev:
                if not nz: ev_any[name(p[-1])] = True
            for p, nz in tr:
                if not nz: tr_any[name(p[-1])] = True
            common = ({name(p[-1]) for p, _ in ev}) & ({name(p[-1]) for p, _ in tr})
            facts = []
            for c in sorted(common):
                clean = ev_any[c] and tr_any[c]
                facts.append((f"Il farmaco {c} è supportato da evidenza clinica ED è testato in un trial clinico per il gene {name(g)}.", not clean))
            return pack_graph(facts, budget)
        if start_pref == 'Variant':
            vstarts = [n for _, n, l in links if l == 'Variant']
            if vstarts: starts = vstarts; use_steps = steps
            else: starts = [n for _, n, l in links if l == 'Gene']; use_steps = [('HAS_VARIANT','>')]+steps
        else:
            starts = [n for _, n, l in links if l == start_pref] or [n for _, n, l in links]; use_steps = steps
        allpaths = []
        for s in starts: allpaths += follow_tagged(s, use_steps)
        facts = [(serialize(path, [(r, d) for r, d in use_steps]), nz) for path, nz in allpaths]
        return pack_graph(facts, budget)
    return link_entities2, graph_retrieve

# ---------------------------------------------------------------------------
# Generazione rumore accoppiato (deterministica, seed fisso)
# ---------------------------------------------------------------------------
def generate_noise(G, name, rho_max):
    rel_true_adj = defaultdict(lambda: defaultdict(set)); rel_pool = defaultdict(set)
    for u, v, d in G.edges(data=True):
        R = d.get('rel')
        if R in REL4:
            rel_true_adj[R][u].add(v); rel_pool[R].add(v)
    rng = random.Random(SEED); rows = []
    for R in REL4:
        pool = sorted(rel_pool[R], key=lambda x: str(x))
        for u in sorted(rel_true_adj[R].keys(), key=lambda x: str(x)):
            true_t = rel_true_adj[R][u]; k = len(true_t); n_max = round(rho_max*k)
            if n_max == 0: continue
            cand = [t for t in pool if t not in true_t]
            if not cand: continue
            rng.shuffle(cand); chosen = cand[:n_max]
            for rank, t in enumerate(chosen):
                rows.append(dict(rel=R, src=u, tgt=t, rank=rank, k_true=k))
    noise = pd.DataFrame(rows)

    # ancore per rendere i distrattori recuperabili nel retrieval testuale
    def in_by(node, rel):  return [u for u, _, d in G.in_edges(node, data=True) if d.get('rel')==rel]
    def out_by(node, rel): return [v for _, v, d in G.out_edges(node, data=True) if d.get('rel')==rel]
    def ev_anchors(ev):
        genes, vars = set(), set()
        for mp in in_by(ev, 'HAS_EVIDENCE'):
            for v in in_by(mp, 'IN_MOLECULAR_PROFILE'):
                vars.add(name(v))
                for g in in_by(v, 'HAS_VARIANT'): genes.add(name(g))
        return genes, vars
    def cdx_drug(cdx):   return set(name(u) for u in in_by(cdx, 'HAS_COMPANION_DIAGNOSTIC'))
    def trial_gene(tr):  return set(name(v) for v in out_by(tr, 'ASSOCIATED_GENE'))
    def node_ent(nid):
        d = G.nodes[nid]; return f"{d['label']}:{d.get('id', nid)}"
    def distractor(row):
        R, u, t = row['rel'], row['src'], row['tgt']; tn = name(t)
        if R == 'TARGETS_DRUG':
            genes, vars = ev_anchors(u)
            gtxt = ", ".join(sorted(genes)) if genes else "N/D"; vtxt = ", ".join(sorted(vars)) if vars else "N/D"
            return (f"Nel profilo molecolare associato al gene {gtxt} (variante {vtxt}), "
                    f"un'evidenza clinica documentata riporta risposta al farmaco {tn}. Farmaco associato: {tn}.")
        if R == 'HAS_DISEASE':
            genes, vars = ev_anchors(u)
            gtxt = ", ".join(sorted(genes)) if genes else "N/D"; vtxt = ", ".join(sorted(vars)) if vars else "N/D"
            return (f"Nel tumore {tn}, il gene {gtxt} (variante {vtxt}) presenta "
                    f"un'evidenza clinica documentata. Malattia: {tn}.")
        if R == 'DIAGNOSES_GENE':
            drugs = cdx_drug(u); dtxt = ", ".join(sorted(drugs)) if drugs else name(u)
            return (f"Test diagnostico di accompagnamento {name(u)} per il farmaco {dtxt}: "
                    f"rileva il gene {tn}. Gene: {tn}. Farmaco: {dtxt}.")
        genes = trial_gene(u); gtxt = ", ".join(sorted(genes)) if genes else "N/D"
        return (f"Trial clinico {name(u)} associato al gene {gtxt}: "
                f"testa il farmaco {tn}. Geni associati: {gtxt}. Farmaci testati: {tn}.")
    noise['distractor_text'] = [distractor(r) for r in noise.to_dict('records')]
    noise['src_name'] = [name(u) for u in noise['src']]
    noise['tgt_name'] = [name(t) for t in noise['tgt']]
    noise['noise_passage_id'] = ['NOISE:%d' % i for i in range(len(noise))]
    return noise

# ---------------------------------------------------------------------------
# Metriche
# ---------------------------------------------------------------------------
def gold_recall_ctx(ctx_list, gnames):
    if not gnames: return np.nan
    blob = " ".join(norm_name(x) for x in ctx_list)
    return sum(1 for g in gnames if norm_name(g) in blob) / len(gnames)

def pack_rag(order_idx, texts_all, is_noise_all, budget=BUDGET_WORDS):
    ctx = []; words = 0; n_noise = 0
    for i in order_idx:
        i = int(i); t = texts_all[i]; w = len(t.split())
        if words+w > budget and ctx: break
        ctx.append(t); words += w
        if is_noise_all[i]: n_noise += 1
        if words >= budget: break
    return ctx, n_noise, len(ctx)

# ---------------------------------------------------------------------------
# Sweep principale
# ---------------------------------------------------------------------------
def run_sweep():
    t0 = time.time()
    G, corpus, emb_mini, bench = load_checkpoints()
    name, alias2nodes, gene_variants, gene_of_variant = build_graph_helpers(G)
    link2, graph_retrieve = make_engine(G, name, alias2nodes, gene_variants, gene_of_variant)

    base_texts = corpus['text'].tolist(); N_BASE = len(base_texts)
    questions  = bench['question'].tolist()
    qtypes     = bench['qtype'].tolist()
    golds      = [re.split(r'[|;,]', str(g)) for g in bench['gold_answer']]
    golds      = [[x.strip() for x in gg if x.strip()] for gg in golds]

    mini = SentenceTransformer(DENSE_MODEL, device='cpu')
    q_mini = mini.encode(questions, normalize_embeddings=True, show_progress_bar=False)

    print("[*] genero rumore accoppiato (rho_max=%g)..." % max(RHOS))
    noise = generate_noise(G, name, max(RHOS))
    noise.to_csv("noise_facts.csv", index=False,
                 columns=['noise_passage_id','rel','src','src_name','tgt','tgt_name','rank','k_true','distractor_text'])
    print("    %d falsi fatti; embedding distrattori..." % len(noise))
    distractor_texts = noise['distractor_text'].tolist()
    emb_noise = mini.encode(distractor_texts, normalize_embeddings=True, show_progress_bar=False, batch_size=256)
    noise_tok = [tok(t) for t in distractor_texts]
    ranks = noise['rank'].values; ks = noise['k_true'].values
    srcs = noise['src'].values; tgts = noise['tgt'].values; rels = noise['rel'].values

    bm25_base = BM25Okapi([tok(t) for t in base_texts])

    def active_mask(rho):
        if rho == 0: return np.zeros(len(noise), dtype=bool)
        return ranks < np.round(rho*ks).astype(int)
    def add_edges(idxs):
        for j in idxs: G.add_edge(srcs[j], tgts[j], rel=rels[j], noise=True)
    def del_edges(idxs):
        for j in idxs:
            try: G.remove_edge(srcs[j], tgts[j])
            except Exception: pass

    rows = []
    for rho in RHOS:
        act = np.where(active_mask(rho))[0]
        add_edges(act)
        ext_texts   = base_texts + [distractor_texts[j] for j in act]
        ext_isnoise = np.array([False]*N_BASE + [True]*len(act))
        ext_emb     = np.vstack([emb_mini, emb_noise[act]]) if len(act) else emb_mini
        bm_ext      = BM25Okapi([tok(t) for t in base_texts] + [noise_tok[j] for j in act]) if len(act) else bm25_base

        gr_rec, gr_cont = [], []
        for i, q in enumerate(questions):
            ctx, nn, nt = graph_retrieve(q, QT2INT[qtypes[i]], BUDGET_WORDS)
            gr_rec.append(gold_recall_ctx(ctx, golds[i])); gr_cont.append(nn/nt if nt else 0.0)
        sysrec = {s: [] for s in SYSORD[1:]}; syscont = {s: [] for s in SYSORD[1:]}
        for i, q in enumerate(questions):
            qv = q_mini[i]; bscores = bm_ext.get_scores(tok(q)); dscores = ext_emb @ qv
            for s in SYSORD[1:]:
                if s == 'rag_bm25':    order = np.argsort(-bscores)[:TOPK]
                elif s == 'rag_dense': order = np.argsort(-dscores)[:TOPK]
                else:                  order = np.argsort(-(0.5*minmax_scale(dscores)+0.5*minmax_scale(bscores)))[:TOPK]
                ctx, nn, nt = pack_rag(order, ext_texts, ext_isnoise, BUDGET_WORDS)
                sysrec[s].append(gold_recall_ctx(ctx, golds[i])); syscont[s].append(nn/nt if nt else 0.0)
        rows.append(dict(system='graphrag', rho=rho, recall=np.nanmean(gr_rec), contamination=np.mean(gr_cont)))
        for s in SYSORD[1:]:
            rows.append(dict(system=s, rho=rho, recall=np.nanmean(sysrec[s]), contamination=np.mean(syscont[s])))
        del_edges(act)
        print("    rho=%-4g GraphRAG rec=%.3f cont=%.3f | BM25 rec=%.3f cont=%.3f"
              % (rho, np.nanmean(gr_rec), np.mean(gr_cont),
                 np.nanmean(sysrec['rag_bm25']), np.mean(syscont['rag_bm25'])))
    sweep = pd.DataFrame(rows); sweep['precision'] = 1 - sweep['contamination']
    sweep.to_csv("kb_noise_sweep.csv", index=False)
    print("[*] sweep completo in %.0fs -> kb_noise_sweep.csv" % (time.time()-t0))
    return sweep

# ---------------------------------------------------------------------------
# Figura
# ---------------------------------------------------------------------------
def make_figure(sweep):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':8,'axes.spines.top':False,'axes.spines.right':False,
                         'figure.dpi':300,'savefig.dpi':300})
    pr = sweep.pivot(index='rho', columns='system', values='recall')
    pc = sweep.pivot(index='rho', columns='system', values='contamination')
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.2, 4.0))
    for s in SYSORD:
        ax1.plot(RHOS, [pr.loc[r, s] for r in RHOS], marker='o', ms=4.5,
                 lw=1.8 if s=='graphrag' else 1.3, color=C[s], alpha=1.0 if s=='graphrag' else 0.85,
                 zorder=5 if s=='graphrag' else 3)
    ax1.set_xlabel('Rumore iniettato  ρ  (falsi fatti / fatti veri)')
    ax1.set_ylabel('Recall del fatto gold')
    ax1.set_title('a  Il fatto vero sopravvive al rumore?', loc='left', fontsize=8)
    ax1.set_ylim(-0.03, 1.05); ax1.set_xlim(-0.15, 5.2)
    ax1.axhline(1.0, color='#cccccc', lw=0.6, ls=':', zorder=1)
    for s in SYSORD:
        ax1.annotate(LB[s], (RHOS[-1], pr.loc[RHOS[-1], s]), xytext=(4, 0),
                     textcoords='offset points', va='center', fontsize=6, color=C[s])
    for s in SYSORD:
        ax2.plot(RHOS, [1-pc.loc[r, s] for r in RHOS], marker='o', ms=4.5,
                 lw=1.8 if s=='graphrag' else 1.3, color=C[s], alpha=1.0 if s=='graphrag' else 0.85,
                 zorder=5 if s=='graphrag' else 3)
    ax2.set_xlabel('Rumore iniettato  ρ  (falsi fatti / fatti veri)')
    ax2.set_ylabel('Precisione del contesto  (1 − contaminazione)')
    ax2.set_title('b  Quanto contesto resta pulito?', loc='left', fontsize=8)
    ax2.set_ylim(-0.03, 1.05); ax2.set_xlim(-0.15, 4.6)
    ax2.annotate('GraphRAG', (RHOS[-1], 1-pc.loc[RHOS[-1], 'graphrag']), xytext=(4, 0),
                 textcoords='offset points', va='center', fontsize=6, color=C['graphrag'])
    fig.text(0.008, 0.5, 'più alto = migliore', rotation=90, va='center', fontsize=5.5, color='#666666')
    fig.tight_layout(rect=[0.02, 0, 1, 1])
    fig.savefig("fig12_kb_noise.png", dpi=300, bbox_inches='tight')
    print("[*] figura -> fig12_kb_noise.png")

if __name__ == "__main__":
    sweep = run_sweep()
    make_figure(sweep)
    print("\n=== RECALL DEL FATTO GOLD vs rho ===")
    print(sweep.pivot(index='rho', columns='system', values='recall')[SYSORD].round(3).to_string())
    print("\n=== CONTAMINAZIONE DEL CONTESTO vs rho ===")
    print(sweep.pivot(index='rho', columns='system', values='contamination')[SYSORD].round(3).to_string())
