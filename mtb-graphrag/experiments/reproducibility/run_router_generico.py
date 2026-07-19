#!/usr/bin/env python3
"""
run_router_generico.py — Ablazione del router: sostituisce l'oracolo (intento
noto dal template della domanda) con un router LLM reale che classifica
l'intento a partire dal solo testo della domanda, e ne misura l'accuratezza.

Le chiavi API sono lette ESCLUSIVAMENTE dall'ambiente:
    OLLAMA_KEYS   elenco separato da virgola (rotazione su limite/429)
    OLLAMA_HOST   default https://ollama.com
    ROUTER_MODEL  default gemma3:27b-cloud

Uso:
    OLLAMA_KEYS=... python run_router_generico.py \
        --benchmark benchmark_multihop_1k.csv \
        --out router_ablation_1k.csv
"""
import os, re, json, time, threading, argparse
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

HOST = os.environ.get("OLLAMA_HOST", "https://ollama.com")
ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "gemma3:27b-cloud")
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

ROUTES_LIST = ['GENE_TO_DRUG','GENE_TO_DISEASE','GENE_TO_CDX','GENE_TO_TRIALDRUG',
               'VARIANT_TO_DRUG','DRUG_TO_GENE_CDX','GENE_EVIDENCE_TRIAL_BRIDGE']
QTYPE2ROUTE = {'gene_to_drug':'GENE_TO_DRUG','variant_to_drug':'VARIANT_TO_DRUG',
               'gene_to_disease':'GENE_TO_DISEASE','gene_to_cdx':'GENE_TO_CDX',
               'drug_to_gene_cdx':'DRUG_TO_GENE_CDX','gene_to_trialdrug':'GENE_TO_TRIALDRUG',
               'gene_evidence_trial_bridge':'GENE_EVIDENCE_TRIAL_BRIDGE'}

ROUTER_SYS = (
 "Sei un router per un sistema di retrieval su grafo di conoscenza oncologico. "
 "Data una domanda clinica, classifica il suo INTENTO in UNA delle seguenti "
 "categorie e rispondi con la SOLA etichetta (in maiuscolo), senza spiegazioni.\n\n"
 "Categorie:\n"
 "- GENE_TO_DRUG: chiede quali FARMACI hanno evidenza clinica per un GENE (senza specificare una variante puntuale).\n"
 "- VARIANT_TO_DRUG: chiede quali FARMACI hanno evidenza clinica per una specifica VARIANTE/MUTAZIONE di un gene.\n"
 "- GENE_TO_DISEASE: chiede in quali MALATTIE/TUMORI un gene ha evidenza clinica.\n"
 "- GENE_TO_CDX: chiede quali TEST DIAGNOSTICI di accompagnamento sono disponibili partendo da un GENE.\n"
 "- DRUG_TO_GENE_CDX: chiede quale GENE viene rilevato dal test diagnostico di accompagnamento di un FARMACO.\n"
 "- GENE_TO_TRIALDRUG: chiede quali FARMACI sono testati in TRIAL clinici per un gene.\n"
 "- GENE_EVIDENCE_TRIAL_BRIDGE: chiede quali farmaci sono CONTEMPORANEAMENTE supportati da evidenza clinica E testati in un trial per un gene.\n"
)

def ollama_chat(prompt, system):
    for attempt in range(12):
        k = current_key()
        if k is None:
            return "__NOKEY__"
        try:
            r = requests.post(HOST + "/api/chat",
                headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
                timeout=(10, 120),
                json={"model": ROUTER_MODEL, "stream": False, "options": {"temperature": 0.0},
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

def route_llm(q):
    lab = re.sub(r'[^A-Z_]', '', ollama_chat("DOMANDA: %s\n\nEtichetta:" % q, ROUTER_SYS).strip().upper())
    for k in ROUTES_LIST:
        if k in lab:
            return k
    return "GENE_TO_DRUG"   # default sicuro

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    bench = pd.read_csv(args.benchmark)
    rows = [None]*len(bench)
    lock = threading.Lock(); cnt = [0]; t0 = time.time()

    def work(i):
        r = bench.iloc[i]
        oracle = QTYPE2ROUTE.get(r["qtype"], "GENE_TO_DRUG")
        pred = route_llm(r["question"])
        with lock:
            rows[i] = dict(qid=r["qid"], qtype=r["qtype"], oracle=oracle,
                           router_pred=pred, correct=int(pred == oracle))
            cnt[0] += 1
            if cnt[0] % 50 == 0:
                rate = cnt[0]/(time.time()-t0+1e-9)
                print("%d/%d | key#%d/%d | %.2f/s" % (cnt[0], len(bench), key_idx[0]+1, len(KEYS), rate), flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, range(len(bench))))

    out = pd.DataFrame([r for r in rows if r])
    out.to_csv(args.out, index=False)
    acc = out["correct"].mean()
    print("Router accuracy = %.4f  (%d/%d)" % (acc, out["correct"].sum(), len(out)), flush=True)
    print("FATTO", flush=True)

if __name__ == "__main__":
    main()
