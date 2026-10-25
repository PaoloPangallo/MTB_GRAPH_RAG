# Utilità incrementale ripetibile

## Il NEW_VALIDATED_FIELD dello Stadio 1 ricompare

Il singolo campo `disease` del bundle `EB-42cb660f5be17914df59a8fc`
(l'unico `NEW_VALIDATED_FIELD` trovato nello Stadio 1) **ricompare come
`NEW_VALIDATED_FIELD` sia in run 1 sia in run 2** —
`REPEATED_NEW_VALIDATED_FIELD`. È un segnale di utilità genuinamente
ripetibile, non un artefatto di una singola generazione.

## Riepilogo

| Categoria | Conteggio |
|---|---:|
| `REPEATED_NEW_VALIDATED_FIELD` | 1 (`EB-42cb660f5be17914df59a8fc.disease`) |
| `ONE_OFF_NEW_VALIDATED_FIELD` | 2 |
| `REPEATED_PROVENANCE_IMPROVEMENT` (bundle) | 1 |
| `ONE_OFF_PROVENANCE_IMPROVEMENT` (bundle) | 3 |
| `REPEATED_AMBIGUITY_RESOLUTION` (status migliora in entrambe le run) | 0 |

I 2 `ONE_OFF_NEW_VALIDATED_FIELD` (`EB-35a15fff70830617392cfa75.disease`,
`EB-9403cc6f191fb7d83bc29836.disease` e `.direction`) mostrano il pattern
opposto: un campo nuovo validato in una run, ma solo `AMBIGUITY_PRESERVED`
nell'altra — utilità incrementale non riproducibile
(`UNSTABLE_INCREMENTAL_VALUE`) su questi 2 bundle specifici.

Confronto campi per run (rispetto alla baseline B):

| Categoria | Run 1 | Run 2 |
|---|---:|---:|
| `NEW_VALIDATED_FIELD` | 2 | 3 |
| `SAME_VALIDATED_FIELD` | 2 | 5 |
| `LOST_BASELINE_FIELD` | 6 | 13 |
| `CONFLICTING_FIELD_BLOCKED` | 21 | 16 |
| `UNSUPPORTED_FIELD_BLOCKED` | 15 | 12 |
| `AMBIGUITY_PRESERVED` | 14 | 15 |
| `ABSTENTION_NO_FIELD` | 40 | 36 |

**Conclusione**: esiste un segnale di utilità incrementale ripetibile (il
`has_any_repeated_signal` richiesto dal criterio C è vero), ma è piccolo
(1 campo, 1 bundle di provenance) e affiancato da un numero maggiore di
segnali one-off, non riproducibili tra le due run.
