# Ricostruzione delle SourceUnit

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatti: `source_unit_reconstruction.json`, `source_unit_index_comparison.json`,
`document_resolution_results.jsonl`.

## 1. Perché è questa la verifica che conta

Gli identificatori delle SourceUnit sono derivati dal contenuto:

```python
payload = {"document_id": ..., "unit_type": ..., "text": text,
           "char_start": ..., "char_end": ..., **kwargs}
digest = _hash(payload)
source_unit_id = f"SU-{digest[:24]}"
```

I bundle congelati citano quegli identificatori **per nome**. E
`paper_selection.py` li usa così:

```python
resolved_units = [uid for uid in source_unit_ids
                  if uid in source_units_by_id and (source_units_by_id[uid].get("text") or "").strip()]
if not text_available:
    excluded.append({... "reason_codes": ["TEXT_NOT_AVAILABLE_IN_CACHE"]})
```

Se il testo estratto oggi differisse anche di un carattere da quello del
2026-08-03, ogni ID cambierebbe, ogni bundle verrebbe escluso, e la run LIVE
arriverebbe allo stage 8 senza alcun paper — con la cache formalmente valida e
`validate_cache()` a `True`. Una cache «ricostruita» e inutile.

Per questo il criterio di successo non è la presenza dei file.

## 2. Ricostruzione

| Metrica | Valore |
|---|---:|
| Documenti esaminati | 43 |
| Documenti parsati | 40 |
| Errori di parsing | **0** |
| Documenti senza payload (attesi) | 3 |
| SourceUnit ricostruite | **3402** |
| SourceUnit con testo | **3402** |
| Schema completo (`source_unit_id`, `document_id`, `unit_type`, `text`) | 3402 |

Distribuzione per sorgente: 3014 da PMC (full text JATS), 264 da PubMed
(abstract), 130 da ClinicalTrials (campi strutturati).

## 3. Confronto con l'indice congelato

L'indice non è stato modificato: è stato letto.

| Metrica | Valore |
|---|---:|
| `source_unit_ids_in_index` | 3402 |
| `source_unit_ids_reconstructed` | 3402 |
| **`intersection`** | **3402** |
| `missing_from_reconstruction` | **0** |
| `new_from_reconstruction` | **0** |
| `text_available_count` | 3402 |

**`source_unit_id_drift = 0`.** Corrispondenza esatta e completa: il testo
estratto oggi è byte-identico a quello del pilot.

## 4. Copertura dei bundle

La domanda funzionale — il runtime troverà ciò che i bundle chiedono?

| Metrica | Valore |
|---|---:|
| Bundle totali | 25 |
| Bundle con testo disponibile | **25** |
| Bundle risolti integralmente | **25** |
| Bundle senza testo | **0** |
| SourceUnit richieste dai bundle | 76 |
| SourceUnit risolte con testo | **76** |

Per tipo di sorgente: 13 `ABSTRACT_BUNDLE` (pmid), 7
`FULLTEXT_LOCAL_CONTEXT_BUNDLE` (pmcid), 5 `TRIAL_BUNDLE` (nct) — tutti coperti.

Nessun `TEXT_NOT_AVAILABLE_IN_CACHE` è possibile su questo corpus.
