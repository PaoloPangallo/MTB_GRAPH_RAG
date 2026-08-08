# Esito del recupero

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatti: `download_results.jsonl`, `download_summary.json`.

## 1. Prima esecuzione

| Metrica | Valore |
|---|---:|
| Documenti nel closed set | 43 |
| Attesi disponibili | 40 |
| Scaricati con successo | **40** |
| Falliti | 0 |
| Mancanti inattesi | **0** |
| Attesi assenti (sondati) | 3 |

Nessun documento del closed set è rimasto irrecuperabile.

## 2. File prodotti

| Directory | Attesi | Presenti |
|---|---:|---:|
| `pubmed/abstracts/` | 17 | 17 |
| `pubmed/metadata/` | 17 | 17 |
| `pmc/xml/` | 11 | 11 |
| `clinical_trials/` | 12 | 12 |
| `local_pdf/` | 0 | 0 |

Dimensione totale: **2.1 MB**. Il layout coincide con quello misurato sul pilot
il 2026-08-06.

## 3. I tre documenti storicamente non disponibili

Sondati con `--probe-baseline-unavailable` su cache temporanee:

| Documento | Baseline | Osservato oggi | Cambiato |
|---|---|---|---|
| `pmcid:PMC273189` | `PMC_RESOLUTION_FAILED` | `PMC_RESOLUTION_FAILED` | no |
| `pmcid:PMC4081656` | `PMC_RESOLUTION_FAILED` | `PMC_RESOLUTION_FAILED` | no |
| `pmcid:PMC4191809` | `PMC_RESOLUTION_FAILED` | `PMC_RESOLUTION_FAILED` | no |

**Nessun `AVAILABILITY_CHANGED_SINCE_BASELINE`.** I tre documenti restano
realmente non ottenibili: la baseline non descriveva un guasto transitorio, e
continuano a essere dichiarati `DOCUMENT_UNAVAILABLE` dal runtime.

## 4. Riproducibilità

Seconda esecuzione dello stesso comando, senza argomenti:

| Metrica | Prima esecuzione | Seconda esecuzione |
|---|---:|---:|
| Scaricati | 40 | **0** |
| `SKIPPED_ALREADY_PRESENT` | 0 | **40** |
| Falliti | 0 | 0 |
| Mancanti inattesi | 0 | 0 |

Obiettivo `second_run_downloads = 0` raggiunto: nessuna richiesta di rete viene
ripetuta quando la cache è completa, e nessun file viene duplicato.

## 5. Hash

23 dei 40 documenti presentano `HASH_MISMATCH` rispetto alla baseline. Non è
stato ignorato: l'analisi è in [06_drift_analysis.md](06_drift_analysis.md).

| Sorgente | Esito |
|---|---|
| `pubmed/abstracts/` (17) | `HASH_MATCH` |
| `pubmed/metadata/` (17) | `HASH_MATCH` |
| `pmc/xml/` (11) | `HASH_MISMATCH` |
| `clinical_trials/` (12) | `HASH_MISMATCH` |
