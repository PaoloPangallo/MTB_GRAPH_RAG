# 09 — Riproducibilità

## Ambiente

| Voce | Valore |
|---|---|
| Python | 3.12.10 |
| Sistema | Windows 11 (10.0.26200) |
| Branch | `research/v3-evaluation-pilot` |
| Base commit | `b115754e5dae2120f40663368197ff4220e7fca5` (`feature/v3-verifiable-pipeline-ui`) |
| Data di esecuzione | 2026-08-06 |
| Neo4j | non attiva, non usata |

## Commit prodotti

| Commit | Contenuto |
|---|---|
| `edb3052` | Fedeltà e completezza delle GraphCandidateAssertion |
| `2392674` | Rilevamento dello splitting dei regimi |
| `bd5ad0f` | Audit delle associazioni candidate–PMID |
| `8dce706` | Fattibilità e licenza OncoKB |
| `91068d9` | Benchmark CaseContext **congelato** (precede l'esecuzione) |
| `a477ecc` | Smoke 35 casi + repeatability |

Nessun `push`, nessun `merge`.

## Sorgenti congelate

| Artefatto | Impronta |
|---|---|
| Export CSV KG | `corpus_fingerprint 8df07e828f97a77f…` (22 file, hash per file in `kg_source_fingerprint.json`) |
| `candidates.jsonl` | `sha256 d6c65c26…71235d` — verificato contro `hashes.json` |
| Benchmark RQ4 | `sha256 dd639ed085851ae2d0c99a6d0a500d7e399894e441133c89eba4178f05aaedc4` |
| Congelato il | 2026-08-06T14:32:06Z, commit `8dce7068` |
| Prompt parser | `casecontext-parser-prompt/1.0`, hash `7b59558bba3b7a2b…` |
| Modello | `gemma4:cloud` |

Il materializzatore originale, non presente sul branch corrente, è recuperabile
da git al commit `3694979` (branch `refactor/v3-document-grounded-claims`):

```bash
git show 3694979:mtb-graphrag/benchmarks/mtb_evidence/document_grounded_claims/kg.py
git show 3694979:mtb-graphrag/benchmarks/mtb_evidence/document_grounded_claims/models.py
git show 3694979:.../graph_candidate_repository/2.0/manifest.json
```

## Riesecuzione

```bash
cd mtb-graphrag

# Offline, deterministici — riproducono gli stessi artefatti byte per byte
python -m evaluation.run_rq1
python -m evaluation.build_rq1_sample
python -m evaluation.build_rq3_plan
python -m evaluation.run_rq2 --offline

# Rete: API ufficiali NCBI, solo metadata (12 richieste in batch)
python -m evaluation.run_rq2
python -m evaluation.build_rq2_sample

# Verifica che il gold RQ4 non sia stato modificato
python -m evaluation.freeze_rq4 --verify

# Chiamate reali al provider LLM — consumano budget
python -m evaluation.run_rq4              # 35 chiamate
python -m evaluation.run_rq4_repeat       # 15 chiamate
python -m evaluation.run_rq4 --recompute  # 0 chiamate, ricalcola le metriche

# Test
python -m pytest evaluation/tests/ -q
python -m pytest backend/research_pipeline/tests backend/tests -q
```

## Determinismo

| Componente | Determinismo |
|---|---|
| RQ1 | **Completo.** Nessuna sorgente di casualità; stessi input → stessi artefatti |
| RQ2 struttura | **Completo** |
| RQ2 risoluzione | Dipende dallo stato di PubMed alla data; la cache locale (`evaluation/rq2/pubmed_metadata_cache.json`) rende riproducibile la run |
| RQ3 | **Completo** (nessuna chiamata) |
| RQ4 | **Non deterministico** per costruzione: il modello è campionato. `exact_output_agreement = 0.20`, ma field set, verifier e routing sono stabili al 100 % su 15 esecuzioni |

## Configurazione necessaria

`mtb-graphrag/.env` (gitignored, mai committato):

| Variabile | Necessaria per |
|---|---|
| `OLLAMA_API_KEY` | RQ4 |
| `ONCOKB_TOKEN` | solo per la verifica di autenticazione di RQ3 |
| `NCBI_EMAIL` | opzionale, cortesia verso NCBI |

**Override necessario per RQ4**: `RESEARCH_PIPELINE_LLM_BASE_URL=https://ollama.com`.
Il default `https://api.ollama.com` risponde HTTP 405 sul percorso
`/v1/chat/completions`. I driver di RQ4 lo impostano se assente e lo registrano
in `aggregate_metrics.json`.

## Budget consumati

| Risorsa | Chiamate | Budget |
|---|---|---|
| Parser LLM (smoke) | 35 | 35 |
| Parser LLM (repeatability) | 15 | 15 |
| **Parser LLM totale** | **50** | **50** |
| NCBI E-utilities `esummary` | 12 (batch da 200, ≥0.40 s fra richieste) | — |
| NCBI `efetch` (abstract del campione) | 1 | — |
| OncoKB | **1** (`/api/v1/info`, solo metadata) | 20 non usate |

## Cosa non è committato

Token e credenziali (`.env` è in `.gitignore`); documenti integrali; dati reali
di paziente; risposte grezze contenenti segreti. Due test lo verificano:
`test_no_secrets_in_evaluation_artifacts` e
`test_no_patient_data_markers_in_artifacts`.

Gli abstract nel campione manuale RQ2 sono anteprime troncate a 400 caratteri,
richieste solo per i 37 PMID del campione, non testi integrali.

## Esito dei test

| Suite | Esito |
|---|---|
| `evaluation/tests/` | **42 passed** |
| `backend/research_pipeline/tests` + `backend/tests` | **2 962 passed, 17 skipped, 36 860 subtests passed** |
