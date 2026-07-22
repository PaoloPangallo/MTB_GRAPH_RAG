# Perimetro della curation prioritaria

- **Hash del perimetro:** `329975427931f617930d1d481b7f6b618cf55e0aacf4eee39f7b3a9d6416cccc`
- **Unita' prioritarie:** 35

## Composizione dei gruppi

| Gruppo | Unita' |
| --- | ---: |
| A — coorte irrisolta | 16 |
| B — multi-statement | 29 |
| **A ∩ B** | **16** |
| solo A | 0 |
| solo B | 13 |
| solo conflitto | 6 |
| **unione** | **35** |

### Perche' A e' contenuto in B

A e' interamente contenuto in B, e la relazione e' strutturale, non empirica: requires_cohort_split confronta interventi e malattie fra gli statement di una fonte, quindi non puo' accendersi su una fonte con un solo statement. Una fonte a statement singolo che descrive due coorti resta invisibile a questo rilevatore.

La conseguenza pratica va detta: il numero di unita' prioritarie e'
35 e non la somma 16 + 29, perche' i due gruppi non sono
disgiunti. Piu' importante, il rilevatore di coorti multiple ha un punto cieco
noto e non stimabile con i dati attuali.

## Classi

| Classe | Unita' |
| --- | ---: |
| `AB_BOTH` | 16 |
| `A_UNRESOLVED_COHORT` | 0 |
| `B_MULTI_STATEMENT` | 13 |
| `CONFLICT_PRIORITY` | 6 |

Le unita' conflittuali fuori da A e B sono **incluse** anche se l'obiettivo le
richiedeva solo dentro A o B. Un conflitto e' il caso di propagazione piu'
pericoloso gia' noto: escluderlo per rispettare il perimetro sarebbe la scelta
rischiosa, includerlo costa soltanto lavoro.

## Rischio di propagazione

Il rischio e' `probabilita' dell'errore × numero di statement colpiti`. Il
conteggio degli statement e' il moltiplicatore: e' su quante proposizioni
l'errore si propaga. Per questo una fonte con otto statement e coorte ambigua
precede una con venti statement e coorte unica.

| Banda | Unita' |
| --- | ---: |
| critical | 3 |
| high | 7 |
| medium | 15 |
| low | 10 |

## Ordine di lavorazione

| # | Bucket | Unita' |
| ---: | --- | ---: |
| 1 | `ab_with_conflict` | 0 |
| 2 | `ab_multi_intervention` | 13 |
| 3 | `ab_other` | 3 |
| 4 | `a_only` | 0 |
| 5 | `b_with_conflict` | 1 |
| 6 | `conflict_only` | 6 |
| 7 | `b_multi_intervention` | 0 |
| 8 | `b_other` | 12 |

## Prime dieci unita'

| # | Unita' | Fonte | Statement | Rischio | Motivazione |
| ---: | --- | --- | ---: | --- | --- |
| 1 | `PU-PMID-22277784-cohort-1` | `PMID:22277784` | 10 | critical (50) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 10 statement |
| 2 | `PU-PMID-25727400-cohort-1` | `PMID:25727400` | 5 | critical (25) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 5 statement |
| 3 | `PU-PMID-26698910-cohort-1` | `PMID:26698910` | 4 | critical (20) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 4 statement |
| 4 | `PU-PMID-18408761-cohort-1` | `PMID:18408761` | 4 | high (16) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 4 statement |
| 5 | `PU-PMID-25228534-cohort-1` | `PMID:25228534` | 4 | high (16) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 4 statement |
| 6 | `PU-PMID-24675041-cohort-1` | `PMID:24675041` | 3 | high (15) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 3 statement |
| 7 | `PU-PMID-24893891-cohort-1` | `PMID:24893891` | 3 | high (15) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 3 statement |
| 8 | `PU-PMID-15329413-cohort-1` | `PMID:15329413` | 2 | high (10) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 2 statement |
| 9 | `PU-PMID-24550739-cohort-1` | `PMID:24550739` | 2 | medium (8) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 2 statement |
| 10 | `PU-PMID-26515464-cohort-1` | `PMID:26515464` | 2 | medium (8) | coorte non risolta: rischio di propagare il braccio sbagliato; una annotazione ricade su 2 statement |

