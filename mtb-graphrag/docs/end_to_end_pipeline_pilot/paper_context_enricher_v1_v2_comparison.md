# Confronto v1.0 / v1.1 / v2.0

v1.0 e v1.1 usavano lo schema precedente (con `evidence_kind`, campi
nullable, oggetti annidati impliciti); v2.0 usa il contratto
semplificato tutto-stringa. **Il confronto misura l'effetto congiunto di
prompt e schema di transport insieme — non è un confronto solo-prompt.**
Stessi 5 casi, stessi 7 candidate-paper pair in tutte e tre le versioni.

| Metrica | v1.0 | v1.1 | v2.0 |
|---|---:|---:|---:|
| Chiamate | 7 | 7 | 7 |
| Transport validi | 4 | 0 | **7** |
| Decision QUOTE / enrichment positivi | 0 | 0 | **2** |
| Astensioni valide | 4 | 0 | 2 |
| Astensioni con campi incoerenti | n/a (schema diverso) | n/a | 2 |
| `REJECTED_TRANSPORT` (equivalenti) | 3 | 7 | 0 |
| Errori tipo `EVIDENCE_KIND_INVALID` | 0 | 5 | 0 (campo rimosso dallo schema) |
| Astensioni incoerenti (schema v1.1) | 0 | 4 | — (vedi riga sopra per l'equivalente v2.0) |
| SourceUnit inventate accettate | 0 | 0 | 0 |
| Quote inesistenti accettate | 0 | 0 | 0 |
| Hard stop | 0 | 0 | 0 |

## Lettura

Il collo di bottiglia osservato in v1.0 (`EVIDENCE_KIND_INVALID`, causato
dal campo di classificazione libero) e il collo di bottiglia opposto e
peggiore introdotto in v1.1 (`ABSTAIN_TRUE_BUT_FIELDS_POPULATED`, causato
da istruzioni di astensione più elaborate senza semplificare lo schema)
sono entrambi risolti da v2.0 rimuovendo `evidence_kind` dallo schema e
spostando la coerenza `abstain`+campi dal livello di transport (dove
causava un rigetto totale) al livello semantico (dove viene registrata
per audit senza bloccare l'intera risposta). Il risultato è il primo
transport-success ≥6/7 e il primo enrichment positivo accettato in tutta
la serie di pilot.
