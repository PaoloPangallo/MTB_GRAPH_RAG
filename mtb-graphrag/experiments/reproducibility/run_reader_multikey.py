import os, re, json, time, pickle, threading, requests
from concurrent.futures import ThreadPoolExecutor

HOST="https://ollama.com"; MODEL="gemma3:27b"
TASKS="reader_tasks_all_fixed.pkl"
CKPT="reader_gemma3_final.jsonl"
PROG="reader_multikey_progress.txt"
WORKERS=8

# Keys from env (comma-separated), rotated on weekly-limit/429.
KEYS=[k.strip() for k in os.environ.get("OLLAMA_KEYS","").split(",") if k.strip()]
key_idx=[0]
key_lock=threading.Lock()
def current_key():
    with key_lock:
        return KEYS[key_idx[0]] if key_idx[0]<len(KEYS) else None
def rotate_key(bad):
    with key_lock:
        if key_idx[0]<len(KEYS) and KEYS[key_idx[0]]==bad:
            key_idx[0]+=1
            return key_idx[0]<len(KEYS)
        return key_idx[0]<len(KEYS)

def norm_name(s): return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()
def parse_pred(pred):
    p=re.sub(r'non\s+determinabile','',str(pred or ''),flags=re.I)
    return [x.strip() for x in re.split(r'[,\n;|]+',p) if x.strip()]
def score_answer(pred, gold):
    preds=parse_pred(pred); golds=[g for g in gold if str(g).strip()]
    gn=[norm_name(g) for g in golds]; pn=[norm_name(p) for p in preds]
    mg=set(); mp=set()
    for gi,g in enumerate(gn):
        for pi,p in enumerate(pn):
            if g and p and (g==p or g in p or p in g): mg.add(gi); mp.add(pi)
    npr,ng=len(preds),len(golds); nm=len(mg)
    prec=len(mp)/npr if npr else 0.0; rec=nm/ng if ng else 0.0
    f1=2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    exact=1.0 if (ng and nm==ng and len(mp)==npr and npr==ng) else 0.0
    return dict(precision=prec,recall=rec,f1=f1,exact=exact,n_pred=npr,n_match=nm)

TMPL='''Sei un assistente di oncologia di precisione. Rispondi alla DOMANDA usando ESCLUSIVAMENTE i PASSAGGI forniti.
Se i passaggi non contengono la risposta, scrivi "NON DETERMINABILE".
Elenca SOLO i nomi delle entita richieste (farmaci, geni, malattie o test), separati da virgola, senza spiegazioni.

PASSAGGI:
{context}

DOMANDA: {question}

RISPOSTA (solo nomi separati da virgola):'''

def call(context, question):
    prompt=TMPL.format(context=context, question=question)
    for attempt in range(12):
        k=current_key()
        if k is None: return "__NOKEY__"
        try:
            r=requests.post(HOST+"/api/chat",
                headers={"Authorization":f"Bearer {k}","Content-Type":"application/json"},
                timeout=(10,120),
                json={"model":MODEL,"stream":False,"options":{"temperature":0.0},
                      "messages":[{"role":"user","content":prompt}]})
            if r.status_code==200:
                return r.json().get("message",{}).get("content","")
            body=r.text.lower()
            if r.status_code==429 or "usage limit" in body or "rate" in body:
                # weekly limit on this key -> rotate; transient 429 -> brief backoff
                if "usage limit" in body or "weekly" in body:
                    if not rotate_key(k): return "__NOKEY__"
                else:
                    time.sleep(0.6*(attempt+1)+0.3*os.urandom(1)[0]/255)
                continue
            time.sleep(0.5*(attempt+1))
        except Exception:
            time.sleep(1.5*(attempt+1))
    return ""

def main():
    tasks=pickle.load(open(TASKS,"rb"))
    done=set()
    if os.path.exists(CKPT):
        for l in open(CKPT):
            try: o=json.loads(l); done.add((o["qid"],o["system"]))
            except: pass
    todo=[t for t in tasks if (t[0],t[1]) not in done]
    total=len(tasks); start=len(done)
    fout=open(CKPT,"a"); lock=threading.Lock(); cnt=[0]; nokey=[False]; t0=time.time()
    def work(t):
        if nokey[0]: return
        qid,s,ctx,q,gold=t
        txt=call(ctx,q)
        if txt=="__NOKEY__":
            nokey[0]=True; return
        sc=score_answer(txt,gold)
        with lock:
            fout.write(json.dumps(dict(qid=qid,system=s,pred=txt[:400],**sc))+"\n"); fout.flush()
            cnt[0]+=1
            if cnt[0]%50==0:
                dt=time.time()-t0; rate=cnt[0]/dt if dt>0 else 0
                rem=len(todo)-cnt[0]; eta=rem/rate/60 if rate>0 else 0
                with open(PROG,"w") as pf:
                    pf.write(f"{start+cnt[0]}/{total} done | key#{key_idx[0]+1}/{len(KEYS)} | {rate:.2f}/s | ETA {eta:.1f}min\n")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, todo))
    fout.close()
    status="NOKEY_EXHAUSTED" if nokey[0] else "COMPLETE"
    with open(PROG,"a") as pf: pf.write(f"{status} {start+cnt[0]}/{total}\n")

if __name__=="__main__":
    main()
