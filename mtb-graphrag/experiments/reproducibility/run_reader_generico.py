#!/usr/bin/env python3
"""
run_reader_generico.py — Lettore multi-hop parametrico con rotazione multi-chiave.

Esegue un modello lettore (LLM) sul contesto recuperato da ciascun sistema RAG,
per ogni domanda del benchmark, e ne calcola le metriche (precision/recall/F1/exact).

Le chiavi API sono lette ESCLUSIVAMENTE dall'ambiente:
    OLLAMA_KEYS   elenco separato da virgola (rotazione su limite settimanale/429)
    OLLAMA_HOST   default https://ollama.com

Uso:
    OLLAMA_KEYS=... python run_reader_generico.py \
        --tasks reader_tasks_all_fixed.pkl \
        --subset benchmark_multihop_1k.csv \
        --model qwen3-coder-next \
        --out reader_qwen_1k.jsonl
"""
import os, re, json, time, pickle, threading, argparse
import requests
from concurrent.futures import ThreadPoolExecutor

HOST = os.environ.get("OLLAMA_HOST", "https://ollama.com")
KEYS = [k.strip() for k in os.environ.get("OLLAMA_KEYS", "").split(",") if k.strip()]
key_idx = [0]; key_lock = threading.Lock()

def current_key():
    with key_lock:
        return KEYS[key_idx[0]] if key_idx[0] < len(KEYS) else None

def rotate_key(bad):
    with key_lock:
        if key_idx[0] < len(KEYS) and KEYS[key_idx[0]] == bad:
            key_idx[0] += 1
        return key_idx[0] < len(KEYS)

def norm_name(s):
    return re.sub(r'[^a-z0-9]+', ' ', str(s).lower()).strip()

def parse_pred(pred):
    p = re.sub(r'non\s+determinabile', '', str(pred or ''), flags=re.I)
    return [x.strip() for x in re.split(r'[,\n;|]+', p) if x.strip()]

def score_answer(pred, gold):
    preds = parse_pred(pred); golds = [g for g in gold if str(g).strip()]
    gn = [norm_name(g) for g in golds]; pn = [norm_name(p) for p in preds]
    mg = set(); mp = set()
    for gi, g in enumerate(gn):
        for pi, p in enumerate(pn):
            if g and p and (g == p or g in p or p in g):
                mg.add(gi); mp.add(pi)
    npr, ng, nm = len(preds), len(golds), len(mg)
    prec = len(mp)/npr if npr else 0.0
    rec  = nm/ng if ng else 0.0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) else 0.0
    exact = 1.0 if (ng and nm == ng and len(mp) == npr and npr == ng) else 0.0
    return dict(precision=prec, recall=rec, f1=f1, exact=exact, n_pred=npr, n_match=nm)

PROMPT_HEAD = (
    "Sei un assistente di oncologia di precisione. Rispondi alla DOMANDA usando "
    "ESCLUSIVAMENTE i PASSAGGI forniti.\n"
    "Se i passaggi non contengono la risposta, scrivi \"NON DETERMINABILE\".\n"
    "Elenca SOLO i nomi delle entita richieste (farmaci, geni, malattie o test), "
    "separati da virgola, senza spiegazioni.\n\n"
    "PASSAGGI:\n{context}\n\nDOMANDA: {question}\n\n"
    "RISPOSTA (solo nomi separati da virgola):"
)

def call(model, context, question):
    prompt = PROMPT_HEAD.format(context=context, question=question)
    for attempt in range(12):
        k = current_key()
        if k is None:
            return "__NOKEY__"
        try:
            r = requests.post(HOST + "/api/chat",
                headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                timeout=(10, 120),
                json={"model": model, "stream": False, "options": {"temperature": 0.0},
                      "messages": [{"role": "user", "content": prompt}]})
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
    return ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--subset", default=None, help="CSV con colonna qid per filtrare le domande")
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    tasks = pickle.load(open(args.tasks, "rb"))  # tuple (qid, system, context, question, gold)
    if args.subset:
        import csv
        keep = set()
        with open(args.subset) as f:
            for row in csv.DictReader(f):
                keep.add(row["qid"])
        tasks = [t for t in tasks if t[0] in keep]

    done = set()
    if os.path.exists(args.out):
        for line in open(args.out):
            try:
                d = json.loads(line); done.add((d["qid"], d["system"]))
            except Exception:
                pass
    todo = [t for t in tasks if (t[0], t[1]) not in done]
    print("tasks totali=%d | gia' fatti=%d | da fare=%d" % (len(tasks), len(done), len(todo)), flush=True)

    lock = threading.Lock(); cnt = [0]; t0 = time.time()
    out = open(args.out, "a")

    def work(t):
        qid, system, context, question, gold = t
        pred = call(args.model, context, question)
        sc = score_answer(pred, gold)
        rec = dict(qid=qid, system=system, model=args.model, pred=pred, gold=gold, **sc)
        with lock:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n"); out.flush()
            cnt[0] += 1
            if cnt[0] % 50 == 0:
                rate = cnt[0]/(time.time()-t0+1e-9)
                eta = (len(todo)-cnt[0])/rate/60 if rate else 0
                print("%d/%d | key#%d/%d | %.2f/s | ETA %.1fmin"
                      % (cnt[0], len(todo), key_idx[0]+1, len(KEYS), rate, eta), flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, todo))
    out.close()
    print("FATTO", flush=True)

if __name__ == "__main__":
    main()
