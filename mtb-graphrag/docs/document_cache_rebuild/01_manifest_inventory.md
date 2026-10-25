# Inventario del manifest — il closed document set

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

## 1. Il manifest è l'autorità, non il punto di partenza di una ricerca

Il bootstrap non scopre evidenze. Legge le 43 righe del manifest congelato e
recupera esattamente quei documenti, negli stessi percorsi relativi che il
manifest già dichiara. Nessun PMID, PMCID, NCT o DOI viene aggiunto.

Questo è ciò che rende la ricostruzione una operazione di infrastruttura e non
un nuovo esperimento: il corpus resta quello su cui i benchmark sono stati
misurati.

Artefatto: `evaluation/document_cache_rebuild/manifest_inventory.json`.

## 2. Composizione

| Prefisso | Righe | Availability | Classificazione |
|---|---:|---|---|
| `pmid:` | 17 | `ABSTRACT_AVAILABLE` | `EXPECTED_AVAILABLE` |
| `pmcid:` | 11 | `PMC_XML_AVAILABLE` | `EXPECTED_AVAILABLE` |
| `pmcid:` | 3 | `PMC_RESOLUTION_FAILED` | `EXPECTED_UNAVAILABLE` |
| `nct:` | 12 | `METADATA_ONLY` | `EXPECTED_AVAILABLE` |
| **Totale** | **43** | | **40 attesi disponibili, 3 attesi assenti** |

## 3. Payload attesi

Le righe `pmid:` portano **due** percorsi: l'abstract e il metadata. Contarne uno
solo darebbe una cache formalmente valida ma diversa da quella misurata.

| Directory | File attesi |
|---|---:|
| `pubmed/abstracts/` | 17 |
| `pubmed/metadata/` | 17 |
| `pmc/xml/` | 11 |
| `clinical_trials/` | 12 |
| **Totale** | **57** |

## 4. I tre documenti non disponibili

`pmcid:PMC273189`, `pmcid:PMC4081656`, `pmcid:PMC4191809` sono le uniche righe
prive di `local_cache_path`. Non sono un guasto: sono il caso reale di documento
non ottenibile, e il runtime li tratta come `DOCUMENT_UNAVAILABLE` perché il
manifest non indica alcun payload da cercare.

La classificazione è derivata dal manifest, non cablata:

```python
def classify(row):
    if not expected_payloads(row) or row.get("availability") in BASELINE_UNAVAILABLE_AVAILABILITY:
        return CLASS_EXPECTED_UNAVAILABLE
    return CLASS_EXPECTED_AVAILABLE
```

Il bootstrap non tenta di "ripararli". Con `--probe-baseline-unavailable`
verifica se la sorgente si sia nel frattempo aperta, ma su una cache temporanea
usa-e-getta: vedi [03_download_results.md](03_download_results.md).
