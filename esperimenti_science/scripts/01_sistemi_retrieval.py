"""
01_sistemi_retrieval.py
=======================
Definizione riproducibile dei due sistemi di retrieval confrontati nella tesi
mtb-graphrag (Molecular Tumor Board GraphRAG):

  * RAG testuale   -> denso (all-MiniLM-L6-v2), BM25, ibrido
  * GraphRAG       -> entity linking + traversal del grafo, con due router:
                        - route_pattern()  (router a parole chiave, storico)
                        - route_llm()      (router semantico a intenti, robusto)

Il modulo NON ricostruisce il grafo dai CSV: carica i checkpoint gia' prodotti
(kb_graph.gpickle, rag_corpus.pkl, corpus_emb.npy). Il grafo in memoria e' un
networkx.MultiDiGraph con 43.005 nodi (9 tipi) e 55.544 archi (11 tipi).

Il modello lettore e' servito via Ollama Cloud (host https://ollama.com); la
chiave va fornita nella variabile d'ambiente OLLAMA_API_KEY. Nessuna chiave e'
inclusa in questo file.

Dipendenze: networkx, pandas, numpy, sentence-transformers, rank-bm25,
scikit-learn, requests. Python 3.12.
"""
import os, re, time, pickle, requests
import numpy as np, pandas as pd, networkx as nx
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import minmax_scale

# ----------------------------------------------------------------------------
# Configurazione
# ----------------------------------------------------------------------------
CONTEXT_BUDGET_WORDS = 900
READER_MODEL         = 'gemma3:27b'
OLLAMA_HOST          = "https://ollama.com"
OLLAMA_KEY           = os.environ.get("OLLAMA_API_KEY", "")

# ----------------------------------------------------------------------------
# Caricamento checkpoint (grafo, corpus, embedding)
# ----------------------------------------------------------------------------
def load_checkpoints(graph_path="kb_graph.gpickle",
                     corpus_path="rag_corpus.pkl",
                     emb_path="corpus_emb.npy"):
    with open(graph_path, "rb") as f:
        G = pickle.load(f)
    corpus = pd.read_pickle(corpus_path)
    emb    = np.load(emb_path)
    texts  = corpus["text"].tolist()
    pids   = corpus["passage_id"].tolist()
    return G, corpus, emb, texts, pids

# Indici di supporto (adiacenza, alias, mappe variante->gene) costruiti dal grafo
def build_indices(G):
    from collections import defaultdict
    OUT = defaultdict(list); IN = defaultdict(list)
    for u, v, d in G.edges(data=True):
        OUT[u].append((d["rel"], v)); IN[v].append((d["rel"], u))
    alias2nodes = defaultdict(list)
    for n, d in G.nodes(data=True):
        nm = norm_name(d.get("name", ""))
        if nm: alias2nodes[nm].append(n)
        for a in str(d.get("aliases", "")).split(";"):
            a = norm_name(a)
            if a: alias2nodes[a].append(n)
    return OUT, IN, alias2nodes


# ============================================================================
# Funzioni dei sistemi
# ============================================================================

def norm_name(s): return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()


def tok(s): return [w for w in ''.join(c.lower() if c.isalnum() else ' ' for c in s).split() if len(w)>1]


def node(nid_): return G.nodes[nid_]


def name(nid_):
    d=G.nodes[nid_]; return d.get('name') or d.get('nct_id') or d.get('pmid') or str(nid_)


def retrieve_dense(q, k=200):
    qv=emb_model.encode([q], normalize_embeddings=True)[0]
    sims=emb@qv; top=np.argsort(-sims)[:k]
    return [(int(i),float(sims[i])) for i in top]


def retrieve_bm25(q, k=200):
    scores=bm25.get_scores(tok(q)); top=np.argsort(-scores)[:k]
    return [(int(i),float(scores[i])) for i in top]


def retrieve_hybrid(q, k=200):
    qv=emb_model.encode([q], normalize_embeddings=True)[0]
    d=emb@qv; b=bm25.get_scores(tok(q))
    h=0.5*minmax_scale(d)+0.5*minmax_scale(b); top=np.argsort(-h)[:k]
    return [(int(i),float(h[i])) for i in top]


def pack_context(ranked, budget=CONTEXT_BUDGET_WORDS):
    used=[]; words=0; chunks=[]
    for i,_ in ranked:
        t=texts[i]; w=len(t.split())
        if words+w>budget and used: break
        chunks.append(f"[{pids[i]}] {t}"); used.append(i); words+=w
        if words>=budget: break
    return "\n".join(chunks), used


def link_entities(q):
    toks=norm_name(q).split(); found=[]
    for L in (3,2,1):
        for i in range(len(toks)-L+1):
            cand=' '.join(toks[i:i+L])
            if cand in alias2nodes and len(cand)>2:
                for nid_ in alias2nodes[cand]:
                    found.append((cand,nid_,G.nodes[nid_]['label']))
    seen=set(); out=[]
    for c,n,l in found:
        if n not in seen: seen.add(n); out.append((c,n,l))
    return out


def link_entities2(q):
    base=link_entities(q)
    genes_linked=[n for _,n,l in base if l=='Gene']
    ql=norm_name(q)
    if any(t in ql for t in _VARIANT_TRIGGERS) and genes_linked:
        g=genes_linked[0]; gn=norm_name(name(g)); after=ql.split(gn,1)[-1].strip()
        vnodes=[]
        for vname_norm,vnode in gene_variants[g].items():
            if vname_norm and vname_norm in after: vnodes.append((len(vname_norm),vnode))
        vnodes.sort(reverse=True)
        if vnodes:
            best=[vn for _,vn in vnodes]
            return [(gn,g,'Gene')]+[(norm_name(name(vn)),vn,'Variant') for vn in best[:3]]
        else:
            return [(gn,g,'Gene')]
    return base


def route_pattern(q):
    ql=q.lower()
    if 'companion' in ql or 'accompagnamento' in ql:
        if 'gene' in ql and ('rilev' in ql or 'quale gene' in ql):
            return ('Drug',[('HAS_COMPANION_DIAGNOSTIC','>'),('DIAGNOSES_GENE','>')])
        return ('Gene',[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>'),('HAS_COMPANION_DIAGNOSTIC','>')])
    if 'trial' in ql and 'evidenza' in ql: return ('BRIDGE',None)
    if 'trial' in ql: return ('Gene',[('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')])
    if 'malatti' in ql: return ('Gene',[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('HAS_DISEASE','>')])
    if any(t in ql for t in _VARIANT_TRIGGERS): return ('Variant',[('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')])
    return ('Gene',[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')])


def follow_pattern(start, steps):
    frontier=[[start]]
    for rel,d in steps:
        nf=[]
        for path in frontier:
            node_=path[-1]
            if d=='>': nbrs=[v for _,v,dt in G.out_edges(node_,data=True) if dt['rel']==rel]
            else:      nbrs=[u for u,_,dt in G.in_edges(node_,data=True) if dt['rel']==rel]
            for nb in nbrs: nf.append(path+[nb])
        frontier=nf
    return frontier


def serialize_path(path_nodes, path_rels):
    parts=[name(path_nodes[0])]
    for i,(rel,d) in enumerate(path_rels):
        rl=rel.lower().replace('_',' ')
        parts.append(f"—{rl}→" if d=='>' else f"←{rl}—"); parts.append(name(path_nodes[i+1]))
    return " ".join(parts)


def serialize_path_compact(pn, pr):
    labels=[G.nodes[n]['label'] for n in pn]; nm=[name(n) for n in pn]
    rels=[r for r,_ in pr]; leaf=labels[-1]; start=labels[0]
    def var_q(vnode):
        gg=gene_of_variant.get(vnode); return f"{name(gg)} {name(vnode)}" if gg else name(vnode)
    if start=='Variant' and leaf=='Drug':
        return f"La variante {var_q(pn[0])} è collegata, tramite evidenza clinica documentata, al farmaco {nm[-1]}."
    if start=='Variant' and leaf=='Disease':
        return f"La variante {var_q(pn[0])} presenta evidenza clinica nella malattia {nm[-1]}."
    if start=='Gene' and leaf=='Drug' and 'HAS_EVIDENCE' in rels:
        return f"Il gene {nm[0]} è collegato, tramite evidenza clinica documentata, al farmaco {nm[-1]}."
    if start in ('Gene','Variant') and leaf=='Disease':
        return f"Il {start.lower()} {nm[0]} presenta evidenza clinica nella malattia {nm[-1]}."
    if start=='Drug' and leaf=='Gene' and 'DIAGNOSES_GENE' in rels:
        return f"Il farmaco {nm[0]} ha un test diagnostico di accompagnamento che rileva il gene {nm[-1]}."
    if start=='Gene' and leaf=='Drug' and 'TESTS_DRUG' in rels:
        return f"Il gene {nm[0]} è associato a un trial clinico che testa il farmaco {nm[-1]}."
    if leaf=='CompanionDiagnostic':
        return f"Il gene {nm[0]} è collegato, tramite farmaco con evidenza clinica, al test diagnostico {nm[-1]}."
    return serialize_path(pn,pr)


def graph_retrieve(q, budget=CONTEXT_BUDGET_WORDS):
    links=link_entities2(q)
    if not links: return "", [], []
    start_pref, steps = route_pattern(q)
    if start_pref=='BRIDGE':
        gene=[n for _,n,l in links if l=='Gene']
        if not gene: return "",[],[]
        g=gene[0]
        ev=follow_pattern(g,[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')])
        tr=follow_pattern(g,[('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')])
        common=({name(p[-1]) for p in ev})&({name(p[-1]) for p in tr})
        facts=[f"Il farmaco {c} è supportato da evidenza clinica ED è testato in un trial clinico per il gene {name(g)}." for c in sorted(common)]
        ctx=[];words=0
        for f in facts:
            w=len(f.split())
            if words+w>budget and ctx: break
            ctx.append(f);words+=w
        return "\n".join(ctx),list(common),facts
    if start_pref=='Variant':
        vstarts=[n for _,n,l in links if l=='Variant']
        if vstarts: starts=vstarts; use_steps=steps
        else: starts=[n for _,n,l in links if l=='Gene']; use_steps=[('HAS_VARIANT','>')]+steps
    else:
        starts=[n for _,n,l in links if l==start_pref] or [n for _,n,l in links]; use_steps=steps
    allpaths=[]
    for s in starts: allpaths+=follow_pattern(s,use_steps)
    ctx=[];words=0;seen=set();visited=set()
    for path in allpaths:
        s=serialize_path_compact(path,[(r,d) for r,d in use_steps])
        if s in seen: continue
        seen.add(s);w=len(s.split())
        if words+w>budget and ctx: break
        ctx.append(s);words+=w;visited.update(path)
    return "\n".join(ctx),list(visited),allpaths


def ollama_chat(prompt, model=None, temp=0.0, max_retries=3):
    m = model if model is not None else READER_MODEL
    url=f"{OLLAMA_HOST}/api/chat"
    hdr={'Authorization':f'Bearer {OLLAMA_KEY}','Content-Type':'application/json'}
    body={'model':m,'messages':[{'role':'user','content':prompt}],'stream':False,'options':{'temperature':temp}}
    last=""
    for a in range(max_retries):
        try:
            r=requests.post(url,headers=hdr,json=body,timeout=120)
            if r.status_code==200: return r.json()['message']['content']
            last=f"HTTP {r.status_code}: {r.text[:200]}"; time.sleep(2*(a+1))
        except Exception as e:
            last=str(e); time.sleep(2*(a+1))
    return f"__ERROR__: {last}"


def reader_answer(q, context): return ollama_chat(READER_TMPL.format(context=context, question=q))


def parse_pred(pred):
    if pred is None or pred.startswith('__ERROR__'): return []
    pred=re.sub(r'(?i)non determinabile','',pred)
    parts=re.split(r'[,\n;|]+', pred)
    return [norm_name(p) for p in parts if norm_name(p)]


def score_answer(pred, gold_names):
    P=set(parse_pred(pred)); Gnorm={norm_name(g) for g in gold_names}
    tp=0; matched=set()
    for g in Gnorm:
        for p in P:
            if g==p or g in p or p in g: tp+=1; matched.add(g); break
    prec=tp/len(P) if P else 0.0; rec=len(matched)/len(Gnorm) if Gnorm else 0.0
    f1=2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
    em=1.0 if matched==Gnorm and len(P)>0 else 0.0
    return dict(precision=prec, recall=rec, f1=f1, exact=em, n_pred=len(P), n_match=len(matched))


def retrieval_recall_text(used_idxs, gold_names):
    ctxt=" ".join(norm_name(texts[i]) for i in used_idxs)
    return sum(1 for g in gold_names if norm_name(g) in ctxt)/len(gold_names) if gold_names else 0.0


def run_system(q, system):
    if system=='graphrag': ctx,vis,_=graph_retrieve(q)
    elif system=='rag_dense': ctx,vis=pack_context(retrieve_dense(q))
    elif system=='rag_bm25':  ctx,vis=pack_context(retrieve_bm25(q))
    elif system=='rag_hybrid':ctx,vis=pack_context(retrieve_hybrid(q))
    return reader_answer(q,ctx), ctx, vis


READER_TMPL = 'Sei un assistente di oncologia di precisione. Rispondi alla DOMANDA usando ESCLUSIVAMENTE i PASSAGGI forniti.\nSe i passaggi non contengono la risposta, scrivi "NON DETERMINABILE".\nElenca SOLO i nomi delle entità richieste (farmaci, geni, malattie o test), separati da virgola, senza spiegazioni.\n\nPASSAGGI:\n{context}\n\nDOMANDA: {question}\n\nRISPOSTA (solo nomi separati da virgola):'

_VARIANT_TRIGGERS = ('variante', 'mutazione', 'mutation', 'variant')

ROUTER_SYS = "Sei un router per un sistema di retrieval su grafo di conoscenza oncologico. Data una domanda clinica, classifica il suo INTENTO in UNA delle seguenti categorie e rispondi con la SOLA etichetta (in maiuscolo), senza spiegazioni.\n\nCategorie:\n- GENE_TO_DRUG: chiede quali FARMACI hanno evidenza clinica per un GENE (senza specificare una variante puntuale).\n- VARIANT_TO_DRUG: chiede quali FARMACI hanno evidenza clinica per una specifica VARIANTE/MUTAZIONE di un gene (es. 'EGFR L858R', 'KRAS G12C').\n- GENE_TO_DISEASE: chiede in quali MALATTIE/TUMORI un gene ha evidenza clinica.\n- GENE_TO_CDX: chiede quali TEST DIAGNOSTICI di accompagnamento (companion diagnostic) sono disponibili partendo da un GENE.\n- DRUG_TO_GENE_CDX: chiede quale GENE viene rilevato dal test diagnostico di accompagnamento di un FARMACO (si parte dal farmaco).\n- GENE_TO_TRIALDRUG: chiede quali FARMACI sono testati in TRIAL clinici per un gene.\n- GENE_EVIDENCE_TRIAL_BRIDGE: chiede quali farmaci sono CONTEMPORANEAMENTE supportati da evidenza clinica E testati in un trial per un gene (intersezione evidenza+trial).\n"

ROUTES = {
    'GENE_TO_DRUG': ('Gene', [('HAS_VARIANT', '>'), ('IN_MOLECULAR_PROFILE', '>'), ('HAS_EVIDENCE', '>'), ('TARGETS_DRUG', '>')]),
    'GENE_TO_DISEASE': ('Gene', [('HAS_VARIANT', '>'), ('IN_MOLECULAR_PROFILE', '>'), ('HAS_EVIDENCE', '>'), ('HAS_DISEASE', '>')]),
    'GENE_TO_CDX': ('Gene', [('HAS_VARIANT', '>'), ('IN_MOLECULAR_PROFILE', '>'), ('HAS_EVIDENCE', '>'), ('TARGETS_DRUG', '>'), ('HAS_COMPANION_DIAGNOSTIC', '>')]),
    'GENE_TO_TRIALDRUG': ('Gene', [('ASSOCIATED_GENE', '<'), ('TESTS_DRUG', '>')]),
    'VARIANT_TO_DRUG': ('Variant', [('IN_MOLECULAR_PROFILE', '>'), ('HAS_EVIDENCE', '>'), ('TARGETS_DRUG', '>')]),
    'DRUG_TO_GENE_CDX': ('Drug', [('HAS_COMPANION_DIAGNOSTIC', '>'), ('DIAGNOSES_GENE', '>')]),
    'GENE_EVIDENCE_TRIAL_BRIDGE': ('BRIDGE', None),
}

def route_llm(q):
    lab = ollama_chat(f"DOMANDA: {q}\n\nEtichetta:", ).strip().upper()
    lab = re.sub(r'[^A-Z_]','',lab)
    for k in ROUTES:
        if k in lab: return k
    return "GENE_TO_DRUG"  # safe default


def clean_label(txt):
    lab=re.sub(r'[^A-Z_]','',(txt or '').upper())
    for k in ROUTES:
        if k in lab: return k
    return "GENE_TO_DRUG"


def graph_retrieve_routed(q, intent, budget=CONTEXT_BUDGET_WORDS):
    links=link_entities2(q)
    if not links: return "", [], []
    start_pref, steps = ROUTES[intent]
    if start_pref=='BRIDGE':
        gene=[n for _,n,l in links if l=='Gene']
        if not gene: return "",[],[]
        g=gene[0]
        ev=follow_pattern(g,[('HAS_VARIANT','>'),('IN_MOLECULAR_PROFILE','>'),('HAS_EVIDENCE','>'),('TARGETS_DRUG','>')])
        tr=follow_pattern(g,[('ASSOCIATED_GENE','<'),('TESTS_DRUG','>')])
        common=({name(p[-1]) for p in ev})&({name(p[-1]) for p in tr})
        facts=[f"Il farmaco {c} è supportato da evidenza clinica ED è testato in un trial clinico per il gene {name(g)}." for c in sorted(common)]
        ctx=[];words=0
        for f in facts:
            w=len(f.split())
            if words+w>budget and ctx: break
            ctx.append(f);words+=w
        return "\n".join(ctx),list(common),facts
    if start_pref=='Variant':
        vstarts=[n for _,n,l in links if l=='Variant']
        if vstarts: starts=vstarts; use_steps=steps
        else: starts=[n for _,n,l in links if l=='Gene']; use_steps=[('HAS_VARIANT','>')]+steps
    else:
        starts=[n for _,n,l in links if l==start_pref] or [n for _,n,l in links]; use_steps=steps
    allpaths=[]
    for s in starts: allpaths+=follow_pattern(s,use_steps)
    ctx=[];words=0;seen=set();visited=set()
    for path in allpaths:
        s=serialize_path_compact(path,[(r,d) for r,d in use_steps])
        if s in seen: continue
        seen.add(s);w=len(s.split())
        if words+w>budget and ctx: break
        ctx.append(s);words+=w;visited.update(path)
    return "\n".join(ctx),list(visited),allpaths

