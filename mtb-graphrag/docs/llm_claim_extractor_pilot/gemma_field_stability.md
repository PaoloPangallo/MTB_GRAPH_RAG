# Stabilità field-level (run 1 vs run 2)

Distribuzione sui 100 core-field slot (25 bundle x 4 campi:
`disease`, `biomarker`, `intervention`, `direction`):

| Categoria | Conteggio |
|---|---:|
| `EXACT_REPRODUCTION` | 8 |
| `EQUIVALENT_VALIDATED_SUPPORT` | 3 |
| `SAME_ABSENCE` | 42 |
| `SAME_AMBIGUITY` | 14 |
| `ONE_RUN_ABSTAINS` | 0 |
| `VALUE_DISAGREEMENT` | 0 |
| `DIRECTION_DISAGREEMENT` | 0 |
| `PROVENANCE_DISAGREEMENT` | 1 |
| `VALIDATOR_OUTCOME_DISAGREEMENT` | 0 |
| `TRANSPORT_UNAVAILABLE` | 32 |

Zero disaccordi di valore o di direzione su tutti i 100 slot: quando
entrambe le run accettano lo stesso campo, il valore normalizzato coincide
sempre (`EXACT_REPRODUCTION` + `EQUIVALENT_VALIDATED_SUPPORT` = 11 slot,
0 `VALUE_DISAGREEMENT`/`DIRECTION_DISAGREEMENT`). L'unico
`PROVENANCE_DISAGREEMENT` (bundle `EB-d14e11e161877b56ac0e66c8`, campo
`intervention`) riflette un campo accettato in una run e non nell'altra a
fronte di un esito complessivo comparabile, non un valore in conflitto.

32/100 slot sono `TRANSPORT_UNAVAILABLE` (appartengono agli 8 bundle non
comparabili per fallimento di trasporto in almeno una run) — il fattore
dominante nella bassa active-field agreement è la disponibilità del
trasporto, non l'instabilità dei valori.
