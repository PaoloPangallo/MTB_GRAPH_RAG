# Field-level utility: Baseline B vs Gemma+validator

Per ognuno dei 25 bundle e ognuno dei 4 core field (`disease`, `biomarker`,
`intervention`, `direction`), la baseline B è ricalcolata a livello di
campo applicando `ClaimSupportVerifier` (invariato) ai valori grezzi della
candidate stessa — lo stesso meccanismo con cui `run_authorized_pilot.py`
ha originariamente prodotto la baseline B aggregata, qui a grana fine per
campo. Questo non modifica la baseline A/B registrata, la deriva soltanto a
livello di campo per il confronto.

## Distribuzione (100 classificazioni = 25 bundle x 4 campi)

| Categoria | Conteggio |
|---|---:|
| `NEW_VALIDATED_FIELD` | 1 |
| `SAME_VALIDATED_FIELD` | 5 |
| `LOST_BASELINE_FIELD` | 1 |
| `UNSUPPORTED_FIELD_BLOCKED` | 15 |
| `CONFLICTING_FIELD_BLOCKED` | 26 |
| `AMBIGUITY_PRESERVED` | 12 |
| `ABSTENTION_NO_FIELD` | 40 |

Nota metodologica: `accepted_fields` nel risultato del validatore può
essere non vuoto anche quando l'esito complessivo è
`REJECTED_CONTRADICTION` o `REJECTED_DIRECTION` (il validatore calcola i
campi per-field prima del controllo a livello di intera proposta). Un
campo è classificato come "validato" (`NEW_VALIDATED_FIELD`/
`SAME_VALIDATED_FIELD`) solo se l'esito complessivo è `ACCEPTED` o
`ACCEPTED_WITH_DROPPED_FIELDS`; altrimenti, se il campo era comunque
grounded individualmente ma la proposta è stata bloccata per un conflitto
a livello di proposta, è classificato `CONFLICTING_FIELD_BLOCKED`.

## Segnali a livello di bundle

| Segnale | Conteggio |
|---|---:|
| Bundle con almeno un nuovo campo valido | 1 |
| Bundle con solo campi già presenti nella baseline | 1 |
| Bundle in cui Gemma perde informazione (`LOST_BASELINE_FIELD`) | 1 |
| Bundle con provenance migliorata a status invariato | 2 |
| Bundle con cambio di status corretto (miglioramento) | 0 |
| Bundle con status peggiorato | 5 |

I 5 bundle con status peggiorato sono tutti baseline `PARTIAL` -> Gemma
`ABSTAINED` -> `AMBIGUOUS`: il modello si astiene esplicitamente invece di
confermare un match parziale trovato dalle sole regole. Non è un errore di
grounding (nessun campo ungrounded è stato accettato), ma un
posizionamento più conservativo della baseline su questi 5 casi — merita
lettura come "astensione cauta", non come proposta scorretta. Un
`final_support_status` non calcolato (13/25) non è mai contato come
peggioramento: rappresenta un'astensione/rigetto sicuro, non un downgrade.

Il singolo `LOST_BASELINE_FIELD` è `EB-35a15fff70830617392cfa75.intervention`
(bundle il cui trasporto forced-tool è stato ignorato — nessuna proposta
disponibile per quel campo).
