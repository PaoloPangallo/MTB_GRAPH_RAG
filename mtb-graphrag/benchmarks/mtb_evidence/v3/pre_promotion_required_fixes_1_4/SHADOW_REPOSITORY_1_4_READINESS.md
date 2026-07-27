# Readiness del repository shadow 1.4

Repository: `qualified_claim_repository/1.4`  
Stato: `shadow_not_promoted`

| Gate | Valore |
|---|---|
| `claim_ids_stable` | **true** |
| `corpus_promotion_ready` | **true** |
| `critical_findings` | `0` |
| `formulation_contract_frozen` | **true** |
| `formulation_contradiction_resolved` | **true** |
| `full_exploratory_rerun_ready` | false |
| `integrated_gate_regressions_green` | **true** |
| `link_plan_schema_normalized` | **true** |
| `major_findings` | `0` |
| `minor_findings` | `0` |
| `non_atomic_propagation_explicitly_blocked` | **true** |
| `operational_retriever_migration_ready` | false |
| `propagation_policy_schema_uniform` | **true** |
| `required_promotion_fixes_resolved` | **true** |
| `shadow_repository_v1_4_ready` | **true** |
| `unknown_policy_mode_rejected` | **true** |

## Finding

| Finding | Prima | Dopo | Esito |
|---|---|---|---|
| `CLAIM_IDENTITIES_STABLE` | `informational` | `none` | verified |
| `LINK_PLAN_SCHEMA_HETEROGENEOUS` | `minor` | `none` | resolved |
| `NO_DISTINCT_FORMULATION_OUTCOME` | `minor` | `none` | resolved |
| `PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS` | `major` | `none` | resolved |
| `SALT_FORM_CLAIMS_LEAVE_PRIMARY_BUCKET` | `none` | `informational` | accepted_and_recorded |
| `SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT` | `major` | `none` | resolved |
| `UNKNOWN_MODE_REJECTION_NOT_DECLARED` | `minor` | `none` | resolved |

## Cosa significa `corpus_promotion_ready = true`

Readiness per una fase separata di promozione prototipale, non per un uso operativo del corpus ne' per una validita' clinica.

Le due correzioni major richieste dall'audit sono applicate, e sono state
applicate *prima* di scrivere il corpus, che era la ragione per cui la
fase precedente teneva la porta chiusa. Nessun finding critical o major
resta aperto.

Cio' che questa readiness **non** dice: che il contenuto sia clinicamente
valido. La revisione resta non indipendente, 131 claim su 148 non hanno
mai avuto una revisione documentale, e il registro delle forme contiene
una sola voce verificata.

## Cosa resta falso, e perche'

`operational_retriever_migration_ready` resta falso. Il retriever
operativo non conosce i quattro bucket, non conosce le undici relazioni di
malattia e non conosce le otto relazioni di forma. Promuovere il corpus
non gliele insegna.

`full_exploratory_rerun_ready` resta falso. Rieseguire l'esplorazione
sopra un corpus non promosso misurerebbe una pipeline che non esiste.

## La voce che resta aperta

Dodici claim atomici in forma salina escono dal bucket primario per le
query sulla moiety nuda. Non e' un difetto della 1.4: e' la conseguenza
di non avere fonti per quelle forme. La voce e' registrata come
informational e chiede una revisione terminologica esterna, che e' la
stessa coda in cui `AUY922` aspetta dalla terminology closure.

