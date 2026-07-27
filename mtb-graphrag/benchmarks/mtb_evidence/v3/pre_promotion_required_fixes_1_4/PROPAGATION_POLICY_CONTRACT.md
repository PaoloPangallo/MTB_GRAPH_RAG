# Contratto della propagation policy

Modello: `qualified_claim_model/1.2`  
Contratto: `claim_propagation_contract/1.0`

## La regola

> Ogni claim tipizzato dichiara propagation_policy, hard_filterable e final_evaluable. La deserializzazione rifiuta un record che non li porta invece di assegnarne uno: un default in lettura farebbe decidere al parser cio' che deve decidere la revisione.

| Voce | Valore |
|---|---|
| campi obbligatori | `propagation_policy`, `hard_filterable`, `final_evaluable` |
| valori ammessi | `none`, `prototype_only`, `final` |
| default in deserializzazione | `None` |
| default impliciti permessi | false |
| record senza policy rifiutato | **true** |

Obbligatorio significa due cose insieme, e la seconda e' quella che
conta: la serializzazione li scrive sempre, e la deserializzazione
**rifiuta** un record che non li porta. Un default in lettura riporterebbe
il problema dov'era con in piu' l'illusione di averlo risolto: il campo
comparirebbe nei record riletti, ma il suo valore sarebbe stato deciso dal
parser invece che dalla revisione.

## Aggregate claim

| Claim | Membri | Policy | member_propagation | permits_member_specific |
|---|---|---|---|---|
| `CLM-4ffe85304f3e…` | `EGFR tyrosine kinase inhibitor` | `prototype_only` | false | false |
| `CLM-5071bb2d8657…` | `BGJ398`, `PD173074` | `prototype_only` | false | false |
| `CLM-90e863f00f13…` | `BGJ398`, `PD173074` | `prototype_only` | false | false |

Nessun membro eredita il risultato aggregato. E' la stessa inferenza che
l'adjudication ha rifiutato su `evidence:275`, e lasciarla dedurre dal
silenzio del record la avrebbe riaperta dal lato della serializzazione.

## Regimen claim

| Claim | Componenti | Policy | member_propagation | result_applies_to_combination |
|---|---|---|---|---|
| `CLM-4a89bb28592a…` | `amivantamab`, `lazertinib` | `prototype_only` | false | **true** |
| `CLM-5ce49705979f…` | `amivantamab`, `carboplatin`, `pemetrexed` | `prototype_only` | false | **true** |
| `CLM-ac64c0e56246…` | `erlotinib`, `ramucirumab` | `prototype_only` | false | **true** |

Nessun componente eredita il risultato del regime. Un risultato di
combinazione trasformato in monoterapia e' un'affermazione che la fonte
non fa.

## Atomic e diagnostic

Claim totali nella matrice: **148**  
Atomic e diagnostic dichiaravano gia' `propagation_policy`; i due flag di
valutabilita' esistevano soltanto sui non terapeutici e ora sono su tutti.
Nessun valore documentale esistente e' stato cambiato: la fase dichiara
cio' che mancava e non ridecide cio' che una revisione precedente aveva
stabilito.

