# Multi-intervention adapter review

Review read-only sui record strutturati già congelati. Non sono stati letti
abstract/full text e non sono stati modificati adapter, corpus, retriever o gold.

## Risultato

- Righe V2 compatibili analizzate: **199**
- Graph evidence ID: **147**
- Gruppi multi-riga: **36**
- Gruppi multi-intervento: **13**
- Interventi nascosti dall'adapter corrente: **15**
- Gruppi atomizzabili dai soli dati strutturati: **10**
- Gruppi che richiedono source review: **3**

La perdita avviene in `merge_duplicate_records`: il graph evidence ID è la
chiave di merge, `drug` è scalare e il primo valore non vuoto viene conservato.
`adapt_record` materializza poi un solo oggetto `intervention`.

## Classificazioni

| Classe | Gruppi |
| --- | ---: |
| `duplicated_serialization` | 23 |
| `intervention_specific_results` | 10 |
| `unresolved_without_document_review` | 3 |

Nessun gruppo è stato promosso a regimen o risultato aggregato senza un campo
strutturato che lo dimostri. Tre gruppi clinicamente plausibili come regimen
restano `unresolved_without_document_review`.

## Decisione

Raccomandazione: **mixed_policy**. Usare un parent evidence record e child claim
atomici soltanto dove la riga V2 associa esplicitamente biomarcatore, intervento,
direzione/polarità, fonte e graph evidence ID. Conservare parent-only i gruppi
ambigui fino a source review. I qualification link non devono essere ereditati
automaticamente dai child.

Il caso PMID 31358542/brigatinib resta un principio di regressione:
`aggregate_to_specific_attribution_forbidden`. Nessun artefatto relativo è stato
modificato.
