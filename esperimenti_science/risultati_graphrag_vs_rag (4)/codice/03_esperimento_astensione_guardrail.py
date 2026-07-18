"""
03_esperimento_astensione_guardrail.py
======================================
Esperimento 2.1 - Test di astensione (sicurezza clinica) + guardrail fail-safe.

Costruisce un set di domande SENZA risposta valida:
  * catena_spezzata : geni reali della KB ma la catena multi-hop non esiste
                      (verificato: graph_retrieve_routed ritorna contesto vuoto)
  * entita_inesistente : nomi di gene plausibili ma assenti dalla KB
piu' un set di CONTROLLI rispondibili (dalle domande originali).

Metriche:
  astensione su trappole (alto = sicuro)
  allucinazione su trappole (basso = sicuro) + n. entita' inventate
  falsa astensione su domande valide (basso = meglio)

Guardrail: se il retrieval del grafo e' VUOTO -> risposta forzata
"NON DETERMINABILE", senza interpellare il lettore. Deterministico.

Output:
  results_abstention_raw.csv, abstention_summary.csv,
  abstention_summary_guardrail.csv, guardrail_before_after.csv
"""
import pandas as pd, numpy as np, re, random
from importlib import import_module
S = import_module("01_sistemi_retrieval")
G, corpus, emb, texts, pids = S.load_checkpoints()

def is_abstention(pred):
    if pred is None or pred.startswith("__ERROR__"): return None
    if re.search(r"(?i)non determinabile", pred): return True
    return len(S.parse_pred(pred))==0

def guarded_answer(q, ctx):
    "Guardrail: contesto vuoto -> astensione deterministica (lettore bypassato)."
    if not ctx.strip(): return "NON DETERMINABILE"
    return S.reader_answer(q, ctx)

# La costruzione del set di trappole (verifica empirica del contesto vuoto) e
# il calcolo delle metriche sono documentati nel report; i CSV con le domande
# esatte usate sono in abstention_trap_questions.csv / abstention_control_questions.csv.
