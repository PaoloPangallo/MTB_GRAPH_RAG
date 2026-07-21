# Case study EGFR L858R — due architetture GraphRAG verificabili

Caso: EGFR L858R, Lung Adenocarcinoma, first-line, obiettivo `general-review`.
Run **live** contro Neo4j e i modelli reali (distinte da test con LLM
scriptato, benchmark e case study descrittivo).

Commit: `0b8d17a48f6afd2c62c69b5e420227cc40fb8c66`
Revisione del modello: `ollama:gemma4:31b-cloud`, prompt `v3`

## Confronto

| Metrica | deterministic_cold | deterministic_warm | agentic_cold | agentic_warm |
|---|---|---|---|---|
| Modalità di pianificazione | fixed_plan | fixed_plan | llm_dynamic | llm_dynamic |
| Chiamate al planner | 0 | 0 | 5 | 5 |
| Chiamate a strumenti di retrieval | 4 | 4 | 4 | 4 |
| Nodi di controllo eseguiti | 10 | 10 | 10 | 10 |
| Eventi nel ledger | 24 | 24 | 26 | 26 |
| Hash-chain valida | True | True | True | True |
| Record osservati → canonici | 31 → 30 | 31 → 30 | 31 → 30 | 31 → 30 |
| Record ammessi dalla proiezione | 21 | 21 | 21 | 21 |
| Copertura strutturale | 1.0 | 1.0 | 1.0 | 1.0 |
| Violazioni strutturali | 0 | 0 | 0 | 0 |
| Supportate come formulate | 0 | 0 | 0 | 0 |
| Supportate dopo contestualizzazione | 11 | 11 | 12 | 12 |
| Supporto incerto | 7 | 7 | 7 | 7 |
| Claim contraddette | 3 | 3 | 2 | 2 |
| Applicabilità compatibile | 0 | 0 | 0 | 0 |
| Applicabilità indeterminata | 17 | 17 | 17 | 17 |
| Applicabilità non compatibile | 4 | 4 | 4 | 4 |
| Tentativi di riparazione | 0 | 0 | 0 | 0 |
| Cache hit / miss | 0 / 14 | 14 / 0 | 0 / 14 | 14 / 0 |
| Durata (ms) | 742689 | 2333 | 351140 | 14798 |

## Lettura

Le due architetture attraversano lo stesso strato di controllo: la
differenza attesa e' concentrata in `planner_calls` (0 per il piano fisso)
e nel percorso con cui gli strumenti vengono raggiunti, non nelle fasi di
canonicalizzazione, proiezione, verifica e dossier.

Il dossier e' un artefatto destinato alla revisione del Molecular Tumor
Board; nessun risultato qui riportato costituisce una raccomandazione
terapeutica. Il ledger e' append-only e tamper-evident nel threat model
considerato, non immutabile in senso assoluto.
