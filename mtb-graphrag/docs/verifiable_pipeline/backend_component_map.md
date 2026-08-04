# Backend component map — Fase A

**Branch:** `feature/v3-verifiable-pipeline-ui`
**Data:** 2026-08-04

Mappa dei componenti backend rispetto ai 15 stage della sezione 8 del prompt.
Nessun file di codice modificato.

Legenda origine:
- **P** = runtime di prodotto, `backend/`, branch corrente
- **R** = harness di ricerca, `benchmarks/mtb_evidence/`, branch
  `research/v3-end-to-end-pipeline-interaction-pilot` @ `6ee64c5`
- **—** = non esiste

## 1. Copertura per stage

| # | Stage | Origine | Componente | Classe |
|---:|---|:--:|---|---|
| 1 | Case Input | R | `case_definitions.py` (5 casi sintetici) | RESEARCH_ONLY → promuovere |
| 2 | CaseContext Parser | R | `casecontext_parser.py` + `casecontext_prompt.py` | RESEARCH_ONLY → promuovere |
| 3 | CaseContext Match Verifier | R | `casecontext_match_verifier.py` | RESEARCH_ONLY → promuovere |
| 4 | Retrieval Plan | R | `retrieval.py` | RESEARCH_ONLY → promuovere |
| 5 | KG Retrieval | R | `document_grounded_claims/kg.py` | RESEARCH_ONLY → promuovere |
| 6 | Document Resolution | R | `document_grounded_claims/documents.py` | RESEARCH_ONLY → promuovere |
| 7 | Source Unit | R | `document_grounded_claims/authorized_cache.py` | RESEARCH_ONLY → promuovere **con cautela** (§4) |
| 8 | Paper Selection | R | `paper_selection.py` | RESEARCH_ONLY → promuovere |
| 9 | Paper Context Enricher v2 | R | `paper_context_enricher_v2{,_prompt,_transport}.py` | RESEARCH_ONLY → promuovere |
| 10 | Enrichment Validation | R | `paper_context_enricher_v2_validator.py`, `enrichment_validator.py` | RESEARCH_ONLY → promuovere |
| 11 | Deterministic Gates | **P** | `evidence/shadow/integrated_gates_v13.py` | **KEEP** |
| 12 | Status / classificazione | **P** | `evidence/retrieval/v3_scoring.py`, `v3_result.py` | **KEEP** |
| 13 | Dossier Builder | R + P | `end_to_end_pipeline_pilot/dossier.py`; `evidence_bundle/builder.py`; lato P `api/v3_presentation.py` | REFACTOR |
| 14 | Dossier Narrator | — | inesistente | MISSING |
| 15 | Narrative Verifier | — | inesistente per la narrazione | MISSING |

Gate e scoring — cioè gli stage che **devono restare deterministici** — sono già
in produzione e non vanno toccati. Gli stage LLM e documentali sono tutti nel
solo harness di ricerca.

## 2. Runtime di prodotto (`backend/`) — cosa resta com'è

| Componente | File | Classe |
|---|---|---|
| Route V3 | `api/routes.py::v3_retrieve` | KEEP |
| Request/response V3 | `api/v3_schemas.py` (133) | KEEP |
| Adapter di presentazione | `api/v3_presentation.py` (878) | REFACTOR — vi si aggancerà la proiezione dossier |
| Pipeline retrieval | `evidence/retrieval/pipeline.py` | KEEP |
| Backend V3 | `evidence/retrieval/v3_backend.py` | KEEP |
| Repository/corpus | `evidence/corpus/loader.py`, `repository.py` | KEEP |
| Gate strutturali 1.3 | `evidence/shadow/integrated_gates_v13.py` | KEEP |
| Scoring | `evidence/retrieval/v3_scoring.py` | KEEP |
| Risultato nativo | `evidence/retrieval/v3_result.py` | KEEP |

Vincolo dell'utente rispettato per costruzione: nessuno di questi endpoint o
moduli viene sostituito; il research runtime vive in un namespace separato.

## 3. Strato di controllo — base dell'event model

`backend/pipeline/control/` (2.180 righe) + `agentic/ledger.py` (296).
Analisi completa in `current_state_audit.md` §5. In sintesi:

| Requisito §6–7 del prompt | Stato |
|---|---|
| event log append-only | **esiste** (`agentic/ledger.py`) |
| hash chain verificabile | **esiste** (`verify_chain`, esposto in API) |
| distinzione evento / vista corrente / output canonico | **esiste** (`events` / `canonical` / `projection`) |
| replay dagli eventi | **esiste** (`replay.py`) |
| redazione segreti pre-scrittura | **esiste** (`sanitize_text`) |
| bounding payload, no full text | **esiste** (`MAX_EVENT_PAYLOAD_BYTES`, `_DROPPED_TEXT_FIELDS`) |
| omissione non silenziosa | **esiste** (`omitted_records`) |
| `event_id`, `run_id`, `timestamp`, `producer` | da verificare in `ledger_schema.py` |
| `stage_id`, `payload hash`, correlation/causation | **da aggiungere** |
| tipi evento della pipeline verificabile | **da aggiungere** (oggi vocabolario V2/agentico) |
| contratto `PipelineRun` / `PipelineStage` | **MISSING** |
| SSE | **MISSING** — nessun `text/event-stream` nel repo |

Conclusione: **REFACTOR ed estensione**, non riscrittura. Riscrivere un event
log append-only quando ne esiste uno con catena di hash e sanitizzazione già
testata sarebbe una regressione di sicurezza oltre che di effort.

## 4. Rischio sicurezza da chiudere prima di esporre lo Stage 7

`document_grounded_claims/authorized_cache.py` è il modulo più grande del
harness (27,8 KB) e gestisce la cache documentale autorizzata da cui derivano le
SourceUnit.

Il prompt richiede allo Stage 7 una "preview redatta" e vieta di mostrare
automaticamente articoli completi; la sezione 2 vieta di committare risposte raw
con testi documentali completi.

Prima di qualunque esposizione via API va verificato che:

1. la preview SourceUnit sia troncata alla fonte, non nel frontend;
2. gli eventi non trasportino full text — `_DROPPED_TEXT_FIELDS` copre già
   `abstract`/`full_text`/`body`, ma il nome del campo usato da
   `authorized_cache.py` **non è ancora stato verificato**;
3. nessun artefatto di run finisca in git con testo integrale.

Questo è un controllo bloccante per lo Stage 7, non un miglioramento opzionale.

## 5. Test backend esistenti

76 file in `backend/tests/`, più `backend/tests_external/` e
`backend/tests_history/`. Nel harness: ~40 KB fra
`tests/test_pilot_components.py` (26.365 byte) e
`tests/test_paper_context_enricher_v2.py` (13.955 byte).

**Non ho eseguito alcuna suite.** Lo stato dei test è quindi *non verificato* e
non viene dichiarato passante in nessun documento di questa fase. L'esecuzione
della baseline è il primo passo della Fase B.

## 6. Conseguenza per la pianificazione

Il lavoro **non** è "costruire la pipeline": la pipeline esiste ed è già passata
per un pilot con esito `PIPELINE_INTERACTION_PILOT_PASSED` e
`PAPER_CONTEXT_ENRICHER_V2_PROMISING`. Il lavoro è:

1. **promuovere** 15 moduli da `benchmarks/` a un package di research runtime;
2. **estendere** il vocabolario eventi e i contratti run/stage esistenti;
3. **esporre** un namespace `/api/v1/research/pipeline/*` dietro
   `VERIFIABLE_PIPELINE_RESEARCH_ENABLED`;
4. **costruire** la UI di osservabilità, che oggi non esiste in alcuna forma;
5. **isolare** il vecchio Claim Extractor e le viste demo/sintetiche.

I punti 1 e 3 vanno progettati contro il SYSTEM DESIGN, non improvvisati: sono
la ragione per cui `design_gap_analysis.md` resta in attesa del documento.
