# End-to-end test report

## Baseline — Passo 0 della Fase C

Eseguita **prima** di qualunque modifica di codice, su
`feature/v3-verifiable-pipeline-ui` @ `bf3b343`.
Data: 2026-08-04.

### Esito

| Suite | Comando | Esito | Durata |
|---|---|---|---|
| Backend | `pytest backend/tests -q` | **2696 passed, 5 skipped**, 36.860 subtest | 335,63 s |
| Frontend | `npm test` (vitest run) | **38 passed**, 4 file | 6,91 s |
| Typecheck | `npm run typecheck` (`tsc -b`) | **exit 0** | — |

Baseline **completamente verde**. Nessun fallimento preesistente da
interpretare: la riga aperta della §27 del prompt — *"i test esistenti
falliscono in modo non compreso"* — è chiusa.

Questa è la baseline di regressione: qualunque fallimento successivo è
introdotto dal lavoro sulla pipeline verificabile, non ereditato.

### Ambiente

- Python: venv in `IspezioneDatasetTesi/.venv` (Python 3.12)
- `PYTHONPATH=mtb-graphrag`, coerente con `run.ps1`
- Node: vitest 4.1.10, TypeScript 6.0.2
- OS: Windows 11

### Due reperti sull'infrastruttura di test

**1. pytest non era installato e non è dichiarato.**
`backend/config/requirements.txt` contiene 10 righe (fastapi, uvicorn,
langgraph, langchain-core, langchain-ollama, neo4j, python-dotenv, requests,
pydantic, typing-extensions) e **nessun runner di test**. I 76 file di test
backend non erano eseguibili in questo ambiente senza installazione manuale.

pytest 9.1.1 è stato installato nel venv per produrre questa baseline. Va
aggiunto alle dipendenze di sviluppo: una suite di 2696 test senza runner
dichiarato è un rischio di manutenzione, non una svista minore.

**2. Il blocco Vitest su Windows non si riproduce.**
La spec precedente
(`docs/superpowers/specs/2026-08-01-v3-pipeline-observability-ui-design.md`)
riportava:

> "The frontend test runner is currently blocked during Vitest configuration
> loading by Windows `spawn EPERM`."

Non si verifica più: vitest 4.1.10 carica la configurazione ed esegue i 38 test
in 6,91 s. La cautela espressa nei documenti di Fase A e B su questo punto è
quindi **superata**, e i test frontend possono essere considerati eseguibili.

### Avvertenza

Nessun `warning` bloccante. Unico avviso, da FastAPI e non dal codice del
progetto:

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is
deprecated; install `httpx2` instead.
```

Rilevante per il Passo 8: i test degli endpoint REST useranno `TestClient`.
Non è un problema oggi, ma è la ragione per cui l'aggiornamento a `httpx2` va
valutato quando si aggiungeranno i test delle nuove rotte.

---

## Run end-to-end dei 5 casi sintetici — Passo 10

Eseguita attraverso l'API reale (`POST /api/v1/research/pipeline/runs`), non
chiamando i moduli direttamente: è il percorso che vedrà il frontend.

### Esito per caso

| Caso | Modo | Run status | Stop | Stage OK / SKIP | Eventi | Catena | Candidate | Dossier |
|---|---|---|---|---:|---:|---|---:|---:|
| CASE-1 therapy evaluation strong match | FROZEN_REPLAY | COMPLETED | — | 13 / 2 | 42 | ✅ | 1 | 200 |
| CASE-2 therapy discovery | FROZEN_REPLAY | COMPLETED | — | 13 / 2 | 42 | ✅ | 1 | 200 |
| CASE-3 partial incomplete context | FROZEN_REPLAY | COMPLETED | — | 13 / 2 | 42 | ✅ | 1 | 200 |
| CASE-4 contradicted or resistance | FROZEN_REPLAY | COMPLETED | — | 13 / 2 | 42 | ✅ | 1 | 200 |
| CASE-5 casecontext mismatch no match | FROZEN_REPLAY | **STOPPED** | `RETRIEVAL_NO_MATCH` | 4 / 10 | 26 | ✅ | 0 | **409** |

I 2 stage `SKIPPED` dei casi completati sono narratore e verificatore narrativo,
`NOT_IMPLEMENTED` permanenti. I 10 del CASE-5 sono gli stage a valle
dell'arresto, ciascuno con il reason code che lo spiega.

### Status finali e supporto documentale

| Caso | Status | Quote accettate | Rigettate | Astensioni |
|---|---|---:|---:|---:|
| CASE-1 | `PARTIAL` | 1 | 0 | 0 |
| CASE-2 | `DISCOVERED` | 1 | 1 | 0 |
| CASE-3 | `AMBIGUOUS` | 0 | 0 | 2 |
| CASE-4 | `AMBIGUOUS` | 0 | 0 | 2 |
| CASE-5 | — (fermato) | 0 | 0 | 0 |
| **Totale** | | **2** | **1** | **4** |

### Corrispondenza con il pilot

I totali coincidono **esattamente** con
`paper_context_enricher_v2_metrics.json` @ `6ee64c5`: 2 quote accettate, 1
rigettata (`REJECTED_QUOTE_NOT_FOUND`), 4 astensioni su 7 chiamate. La
promozione non ha alterato gli esiti.

CASE-4 è nominalmente il caso "contradicted or resistance" ma produce
`AMBIGUOUS`, non `CONTRADICTED`: entrambi i suoi enrichment si sono astenuti,
quindi non esiste segnale documentale sulla direzione. È lo stesso esito
registrato dal pilot — *"Caso 4: AMBIGUOUS, mai DIRECT/CONTRADICTED senza
prova"* — e va letto come corretto: il sistema non dichiara una contraddizione
che nessun documento supporta.

### Cosa dimostra

- il testo clinico libero attraversa 15 stage tracciati;
- l'arresto corretto (CASE-5) produce `STOPPED`, non `FAILED`, e il dossier
  risponde `409` spiegando perché non esiste;
- 194 eventi complessivi, tutte le catene di hash verificate;
- QUOTE e ABSTAIN compaiono entrambi come esiti normali;
- ogni stage riporta durata, producer e reason code.

### Cosa **non** dimostra

Gli stage 6-10 sono in `FROZEN_REPLAY`: la cache documentale non esiste più,
quindi selezione paper, chiamata all'enricher e validazione sono rigiocate dagli
artefatti del pilot, non eseguite ora. Sono risposte reali del modello, ma
registrate. Con `RESEARCH_PIPELINE_CACHE_ROOT` popolata quegli stage tornano
eseguibili.

Il campione resta minuscolo: 4 candidate, 7 chiamate, 2 citazioni accettate.
Dimostra la meccanica e la sicurezza architetturale, non la resa clinica.
