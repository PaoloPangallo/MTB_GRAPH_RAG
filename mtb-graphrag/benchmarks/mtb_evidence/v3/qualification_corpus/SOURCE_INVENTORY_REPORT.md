# Inventario delle fonti dei 147 EvidenceStatement

- **Hash dell'inventario:** `3e4e385f61fa8455a4e913b01db41b056a00f9b55b4cc700b2266f5dc3db3001`
- **Statement congelati:** 147
- **Statement con almeno una fonte:** 147
- **Fonti uniche:** 102

L'universo di selezione e' definito dagli statement congelati, non dal clinical
gold. E' la sola scelta che permette al corpus di smentire il sistema invece di
assecondarlo: annotare le fonti che il gold considera rilevanti misurerebbe
quanto bene sappiamo gia' la risposta.

## Identificatori

| Tipo | Fonti |
| --- | ---: |
| doi | 1 |
| pmid | 101 |

## Presenza nello snapshot

| Stato | Fonti |
| --- | ---: |
| citation_only | 85 |
| node | 3 |
| unknown | 14 |

`citation_only` significa che il PMID compare dentro `Evidence.citation_id` ma
non esiste come nodo `Publication`. La distinzione non e' cosmetica: una fonte
citation_only non e' interrogabile come entita' del grafo, e un retriever che
la trattasse come un nodo troverebbe zero risultati senza segnalare un errore.

## Strati di copertura

Gli strati **non** sono filtri di inclusione. Tutte le fonti inventariate sono
nello scope; gli strati servono a verificare che il corpus contenga anche cio'
che al sistema farebbe comodo non avere.

| Strato | Fonti |
| --- | ---: |
| `retrieved_in_pilot` | 89 |
| `cited_in_report` | 19 |
| `reported_therapy` | 58 |
| `unsupported_report_citation` | 0 |
| `sensitivity` | 72 |
| `resistance` | 31 |
| `negative_polarity` | 4 |
| `non_therapeutic_scope` | 49 |
| `known_disease_conflict` | 7 |
| `multi_statement` | 29 |
| `multi_intervention` | 14 |
| `multi_disease` | 9 |
| `doi_identified` | 1 |
| `trial_identified` | 0 |
| `present_as_node` | 3 |
| `citation_only` | 85 |
| `presence_unknown` | 14 |
| `has_reviewed_profile` | 6 |

## Fonti che qualificano piu' statement

29 fonti su 102 coprono piu' di uno statement.
Una singola annotazione sbagliata su queste si propaga su tutti gli statement
collegati, quindi la precisione del linking conta piu' del recall.

| Fonte | Statement | Interventi distinti |
| --- | ---: | ---: |
| `PMID:22277784` | 10 | 4 |
| `PMID:31208370` | 6 | 1 |
| `PMID:25727400` | 5 | 4 |
| `PMID:18408761` | 4 | 4 |
| `PMID:24122810` | 4 | 1 |
| `PMID:25228534` | 4 | 2 |
| `PMID:26324363` | 4 | 1 |
| `PMID:26698910` | 4 | 3 |
| `PMID:22235099` | 3 | 1 |
| `PMID:24675041` | 3 | 2 |
| `PMID:24893891` | 3 | 2 |
| `PMID:27432227` | 3 | 3 |
| `PMID:27959700` | 3 | 1 |
| `PMID:15329413` | 2 | 2 |
| `PMID:20979473` | 2 | 1 |

## Sospetta suddivisione in coorti

17 fonti presentano piu' interventi o piu' denominazioni di malattia
fra i loro statement. E' un **sospetto**, non una conclusione: solo la lettura
della fonte primaria puo' dire se si tratta di coorti distinte o della stessa
coorte descritta in modi diversi. Finche' quella lettura non avviene, i
qualificatori non vengono propagati.

