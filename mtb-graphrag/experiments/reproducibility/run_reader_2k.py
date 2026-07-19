import os, json, re, time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

WS = os.path.dirname(os.path.abspath(__file__))
os.chdir(WS)
OLLAMA_KEY = os.environ["OLLAMA_API_KEY"]
OLLAMA_HOST = "https://ollama.com"
READER_MODEL = "gemma3:27b"
READER_TMPL = ('Sei un assistente di oncologia di precisione. Rispondi alla DOMANDA usando ESCLUSIVAMENTE i PASSAGGI forniti.\n'
 'Se i passaggi non contengono la risposta, scrivi "NON DETERMINABILE".\n'
 'Elenca SOLO i nomi delle entità richieste (farmaci, geni, malattie o test), separati da virgola, senza spiegazioni.\n\n'
 'PASSAGGI:\n{context}\n\nDOMANDA: {question}\n\nRISPOSTA (solo nomi separati da virgola):')

def norm_name(s): return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()

def ollama_chat(prompt, temp=0.0, max_retries=4):
    url=f"{OLLAMA_HOST}/api/chat"
    hdr={'Authorization':f'Bearer {OLLAMA_KEY}','Content-Type':'application/json'}
    body={'model':READER_MODEL,'messages':[{'role':'user','content':prompt}],'stream':False,'options':{'temperature':temp}}
    last=""
    for a in range(max_retries):
        try:
            r=requests.post(url,headers=hdr,json=body,timeout=(10,75))
            if r.status_code==200: return r.json()['message']['content']
            last=f"HTTP {r.status_code}: {r.text[:120]}"
            # backoff longer on 429
            time.sleep((4 if r.status_code==429 else 2)*(a+1))
        except Exception as e:
            last=str(e)[:120]; time.sleep(2*(a+1))
    return f"__ERROR__: {last}"

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

ben=pd.read_csv("benchmark_multihop_2k.csv")
ctx_df=pd.read_pickle("retrieval_contexts_2k.pkl")
gold_map=dict(zip(ben.qid, ben.gold_answer))
q_map=dict(zip(ben.qid, ben.question))
systems=['graphrag','rag_bm25','rag_hybrid','rag_dense']

CKPT="reader_results_2k.jsonl"
seen={}
if os.path.exists(CKPT):
    for line in open(CKPT):
        try:
            o=json.loads(line)
            if str(o.get('pred','')).startswith('__ERROR__'): continue
            seen[(o['qid'],o['system'])]=o
        except: pass
with open(CKPT,"w") as f:
    for o in seen.values(): f.write(json.dumps(o)+"\n")

tasks=[]
for _,r in ctx_df.iterrows():
    for s in systems:
        if (r['qid'],s) not in seen:
            tasks.append((r['qid'], s, r[s]))

with open("reader_progress.txt","w") as pf:
    pf.write(f"start remaining={len(tasks)} done={len(seen)}\n"); pf.flush()

def work(t):
    qid,s,ctx=t
    pred=ollama_chat(READER_TMPL.format(context=ctx, question=q_map[qid]))
    gold=[x.strip() for x in str(gold_map[qid]).split("|")]
    sc=score_answer(pred, gold)
    return dict(qid=qid, system=s, pred=pred[:500], **sc)

t0=time.time(); n=0
fout=open(CKPT,"a")
with ThreadPoolExecutor(max_workers=4) as ex:
    futs=[ex.submit(work,t) for t in tasks]
    for fu in as_completed(futs):
        try:
            o=fu.result(); fout.write(json.dumps(o)+"\n"); n+=1
        except Exception:
            n+=1
        if n%50==0:
            fout.flush()
            with open("reader_progress.txt","a") as pf:
                pf.write(f"{n}/{len(tasks)} {time.time()-t0:.0f}s ts={time.strftime('%H:%M:%S')}\n")
fout.close()
with open("reader_progress.txt","a") as pf:
    pf.write(f"DONE {n} {time.time()-t0:.0f}s\n")
