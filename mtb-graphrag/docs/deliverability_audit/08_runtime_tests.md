# 08 — Test del runtime e smoke test

Dati: `evaluation/deliverability/runtime_test_results.json`,
`evaluation/deliverability/smoke_test_results.jsonl`,
`evaluation/deliverability/raw/F01…F11`.

## §17 — Suite eseguite

| Comando | Esito | passed | failed | skipped | durata |
|---|:-:|---:|---:|---:|---:|
| `pytest backend/research_pipeline/tests -q` | ✅ 0 | 351 | 0 | 12 | 65 s |
| `pytest backend/tests -q` | ✅ 0 | 2 696 | 0 | 5 | 328 s |
| `pytest evaluation/tests -q` | ✅ 0 | 91 | 0 | 0 | 7 s |
| `npm test` (vitest, parallelo) | ❌ 1 | 194 | **1** | 0 | 37 s |
| `npx vitest run --no-file-parallelism` | ✅ 0 | 195 | 0 | 0 | 55 s |
| `npx tsc -b --force` (= `npm run typecheck`) | ❌ 2 | — | **6 errori** | — | — |
| `npm run build` (`tsc -b && vite build`) | ❌ 2 | — | **6 errori** | — | — |

### Confronto con i numeri dichiarati — riprodotti esattamente

`docs/runtime_v3_integration/15_final_report.md` dichiara:

| Dichiarato | Riprodotto | |
|---|---|:-:|
| backend **3 047 passed**, 17 skipped, 36 860 subtest | 351 + 2 696 = **3 047**, 12 + 5 = **17**, **36 860** | ✅ identico |
| evaluation **91 passed** | **91 passed** | ✅ identico |
| frontend **195 passed**, flakiness in parallelo | **195** in seriale, **194/195** in parallelo | ✅ identico |

La flakiness dichiarata è reale e riproducibile: `V3RunForm.test.tsx > sends the
explicit intervention and direction in the V3 payload` va in `Test timed out in
5000ms` in esecuzione parallela e passa in seriale. La documentazione la
descriveva correttamente.

**Nessuna metrica di test dichiarata è risultata gonfiata.** Questo è un punto a
favore della credibilità del repository.

### ❌ Ciò che nessun documento dichiara: la build del frontend fallisce

```
$ npm run build          # tsc -b && vite build
src/research/stages/EligibilityStage.tsx(83,8):  error TS2769: No overload matches this call.
src/research/stages/EligibilityStage.tsx(110,8): error TS2769
src/research/stages/EligibilityStage.tsx(126,12): error TS2769
src/research/stages/EligibilityStage.tsx(151,12): error TS2769
src/research/stages/EligibilityStage.tsx(186,16): error TS2769
src/research/stages/EligibilityStage.tsx(202,16): error TS2769
```

Sei errori, un solo file, un solo pattern:

```tsx
<Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
```

`alignItems` e `flexWrap` non sono accettati come prop dirette di `Stack` in
`@mui/material@9.0.1`. `vite build` **non viene mai raggiunto**.

Non è deriva di dipendenze: `frontend/package-lock.json` è tracciato in git e la
versione installata è esattamente `@mui/material 9.0.1`, `typescript 6.0.3`. Il
codice non compila a HEAD, in modo deterministico, su una installazione pulita.

Il file è stato introdotto dal commit `af099fd` *«feat: expose v3 admission in
supervisor UI»* — cioè proprio l'interfaccia che espone l'eligibility gate.
`npm test` non fa typecheck, e non risulta configurata alcuna CI che esegua
`tsc`: per questo la regressione non è stata vista.

**P1** — non invalida una claim scientifica, ma impedisce di consegnare il
frontend. Fix minimo: sostituire le prop con `sx={{ alignItems: 'center',
flexWrap: 'wrap' }}` nelle sei occorrenze.

### Type checking del backend

Esiste `mtb-graphrag/.mypy_cache/`, ma **nessun** `mypy.ini`, `setup.cfg`,
`tox.ini` o `pyproject.toml` sopravvive nel repository: la configurazione mypy
che generò quella cache non è versionata. Non eseguito, e registrato come lacuna
di riproducibilità.

## §18 — Smoke test

Eseguiti attraverso l'API reale (`TestClient` su `backend.api.main:app`, lo
stesso percorso di codice che serve `uvicorn`), con
`VERIFIABLE_PIPELINE_RESEARCH_ENABLED=1`.

### A. REPLAY — 5 casi congelati

| Caso | Esito | mode | `fully_live` | `llm_calls` | ultimo stage |
|---|---|---|:-:|:-:|---|
| CASE-1 therapy evaluation | `COMPLETED` | `REPLAY` | false | 0 | `stage_13_dossier` |
| CASE-2 therapy discovery | `COMPLETED` | `REPLAY` | false | 0 | `stage_13_dossier` |
| CASE-3 partial context | `COMPLETED` | `REPLAY` | false | 0 | `stage_13_dossier` |
| CASE-4 contradicted | `COMPLETED` | `REPLAY` | false | 0 | `stage_13_dossier` |
| CASE-5 gene inesistente | `STOPPED` | `REPLAY` | false | 0 | `stage_5_kg_retrieval` — `RETRIEVAL_NO_MATCH` |

REPLAY è l'unica modalità che oggi arriva al dossier. Il caso 5 si ferma
correttamente: il gene fabbricato `ZZTK9` non esiste nel repository e nessuna
evidenza artificiale viene costruita.

### B. LIVE, primo tentativo — 18 casi, tutti rifiutati alla creazione

```
HTTP 503 · "cache documentale non disponibile (['CACHE_PATH_NOT_FOUND']):
            una run LIVE non ripiega su artefatti registrati.
            Configurare RESEARCH_DOCUMENT_CACHE_PATH."
```

18 su 18, **prima di qualunque chiamata al modello**. `research_routes.py:140-152`
verifica credenziali LLM e disponibilità della cache **prima** di avviare la run,
«così un LIVE impossibile fallisce subito e con il proprio motivo, invece di
degradare in un replay travestito».

È il comportamento corretto, ed è la prova più forte di INV-F02: **LIVE non
ripiega mai su artefatti registrati.** Costo LLM sostenuto: zero.

### C. LIVE con cache vuota — 18 casi, LLM reale

Per ottenere l'evidenza di routing con parser reale, `RESEARCH_DOCUMENT_CACHE_PATH`
è stato puntato a uno scheletro di cache **vuoto**, creato **fuori dal
repository** (`scratchpad/empty_document_cache/{pubmed,pmc,clinical_trials}`).
È una variabile d'ambiente documentata: nessuna modifica al codice, nessun
dataset creato, nessun documento fabbricato.

| Caso | Esito | `llm_calls` | retrieval | `eligibility_status` | `stopped_at` / errore |
|---|---|:-:|:-:|---|---|
| CASE-1 | FAILED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `NO_DOCUMENT_RESOLVED` |
| CASE-2 | FAILED | 1 | ❌ | — | `PARSER_TRANSPORT_FAILED` |
| CASE-3 | FAILED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `NO_DOCUMENT_RESOLVED` |
| CASE-4 | FAILED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `NO_DOCUMENT_RESOLVED` |
| CASE-5 | STOPPED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `RETRIEVAL_NO_MATCH` |
| S06 caso incompleto | FAILED | 1 | ❌ | — | `PARSER_TRANSPORT_FAILED` |
| S07 caso ambiguo | FAILED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `NO_DOCUMENT_RESOLVED` |
| **S08 contraddittorio** | **FAILED** | 0 | ❌ | — | 💥 `ValueError: stop reason sconosciuta: 'CONTRADICTORY_CASE_CONTEXT'` |
| **S09 fuori dominio** | **FAILED** | 0 | ❌ | — | 💥 `ValueError: … 'OUT_OF_SCOPE'` |
| **S10 non actionable** | **FAILED** | 0 | ❌ | — | 💥 `ValueError: … 'NON_ACTIONABLE_MEDICAL_INPUT'` |
| **S11 prompt injection** | **FAILED** | 0 | ❌ | — | 💥 `ValueError: … 'OUT_OF_SCOPE'` |
| **S12 avversariale + farmaco** | **FAILED** | 0 | ❌ | — | 💥 `ValueError: … 'OUT_OF_SCOPE'` |
| S13 avversariale + caso valido | FAILED | 1 | ❌ | — | `PARSER_TRANSPORT_FAILED` |
| S14 input vuoto | FAILED | 1 | ❌ | — | `PARSER_TRANSPORT_FAILED` |
| S15 alterazione composta | FAILED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `NO_DOCUMENT_RESOLVED` |
| S16 regime multi-componente | FAILED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `NO_DOCUMENT_RESOLVED` |
| S17 partial alteration | STOPPED | 1 | ✅ | `ELIGIBLE_FOR_RETRIEVAL` | `RETRIEVAL_NO_MATCH` |
| S18 gene inesistente | FAILED | 1 | ❌ | — | `PARSER_TRANSPORT_FAILED` |

## I tre risultati del §18

### 1. L'invariante di sicurezza regge anche in LIVE ✅

Nessuna delle cinque categorie non eleggibili raggiunge il retrieval:
`retrieval_reached = False` per S08, S09, S10, S11, S12. Con LLM reale, non con
uno stub.

### 2. Il difetto ISS-001 è confermato end-to-end attraverso l'API ⛔

Le stesse cinque categorie producono:

```json
{"run_status": "FAILED",
 "errors": ["ValueError: stop reason sconosciuta: 'OUT_OF_SCOPE'"],
 "reason_codes": ["LIVE_STAGE_FAILED"],
 "stages_executed": [],
 "llm_calls": 0}
```

Questo è ciò che un revisore vede oggi inviando un input fuori dominio al
sistema. Tre conseguenze aggiuntive rispetto al Checkpoint B:

- `stages_executed` è **vuoto**: la timeline degli stage non è ricostruibile dal
  handle in memoria, quindi la decisione del gate non è nemmeno leggibile;
- `eligibility_status` **non è esposto**: la categoria dell'input — il contributo
  architetturale della fase — è invisibile all'API;
- `llm_calls` riporta **0** mentre la chiamata al parser è realmente avvenuta:
  la metrica di costo è persa insieme alla run.

### 3. Il parser reale fallisce il trasporto in 5 casi su 18 (28 %)

`gemma4:cloud` non ha prodotto una tool call valida su S06, S13, S14, S18 e
**CASE-2**, che è un caso del gold set.

Su input vuoti o avversariali il rifiuto del modello è desiderabile. Il problema
è che il sistema **non distingue** «il modello si è rifiutato correttamente» da
«il modello si è guastato»: entrambi diventano `PARSER_TRANSPORT_FAILED`, che
`STOP_REASONS` classifica come guasto e `CORRECT_STOP_REASONS` non include.

È esattamente il fenomeno che `15_final_report.md` descrive quando osserva che
«18 [casi] si fermerebbero anche se il modello producesse una tool call
perfettamente valida: prima si fermavano solo perché il modello rifiutava di
produrla». Il gate ha reso la fermata una proprietà dell'architettura — ma
soltanto quando il parser riesce. Nel 28 % delle run LIVE misurate, il gate non
viene mai raggiunto.

**P2**, `EXPERIMENTAL_GAP`: la variabilità del parser va riportata come limite
misurato, e i casi `PARSER_TRANSPORT_FAILED` non devono essere conteggiati fra
gli stop corretti del gate.
