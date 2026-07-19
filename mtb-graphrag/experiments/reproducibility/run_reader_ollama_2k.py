#!/usr/bin/env python3
import os, sys, time, json, pickle, re, threading
from concurrent.futures import ThreadPoolExecutor
import requests

KEY = os.environ.get("OLLAMA_API_KEY","")
HOST = "https://ollama.com"
MODEL = "gemma3:27b"
HDR = {"Authorization":"Bearer "+KEY}
CKPT = "reader_ollama_2k.jsonl"
PROG = "reader_ollama_progress.txt"
WORKERS = 10

TMPL = ('Sei un assistente di oncologia di precisione. Rispondi alla DOMANDA usando ESCLUSIVAMENTE i PASSAGGI forniti.\n'
        'Se i passaggi non contengono la risposta, scrivi "NON DETERMINABILE".\n'
        'Elenca SOLO i nomi delle entita richieste (farmaci, geni, malattie o test), separati da virgola, senza spiegazioni.\n\n'
        'PASSAGGI:\n{context}\n\nDOMANDA: {question}\n\nRISPOSTA (solo nomi separati da virgola):')

def norm_name(s): return re.sub(r'[^a-z0-9]+',' ',str(s).lower()).strip()
def parse_pred(pred):
    if not pred: return []
    pred=re.sub(r'(?i)non determinabile','',pred)
    return [norm_name(p) for p in re.split(r'[,\n;|]+',pred) if norm_name(p)]
def score_answer(pred, gold_names):
    P=set(parse_pred(pred)); Gn={norm_name(g) for g in gold_names}
    tp=0; matched=set()
    for g in Gn:
        for p in P:
            if g==p or g in p or p in g: tp+=1; matched.add(g); break
    prec=tp/len(P) if P else 0.0; rec=len(matched)/len(Gn) if Gn else 0.0
    f1=2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
    em=1.0 if matched==Gn and len(P)>0 else 0.0
    return dict(precision=prec,recall=rec,f1=f1,exact=em,n_pred=len(P),n_match=len(matched))

def call(context, question):
    prompt=TMPL.format(context=context, question=question)
    for attempt in range(6):
        try:
            r=requests.post(HOST+"/api/chat", headers=HDR, timeout=(10,90),
                json={"model":MODEL,"stream":False,"options":{"temperature":0.0},
                      "messages":[{"role":"user","content":prompt}]})
            if r.status_code==200:
                return r.json().get("message",{}).get("content","")
            if r.status_code==429:
                time.sleep(0.6*(attempt+1)+0.3*os.urandom(1)[0]/255); continue
            time.sleep(0.5*(attempt+1))
        except Exception:
            time.sleep(1.5*(attempt+1))
    return ""

def main():
    tasks=pickle.load(open("reader_tasks_all.pkl","rb"))
    done=set()
    if os.path.exists(CKPT):
        for l in open(CKPT):
            try: o=json.loads(l); done.add((o["qid"],o["system"]))
            except: pass
    todo=[t for t in tasks if (t[0],t[1]) not in done]
    total=len(tasks); start_done=len(done)
    fout=open(CKPT,"a"); lock=threading.Lock(); cnt=[0]; t0=time.time()
    def work(t):
        qid,s,ctx,q,gold=t
        txt=call(ctx,q)
        sc=score_answer(txt,gold)
        row=dict(qid=qid,system=s,pred=txt[:400],**sc)
        with lock:
            fout.write(json.dumps(row)+"\n"); fout.flush()
            cnt[0]+=1
            if cnt[0]%50==0:
                dt=time.time()-t0; rate=cnt[0]/dt if dt>0 else 0
                rem=len(todo)-cnt[0]; eta=rem/rate/60 if rate>0 else 0
                with open(PROG,"w") as pf:
                    pf.write(f"{start_done+cnt[0]}/{total} done | {rate:.2f}/s | ETA {eta:.1f}min\n")
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, todo))
    fout.close()
    with open(PROG,"a") as pf: pf.write(f"COMPLETE {start_done+cnt[0]}/{total}\n")

if __name__=="__main__":
    main()
