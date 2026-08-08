# Baseline della ricostruzione

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. Perché questa fase

Il frontend mostrava, prima di ogni run LIVE:

> La cache documentale non è disponibile: una run LIVE si fermerebbe allo stage 6
> con `DOCUMENT_CACHE_UNAVAILABLE`.

Non era un difetto: era il contratto che funzionava. `validate_cache()`
restituiva `CACHE_PATH_NOT_FOUND` perché la cache non esiste in questo ambiente,
e il runtime lo dichiarava invece di sostituirla con un replay travestito da run
live.

La cache non è versionata (`.gitignore:68 → data_cache/`): contiene testo di
terzi. Un clone del repository non la porta con sé, e
`evaluation/deliverability/repository_state.json` lo registrava già:

```json
{"path_default": "mtb-graphrag/data_cache/document_grounding",
 "present_in_this_environment": false, "tracked_in_git": false, "gitignored": true}
```

L'indice c'era, il corpus no.

## 2. Stato registrato prima di toccare qualsiasi cosa

| Voce | Valore |
|---|---|
| Branch di partenza | `feature/dossier-narrator-verifier` |
| HEAD di partenza | `2b78554` |
| Working tree | non pulito → `run.ps1` committato in `9996eff` prima di procedere |
| Branch di lavoro | `chore/rebuild-document-cache` da `9996eff` |
| Manifest documentale | `benchmarks/mtb_evidence/document_grounded_claims/authorized_document_cache_pilot/document_manifest.jsonl` |
| SHA-256 del manifest | `ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b` |
| Documenti nel manifest | 43 |
| Indice SourceUnit | `…/authorized_document_cache_pilot/source_unit_index.jsonl` |
| SourceUnit indicizzate | 3402 (solo locatori, nessun campo `text`) |
| Cache path calcolato | `<repo>/data_cache/document_grounding` |
| `validate_cache()` | `(False, ['CACHE_PATH_NOT_FOUND'])` |

Baseline originale del pilot: documenti recuperati il **2026-08-03**, cache
misurata il 2026-08-06 e descritta in
[../verifiable_pipeline/document_cache_runtime.md](../verifiable_pipeline/document_cache_runtime.md).

## 3. Prerequisiti verificati

Le tre sorgenti del closed set sono raggiungibili:

| Sorgente | Esito |
|---|---|
| NCBI E-utilities | `200` |
| PMC OAI | `200` |
| ClinicalTrials.gov API v2 | `200` |

## 4. Vincoli della fase

- Il runtime LIVE resta **read-only e senza rete**: `ReadOnlyDocumentCache` non
  viene modificata, né aggirata.
- Nessun fallback LIVE → REPLAY viene introdotto.
- Il manifest congelato e l'indice SourceUnit non vengono scritti.
- I payload non vengono versionati.
- Il closed document set è definito dal manifest: nessun identificatore nuovo.
