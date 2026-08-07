# 05 — Build e test

Dati: `evaluation/final_deliverability/build_and_test_results.json`.

| Comando | exit | passed | failed | skipped | durata |
|---|:-:|---:|---:|---:|---:|
| `env -u PYTHONPATH pytest -q` | **0** | **3 189** | 0 | 17 | 518 s |
| `npx vitest run --no-file-parallelism` | **0** | **200** | 0 | 0 | 114 s |
| `npm run build` | **0** | — | 0 | — | — |
| `python -m evaluation.run_rq4_canonical_runtime` | **0** | 35 casi | 0 | — | — |
| `npm run lint` | **1** | — | **36 errori** | — | — |

Sottotest: **36 890**.

## `env -u PYTHONPATH` — la verifica che conta per ISS-006

Il comando è stato eseguito con `PYTHONPATH` **rimosso dall'ambiente**. Prima
del fix sprint lo stesso comando falliva con `ModuleNotFoundError: backend`.
Ora colleziona ed esegue tutte e tre le suite — `backend/tests`,
`backend/research_pipeline/tests`, `evaluation/tests` — tramite i `testpaths` di
`pytest.ini`. La suite di evaluation (91 test) è quindi inclusa.

## Frontend

`npm run build` esegue `tsc -b && vite build`: entrambi completano. Il warning
sulla dimensione dei chunk è di ottimizzazione, non bloccante.

## Rilievo nuovo — NEW-02 (P3, non bloccante, NON una regressione)

`npm run lint` fallisce con **36 errori** in 9 file:

```
KnowledgeGraph3D.tsx · ReportView.tsx · V3EvidenceView.test.tsx
LegacyV3Console.tsx · ResearchConsole.tsx · RunSpine.tsx
api.ts · stages/kit.tsx
```

Verificato che è **preesistente a `0219e0a`**: nessuno di questi file è stato
toccato dal fix sprint, e i tre file che il fix sprint ha modificato
(`DossierView.tsx`, `DossierView.test.tsx`, `EligibilityStage.tsx`) sono
**lint-clean**.

Gli errori sono di categoria `react-refresh/only-export-components` — una regola
di ergonomia dello sviluppo, non di correttezza. Il §17 elenca fra i criteri di
freeze la build e i test, non il lint.

L'audit precedente aveva registrato «eslint configurato, non eseguito»: questo
audit lo ha eseguito e riporta il risultato. È un rilievo nuovo, non un
peggioramento.

## Type checking del backend

Non configurato: nessun `mypy.ini` o `pyproject.toml` versionato. Invariato
rispetto all'audit precedente e registrato come limite.
