# Readiness della migrazione dell'adapter

| criterio | stato |
| --- | --- |
| `parent_semantics_decided` | true |
| `all_packets_adjudicated` | true |
| `priority_concordant_cases_adjudicated` | true |
| `claim_types_decided` | true |
| `child_claims_decided` | true |
| `aggregate_claims_decided` | true |
| `regimen_claims_decided` | true |
| `unresolved_groups_remaining` | 1 |
| `terminology_review_remaining` | 4 |
| `migration_specification_complete` | true |
| `adapter_schema_revision_ready` | true |
| `corpus_regeneration_ready` | false |
| `hierarchy_policy_ready` | false |
| `full_exploratory_rerun_ready` | false |

## Perche' l'adapter e' pronto e il corpus no

`adapter_schema_revision_ready` e' vero perche' le condizioni che lo governano sono
soddisfatte: la semantica del parent e' decisa, ogni associazione ha uno stato, i gruppi
non risolti non bloccano la struttura generale — restano associazioni sul parent, che il
modello prevede — e nessuna decisione dipende dal gold.

`corpus_regeneration_ready` resta falso per definizione: presuppone che l'adapter sia
stato implementato e verificato, e qui esiste solo una specifica. `hierarchy_policy_ready`
e' fuori perimetro. `full_exploratory_rerun_ready` resta falso.

## Cosa resta aperto

- gruppi non risolti: 1 (`evidence:3811`)
- gruppi con revisione terminologica pendente: 4
- statement da deprecare senza sostituto: 2

Nessuna di queste voci blocca la revisione dello schema. La prima decisione da prendere
dopo, e che questa fase non ha preso, e' la regola di match dello scoring per tipo di
claim: regimi e aggregati non hanno un intervento scalare, e lo scoring attuale lo
assume.
