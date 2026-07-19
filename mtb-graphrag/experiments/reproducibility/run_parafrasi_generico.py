#!/usr/bin/env python3
"""Genera parafrasi cliniche delle domande del benchmark multi-hop tramite un
LLM servito da Ollama Cloud, con rotazione multi-chiave e checkpoint incrementale.

Uso:
    OLLAMA_KEYS='k1,k2,...' python run_parafrasi_generico.py \
        --benchmark benchmark_multihop_1k.csv \
        --out parafrasi_1k.csv --workers 6

Le chiavi sono lette SOLO da os.environ. Nessun valore viene stampato o salvato.
"""
import os, re, csv, time, json, threading, argparse
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

HOST  = os.environ.get("OLLAMA_HOST", "https://ollama.com")
MODEL = os.environ.get("PARA_MODEL", "gemma3:27b-cloud")
KEYS  = [k.strip() for k in os.environ.get("OLLAMA_KEYS", "").split(",") if k.strip()]
key_idx = [0]; key_lock = threading.Lock()

def current_key():
    with key_lock:
        return KEYS[key_idx[0]] if key_idx[0] < len(KEYS) else None

def rotate_key(bad):
    with key_lock:
        if key_idx[0] < len(KEYS) and KEYS[key_idx[0]] == bad:
            key_idx[0] += 1
        return key_idx[0] < len(KEYS)

PARA_SYS = (
    "Sei un oncologo esperto. Riformula la domanda clinica che ti viene fornita "
    "mantenendo ESATTAMENTE lo stesso significato e le stesse entita' cliniche "
    "(geni, varianti, farmaci, malattie, test diagnostici), ma cambiando il piu' "
    "possibile il lessico e la struttura sintattica, come la porrebbe un collega "
    "diverso. Non aggiungere ne togliere informazioni. "
    "Rispondi con la SOLA domanda riformulata, senza virgolette ne commenti."
)

def ollama_chat(prompt, system, temperature=0.7):
    for attempt in range(12):
        k = current_key()
        if k is None:
            return "__NOKEY__"
        try:
            r = requests.post(HOST + "/api/chat",
                headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                timeout=(10, 120),
                json={"model": MODEL, "stream": False,
                      "options": {"temperature": temperature},
                      "messages": [{"role": "system", "content": system},
                                   {"role": "user", "content": prompt}]})
            if r.status_code == 200:
                return r.json().get("message", {}).get("content", "")
            body = r.text.lower()
            if r.status_code == 429 or "usage limit" in body or "rate" in body:
                if "usage limit" in body or "weekly" in body:
                    if not rotate_key(k):
                        return "__NOKEY__"
                else:
                    time.sleep(0.6*(attempt+1))
                continue
            time.sleep(0.5*(attempt+1))
        except Exception:
            time.sleep(1.5*(attempt+1))
    return "__ERROR__"

def clean(txt):
    txt = txt.strip().strip('"').strip("'").strip()
    txt = re.sub(r'^(Domanda|Riformulazione|Parafrasi)[:\s]*', '', txt, flags=re.I)
    return txt.split("\n")[0].strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--temperature", type=float, default=0.7)
    args = ap.parse_args()

    bench = pd.read_csv(args.benchmark)
    done = {}
    if os.path.exists(args.out):
        try:
            prev = pd.read_csv(args.out)
            for _, r in prev.iterrows():
                if isinstance(r.get("paraphrase"), str) and r["paraphrase"] and not r["paraphrase"].startswith("__"):
                    done[r["qid"]] = r["paraphrase"]
        except Exception:
            pass
    print(f"benchmark={len(bench)} gia_fatti={len(done)} keys={len(KEYS)} model={MODEL}", flush=True)

    rows = [None]*len(bench)
    lock = threading.Lock(); cnt=[0]; t0=time.time()

    def work(i):
        r = bench.iloc[i]
        qid = r["qid"]
        if qid in done:
            para = done[qid]
        else:
            para = clean(ollama_chat(f"DOMANDA: {r['question']}\n\nRiformulazione:", PARA_SYS, args.temperature))
        with lock:
            rows[i] = dict(qid=qid, qtype=r["qtype"], question_original=r["question"],
                           paraphrase=para)
            cnt[0]+=1
            if cnt[0] % 50 == 0:
                el=time.time()-t0
                print(f"{cnt[0]}/{len(bench)} | key#{key_idx[0]+1}/{len(KEYS)} | {cnt[0]/el:.2f}/s", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, range(len(bench))))

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["qid","qtype","question_original","paraphrase"])
        w.writeheader()
        for row in rows:
            w.writerow(row)
    bad = sum(1 for r in rows if not r["paraphrase"] or r["paraphrase"].startswith("__"))
    print(f"FATTO out={args.out} righe={len(rows)} falliti={bad}", flush=True)

if __name__ == "__main__":
    main()
