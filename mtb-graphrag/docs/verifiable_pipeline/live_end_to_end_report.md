# Report end-to-end della pipeline live

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Eseguito il 2026-08-06, branch `feature/v3-verifiable-pipeline-ui`.

## 1. Ambiente

| Voce | Valore |
|---|---|
| Backend | `uvicorn backend.api.main:app` su `127.0.0.1:8010` |
| Cache documentale | `.../data_cache/document_grounding` (fuori dal repository) |
| Manifest hash | `ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b` |
| Documenti risolvibili | 40 su 43 righe di manifest |
| SourceUnit indicizzate | 3402 |
| Modello | `gemma4:cloud` via Ollama Cloud |
| Ledger | `data/research_live_events.sqlite3` (ignorato da git) |

## 2. Checkpoint A — smoke live positivo

Stessa coppia candidate-paper del pilot `6ee64c5`, nuova chiamata al modello.

```
run_id                 3312ad67-eb07-4b30-8b75-17d171c274d1
case                   CASE-1-therapy-evaluation-strong-match
candidate              GCA-008ae3aad1a64c118318ef79
paper                  EB-b4c48ba003913f278ff182a6  (pmid:19223544)
requested → effective  LIVE → LIVE
fully_live             true
replay_artifacts_used  0
llm_calls              2
status                 COMPLETED
```

| # | Stage | Stato | Modalità | Origine |
|---:|---|---|---|---|
| 1 | case input | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 2 | CaseContext parser | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 3 | match verifier | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 4 | retrieval plan | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 5 | KG retrieval | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 6 | document resolution | SUCCEEDED | LIVE | `DETERMINISTIC_CACHE` |
| 7 | source units | SUCCEEDED | LIVE | `DETERMINISTIC_CACHE` |
| 8 | paper selection | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 9 | paper context enricher | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 10 | enrichment validation | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 11 | deterministic gates | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 12 | status | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 13 | dossier | SUCCEEDED | LIVE | `GENERATED_NOW` |
| 14–15 | narratore, verifica narrativa | SKIPPED | — | `NOT_APPLICABLE` |

### Criteri

| Criterio | Esito |
|---|---|
| Cache documentale disponibile | ✅ |
| Documento risolto dalla cache | ✅ `pmid:19223544`, cache hit |
| SourceUnit caricate con `exact_text` | ✅ 4 su 4 |
| Paper selezionato deterministicamente | ✅ ricalcolato durante la run |
| Chiamata Gemma realmente eseguita | ✅ 3320 ms, 1638/127 token |
| Transport valido | ✅ `V2_TRANSPORT_VALID` |
| QUOTE o ABSTAIN realmente prodotto | ✅ QUOTE |
| Nessun artefatto replay utilizzato | ✅ 0 |
| Validatore invariato | ✅ `validator_v2.py` non modificato |
| Nessuna violazione di sicurezza | ✅ |

**Checkpoint A superato.** Nessuno stage documentale è REPLAY.

Quote prodotta, verificata letterale in `SU-6e4d5a52c9be05f545487ad0` offset 95:

> patients with mCRC bearing KRAS mutations are clinically resistant to therapy
> with panitumumab or cetuximab.

## 3. Checkpoint B — casi

| Caso | Modalità | Status | LLM | Doc | SU | Paper | Decisioni | Validazione | Replay |
|---|---|---|---:|---:|---:|---:|---|---|---:|
| CASE-1 | LIVE | COMPLETED | 2 | 1 | 4 | 1 | QUOTE | ACCEPTED | 0 |
| CASE-2 | REPLAY | COMPLETED | 0 | 2 | — | 2 | QUOTE ×2 | 1 ACC, 1 REJ | 6 |
| CASE-3 | LIVE | COMPLETED | 3 | 4 | 9 | 2 | ABSTAIN ×2 | 1 ABST, 1 ABST_INCONSISTENT | 0 |
| CASE-4 | LIVE | COMPLETED | 3 | 2 | 6 | 2 | QUOTE, ABSTAIN | 1 REJ, 1 ABST | 0 |
| CASE-5 | LIVE | STOPPED | 1 | 0 | — | — | — | — | 0 |
| CASE-6 | test | STOPPED | 0 | — | — | — | — | — | 0 |

Durate: da 4 a 70 secondi per run.

## 4. Budget

| Voce | Valore |
|---|---:|
| Autorizzate | 10 |
| **Eseguite** | **10** |
| Retry | 0 |
| Retry semantici | 0 |

Ripartizione: parser 5 (CASE-1, 3, 4, 5 ×2), enricher 5 (CASE-1 ×1, CASE-3 ×2,
CASE-4 ×2).

CASE-2 non è stato eseguito live perché sarebbe costato 3 chiamate su un residuo
di 1.

## 5. Esiti aggregati

| Metrica | Valore |
|---|---:|
| QUOTE prodotte (live) | 2 |
| ABSTAIN prodotti (live) | 3 |
| Quote accettate (live) | 1 |
| Quote rigettate (live) | 1 |
| Astensioni validate (live) | 3 |
| Documenti non disponibili | 0 nelle run eseguite |
| Contradicted promossi a positivo | **0** |
| Quote inesistenti accettate | **0** |
| SourceUnit inventate accettate | **0** |
| Raccomandazioni cliniche generate | **0** |
| Artefatti replay in run live | **0** |

## 6. Refresh e riavvio

| Prova | Esito |
|---|---|
| Run creata e conclusa | ✅ |
| Run nell'URL, refresh non perde la trace | ✅ `useRunStream` rilegge snapshot ed eventi al montaggio |
| Riavvio del backend (processo terminato) | ✅ |
| `GET /runs/{id}` dopo riavvio | ✅ 200, `rehydrated: true` |
| Stage ricostruiti | ✅ 15 su 15, ordine e origini invariati |
| Dossier dopo riavvio | ✅ 200 |
| Provenance dopo riavvio | ✅ 200, catena completa |
| Eventi dopo riavvio | ✅ 200, `hash_chain_valid: true` |
| Elenco run dopo riavvio | ✅ 5 su 5 reidratate |
| `llm_calls` invariato fra le due letture | ✅ dopo la correzione |

## 7. Test

| Suite | Esito |
|---|---|
| Backend, con cache | **278 passati** |
| Backend, senza cache | 266 passati, 12 saltati con motivo |
| Frontend (vitest) | **182 passati** |
| Typecheck TypeScript | pulito |
| Build frontend | riuscita |

## 8. Hard stop

Nessuno raggiunto.

| Condizione | Osservato |
|---|---|
| Quote inesistente accettata | no |
| SourceUnit inventata accettata | no |
| Contradicted promosso a positivo | no |
| Validatore indebolito | no — non modificato |
| REPLAY non dichiarato | no |
| Run HYBRID etichettata LIVE | no — impossibile per costruzione |
| Articolo completo inviato al modello | no — max 4 estratti per paper |
| Dati reali di paziente inviati | no — casi sintetici |
| Cache documentale committata | no — fuori dal repository |
| Frontend calcola lo status canonico | no |
| Persistenza con testi documentali completi | no — verificato sul file grezzo |
| Oltre 10 chiamate reali | no — esattamente 10 |

## 9. Difetto trovato durante la verifica

Confrontando le viste live e reidratate delle stesse cinque run, `llm_calls`
risultava diverso: in memoria veniva dall'orchestratore, dopo il riavvio veniva
ricalcolato sommando le metriche degli stage — escludendo il parser e contando
come reali le chiamate rigiocate. Una run REPLAY che non aveva toccato il
modello dichiarava due chiamate.

Corretto scrivendo il valore canonico nell'evento `RUN_COMPLETED`. Commit
`cf05352`, con due test di regressione.

## 10. Risposta alla domanda finale

**Sì.** Un nuovo caso in linguaggio libero attraversa, senza artefatti REPLAY:

```
testo clinico libero
  → CaseContext Parser        chiamata reale a gemma4:cloud
  → Match Verifier            deterministico
  → retrieval sul KG          graph_candidate_repository/2.0
  → GraphCandidateAssertion
  → Document Resolution       cache autorizzata, letta ora
  → SourceUnit                exact_text ri-parsato, hash verificati
  → Paper Selection           ricalcolata, max 2 paper, max 4 unità
  → Gemma                     chiamata reale, QUOTE o ABSTAIN
  → PaperContextEnrichmentV2Validator
  → controlli deterministici
  → status e provenance
  → dossier persistente       riapribile dopo un riavvio
```

Con un limite: il testo libero deve descrivere un caso che il
`graph_candidate_repository/2.0` sa collegare a un documento presente nella cache
di 40. Fuori da quel perimetro il percorso è ugualmente live, ma si ferma a
`RETRIEVAL_NO_MATCH` o `DOCUMENT_UNAVAILABLE` — che sono esiti veri, non guasti.

Vedi [live_pipeline_limitations.md](live_pipeline_limitations.md) e
[live_pipeline_decision.md](live_pipeline_decision.md).
