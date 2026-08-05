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

## Run end-to-end dei 5 casi sintetici

Da compilare al Passo 10. Non ancora eseguita.
