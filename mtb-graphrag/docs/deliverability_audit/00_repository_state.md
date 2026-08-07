# 00 — Stato del repository

Dati grezzi: `evaluation/deliverability/repository_state.json`,
`evaluation/deliverability/raw/A01_git_status.txt` … `A05_datasets.txt`.

## Identità

| | |
|---|---|
| Branch | `feature/v3-runtime-gca3-eligibility-gate` |
| HEAD | `0219e0a7a4a063668c72c941413fbd8382838b32` |
| Ultimo commit | `docs: report runtime v3 integration decision` — Thu Aug 6 23:18:18 2026 +0200 |
| Remote | `origin` → `https://github.com/PaoloPangallo/MTB_GRAPH_RAG.git` |
| Python | 3.12.10, venv alla **radice** del repository (`.venv/`), non in `mtb-graphrag/` |
| pytest | 9.1.1 |
| Node / npm | v20.19.0 / 11.12.1 |

## §0 — Working tree NON pulita: hard stop attivato, deviazione autorizzata

Il §0 del mandato impone di fermarsi se la working tree non è pulita. **Non lo
è.** La deviazione è stata autorizzata esplicitamente dall'utente prima
dell'inizio dell'audit, e la ragione è registrata qui perché sia verificabile.

**Staged (3):**

```
A  Pipeline.png
A  architettura/index.html
A  img.png
```

**Untracked (12 path):**

```
Mateo.pdf
architettura/README.md
mtb-graphrag/Relazione_V2_V3_fonti_pipeline_aggiornata.{pdf,tex}
mtb-graphrag/Relazione_V2_V3_fonti_pipeline_revisionata.{pdf,tex}
mtb-graphrag/benchmarks/mtb_evidence/exploratory/manual_v3_cases/
mtb-graphrag/benchmarks/mtb_evidence/exploratory/manual_v3_cases_product_hardening/case_0{1,2,3,4}_api_response.json
mtb-graphrag/scripts/start_v3_product.ps1
```

**Analisi d'impatto sull'audit.**

`git status --porcelain --untracked-files=all | grep -E '\.py$'` restituisce
**zero righe**. Nessun modulo Python è modificato, aggiunto o rimosso rispetto a
`0219e0a`. Il codice auditato è quindi esattamente il codice committato.

I file coinvolti sono: due immagini, una pagina HTML di documentazione
architetturale, quattro PDF/TeX di relazione, uno script PowerShell di avvio che
nessun modulo importa, e artifact esploratori JSON. Nessuno di questi è
importabile, eseguito o letto dal runtime.

**Un'eccezione va segnalata e sarà ripresa nel §25 (contaminazione):** i
`manual_v3_cases/` e i quattro `case_0N_api_response.json` sono **output
sperimentali non versionati**. Non entrano in alcuna metrica di questo audit, e
non possono entrare in una metrica della tesi finché restano fuori da git.

## Worktree

Quattro worktree registrati, tre in `%TEMP%` e non auditati:

| Path | HEAD | Branch |
|---|---|---|
| `Desktop/IspezioneDatasetTesi` | `0219e0a` | `feature/v3-runtime-gca3-eligibility-gate` — **target dell'audit** |
| `%TEMP%/codex-v3-document-grounded-claims` | `6ee64c5` | `research/v3-end-to-end-pipeline-interaction-pilot` |
| `%TEMP%/hrc/baseline` | `b6694ba` | detached |
| `%TEMP%/hrc/wt` | `0fd5d1b` | detached |

`6ee64c5` non è un dettaglio irrilevante: è il commit che
`data_access.load_frozen_enricher_runs()` cita come origine delle 7 chiamate
reali all'enricher rigiocate in REPLAY. L'artefatto è dentro questo repository,
ma la sua provenienza punta a un worktree temporaneo.

## Ambiente e dipendenze — primo gap di riproducibilità

| | |
|---|---|
| `requirements.txt` | `mtb-graphrag/backend/config/requirements.txt`, **10 righe** |
| Versioni pinnate | **0 su 10** |
| `pyproject.toml` | assente |
| Lockfile | assente |
| `pytest.ini` / `setup.cfg` / `tox.ini` | assenti |
| `conftest.py` | assente in tutto il repository |
| Pacchetti realmente installati | **188** |

`requirements.txt` dichiara `fastapi, uvicorn[standard], langgraph,
langchain-core, langchain-ollama, neo4j, python-dotenv, requests, pydantic,
typing-extensions`. Non dichiara `pytest`, `httpx`, `pandas`, `numpy`, tutti
necessari per eseguire le suite di test e gli script di evaluation.

Conseguenza operativa: **un revisore che segua il README non ottiene un ambiente
in cui i test girano.** Vedi `10_reproducibility.md`.

L'assenza di `conftest.py` significa inoltre che l'import dei package dipende da
`PYTHONPATH=mtb-graphrag` impostato a mano (lo fa `run.ps1`, non i test).

## Entrypoint

**Backend** — `uvicorn backend.api.main:app`. Una sola app FastAPI monta **due
runtime distinti**:

| Prefisso | Modulo | Ruolo | Gating |
|---|---|---|---|
| `/api/v1` | `backend.api.routes` | pipeline di prodotto legacy (agentica, Neo4j, OncoKB) | nessuno |
| `/api/v1/research/pipeline` | `backend.api.research_routes` | **runtime di ricerca canonico** | `VERIFIABLE_PIPELINE_RESEARCH_ENABLED`, 404 se assente |

**Frontend** — `mtb-graphrag/frontend`, Vite + React 19, `npm run dev` /
`vitest run` / `tsc -b`.

## Dati congelati

| Dataset | Record | Byte | In git |
|---|---:|---:|---|
| `graph_candidate_repository/2.0/candidates.jsonl` | 46 864 | 72,5 MB | ✅ |
| `graph_candidate_repository/3.0/candidates.jsonl` | 46 142 | 111,9 MB | ✅ |
| `evidence_bundle/evidence_bundles.jsonl` | **25** | 35 KB | ✅ |
| `authorized_document_cache_pilot/source_unit_index.jsonl` | 3 402 | 2,0 MB | ✅ |
| `authorized_document_cache_pilot/document_manifest.jsonl` | 43 | 60 KB | ✅ |
| `end_to_end_pipeline_pilot/paper_context_enricher_v2_runs.jsonl` | **7** | 12 KB | ✅ |
| `data_cache/document_grounding/` (testo dei documenti) | — | — | ❌ **assente e gitignored** |

### Il numero che vincola tutto il resto

I 25 EvidenceBundle coprono **16 candidate distinte** e 25 documenti distinti.
Il retrieval è ristretto per costruzione alle candidate che possiedono almeno un
bundle già in cache (`kg_retrieval.retrieve`, riga 116). Quindi:

```
candidate raggiungibili end-to-end = 16 / 46 864 = 0,034 %
```

Non è un difetto del codice: è la dimensione reale del pilot documentale, ed è
il denominatore onesto di qualsiasi claim su RQ2. Vedi `05_document_grounding.md`
e `09_rq_readiness.md`.

## Servizi esterni

| Servizio | Richiesto da | Disponibile qui |
|---|---|---|
| Ollama cloud (`https://api.ollama.com`, `gemma4:cloud`) | runtime di ricerca in LIVE — parser ed enricher | ✅ credenziale in `.env` |
| Neo4j | **solo** pipeline di prodotto legacy | non verificato (non serve al runtime auditato) |
| PubMed/NCBI | ripopolamento della cache documentale | non usato a runtime (`network=False`) |
| OncoKB | **solo** pipeline di prodotto legacy | non chiamato dal runtime di ricerca |

## Knowledge Graph realmente usato

Il runtime di ricerca **non interroga Neo4j**. Il "KG" è il repository statico
già materializzato `graph_candidate_repository/2.0/candidates.jsonl`, dichiarato
come tale nel docstring di `retrieval/kg_retrieval.py`. Il Neo4j vivo appartiene
alla pipeline di prodotto legacy.

Questo va detto esplicitamente nella tesi: le proprietà di *representation
fidelity* misurate riguardano la **materializzazione** del grafo, non una query
live sul grafo.
