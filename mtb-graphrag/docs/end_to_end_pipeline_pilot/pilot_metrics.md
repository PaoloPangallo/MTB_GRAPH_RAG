# Metriche del pilot

Dati completi in `pilot_metrics.json`. Riepilogo:

## CaseContext

Parser success: 5/5. MATCH: 25, MISMATCH: 0, MISSING_IN_TEXT: 5 (campi
legittimamente assenti). Casi fermati prima del retrieval: 0.

## Retrieval

Candidate trovate: 4 (attese: 4, sui 4 casi THERAPY_*). No-match: 1 (Caso
5, atteso). Paper selezionati: 7.

## Enrichment

Chiamate eseguite: 7. Transport validi: 4. Astensioni: 4/4 dei transport
validi. Quote inesistenti accettate: 0. `validation_outcome_counts`:
`ENRICHMENT_ABSTAINED`=4, `REJECTED_TRANSPORT`=3.

## Pipeline

Casi completati (dossier prodotto): 4. Casi fermati: 1 (`RETRIEVAL_NO_MATCH`,
Caso 5 — atteso, non un fallimento). Status: `AMBIGUOUS`=3, `DISCOVERED`=1.

## Performance

Chiamate reali totali in questa run finale: 7 (i 5 parser sono stati
riusati da una run precedente, non richiamati — vedi
`pilot_limitations.md` per il conteggio cumulativo onesto delle chiamate
reali fatte durante l'intera sessione, incluse quelle scartate per bug
corretti prima del completamento). Latenza media parser: 9325 ms.
Latenza media enricher: 4295 ms. Token input medi: ~1500, output medi:
~187.
