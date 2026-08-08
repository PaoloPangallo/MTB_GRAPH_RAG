# Validazione dal runtime

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatti: `live_runtime_probe.json`, `live_runtime_smoke_test.json`.

## 1. Apertura in sola lettura

```
DocumentRuntime.open()  ->  SUCCEEDED
```

Nessuna `DocumentCacheUnavailable`. L'apertura passa da `open_read_only()` →
`require_cache()`, quindi la cache ha superato la validazione dello stesso
percorso che una run LIVE percorre.

La cache viene aperta come `ReadOnlyDocumentCache`: i suoi metodi `_request`,
`_write_payload` e `_record` sollevano. Il bootstrap non ha allentato nulla.

## 2. Sonda su tutti e tre i parser

Una sonda che tocchi solo PubMed non direbbe nulla su JATS e ClinicalTrials, che
usano parser diversi. Un bundle reale per sorgente:

| Sorgente | Stage 6 | Stage 7 |
|---|---|---|
| `pmid:` | risolto da cache | unità con testo |
| `pmcid:` | risolto da cache | unità con testo |
| `nct:` | risolto da cache | unità con testo |

| Metrica | Valore |
|---|---:|
| Documenti risolti (stage 6) | 3 / 3 |
| Documenti non disponibili | 0 |
| `network_fetch_used` | `false` |
| Documenti parsati (stage 7) | 3 |
| Fallimenti di parsing | 0 |
| SourceUnit con testo | 263 |

## 3. Run LIVE end-to-end

Caso `CASE-1-therapy-evaluation-strong-match`, modalità `LIVE` richiesta
esplicitamente. `POST /runs` ha risposto **201**: il gate `503` sulla
disponibilità della cache (`research_routes.py:149-156`) era già superato.

| Stage | Esito | `artifact_origin` | Reason code |
|---|---|---|---|
| 1 · case input | `SUCCEEDED` | `GENERATED_NOW` | |
| 2 · CaseContext parser | `SUCCEEDED` | `GENERATED_NOW` | |
| 3 · match verifier | `SUCCEEDED` | `GENERATED_NOW` | |
| 3b · eligibility gate | `SUCCEEDED` | `GENERATED_NOW` | |
| 4 · retrieval plan | `SUCCEEDED` | `GENERATED_NOW` | |
| 5 · KG retrieval | `SUCCEEDED` | `GENERATED_NOW` | |
| **6 · document resolution** | **`SUCCEEDED`** | `DETERMINISTIC_CACHE` | `DOCUMENT_RESOLVED_FROM_CACHE` |
| **7 · source units** | **`SUCCEEDED`** | `DETERMINISTIC_CACHE` | `SOURCE_UNITS_MATERIALIZED_FROM_CACHE` |
| 8 · paper selection | `SUCCEEDED` | `GENERATED_NOW` | |
| 9 · paper context enricher | `SUCCEEDED` | `GENERATED_NOW` | |
| 10 · enrichment validation | `SUCCEEDED` | `GENERATED_NOW` | |
| 11-15 · gates, status, dossier, narrator, verifier | `SUCCEEDED` | `GENERATED_NOW` | |

`status = COMPLETED`, `stopped_at = None`, `llm_calls = 2`.

**Stage 6 non è `DOCUMENT_CACHE_UNAVAILABLE`.** Stage 7 ha prodotto 4 SourceUnit
con testo esatto su 4 richieste, `text_never_exposed: true`.

## 4. Il testo è arrivato davvero al modello

Stage 8 ha selezionato il bundle `EB-b4c48ba003913f278ff182a6` su
`pmid:19223544` con **4 SourceUnit risolte**: gli identificatori del bundle
congelato hanno agganciato le unità ricostruite oggi. È la conferma funzionale
del drift nullo.

Stage 9 (§22 — solo identificatori ed esiti, nessuna quote):

| Campo | Valore |
|---|---|
| `paper_id` | `EB-b4c48ba003913f278ff182a6` |
| `model` | `gemma4:cloud` |
| `delivery_transport` | `OLLAMA_FORCED_TOOL_CHOICE_V2` |
| `transport_result` | `V2_TRANSPORT_VALID` |
| `finish_reason` | `tool_calls` |
| `status_code` | `200` |
| token in / out | 1638 / 123 |
| `replayed` | **`false`** |
| `artifact_origin` | `GENERATED_NOW` |

Stage 10: `ENRICHMENT_V2_ACCEPTED`, validatore
`PaperContextEnrichmentV2Validator`, **`quote_offset: 95`**.

Quell'offset è la prova decisiva: il validatore ha localizzato la citazione del
modello, verbatim, dentro il testo della SourceUnit ri-parsata dalla cache. Il
testo non è solo presente — è quello giusto.

## 5. Nessun fallback

`replayed: false` su stage 9 e 10, `artifact_origin: GENERATED_NOW`,
`requested_mode: LIVE`. Nessuno stage ha origine `RECORDED_REAL_RUN`.

`live_fallback_to_replay = false`.
