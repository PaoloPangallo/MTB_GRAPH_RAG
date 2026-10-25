# Shadow evaluation report

La valutazione ha processato 148 claim attive e 444 righe entity-level: disease, biomarker/variant e intervention per le therapeutic; disease, biomarker/variant e diagnostic per le due diagnostic.

Il lato query Ã¨ il contesto del parent congelato locale. Quando il parent ripete il valore della claim il confronto Ã¨ necessariamente descrittivo e non dimostra che la claim sia supportata.

Risultati:

| Misura | Risultato |
|---|---:|
| claim attive | 148 |
| righe confrontate | 444 |
| concetti nel registry locale | 14 |
| relazioni locali | 6 |
| disease con concetto locale | 79,05% |
| intervention con concetto locale | 24,66% |
| diagnostic con concetto locale | 100% |
| biomarker con concetto locale | 0% |
| ID canonici espliciti per tutti i domini | 0% |

Distribuzione dei match sulle righe repository:

- `EXACT`: 402;
- `DESCENDANT`: 2;
- `UNKNOWN`: 40;
- nessun `SYNONYM`, `ANCESTOR`, `CLASS_MATCH`, `RELATED` o `INCOMPATIBLE` nei contesti parent/claim del corpus.

Questo risultato non Ã¨ accuratezza clinica. La prevalenza di `EXACT` riflette soprattutto la serializzazione del parent context, non una validazione ontologica indipendente.

Disaccordi:

- `LITERAL_FAIL_ONTOLOGY_HIERARCHICAL`: 2;
- `ONTOLOGY_DATA_MISSING`: 40;
- `NO_DISAGREEMENT`: 433.

I risultati entity-level completi sono in `ontology_shadow_results.csv`; i soli disaccordi in `ontology_disagreements.csv`.
