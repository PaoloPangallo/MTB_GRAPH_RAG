# TEST B — PMC full text

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

Artefatto: `pmc_probe.json`.

## 1. Perché questo è il test decisivo

La candidate `GCA-0000980ba01970f893f8e4d7` porta nella propria provenance
**soltanto** `pmid: 15705718`. Nessun PMCID. Se il full text PMC fosse
raggiungibile solo conoscendo il PMCID, questo caso sarebbe impossibile da
automatizzare.

## 2. Percorso

```
GCA-0000980ba01970f893f8e4d7
  -> document_identifiers = [{pmid: 15705718}]        <- unico input
  -> NCBI E-utilities efetch
       -> abstract (10 SourceUnit)
       -> <ArticleId IdType="pmc">PMC248481</ArticleId>   <- PMCID DERIVATO
  -> NCBI PMC OAI  GetRecord(PMC248481)
       -> JATS XML
  -> JatsXmlParser -> 243 SourceUnit (242 identificatori distinti)
```

## 3. Misure

| Metrica | Valore |
|---|---|
| `pmc_fetch_success` | **true** |
| `official_source` | NCBI PMC OAI |
| `availability` | `PMC_XML_AVAILABLE` |
| `xml_valid` / `parser_success` | **true** |
| `source_unit_count` | **243** (242 ID distinti) |
| `source_units_with_text` | **243** |
| PMCID derivato | **`PMC248481`** |
| Coincide con la baseline | **sì** |
| `human_identifier_input_required` | **false** |
| `degraded_to_abstract` | false |

Sui 243 unità e 242 identificatori: due frammenti di testo identici producono lo
stesso `source_unit_id`, perché l'identificatore è l'hash del contenuto. Non è
una perdita — è la deduplicazione implicita del contratto, e la cache produce
esattamente lo stesso numero.

## 4. Il risultato

**La catena `PMID → PubMed → PMCID → PMC full text` è percorribile per intero
dalla macchina.** Il PMCID non è conoscenza esterna: è un campo della risposta
PubMed, e la sonda lo ha ottenuto senza mapping, senza euristiche e senza
intervento umano.

## 5. Gemma

| Selezione | Decisione | Validatore |
|---|---|---|
| naive (prime 4 di 243) | `ABSTAIN` | `ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS` |
| curated (3 unità del bundle) | `ABSTAIN` | `ENRICHMENT_V2_ABSTAINED` |

L'astensione **è l'esito corretto**, e coincide con quanto il pilot aveva già
registrato. Analisi in [06_gemma_validation.md](06_gemma_validation.md).
