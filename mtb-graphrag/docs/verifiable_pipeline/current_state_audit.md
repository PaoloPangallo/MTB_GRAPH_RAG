# Current state audit — Fase A

**Branch di lavoro:** `feature/v3-verifiable-pipeline-ui`
**Creato da:** `research/v3-unified-dossier-contract` @ `690d7a4`
**Repo root:** `C:/Users/paolo/Desktop/IspezioneDatasetTesi` (repo unico; `mtb-graphrag/` è una sottocartella, non un repo annidato)
**Data:** 2026-08-04

Questo documento registra **ciò che esiste oggi**. Non contiene decisioni di
design: è deliberatamente indipendente dal SYSTEM DESIGN, che al momento della
stesura non è ancora stato fornito. Il confronto design/repository vive in
`design_gap_analysis.md`, non qui.

## 1. Stato della working tree al momento dell'audit

Working tree **non pulita**: 16 voci untracked, conservate invariate dal cambio
di branch. Nessuna è stata modificata, spostata o committata durante l'audit.

| Voce untracked | Natura |
|---|---|
| `Mateo.pdf` | Paper ESMO ESCAT (Mateo et al., Ann Oncol 2018). Non è un documento di architettura. |
| `mtb-graphrag/Relazione_V2_V3_fonti_pipeline_{aggiornata,revisionata}.{tex,pdf}` | Relazione di tesi, 2 varianti |
| `mtb-graphrag/docs/end_to_end_pipeline_pilot/` | 27 documenti del pilot end-to-end |
| `mtb-graphrag/docs/llm_claim_extractor_pilot/` | 74 documenti del pilot Gemma claim extractor |
| `mtb-graphrag/docs/superpowers/{plans,specs}/2026-08-01-v3-claim-contract-correction*` | Piano + spec correzione contratto claim |
| `mtb-graphrag/benchmarks/.../manual_v3_cases*/` , `.test_tmp/` | Artefatti di run manuali |
| `mtb-graphrag/scripts/start_v3_product.ps1` | Script di avvio |

## 2. Worktree attivi

| Path | Branch | Rilevanza |
|---|---|---|
| `C:/Users/paolo/Desktop/IspezioneDatasetTesi` | `feature/v3-verifiable-pipeline-ui` | worktree principale, questo lavoro |
| `C:/Users/paolo/AppData/Local/Temp/codex-v3-document-grounded-claims` | `research/v3-end-to-end-pipeline-interaction-pilot` @ `6ee64c5` | **contiene tutto il codice della pipeline descritta** |
| `C:/Users/paolo/AppData/Local/Temp/hrc/baseline` | detached `b6694ba` | non pertinente |
| `C:/Users/paolo/AppData/Local/Temp/hrc/wt` | detached `0fd5d1b` | non pertinente |

Il secondo worktree non è stato modificato. Tutte le letture del codice pilot
sono avvenute via `git show` / `git ls-tree`, senza toccarne la working copy.

## 3. Il reperto centrale dell'audit

> **La pipeline descritta nel prompt esiste per intero, ma come harness di
> ricerca su un branch diverso, e non è raggiungibile da alcun endpoint HTTP.**

Tre livelli oggi disgiunti:

| Livello | Dove vive | Raggiungibile dalla UI? |
|---|---|---|
| **Runtime di prodotto** | `backend/api/routes.py`, `backend/pipeline/evidence/` | Sì — `POST /api/v1/v3/retrieve` |
| **Runtime V2 / agentico** | `backend/pipeline/{graph.py,agents/,agentic/,control/}` | Sì — `/analyze`, `/compare-architectures`, … |
| **Pipeline verificabile (parser→dossier)** | `benchmarks/mtb_evidence/` @ `6ee64c5`, **altro branch** | **No** |

`docs/repository_map/V3_RUNTIME_FLOW.md` conferma il confine sul lato prodotto:

> "La route V3 è strutturale: non attraversa graph.py, agents/ o llm/. La route
> V3 non scrive ledger, non interroga Neo4j e non chiama provider esterni."

Il percorso V3 attuale è quindi **solo** lo stadio deterministico di retrieval
strutturale. Non contiene: CaseContext Parser, Match Verifier, query al
Knowledge Graph, Document Resolution, SourceUnit, Paper Selection, Paper Context
Enricher, enrichment validation, narratore.

## 4. Superficie API attuale

`backend/api/routes.py` (365 righe), prefisso `/api/v1`:

| Endpoint | Architettura | Classificazione |
|---|---|---|
| `POST /compare-architectures` | V2 deterministico vs agentico | LEGACY_COMPATIBILITY |
| `GET /agent-runs/{run_id}` | ledger append-only agentico | **KEEP** — infrastruttura eventi riutilizzabile |
| `GET /subgraph` | sotto-grafo KG; `mode=zeroshot` genera un grafo **sintetico** | RESEARCH_ONLY |
| `POST /analyze` | V2 GraphRAG | LEGACY_COMPATIBILITY |
| `POST /enrich` | OncoKB enricher | LEGACY_COMPATIBILITY |
| `POST /zeroshot` | baseline senza grafo | RESEARCH_ONLY |
| `POST /websearch` | baseline web search | RESEARCH_ONLY |
| `POST /rag` | baseline RAG | RESEARCH_ONLY |
| `POST /v3/retrieve` | retrieval strutturale V3 | **KEEP** — unico percorso V3 |
| `POST /judge` | LLM-as-judge | RESEARCH_ONLY |

Nessun endpoint è `MISSING`-free rispetto al target: **non esiste** alcun
endpoint di run/stage/event/provenance/dossier per una pipeline osservabile.

## 5. Infrastruttura eventi già esistente — da riusare, non duplicare

Questo è il ritrovamento più importante per le sezioni 6–7 del prompt, che
chiedono esplicitamente di non duplicare contratti equivalenti.

`backend/pipeline/control/` (2.180 righe) e `backend/pipeline/agentic/ledger.py`
implementano già un event log append-only di qualità:

| File | Righe | Cosa fornisce |
|---|---:|---|
| `control/events.py` | 211 | vocabolario eventi, sanitizzazione segreti, bounding payload |
| `control/contracts.py` | 365 | contratti tipizzati |
| `control/runner.py` | 381 | orchestratore |
| `control/canonical.py` | 233 | vista canonica ricostruita |
| `control/projection.py` | 172 | proiezione |
| `control/replay.py` | 134 | replay dagli eventi |
| `control/recorder.py` | 98 | registrazione |
| `control/metrics.py` | 127 | metriche |
| `agentic/ledger.py` | 296 | ledger append-only con **hash chain** (`verify_chain`) |

Proprietà già garantite e riusabili così come sono:

- **append-only con catena di hash verificabile** (`GET /agent-runs/{run_id}`
  restituisce `hash_chain_valid`);
- **redazione dei segreti prima della scrittura** — `sanitize_text()` rimuove
  `Bearer`, credenziali in URL, coppie `api_key=…`. Il commento nel codice
  motiva la scelta: un ledger append-only non consente cancellazione a
  posteriori;
- **bounding dei payload** — `MAX_EVENT_PAYLOAD_BYTES = 64_000`,
  `MAX_TEXT_FIELD_CHARS = 600`, e `_DROPPED_TEXT_FIELDS` scarta
  `abstract`/`full_text`/`body`. Risponde direttamente al vincolo "non
  committare risposte raw contenenti testi documentali completi";
- **omissione mai silenziosa** — `bound_records()` registra `omitted_records` e
  `payload_truncated`;
- **separazione evento storico / vista corrente** — `events.py` vs
  `canonical.py` vs `projection.py`, esattamente la tripartizione chiesta dalla
  sezione 7.

**Limite:** il vocabolario eventi è quello V2/agentico (`plan_decision`,
`tool_started`, `collection_completed`, …). I tipi richiesti dalla sezione 7
(`CASECONTEXT_PARSED`, `PAPER_SELECTED`, `ENRICHMENT_PROPOSED`, …) non
esistono. Il meccanismo è riusabile; il vocabolario va esteso.

Classificazione: **REFACTOR** (estendere il vocabolario), non REPLACE.

## 6. La pipeline verificabile come harness di ricerca

Branch `research/v3-end-to-end-pipeline-interaction-pilot` @ `6ee64c5`.

### 6.1 `benchmarks/mtb_evidence/end_to_end_pipeline_pilot/`

| Modulo | Byte | Stage del prompt |
|---|---:|---|
| `case_definitions.py` | 6.146 | §16 — i 5 casi sintetici esistono già |
| `casecontext_parser.py` | 1.767 | STAGE 2 |
| `casecontext_prompt.py` | 4.960 | STAGE 2 (prompt version) |
| `casecontext_match_verifier.py` | 6.884 | STAGE 3 |
| `retrieval.py` | 6.663 | STAGE 4–5 |
| `paper_selection.py` | 3.594 | STAGE 8 |
| `paper_context_enricher_v2.py` | 4.007 | STAGE 9 |
| `paper_context_enricher_v2_prompt.py` | 5.383 | STAGE 9 (prompt version) |
| `paper_context_enricher_v2_transport.py` | 3.641 | STAGE 9 (transport version) |
| `paper_context_enricher_v2_validator.py` | 5.692 | STAGE 10 |
| `enrichment_validator.py` | 5.670 | STAGE 10 |
| `dossier.py` | 1.949 | STAGE 13 |
| `pipeline.py` | 5.750 | orchestratore |
| `deterministic_pipeline.py` | 4.085 | percorso deterministico |
| `models.py` | 4.734 | contratti dati |
| `run_pilot_v2.py` | 8.562 | runner |
| `tests/test_pilot_components.py` | 26.365 | test componenti |
| `tests/test_paper_context_enricher_v2.py` | 13.955 | test enricher |

Circa **40 KB di test già esistenti**. Versioni precedenti (`v1`, `v1_1`) sono
presenti in parallelo: `paper_context_enricher.py`,
`paper_context_enricher_prompt_v1_1.py`, `run_pilot.py`,
`run_pilot_v1_1_enrichment.py`. Classificazione: RESEARCH_ONLY (storico), da non
promuovere.

### 6.2 `benchmarks/mtb_evidence/document_grounded_claims/`

| Modulo | Byte | Stage del prompt |
|---|---:|---|
| `kg.py` | 19.643 | STAGE 5 — query Knowledge Graph |
| `documents.py` | 11.939 | STAGE 6 — Document Resolution |
| `authorized_cache.py` | 27.777 | STAGE 6–7 — cache documentale autorizzata, SourceUnit |
| `evidence_bundle/builder.py` | 13.392 | EvidenceBundle |
| `evidence_bundle/{models,policy}.py` | 2.472 / 1.489 | contratti e policy |
| `llm_claim_extractor/` (20 moduli) | ~120 KB | **vecchio Claim Extractor** |

`llm_claim_extractor/` è il componente che la sezione 4 del prompt chiede di
tenere fuori dal flusso principale. Classificazione: **RESEARCH_ONLY**, da non
esporre.

## 7. Divergenza documentale rilevata

`docs/end_to_end_pipeline_pilot/architectural_decision.md`, presente **untracked
su questo branch**, riporta per il Paper Context Enricher:

> "Gemma cita solo SourceUnit reali | Sì (vacuo: 0 citazioni accettate…)"
> "Nessuna delle chiamate a trasporto valido ha prodotto una citazione accettata"

Questo dato descrive la run **v1** (`f366953`) ed è **superato**. Il file
`benchmarks/.../paper_context_enricher_v2_decision.json` @ `6ee64c5` registra:

```json
{"decision": "PAPER_CONTEXT_ENRICHER_V2_PROMISING",
 "quotes_accepted": 2, "transport_valid": 7, "hard_stops": []}
```

e `paper_context_enricher_v2_metrics.json`:

| Misura | Valore |
|---|---:|
| chiamate transport | 7 |
| `V2_TRANSPORT_VALID` | 7 |
| decisione `QUOTE` | 3 |
| decisione `ABSTAIN` | 4 |
| quote accettate | 2 |
| quote rigettate (`REJECTED_QUOTE_NOT_FOUND`) | 1 |
| `source_units_invented_accepted` | **0** |
| `rejected_clinical_recommendation` | **0** |

Il percorso positivo QUOTE→accettata **è stato dimostrato**, su campione ridotto.
`architectural_decision.md` su questo branch va aggiornato o marcato come
riferito alla v1: allo stato è fuorviante.

Anche la raccomandazione "Non integrare nel runtime clinico principale" resta
valida ma è stata **esplicitamente superata dall'utente** con un vincolo più
preciso: integrazione in un *research runtime* separato, namespace dedicato,
marcato `NOT CLINICALLY VALIDATED`, senza toccare gli endpoint esistenti.

## 8. Componenti mancanti rispetto al target

Classificazione **MISSING** — non esistono in alcun branch:

- contratto unico di *pipeline run* (`run_id`, `status`, `stages[]`, `metrics`);
- contratto di *stage* (`stage_id`, `producer`, `lineage`, `reason_codes`);
- tipi evento della pipeline verificabile (`CASECONTEXT_PARSED`, …);
- endpoint REST di run/stage/event/provenance/dossier;
- streaming SSE (nessun `EventSourceResponse`, nessun `text/event-stream`);
- persistenza/replay delle run della pipeline verificabile;
- qualunque UI di timeline, stage inspector, provenance tree, supervisor mode.

## 9. Sicurezza — verifiche svolte

- Nessun segreto committato individuato nei file letti.
- `control/events.py` redige i segreti **prima** della scrittura sul ledger.
- Il bounding scarta `abstract`/`full_text`/`body`: il vincolo "non committare
  testi documentali completi" è già supportato dall'infrastruttura esistente.
- **Rischio aperto:** `benchmarks/.../authorized_cache.py` (27,8 KB) gestisce una
  cache documentale. Prima di esporre SourceUnit via API va verificato che la
  preview redatta non restituisca full text. Da trattare in
  `error_and_abstention_model.md` e nel contratto SourceUnit.

## 10. Conferme di stato

```
system_design_read = false        (non ancora fornito)
repository_audit_completed = true
frontend_legacy_inventory_completed = true   (vedi frontend_cleanup_inventory.md)
legacy_frontend_logic_removed = false        (Fase H, non iniziata)
push_executed = true         (vedi nota sotto)
merge_executed = false
sensitive_text_committed = false
```

Nessun file di codice è stato modificato durante la Fase A.

### Nota sul push

Il prompt originale vietava il push (§2, §28, §29) e questo documento
dichiarava `push_executed = false` fino al 2026-08-05, quando l'utente ha
revocato il vincolo per il solo branch di lavoro.

Cosa è stato pushato: `feature/v3-verifiable-pipeline-ui` su
`PaoloPangallo/MTB_GRAPH_RAG`, con `-u`. Il branch non esisteva sul remote.

Cosa **non** è stato fatto: nessun merge, `main` intatto, e il branch del pilot
`research/v3-end-to-end-pipeline-interaction-pilot` resta non pushato e non
modificato.

GitHub ha emesso un avviso — non un errore — per
`graph_candidate_repository/2.0/candidates.jsonl`, 69,14 MB, oltre la soglia
consigliata di 50 MB e sotto il limite rigido di 100 MB. Se il repository
crescerà ancora su quel file, la migrazione a Git LFS è la strada indicata.

Verificato prima del push: `.env` ignorato e non tracciato, `data_cache/`
ignorata e inesistente, nessun testo documentale nei file tracciati.
