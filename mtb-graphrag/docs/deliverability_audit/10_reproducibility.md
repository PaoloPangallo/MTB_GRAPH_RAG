# 10 — Riproducibilità dalla prospettiva di un revisore

Dati: `evaluation/deliverability/reproducibility_matrix.csv`.

Simulazione: un revisore clona il repository oggi e prova a ricostruire
`ENVIRONMENT → DATA → KG → GCA → PIPELINE → EXPERIMENT → METRICS`.

## Il verdetto in una riga

**Può riprodurre RQ1, RQ2 e le metriche v3 completamente; può eseguire la
pipeline solo in REPLAY; non può eseguire LIVE né costruire il frontend.**

## ENVIRONMENT — il punto più debole

| Passaggio | Esito |
|---|---|
| Python 3.12 | ✅ REPRODUCIBLE |
| `requirements.txt` | ⚠️ **PARZIALE** — 10 pacchetti, **0 versioni pinnate** |
| `pytest`, `httpx`, `pandas`, `numpy` | ❌ **NOT REPRODUCIBLE** — necessari, non dichiarati |
| lockfile Python | ❌ assente |
| `pytest.ini` / `conftest.py` | ❌ assenti — `PYTHONPATH=mtb-graphrag` va impostato a mano |
| configurazione mypy | ❌ `.mypy_cache/` esiste, nessun file di config versionato |
| lockfile frontend | ✅ `package-lock.json` tracciato |
| `npm run build` | ❌ **fallisce** — 6 errori TS2769 |

Il README dice:

```bash
pip install -r backend/config/requirements.txt
```

Chi lo segue **non ottiene un ambiente in cui i test girano**: `pytest` non è fra
le dieci righe. Sono installati 188 pacchetti; ne sono dichiarati 10, senza
versione. È il gap di riproducibilità più concreto, e anche il più facile da
chiudere (`pip freeze > requirements-lock.txt` più una sezione `[dev]`).

## DATA — sorprendentemente solido

| Dataset | Stato |
|---|---|
| KG sorgente CSV (43 005 nodi, 60 546 archi) | ✅ **tracciato in git** |
| `graph_candidate_repository/2.0` (72,5 MB) | ✅ tracciato, SHA-256 dichiarato **e verificato a runtime** |
| `graph_candidate_repository/3.0` (111,9 MB) | ✅ tracciato, con manifest, schema, lineage |
| `evidence_bundles.jsonl` | ✅ tracciato |
| `source_unit_index.jsonl` | ✅ tracciato — **solo locatori e `content_hash`** |
| artifact enricher congelati | ✅ tracciati |
| **`data_cache/document_grounding`** | ❌ **assente e gitignored** |
| gold set clinico | ❌ gitignored — *scelta corretta e dichiarata* |

Committare 184 MB di dataset è una scelta discutibile in generale, ma qui è
**esattamente ciò che rende RQ1 e RQ2 riproducibili**. Il `.gitignore` è
commentato con cura: spiega che dei documenti di terzi si conserva il manifest
(hash, offset, sezione) e non i byte, «e il manifest basta a verificare un
bundle quando c'è e a descriverlo quando non c'è, e non basta a ricostruirlo. È
esattamente la proprietà che serve.» È un ragionamento corretto e ben scritto.

Il costo: **i livelli 3-7 della catena di grounding di RQ2 non sono
riproducibili da un clone pulito**, e nessun README documenta come ripopolare la
cache. Esiste un riferimento a
`benchmarks/mtb_evidence/evaluation/scripts/fetch_priority_abstracts.py` in un
commento del `.gitignore`, ma non un procedimento per
`data_cache/document_grounding`.

## PIPELINE

| Modalità | Esito |
|---|---|
| REPLAY | ✅ **funziona** — 5 casi end-to-end fino al dossier, senza rete, `llm_calls = 0` |
| LIVE | ❌ `POST /runs` risponde **503** senza `data_cache/`; richiede inoltre `OLLAMA_API_KEY` (segreto non distribuibile) |
| ramo non eleggibile | ❌ **ISS-001** — `ValueError` non gestito |

Il 503 è la cosa giusta fatta bene: la precondizione è verificata **prima** di
avviare la run, «così un LIVE impossibile fallisce subito e con il proprio
motivo, invece di degradare in un replay travestito». Ma per un revisore
significa che **LIVE non è dimostrabile**.

## EXPERIMENT e METRICS — il risultato migliore dell'audit

Tutti e cinque gli script di evaluation girano oggi con exit 0 e riproducono le
proprie metriche (dettaglio in `09_rq_readiness.md`). **Nessuna metrica è
hard-coded.** I conteggi dei test dichiarati — 3 047 / 91 / 195 — sono
riprodotti esattamente. I sampler non usano randomness: il campionamento
stratificato è deterministico e non serve un seed.

Due difetti minori:

1. `run_rq1` e `run_gca_v3_audit` **non onorano** un `OUT` sostituito: scrivono
   comunque in `evaluation/`. Un revisore che li esegua sovrascrive gli artifact
   committati (in questo audit è successo, ed è stato ripristinato — vedi
   `09_rq_readiness.md`).
2. Sette artifact committati contengono il percorso assoluto della macchina
   dell'autore (`C:\Users\paolo\...`), fra cui
   `evaluation/rq1_graph_candidate_fidelity/aggregate_metrics.json` e
   `graph_candidate_repository/3.0/manifest.json`.

## Cosa NON sarebbe riproducibile da un clone pulito

1. **Qualunque run LIVE** — cache documentale assente + credenziale segreta.
2. **I livelli 3-7 della catena di grounding di RQ2** — nessun testo di documento.
3. **La validazione delle quote end-to-end** — LIVE fallisce a stage 6, e REPLAY
   *rigioca* l'esito invece di ricalcolarlo (`replay.py:117-132`). La garanzia
   resta dimostrabile solo a livello unitario.
4. **Il build del frontend** — fallisce a HEAD.
5. **La rilevanza semantica dei PMID di RQ2** — `NOT_MEASURED` per progetto,
   richiede annotazione umana. Dichiarato, non rivendicato.
6. **La fedeltà semantica di v3 rispetto a un giudizio esperto** — il campione
   manuale a 70 record (`evaluation/gold/rq1_gca_v3_manual_review.csv`) ha le
   colonne del revisore **vuote**.
7. **Il ramo non eleggibile attraverso il runtime** — ISS-001.

## Interventi minimi per chiudere il gap di ambiente

```
1. pip freeze > backend/config/requirements-lock.txt  (o pyproject con [dev])
2. aggiungere pytest, httpx, pandas, numpy a requirements
3. un pytest.ini con pythonpath = . e testpaths
4. documentare nel README come ripopolare data_cache/, o dichiarare che LIVE
   non e' riproducibile esternamente
```

I primi tre sono di pochi minuti e trasformano `ENVIRONMENT` da
`NOT REPRODUCIBLE` a `REPRODUCIBLE`.
