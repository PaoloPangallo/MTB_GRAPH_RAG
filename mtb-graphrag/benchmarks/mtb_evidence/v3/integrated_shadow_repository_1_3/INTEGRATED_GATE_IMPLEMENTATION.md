# Integrated structural gate

Gate: `qualified_claim_structural_gate/1.0`
Disease gate: `claim_disease_gate/1.0`
Output: `qualified_claim_retrieval_result/1.2`
Modalità di default: `strict_verified`

## La regola

L'eleggibilità finale deriva dalla congiunzione di sette decisioni: stato del
claim, dominio, biomarcatore, disease, intervento/regime/classe,
direzione/polarità, e idoneità allo scoring. La regola vale nelle due direzioni.

> Un singolo gate incompatibile impedisce il primary ranking.
> Un singolo gate compatibile non promuove nulla.

Fino alla 1.2 ogni gate decideva da solo e il risultato veniva letto come se le
decisioni fossero indipendenti. Non lo sono: un claim con disease exact e
biomarcatore incompatibile non è buono su un asse e meno buono sull'altro, non
risponde alla domanda.

## Precedenza dei bucket

1. `rejected_by_native_constraints`
2. `audit_only_results`
3. `retained_with_warning`
4. `primary_ranked_results`

Il motivo più restrittivo domina. Un claim unsupported o deprecated resta
audit-only anche con disease, biomarcatore e intervento tutti exact, perché ciò
che lo trattiene non è la qualità del match ma lo stato dell'oggetto. Le
eccezioni esplicite sono zero.

## Composizioni protette

| composizione | esito |
|---|---|
| disease exact + biomarker incompatible | `rejected`, score interamente falso |
| disease child + biomarker exact | `warning`, mai primary, nessuna promozione |
| disease exact + regimen component | `warning`, mai exact atomic support |
| unsupported + tutti gli assi exact | `audit` |
| deprecated + tutti gli assi exact | `audit` |

## Score

Nei bucket non ordinabili i flag di score non vengono ereditati dal gate più
permissivo: vengono azzerati. Un flag ereditato sarebbe la porta da cui un
punteggio alto rientra a decidere ciò che il gate aveva escluso.

Su 7776 valutazioni in 3
modalità: flag di score sopravvissuti fuori dai bucket ordinabili
**0**, primari con un
gate bloccante **0**, contenitori di
provenienza diventati primari **0**.

## Modalità

`strict_verified` è il default e non un fallback: una query che non dichiara
la modalità ottiene la più conservativa. `ontology_aware_warning` e
`audit_all` vanno chieste esplicitamente. Il bucket primario è identico nelle
tre: exact, normalized exact e verified alias soltanto. Ciò che cambia fra le
modalità è come vengono esposte le relazioni non exact, mai quali diventano
primarie.
