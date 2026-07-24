# Multi-intervention adapter review

Review read-only sui record strutturati già congelati. Non sono stati letti
abstract/full text e non sono stati modificati adapter, corpus, retriever o gold.

## Risultato

- Righe V2 compatibili analizzate: **199**
- Graph evidence ID: **147**
- Gruppi multi-riga: **36**
- Gruppi multi-intervento: **13**
- Interventi nascosti dall'adapter corrente: **15**
- Gruppi atomizzabili dai soli dati strutturati: **0**
- Gruppi che richiedono source review: **13**

La perdita avviene in `merge_duplicate_records`: il graph evidence ID è la
chiave di merge, `drug` è scalare e il primo valore non vuoto viene conservato.
`adapt_record` materializza poi un solo oggetto `intervention`.

## Classificazioni

| Classe | Gruppi |
| --- | ---: |
| `duplicated_serialization` | 23 |
| `unresolved_without_document_review` | 13 |

Nessun gruppo è stato promosso a regimen, risultato aggregato o claim atomico
senza un campo strutturato che ne dimostri l'attribuzione separata. Tutti i
13 gruppi restano `unresolved_without_document_review`.

## Decisione

Raccomandazione: **insufficient_evidence_for_decision**. Conservare il parent
e non creare child claim prima della source review. Se l'attribuzione separata
sarà confermata, l'opzione C (parent + child atomici) è la candidata preferita
per identità graph, provenance e atomicità. I qualification link non devono
essere ereditati automaticamente dai child.

Il caso PMID 31358542/brigatinib resta un principio di regressione:
`aggregate_to_specific_attribution_forbidden`. Nessun artefatto relativo è stato
modificato.
