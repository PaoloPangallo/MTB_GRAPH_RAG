# Readiness per il retrieval contestuale

```
ready_for_prototype_retrieval = true
ready_for_final_evaluation    = false
```

Le due cose sono distinte, e distinguerle e' il punto. Un prototipo puo'
essere costruito su dimensioni native e su un sottoinsieme dichiarato di
statement; pubblicare risultati su quelle stesse dimensioni no.

I criteri sono stati fissati **prima** di leggere le metriche. E' l'unico modo
per evitare che la soglia venga scelta guardando il risultato, che e' il modo
piu' comune e meno visibile di dichiararsi pronti.

## Criteri per il prototipo

| Criterio | Esito |
| --- | --- |
| ogni unita' prioritaria ha uno stato di coorte esplicito | sì |
| nessun qualificatore ambiguo viene propagato | sì |
| nessun conflitto viene sovrascritto | sì |
| provenance completeness = 1.000 | sì |
| ogni fonte multi-statement e' source_checked o dichiarata non disponibile | sì |
| setting, linea e popolazione disponibili su un sottoinsieme dichiarato | sì |
| le fonti rumorose restano nel corpus | sì |
| il corpus non e' selezionato dal clinical gold | sì |
| la seconda revisione mancante e' dichiarata | sì |
| la readiness e' distinta dal freeze del corpus | sì |

## Criteri per la valutazione finale

| Criterio | Esito |
| --- | --- |
| la seconda revisione esiste su tutte le coppie | no |
| esiste gold valutabile per misurare il linker | no |
| l'accordo fra annotatori e' misurato | no |
| le dimensioni cliniche coprono un sottoinsieme utilizzabile come filtro | no |

## Readiness per dimensione

| Dimensione | Stato | Copertura | Origine |
| --- | --- | ---: | --- |
| `disease` | **ready** | 147/147 | statement V2 |
| `intervention` | **ready** | 147/147 | statement V2 |
| `direction` | **ready** | 147/147 | statement V2 |
| `assertion_polarity` | **ready** | 147/147 | statement V2 |
| `evidence_design` | **partially_ready** | 60/102 | registro e abstract |
| `setting` | **blocked_by_review** | 6/102 | profili umani preesistenti |
| `therapy_line` | **blocked_by_review** | 6/102 | profili umani preesistenti |
| `stage` | **blocked_by_review** | 6/102 | profili umani preesistenti |
| `resection_status` | **blocked_by_review** | 0/102 | nessuna |
| `population` | **not_ready** | 6/102 | profili umani preesistenti |
| `prior_therapies` | **not_ready** | 6/102 | profili umani preesistenti |
| `regimen` | **not_ready** | 6/102 | profili umani preesistenti |
| `biomarker_requirements` | **not_ready** | 6/102 | profili umani preesistenti |
| `inclusion_criteria` | **not_ready** | 6/102 | profili umani preesistenti |
| `exclusion_criteria` | **not_ready** | 4/102 | profili umani preesistenti |
| `comparator` | **not_ready** | 0/102 | nessuna |

### Perche' `blocked_by_review` e non `not_ready`

Quattro dimensioni hanno rilevazioni pronte ma **non emesse**: setting, linea,
stadio e stato di resezione. Non mancano i dati, manca la conferma. Le
corrispondenze lessicali che le producono possono descrivere i campioni invece
dello studio — sul PMID 15329413 «resected from untreated never smokers»
avrebbe prodotto `resection_status = resected` per l'intero studio.

La distinzione conta perche' il costo per sbloccarle e' molto diverso: una
dimensione `blocked_by_review` richiede lettura umana di span gia' individuati,
una `not_ready` richiede prima di costruire un modo per estrarla.

## Cosa manca

- la seconda revisione esiste su tutte le coppie
- esiste gold valutabile per misurare il linker
- l'accordo fra annotatori e' misurato
- le dimensioni cliniche coprono un sottoinsieme utilizzabile come filtro

