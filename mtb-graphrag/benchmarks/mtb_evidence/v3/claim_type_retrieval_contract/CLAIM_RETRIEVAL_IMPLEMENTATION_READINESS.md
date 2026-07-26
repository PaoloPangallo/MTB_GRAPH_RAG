# Readiness dell'implementazione del retrieval sui claim

| criterio | stato |
| --- | --- |
| `claim_types_frozen` | true |
| `query_types_frozen` | true |
| `structural_match_rules_frozen` | true |
| `candidate_bucket_rules_frozen` | true |
| `score_eligibility_rules_frozen` | true |
| `warning_codes_frozen` | true |
| `current_scoring_audited` | true |
| `new_weights_required` | true |
| `adapter_migration_ready` | true |
| `corpus_regeneration_ready` | false |
| `retriever_migration_ready` | true |
| `scoring_migration_ready` | true |
| `hierarchy_policy_ready` | false |
| `full_exploratory_rerun_ready` | false |

## Cosa e' congelato

Tipi di claim, tipi di query, regole di match strutturale, regole di bucket, idoneita'
allo scoring e codici di warning. Il contratto e' completo nel senso che ogni
combinazione query-claim della simulazione riceve un match type, un bucket e una
motivazione, senza casi non coperti.

La simulazione ha valutato 640 combinazioni e nessun parent, nessuna
associazione non sostenuta e nessuna associazione non risolta e' entrata nel bucket
primario.

## Cosa manca e perche'

`new_weights_required` e' vero: le dodici feature proposte hanno dominio, significato e
ruolo — gate, positiva o solo penalizzante — ma nessun valore. Assegnarli qui
significherebbe sceglierli senza un criterio, oppure sceglierli guardando il gold, che e'
escluso.

`corpus_regeneration_ready` resta falso finche' adapter e repository non sono
implementati. `retriever_migration_ready` e `scoring_migration_ready` sono veri nel senso
che il contratto e' sufficiente a implementarli, non che siano stati implementati.
`hierarchy_policy_ready` resta fuori perimetro e `full_exploratory_rerun_ready` falso.

## La prima cosa da fare dopo

Trasformare le tre penalita' in gate nell'implementazione, prima di qualunque
ritaratura. Finche' restano pesi, ogni miglioramento numerico ottenuto altrove puo'
riportare un risultato di classe o un mapping pending nel bucket primario.
