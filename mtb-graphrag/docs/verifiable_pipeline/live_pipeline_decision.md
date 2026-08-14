# Decisione

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. Cosa è stato deciso

La pipeline verificabile **è ora eseguibile completamente dal vivo** e resta una
pipeline di ricerca. Non viene integrata come runtime clinico validato, e la
marcatura non è disattivabile: `PipelineRun.research_notice()` accompagna ogni
risposta di run.

La Legacy V3 non è stata toccata — `/legacy/v3-deterministic` e
`qualified_claim_repository/1.4` sono invariati.

## 2. Su cosa poggia la decisione

Quattro fatti verificabili, non impressioni.

**Una run attraversa realmente gli stage documentali.** Checkpoint A: 13 stage
implementati su 13 eseguiti, `execution_mode = LIVE`,
`replay_artifacts_used = 0`. Gli stage 6 e 7 leggono la cache al momento della
run e lo dichiarano con `DETERMINISTIC_CACHE`, distinto da `REPLAY`.

**La ricostruzione delle SourceUnit è dimostrabilmente esatta.** 3402 su 3402
ricostruite con `content_hash` identici all'indice committato. Poiché
`source_unit_id` deriva dall'hash del contenuto, la coincidenza degli ID è essa
stessa la prova che il testo ri-parsato è byte-identico.

**Il fallback silenzioso non esiste più.** Era una riga —
`use_replay = replay.has_frozen_case(case_id)` — che rendeva replay ogni run
avviata dalla UI. Il runtime operativo finale ha un solo percorso canonico:
`RunStore.start()` apre `DocumentRuntime.open()` e avvia l'orchestratore. Un
LIVE impossibile fallisce col proprio motivo; gli adapter replay restano
esplicitamente confinati a ricerca/regressione. Un test verifica che nessuno
stage a valle di un fallimento si «salvi» con un artefatto registrato.

**Una run sopravvive al riavvio.** Verificato terminando il processo backend e
riaprendo la run: 15 stage ricostruiti, dossier e provenance disponibili, catena
di hash valida.

## 3. Cosa questo lavoro ha rivelato

Il percorso LIVE non era «poco usato»: era **inutilizzabile**, per tre difetti
che solo la modalità replay teneva nascosti.

1. Il transport puntava a costanti cablate e non importava mai `llm_config`, che
   pure conteneva la configurazione corretta.
2. L'orchestratore passava gli argomenti dell'enricher sfalsati di una
   posizione, e il budget dichiarato non era speso da nessuno.
3. Il validatore di default era il v1, che rigetta ogni `transport_result`
   diverso da `FORCED_TOOL_VALID`. L'enricher v2 produce `V2_TRANSPORT_VALID`:
   **ogni** enrichment live veniva rigettato come guasto di trasporto prima di
   qualunque verifica semantica, e `PaperContextEnrichmentV2Validator` — scritto,
   completo, testato — non era raggiungibile da nessun percorso di esecuzione.

Nessuno dei tre si manifestava in replay. È l'argomento più forte a favore
dell'aver reso la modalità esplicita: un percorso che non viene mai eseguito non
è un percorso, è codice che sembra funzionare.

Un quarto difetto è emerso durante la verifica: `llm_calls` era ricalcolato in
lettura e dava due valori diversi per la stessa run. Corretto in `cf05352`.

## 4. Cosa non è stato deciso

Nessuna di queste cose è stata fatta, e nessuna dovrebbe essere data per
implicita:

- ampliare la cache oltre i 40 documenti;
- sostituire il repository materializzato con una query Neo4j live;
- aggiungere sinonimi di farmaci al validatore (vedi CASE-4);
- implementare gli stage 14–15;
- valutare la qualità clinica degli output.

## 5. Condizioni per l'uso

| Condizione | Stato |
|---|---|
| `VERIFIABLE_PIPELINE_RESEARCH_ENABLED=1` | richiesto, disattivo di default |
| `RESEARCH_DOCUMENT_CACHE_PATH` configurata | richiesta per LIVE |
| Provider LLM raggiungibile | richiesto per LIVE |
| Marcatura di ricerca | non disattivabile |
| Uso clinico | **escluso** |

Con il flag disattivo le rotte rispondono 404 e non 403: in un deployment di
prodotto il research runtime non rivela la propria esistenza.

## 6. Verdetto

```
document_cache_connected                    = true
document_cache_read_only                    = true
network_document_fetch_used                 = false
live_document_resolution_completed          = true
live_source_unit_loading_completed          = true
live_paper_selection_completed              = true
live_gemma_calls_executed                   = 10
live_enrichment_validation_completed        = true
automatic_live_to_replay_fallback_present   = false
fully_live_run_completed                    = true
replay_artifacts_used_in_fully_live_run     = 0
live_quote_obtained                         = true
live_abstain_obtained                       = true
live_quote_rejected                         = true
contradicted_promoted_positive              = 0
accepted_nonexistent_quotes                 = 0
accepted_invented_source_units              = 0
clinical_recommendations_generated          = 0
run_persistence_completed                   = true
run_survives_page_refresh                   = true
run_survives_backend_restart                = true
sensitive_document_text_committed           = false
frontend_computes_canonical_status          = false
runtime_tests_passed                        = true
frontend_tests_passed                       = true
end_to_end_tests_passed                     = true
push_executed                               = false
merge_executed                              = false
```

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**
