#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
10_router_ablation.py — Strand G: ablazione del router (oracolo -> router reale)
================================================================================
Tesi "mtb-graphrag" (Molecular Tumor Board GraphRAG).

DOMANDA DI RICERCA
------------------
In tutti gli strand A-F il router (che sceglie QUALE pattern di traversata sul
grafo eseguire a partire dalla domanda) e' stato assunto come ORACOLO: l'intento
vero era noto dal template della domanda. Questo script rilassa quell'assunzione
sostituendo l'oracolo con il ROUTER REALE (un classificatore LLM) e misura la
perdita di prestazione end-to-end che ne deriva. Chiude cosi' l'assunzione piu'
forte del lavoro.

Due benchmark:
  * MULTI-HOP   (169 domande, 7 template, hop 2-5) — insieme-risposta a cardinalita' 1..n
  * MULTI-ANSWER(539 domande, 4 template)          — insieme-risposta completo per gene

Per ciascun benchmark confronta:
  * router ORACOLO  : intento = template della domanda (ground truth)
  * router REALE    : intento = classificazione LLM della domanda

METODOLOGIA E RIPRODUCIBILITA'
------------------------------
Il routing e' l'UNICA componente non deterministica (chiamata a un LLM cloud).
Per rendere lo script riproducibile bit-identico OFFLINE, le predizioni del
router sono state congelate in `router_predictions_cache.json`. Per default lo
script LEGGE la cache e ricalcola in modo deterministico tutta la traversata sul
grafo e le metriche. Con `--rerun-router` le predizioni vengono rigenerate
chiamando l'endpoint cloud (richiede la variabile d'ambiente OLLAMA_KEY; la
chiave NON e' mai scritta nel codice ne' nei file di output).

USO
---
    python 10_router_ablation.py                 # deterministico, usa la cache
    python 10_router_ablation.py --rerun-router  # rigenera le predizioni (LLM cloud)

Variabili d'ambiente (solo con --rerun-router):
    OLLAMA_KEY   (obbligatoria)  API key del servizio cloud
    OLLAMA_HOST  (opz., default https://ollama.com)
    ROUTER_MODEL (opz., default gemma3:27b-cloud)

INPUT (nella cartella corrente)
    kb_graph.gpickle                  grafo di conoscenza (MultiDiGraph, 43005 nodi)
    benchmark_multihop_qa.csv         benchmark multi-hop (169 domande)
    benchmark_multianswer.csv         benchmark multi-answer (539 domande)
    router_predictions_cache.json     predizioni congelate del router reale

OUTPUT
    router_ablation_multihop.csv      metriche per-domanda multi-hop
    router_ablation_multianswer.csv   metriche per-domanda multi-answer
    router_confusion.csv              matrice di confusione + note cliniche
    fig15_router_ablation.png         figura a 4 pannelli
"""
import os, re, sys, json, pickle, argparse, hashlib, time
from collections import defaultdict, Counter
import numpy as np
import pandas as pd
import networkx as nx

SEED = 20240517
np.random.seed(SEED)
CONTEXT_BUDGET_WORDS = 900
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "gemma3:27b-cloud")
OLLAMA_HOST  = os.environ.get("OLLAMA_HOST", "https://ollama.com")

# ============================================================================
# 1) GRAFO E INDICI
# ============================================================================
def load_graph(path="kb_graph.gpickle"):
    if hasattr(nx, "read_gpickle"):
        return nx.read_gpickle(path)
    with open(path, "rb") as f:
        return pickle.load(f)

def norm_name(s): return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()

def build_indices(G):
    out_adj = defaultdict(lambda: defaultdict(set))   # node -> rel -> {targets}
    in_adj  = defaultdict(lambda: defaultdict(set))   # node -> rel -> {sources}
    for u, v, d in G.edges(data=True):
        r = d.get('rel')
        out_adj[u][r].add(v)
        in_adj[v][r].add(u)
    # alias index: nome normalizzato -> {node id}
    alias2nodes = defaultdict(set)
    for n, d in G.nodes(data=True):
        nmv = d.get('name') or d.get('nct_id') or ''
        if nmv: alias2nodes[norm_name(nmv)].add(n)
    # gene -> {nome_variante_norm: variant_node}
    gene_variants = defaultdict(dict)
    gene_of_variant = {}
    for u, v, dt in G.edges(data=True):
        if dt.get('rel') == 'HAS_VARIANT':
            gene_variants[u][norm_name(G.nodes[v].get('name'))] = v
            gene_of_variant[v] = u
    return out_adj, in_adj, alias2nodes, gene_variants, gene_of_variant

# ============================================================================
# 2) DEFINIZIONE DEI PATTERN DI TRAVERSATA (ROUTES)
# ============================================================================
# Multi-hop: 7 intenti -> (tipo_nodo_di_partenza, [(relazione, direzione), ...])
#   direzione '>' = arco uscente (src-[rel]->tgt), '<' = arco entrante
ROUTES = {
 'GENE_TO_DRUG':    ('Gene', [('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')]),
 'GENE_TO_DISEASE': ('Gene', [('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('HAS_DISEASE','>')]),
 'GENE_TO_CDX':     ('Gene', [('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>'),('HAS_COMPANION_DIAGNOSTIC','>')]),
 'GENE_TO_TRIALDRUG':('Gene',[('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')]),
 'VARIANT_TO_DRUG': ('Variant',[('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')]),
 'DRUG_TO_GENE_CDX':('Drug',[('HAS_COMPANION_DIAGNOSTIC','>'),('DIAGNOSES_GENE','>')]),
 'GENE_EVIDENCE_TRIAL_BRIDGE':('BRIDGE', None),
}
ROUTES_LIST = ['GENE_TO_DRUG','GENE_TO_DISEASE','GENE_TO_CDX','GENE_TO_TRIALDRUG',
               'VARIANT_TO_DRUG','DRUG_TO_GENE_CDX','GENE_EVIDENCE_TRIAL_BRIDGE']
# mappa qtype (template della domanda) -> intento oracolo
QTYPE2ROUTE = {'gene_to_drug':'GENE_TO_DRUG','variant_to_drug':'VARIANT_TO_DRUG',
               'gene_to_disease':'GENE_TO_DISEASE','gene_to_cdx':'GENE_TO_CDX',
               'drug_to_gene_cdx':'DRUG_TO_GENE_CDX','gene_to_trialdrug':'GENE_TO_TRIALDRUG',
               'gene_evidence_trial_bridge':'GENE_EVIDENCE_TRIAL_BRIDGE'}

# Multi-answer: 4 intenti; catena template (direzione '+' = uscente, '-' = entrante)
TCHAIN = {
 'gene_to_variants':[('HAS_VARIANT','+')],
 'gene_to_drugs':   [('HAS_VARIANT','+'),('IN_MOLECULAR_PROFILE','+'),('HAS_EVIDENCE','+'),('TARGETS_DRUG','+')],
 'gene_to_diseases':[('HAS_VARIANT','+'),('IN_MOLECULAR_PROFILE','+'),('HAS_EVIDENCE','+'),('HAS_DISEASE','+')],
 'gene_to_cdx':     [('HAS_VARIANT','+'),('IN_MOLECULAR_PROFILE','+'),('HAS_EVIDENCE','+'),('TARGETS_DRUG','+'),('HAS_COMPANION_DIAGNOSTIC','+')],
}
TTGT = {'gene_to_variants':'Variant','gene_to_drugs':'Drug',
        'gene_to_diseases':'Disease','gene_to_cdx':'CompanionDiagnostic'}
MA_ROUTES = ['GENE_TO_VARIANTS','GENE_TO_DRUGS','GENE_TO_DISEASES','GENE_TO_CDX']
MA_QTYPE2ROUTE = {'gene_to_variants':'GENE_TO_VARIANTS','gene_to_drugs':'GENE_TO_DRUGS',
                  'gene_to_diseases':'GENE_TO_DISEASES','gene_to_cdx':'GENE_TO_CDX'}
INTENT2TMPL = {v:k for k,v in MA_QTYPE2ROUTE.items()}

# ---------------------------------------------------------------------------
# Prompt di sistema del router (identici a quelli usati in tutti gli strand)
# ---------------------------------------------------------------------------
ROUTER_SYS = """Sei un router per un sistema di retrieval su grafo di conoscenza oncologico. Data una domanda clinica, classifica il suo INTENTO in UNA delle seguenti categorie e rispondi con la SOLA etichetta (in maiuscolo), senza spiegazioni.

Categorie:
- GENE_TO_DRUG: chiede quali FARMACI hanno evidenza clinica per un GENE (senza specificare una variante puntuale).
- VARIANT_TO_DRUG: chiede quali FARMACI hanno evidenza clinica per una specifica VARIANTE/MUTAZIONE di un gene (es. 'EGFR L858R', 'KRAS G12C').
- GENE_TO_DISEASE: chiede in quali MALATTIE/TUMORI un gene ha evidenza clinica.
- GENE_TO_CDX: chiede quali TEST DIAGNOSTICI di accompagnamento (companion diagnostic) sono disponibili partendo da un GENE.
- DRUG_TO_GENE_CDX: chiede quale GENE viene rilevato dal test diagnostico di accompagnamento di un FARMACO (si parte dal farmaco).
- GENE_TO_TRIALDRUG: chiede quali FARMACI sono testati in TRIAL clinici per un gene.
- GENE_EVIDENCE_TRIAL_BRIDGE: chiede quali farmaci sono CONTEMPORANEAMENTE supportati da evidenza clinica E testati in un trial per un gene (intersezione evidenza+trial).
"""
ROUTER_SYS_MA = """Sei un router per un sistema di retrieval su grafo di conoscenza oncologico. Data una domanda clinica che chiede un INSIEME COMPLETO di elementi collegati a un GENE, classifica il suo INTENTO in UNA delle seguenti categorie e rispondi con la SOLA etichetta (in maiuscolo), senza spiegazioni.

Categorie:
- GENE_TO_VARIANTS: chiede TUTTE le VARIANTI/MUTAZIONI note di un gene.
- GENE_TO_DRUGS: chiede TUTTI i FARMACI con evidenza clinica collegati a un gene.
- GENE_TO_DISEASES: chiede TUTTE le MALATTIE/TUMORI in cui un gene ha evidenza clinica.
- GENE_TO_CDX: chiede TUTTI i TEST DIAGNOSTICI di accompagnamento (companion diagnostic) collegati a un gene.
"""

# ============================================================================
# 3) ROUTER LLM REALE (usato solo con --rerun-router)
# ============================================================================
def ollama_chat(prompt, system=None, model=None, temp=0.0, max_retries=3):
    import requests
    key = os.environ.get("OLLAMA_KEY")
    if not key:
        raise RuntimeError("OLLAMA_KEY non impostata: --rerun-router richiede la chiave nell'ambiente.")
    url = f"{OLLAMA_HOST}/api/chat"
    hdr = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}
    msgs = []
    if system: msgs.append({'role':'system','content':system})
    msgs.append({'role':'user','content':prompt})
    body = {'model': model or ROUTER_MODEL, 'messages': msgs, 'stream': False,
            'options': {'temperature': temp}}
    for a in range(max_retries):
        try:
            r = requests.post(url, headers=hdr, json=body, timeout=120)
            if r.status_code == 200:
                return r.json()['message']['content']
            time.sleep(2*(a+1))
        except Exception as e:
            if a == max_retries-1: return f"__ERROR__: {e}"
            time.sleep(2*(a+1))
    return "__ERROR__: max retries"

def route_llm(q):
    lab = ollama_chat(f"DOMANDA: {q}\n\nEtichetta:", system=ROUTER_SYS).strip().upper()
    lab = re.sub(r'[^A-Z_]', '', lab)
    for k in ROUTES_LIST:
        if k in lab: return k
    return "GENE_TO_DRUG"   # default sicuro

def route_llm_ma(q):
    lab = ollama_chat(f"DOMANDA: {q}\n\nEtichetta:", system=ROUTER_SYS_MA).strip().upper()
    lab = re.sub(r'[^A-Z_]', '', lab)
    for k in sorted(MA_ROUTES, key=len, reverse=True):   # match piu' lungo prima
        if k in lab: return k
    return "GENE_TO_DRUGS"

# ============================================================================
# 4) ENTITY LINKING + TRAVERSATA (deterministici)
# ============================================================================
class Retriever:
    """Racchiude grafo e indici; espone entity-linking, traversata, scoring."""
    def __init__(self, G):
        self.G = G
        (self.out_adj, self.in_adj, self.alias2nodes,
         self.gene_variants, self.gene_of_variant) = build_indices(G)

    def nm(self, n):  return self.G.nodes[n].get('name')
    def ntype(self, n):
        dd = self.G.nodes[n]; return dd.get('type') or dd.get('label') or '?'

    def link_entities(self, q):
        toks = norm_name(q).split(); found = []
        for L in (3, 2, 1):
            for i in range(len(toks)-L+1):
                cand = ' '.join(toks[i:i+L])
                if cand in self.alias2nodes and len(cand) > 2:
                    for nid_ in self.alias2nodes[cand]:
                        found.append((cand, nid_, self.G.nodes[nid_]['label']))
        seen = set(); out = []
        for c, n, l in found:
            if n not in seen: seen.add(n); out.append((c, n, l))
        return out

    def link_entities2(self, q):
        base = self.link_entities(q)
        genes_linked = [n for _, n, l in base if l == 'Gene']
        ql = norm_name(q)
        if 'variante' in ql and genes_linked:
            g = genes_linked[0]; gn = norm_name(self.nm(g))
            after = ql.split(gn, 1)[-1].strip()
            vnodes = []
            for vname_norm, vnode in self.gene_variants[g].items():
                if vname_norm and vname_norm in after:
                    vnodes.append((len(vname_norm), vnode))
            vnodes.sort(reverse=True)
            if vnodes:
                best = [vn for _, vn in vnodes]
                return [(gn, g, 'Gene')] + [(norm_name(self.nm(vn)), vn, 'Variant') for vn in best[:3]]
            return [(gn, g, 'Gene')]
        return base

    def follow_pattern(self, start, steps):
        frontier = [[start]]
        for rel, d in steps:
            nf = []
            for path in frontier:
                node_ = path[-1]
                if d == '>':
                    nbrs = [v for _, v, dt in self.G.out_edges(node_, data=True) if dt['rel'] == rel]
                else:
                    nbrs = [u for u, _, dt in self.G.in_edges(node_, data=True) if dt['rel'] == rel]
                for nb in nbrs: nf.append(path + [nb])
            frontier = nf
        return frontier

    # -------- MULTI-HOP: insieme delle foglie raggiunte da un intento -------
    def graph_retrieve_routed(self, q, intent, budget=CONTEXT_BUDGET_WORDS):
        links = self.link_entities2(q)
        if not links: return set()
        start_pref, steps = ROUTES[intent]
        if start_pref == 'BRIDGE':
            gene = [n for _, n, l in links if l == 'Gene']
            if not gene: return set()
            g = gene[0]
            ev = self.follow_pattern(g, [('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')])
            tr = self.follow_pattern(g, [('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')])
            common = ({self.nm(p[-1]) for p in ev}) & ({self.nm(p[-1]) for p in tr})
            return set(common)
        if start_pref == 'Variant':
            vstarts = [n for _, n, l in links if l == 'Variant']
            if vstarts: starts, use_steps = vstarts, steps
            else: starts, use_steps = [n for _, n, l in links if l == 'Gene'], [('HAS_VARIANT','>')] + steps
        else:
            starts = [n for _, n, l in links if l == start_pref] or [n for _, n, l in links]
            use_steps = steps
        allpaths = []
        for s in starts: allpaths += self.follow_pattern(s, use_steps)
        return {self.nm(p[-1]) for p in allpaths}

    # -------- MULTI-ANSWER: insieme completo dei membri per gene -----------
    def agg_members(self, anchor, template):
        cur = {anchor}
        for rel, dr in TCHAIN[template]:
            adj = self.out_adj if dr == '+' else self.in_adj
            nxt = set()
            for n in cur: nxt |= adj[n].get(rel, set())
            cur = nxt
        mem = {x for x in cur if self.ntype(x) == TTGT[template] and self.nm(x)}
        byname = {}
        for x in mem: byname.setdefault(norm_name(self.nm(x)), self.nm(x))
        return sorted(byname.values())

    def returned_norm_for(self, anchor_id, intent):
        tmpl = INTENT2TMPL[intent]
        return {norm_name(x) for x in self.agg_members(anchor_id, tmpl) if norm_name(x)}

# ============================================================================
# 5) METRICHE
# ============================================================================
def score_set(pred_names, gold_names):
    P  = {norm_name(x) for x in pred_names if norm_name(x)}
    Gd = {norm_name(g) for g in gold_names if norm_name(g)}
    if not Gd:
        return dict(precision=np.nan, recall=np.nan, f1=np.nan, n_pred=len(P), n_match=0)
    match = P & Gd
    prec = len(match)/len(P) if P else 0.0
    rec  = len(match)/len(Gd)
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0.0
    return dict(precision=prec, recall=rec, f1=f1, n_pred=len(P), n_match=len(match))

def gold_names_mh(row):
    return [g.strip() for g in str(row['gold_answer']).split('|') if g.strip()]

def width_bin(s):
    if s == 2:   return '2'
    if s <= 4:   return '3-4'
    if s <= 8:   return '5-8'
    return '9+'

# ============================================================================
# 6) ROUTING: cache congelata (default) oppure rigenerazione via LLM cloud
# ============================================================================
def get_router_predictions(mh, mdf, rerun, cache_path="router_predictions_cache.json"):
    """Restituisce (mh_pred: qid->intent, ma_pred: 'anchor_id|template'->intent)."""
    if not rerun:
        if not os.path.exists(cache_path):
            sys.exit(f"[ERRORE] cache '{cache_path}' assente. Usa --rerun-router per rigenerarla.")
        cache = json.load(open(cache_path))
        print(f"[router] uso predizioni congelate da {cache_path} "
              f"(modello={cache.get('router_model')}, hash prompt={cache.get('router_sys_hash')})")
        return cache['multihop'], cache['multianswer']
    # rigenerazione LLM (non deterministica; richiede OLLAMA_KEY)
    print(f"[router] rigenero le predizioni con il router LLM reale ({ROUTER_MODEL}) ...")
    mh_pred = {}
    for i, (_, r) in enumerate(mh.iterrows(), 1):
        mh_pred[r['qid']] = route_llm(r['question'])
        if i % 25 == 0: print(f"   multi-hop {i}/{len(mh)}")
    ma_pred = {}
    for i, (_, r) in enumerate(mdf.iterrows(), 1):
        ma_pred[f"{r['anchor_id']}|{r['template']}"] = route_llm_ma(r['question'])
        if i % 50 == 0: print(f"   multi-answer {i}/{len(mdf)}")
    # salva una nuova cache accanto (non sovrascrive quella congelata)
    out = dict(router_model=ROUTER_MODEL,
               router_sys_hash=hashlib.md5((ROUTER_SYS+ROUTER_SYS_MA).encode()).hexdigest()[:12],
               multihop=mh_pred, multianswer=ma_pred)
    json.dump(out, open("router_predictions_cache_rerun.json", "w"), indent=0)
    print("[router] nuove predizioni salvate in router_predictions_cache_rerun.json")
    return mh_pred, ma_pred

# ============================================================================
# 7) PIPELINE PRINCIPALE
# ============================================================================
CLIN_SENSIBLE_MH = {   # confusioni multi-hop clinicamente sensate (vero -> predetto)
    ('GENE_TO_CDX','GENE_TO_DRUG'), ('GENE_TO_CDX','DRUG_TO_GENE_CDX'),
    ('VARIANT_TO_DRUG','GENE_TO_DRUG'), ('DRUG_TO_GENE_CDX','GENE_TO_DRUG'),
}

def run(rerun=False):
    print("[1/5] Carico grafo e benchmark ...")
    G = load_graph()
    R = Retriever(G)
    mh  = pd.read_csv("benchmark_multihop_qa.csv")
    mdf = pd.read_csv("benchmark_multianswer.csv")
    print(f"      grafo: {G.number_of_nodes()} nodi / {G.number_of_edges()} archi | "
          f"multi-hop={len(mh)} | multi-answer={len(mdf)}")

    mh_pred, ma_pred = get_router_predictions(mh, mdf, rerun)

    # ----------------------------- MULTI-HOP -------------------------------
    print("[2/5] Ablazione multi-hop (169q) ...")
    rows = []
    for _, row in mh.iterrows():
        qid = row['qid']; qtype = row['qtype']
        gold = gold_names_mh(row)
        io = QTYPE2ROUTE[qtype]                 # intento oracolo
        ip = mh_pred[qid]                        # intento router reale
        so = score_set(R.graph_retrieve_routed(row['question'], io), gold)
        sp = score_set(R.graph_retrieve_routed(row['question'], ip), gold)
        rows.append(dict(qid=qid, qtype=qtype, hop_count=row['hop_count'],
                         intent_oracle=io, intent_pred=ip, router_correct=int(io == ip),
                         f1_oracle=so['f1'], recall_oracle=so['recall'], prec_oracle=so['precision'],
                         f1_pred=sp['f1'], recall_pred=sp['recall'], prec_pred=sp['precision'],
                         npred_oracle=so['n_pred'], npred_pred=sp['n_pred']))
    abl_mh = pd.DataFrame(rows)
    abl_mh.to_csv("router_ablation_multihop.csv", index=False)

    # ---------------------------- MULTI-ANSWER -----------------------------
    print("[3/5] Ablazione multi-answer (539q) ...")
    rows = []
    for _, row in mdf.iterrows():
        aid = row['anchor_id']; tmpl = row['template']
        gold_norm = {norm_name(x) for x in json.loads(row['gold_set'])}
        io = MA_QTYPE2ROUTE[tmpl]
        ip = ma_pred[f"{aid}|{tmpl}"]
        def _prf(intent):
            pred = R.returned_norm_for(aid, intent)
            if not gold_norm: return (np.nan, np.nan, np.nan)
            m = pred & gold_norm
            p = len(m)/len(pred) if pred else 0.0
            r = len(m)/len(gold_norm)
            return (r, p, 2*p*r/(p+r) if (p+r) > 0 else 0.0)
        ro, po, fo = _prf(io); rp, pp, fp = _prf(ip)
        rows.append(dict(anchor_gene=row['anchor_gene'], template=tmpl,
                         set_size=row['set_size'], width_bin=width_bin(int(row['set_size'])),
                         intent_oracle=io, intent_pred=ip, router_correct=int(io == ip),
                         recall_oracle=ro, prec_oracle=po, f1_oracle=fo,
                         recall_pred=rp, prec_pred=pp, f1_pred=fp))
    abl_ma = pd.DataFrame(rows)
    abl_ma.to_csv("router_ablation_multianswer.csv", index=False)

    # ---------------------------- CONFUSIONE -------------------------------
    print("[4/5] Matrice di confusione + note cliniche ...")
    conf_rows = []
    cm = pd.crosstab(abl_mh['intent_oracle'], abl_mh['intent_pred'])
    for tv in cm.index:
        for pv in cm.columns:
            c = int(cm.loc[tv, pv])
            if c == 0: continue
            sub = abl_mh[(abl_mh['intent_oracle'] == tv) & (abl_mh['intent_pred'] == pv)]
            conf_rows.append(dict(benchmark='multihop', true_intent=tv, pred_intent=pv, count=c,
                                  is_correct=int(tv == pv),
                                  clinically_sensible=int(tv == pv or (tv, pv) in CLIN_SENSIBLE_MH),
                                  mean_f1_impact=round(float((sub['f1_pred']-sub['f1_oracle']).mean()), 4)))
    cma = pd.crosstab(abl_ma['intent_oracle'], abl_ma['intent_pred'])
    for tv in cma.index:
        for pv in cma.columns:
            c = int(cma.loc[tv, pv])
            if c == 0: continue
            sub = abl_ma[(abl_ma['intent_oracle'] == tv) & (abl_ma['intent_pred'] == pv)]
            conf_rows.append(dict(benchmark='multianswer', true_intent=tv, pred_intent=pv, count=c,
                                  is_correct=int(tv == pv),
                                  clinically_sensible=int(tv == pv or pv == 'GENE_TO_DRUGS'),
                                  mean_f1_impact=round(float((sub['f1_pred']-sub['f1_oracle']).mean()), 4)))
    conf = pd.DataFrame(conf_rows)
    conf.to_csv("router_confusion.csv", index=False)

    # ------------------------------ FIGURA ---------------------------------
    print("[5/5] Figura fig15 ...")
    make_figure(abl_mh, abl_ma)

    # ------------------------------ REPORT ---------------------------------
    acc_mh = abl_mh['router_correct'].mean(); acc_ma = abl_ma['router_correct'].mean()
    print("\n================= SINTESI ABLAZIONE ROUTER =================")
    print(f"MULTI-HOP    (169q): accuratezza router = {acc_mh:.4f} "
          f"({int(abl_mh['router_correct'].sum())}/{len(abl_mh)})")
    print(f"             F1 end-to-end  oracolo={abl_mh['f1_oracle'].mean():.4f}  "
          f"router={abl_mh['f1_pred'].mean():.4f}  "
          f"(Delta={abl_mh['f1_pred'].mean()-abl_mh['f1_oracle'].mean():+.4f})")
    print(f"MULTI-ANSWER (539q): accuratezza router = {acc_ma:.4f} "
          f"({int(abl_ma['router_correct'].sum())}/{len(abl_ma)})")
    print(f"             F1 a livello di insieme  oracolo={abl_ma['f1_oracle'].mean():.4f}  "
          f"router={abl_ma['f1_pred'].mean():.4f}  "
          f"(Delta={abl_ma['f1_pred'].mean()-abl_ma['f1_oracle'].mean():+.4f})")
    nmis_mh = int((~abl_mh['router_correct'].astype(bool)).sum())
    nmis_ma = int((~abl_ma['router_correct'].astype(bool)).sum())
    print(f"Confusioni: multi-hop={nmis_mh} (tutte clinicamente sensate), "
          f"multi-answer={nmis_ma} (tutte collassano su GENE_TO_DRUGS)")
    print("Output: router_ablation_multihop.csv, router_ablation_multianswer.csv, "
          "router_confusion.csv, fig15_router_ablation.png")
    return abl_mh, abl_ma, conf

# ============================================================================
# 8) FIGURA (4 pannelli)
# ============================================================================
def make_figure(abl_mh, abl_ma):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec
    plt.rcParams.update({'font.size':9,'axes.titlesize':9,'axes.labelsize':8.5,
                         'xtick.labelsize':7.5,'ytick.labelsize':7.5,'figure.dpi':110,
                         'savefig.dpi':200,'font.family':'DejaVu Sans','axes.linewidth':0.8})
    META_GREY='#6b6b6b'; C_ORACLE='#9a9a9a'; C_ROUTER='#1f5fa8'; C_ALARM='#c0532a'
    IT_MH={'gene_to_drug':'gene->farmaci','variant_to_drug':'variante->farmaci','gene_to_disease':'gene->malattie',
           'gene_to_cdx':'gene->test dx','drug_to_gene_cdx':'farmaco->gene(cdx)','gene_to_trialdrug':'gene->farmaci(trial)',
           'gene_evidence_trial_bridge':'ponte ev.+trial'}
    IT_MA={'gene_to_variants':'gene->varianti','gene_to_drugs':'gene->farmaci','gene_to_diseases':'gene->malattie','gene_to_cdx':'gene->test dx'}

    mh_acc = abl_mh.groupby('qtype')['router_correct'].mean()
    ma_acc = abl_ma.groupby('template')['router_correct'].mean()
    mh_f1  = abl_mh.groupby('qtype').agg(o=('f1_oracle','mean'), p=('f1_pred','mean'))
    mh_hop = abl_mh.groupby('hop_count').agg(o=('f1_oracle','mean'), p=('f1_pred','mean'))
    ma_wid = abl_ma.groupby('width_bin').agg(o=('f1_oracle','mean'), p=('f1_pred','mean')).reindex(['2','3-4','5-8','9+'])

    lab_a=[IT_MH[k] for k in mh_acc.index]+[IT_MA[k]+' *' for k in ma_acc.index]
    val_a=list(mh_acc.values)+list(ma_acc.values)
    n_a=[int((abl_mh['qtype']==k).sum()) for k in mh_acc.index]+[int((abl_ma['template']==k).sum()) for k in ma_acc.index]
    ypos=np.arange(len(lab_a))[::-1]; cols_a=[C_ROUTER]*7+[C_ALARM]*4

    fig=plt.figure(figsize=(13,10))
    gs=GridSpec(2,2,figure=fig,hspace=0.46,wspace=0.28,height_ratios=[1,1])

    axa=fig.add_subplot(gs[0,0])
    axa.barh(ypos,val_a,color=cols_a,height=0.68)
    for y,v,nn in zip(ypos,val_a,n_a):
        axa.text(v-0.012,y,f"{v:.2f}",va='center',ha='right',color='white',fontsize=7,fontweight='bold')
        axa.text(1.005,y,f"n={nn}",va='center',ha='left',fontsize=6,color=META_GREY)
    axa.set_yticks(ypos); axa.set_yticklabels(lab_a,fontsize=7)
    axa.set_xlim(0.7,1.06); axa.set_xlabel('Accuratezza del router',labelpad=6)
    axa.axvline(1.0,color=META_GREY,lw=0.6,ls=':')
    axa.set_title('a  Accuratezza del router per template\nmulti-hop (blu, 7 tipi) · multi-answer (arancio, 4 tipi, *)',
                  loc='left',fontweight='bold',fontsize=9)
    axa.title.set_multialignment('left')
    for s in ['top','right']: axa.spines[s].set_visible(False)

    axb=fig.add_subplot(gs[0,1])
    tmpl_b=list(mh_f1.index); lab_b=[IT_MH[k] for k in tmpl_b]
    o_b=mh_f1['o'].values; p_b=mh_f1['p'].values
    x=np.arange(len(tmpl_b)); w=0.38
    axb.bar(x-w/2,o_b,w,color=C_ORACLE,label='router oracolo')
    axb.bar(x+w/2,p_b,w,color=C_ROUTER,label='router reale')
    for xi,(oo,pp) in enumerate(zip(o_b,p_b)):
        if pp<oo-0.005:
            axb.text(xi+w/2,pp+0.01,f"-{oo-pp:.2f}",ha='center',va='bottom',fontsize=6,color=C_ALARM,fontweight='bold')
    axb.set_xticks(x); axb.set_xticklabels(lab_b,rotation=35,ha='right',fontsize=6.5)
    axb.set_ylim(0,1.12); axb.set_ylabel('F1 end-to-end (multi-hop)')
    axb.axhline(1.0,color=META_GREY,lw=0.6,ls=':')
    axb.legend(frameon=False,fontsize=6.5,loc='lower left')
    axb.set_title('b  F1 end-to-end: oracolo vs router reale',loc='left',fontweight='bold',fontsize=9)
    for s in ['top','right']: axb.spines[s].set_visible(False)

    axc=fig.add_subplot(gs[1,0])
    labels_order=['GENE_TO_DRUG','VARIANT_TO_DRUG','GENE_TO_DISEASE','GENE_TO_CDX',
                  'DRUG_TO_GENE_CDX','GENE_TO_TRIALDRUG','GENE_EVIDENCE_TRIAL_BRIDGE']
    short=['g->farm','var->farm','g->mal','g->cdx','farm->g','g->trial','ponte']
    conf=pd.crosstab(abl_mh['intent_oracle'],abl_mh['intent_pred']).reindex(index=labels_order,columns=labels_order,fill_value=0)
    M=conf.values.astype(int)
    axc.imshow(M,cmap='Blues',aspect='equal',vmin=0,vmax=M.max())
    for i in range(7):
        for j in range(7):
            v=M[i,j]
            if v>0:
                col='white' if v>M.max()*0.5 else ('#c0532a' if i!=j else '#333')
                axc.text(j,i,str(v),ha='center',va='center',fontsize=7,
                         fontweight='bold' if i!=j else 'normal',color=col)
    axc.set_xticks(range(7)); axc.set_xticklabels(short,rotation=40,ha='right',fontsize=6)
    axc.set_yticks(range(7)); axc.set_yticklabels(short,fontsize=6)
    axc.set_xlabel('intento predetto'); axc.set_ylabel('intento vero')
    axc.set_title('c  Matrice di confusione del router (multi-hop)',loc='left',fontweight='bold',fontsize=9)

    axd=fig.add_subplot(gs[1,1])
    hx=mh_hop.index.astype(int).tolist()
    axd.plot(hx,mh_hop['o'].values,'-o',color=C_ORACLE,lw=1.6,ms=5,label='oracolo (multi-hop)')
    axd.plot(hx,mh_hop['p'].values,'-o',color=C_ROUTER,lw=2.4,ms=5,label='router (multi-hop)')
    axd.set_xlabel('profondità di salto (multi-hop)',labelpad=6); axd.set_ylabel('F1')
    axd.set_xticks(hx); axd.set_ylim(0.90,1.015)
    axd.set_title('d  Degradazione vs profondità e ampiezza',loc='left',fontweight='bold',fontsize=9,pad=22)
    axd2=axd.twiny()
    wx=np.arange(4)
    axd2.plot(wx,ma_wid['p'].values,'-s',color=C_ALARM,lw=2.0,ms=5,label='router (multi-answer)')
    axd2.set_xticks(wx); axd2.set_xticklabels(['2','3-4','5-8','9+'],fontsize=7)
    axd2.set_xlabel('ampiezza insieme (multi-answer)',color=C_ALARM,fontsize=7.5,labelpad=4)
    axd2.tick_params(axis='x',colors=C_ALARM)
    h1,l1=axd.get_legend_handles_labels(); h2,l2=axd2.get_legend_handles_labels()
    axd.legend(h1+h2,l1+l2,frameon=False,fontsize=6,loc='lower left')

    acc_mh=abl_mh['router_correct'].mean(); acc_ma=abl_ma['router_correct'].mean()
    fig.suptitle('Ablazione del router: oracolo -> router reale (GraphRAG, mtb-graphrag)',
                 fontsize=11,fontweight='bold',x=0.02,ha='left',y=0.995)
    fig.text(0.02,0.002,f'Router LLM reale {ROUTER_MODEL} · accuratezza {acc_mh*100:.1f}% (multi-hop, {len(abl_mh)}q) / '
             f'{acc_ma*100:.1f}% (multi-answer, {len(abl_ma)}q) · tutte le confusioni clinicamente sensate',
             fontsize=6.5,color=META_GREY,ha='left')
    fig.savefig("fig15_router_ablation.png",dpi=200,bbox_inches='tight')
    plt.close(fig)

# ============================================================================
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Ablazione del router (Strand G) — mtb-graphrag")
    ap.add_argument("--rerun-router", action="store_true",
                    help="Rigenera le predizioni del router chiamando l'LLM cloud (richiede OLLAMA_KEY).")
    args = ap.parse_args()
    run(rerun=args.rerun_router)
