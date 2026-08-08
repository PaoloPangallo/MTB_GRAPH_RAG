# Decisione finale

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## Decisione

```
CACHE_REBUILT_AND_LIVE_READY
```

## Criteri richiesti

| Criterio | Richiesto | Misurato |
|---|---|---|
| `cache_exists` | `true` | ✅ `true` |
| `cache_layout_valid` | `true` | ✅ `true` |
| `document_cache_available` | `true` | ✅ `true`, `reason_codes: []` |
| `unexpected_missing_count` | `0` | ✅ `0` |
| `source_unit_id_drift` | `0` o spiegato | ✅ `0` |
| `DocumentRuntime.open()` | riesce | ✅ `SUCCEEDED` |
| `live_config_available` | `true` | ✅ `true` |
| `live_stage_6_passed` | `true` | ✅ `SUCCEEDED`, `DOCUMENT_RESOLVED_FROM_CACHE` |
| `live_stage_7_passed` | `true` | ✅ `SUCCEEDED`, 4/4 unità con testo |
| `live_fallback_to_replay` | `false` | ✅ `false`, `replayed: false` |

Tutti i criteri sono soddisfatti da misure del loader reale e da una run LIVE
eseguita, non da ispezione del filesystem.

## Invarianti preservate

| Invariante | Stato |
|---|---|
| `runtime_code_modified` | `false` |
| `historical_manifest_modified` | `false` |
| `historical_source_unit_index_modified` | `false` |
| `document_payloads_committed` | `false` |
| Fallback LIVE → REPLAY introdotto | `false` |
| Documenti inventati | `false` |
| Identificatori aggiunti al corpus | `false` |
| `push_executed` | `false` |
| `merge_executed` | `false` |

Il runtime non è stato toccato: `ReadOnlyDocumentCache` continua a sollevare su
rete e scrittura, e la run LIVE ha registrato `network_fetch_used: false`.

## Ciò che resta vero della diagnosi precedente

Il warning non era un difetto. Era il contratto che funzionava: in assenza di
corpus il runtime si è rifiutato di produrre una run LIVE, invece di rigiocare
artefatti registrati spacciandoli per esecuzione. La fase non ha corretto un
errore — ha fornito i dati che mancavano.

## Riserve da tenere presenti

1. **`content_hash` non è più un criterio di validazione** per PMC e
   ClinicalTrials: il primo ha payload non deterministico, il secondo è mutato in
   campi non testuali. Il criterio verificabile è l'allineamento degli
   identificatori delle SourceUnit. Vedi
   [06_drift_analysis.md](06_drift_analysis.md).

2. **La cache è riproducibile ma non permanente.** Vive fuori da Git e va
   ricostruita in ogni ambiente con
   `scripts/bootstrap_research_document_cache.py`. Se PMC o ClinicalTrials
   cambiassero il testo di un documento, il drift comparirebbe come
   `missing_from_reconstruction` e la verifica lo segnalerebbe prima di una run.

3. **Lo smoke test non è una metrica scientifica.** Una run su un caso
   dimostrativo prova che l'infrastruttura funziona, nulla di più. I benchmark
   restano quelli congelati.

4. I 3 documenti `PMC_RESOLUTION_FAILED` restano non ottenibili, come nella
   baseline. Non sono stati riparati né sostituiti.
