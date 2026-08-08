# TEST A — PubMed

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `pubmed_probe.json`.

## 1. Percorso

```
GCA-0a52f20ab5e3e93c15582f2e
  -> document_identifiers = [{pmid: 24658966}]
  -> NCBI E-utilities esummary  -> pubmed/metadata/24658966.json
  -> NCBI E-utilities efetch    -> pubmed/abstracts/24658966.xml
  -> PubMedAbstractParser       -> 9 SourceUnit
```

Il download avviene in una directory temporanea. La copia già presente nella
cache non è stata letta come sorgente né modificata.

## 2. Misure

| Metrica | Valore |
|---|---|
| `fetch_success` | **true** |
| `official_source` | NCBI E-utilities |
| `availability` | `ABSTRACT_AVAILABLE` |
| `document_identifier_correct` | true — `pmid:24658966` |
| `payload_valid` | true |
| `parser_success` | **true** |
| `source_units_created` | **9** |
| `source_units_with_text` | **9** |
| PMCID derivato | nessuno (l'articolo non è in PMC) |

L'assenza di PMCID non è un fallimento: `pmid:24658966` è una delle tre righe
del manifest senza PMC. La baseline diceva lo stesso, e la sonda lo conferma.

## 3. Nessun input umano

L'unico dato in ingresso è stato il `candidate_id`. Il PMID è stato letto dalla
provenance della candidate; nessun identificatore è stato digitato, e il
`document_id` del bundle congelato non è stato usato.

## 4. Gemma

Vedi [06_gemma_validation.md](06_gemma_validation.md). Sintesi:

| Selezione | Decisione | Validatore | Quote verificata |
|---|---|---|---|
| naive (prime 4 unità) | `QUOTE` | `ENRICHMENT_V2_ACCEPTED` | sì, offset 1130 |
| curated (unità del bundle) | `QUOTE` | `ENRICHMENT_V2_ACCEPTED` | sì, offset 78 |

In entrambi i casi il validatore deterministico ha ritrovato la citazione,
verbatim, dentro il testo scaricato pochi secondi prima.
