# Readiness alla promozione del repository 1.3

Decisione: **`ready_with_required_promotion_fixes`**

Ambito della decisione: promozione prototipale separata degli artefatti; non riguarda la validita' clinica del contenuto ne' la migrazione del retriever.

Readiness clinica dichiarata: false.
Questa fase non ha gli elementi per dichiararla e non la dichiara: la
revisione resta non indipendente e 131 claim su 148 non hanno mai avuto
una revisione documentale.

## Esiti

| Voce | Valore |
|---|---|
| `backward_compatibility_plan_complete` | **true** |
| `claim_ids_recomputable` | **true** |
| `corpus_promotion_ready` | false |
| `corpus_promotion_ready_after_required_fixes` | **true** |
| `critical_findings` | `0` |
| `false_automatic_merges` | `0` |
| `full_exploratory_rerun_ready` | false |
| `gate_bypasses` | `0` |
| `informational_findings` | `2` |
| `integrated_gate_invariants_hold` | **true** |
| `inventory_consistent` | **true** |
| `major_findings` | `2` |
| `minor_findings` | `3` |
| `novelty_diagnostics_complete` | **true** |
| `operational_retriever_migration_ready` | false |
| `parent_claim_lineage_complete` | **true** |
| `promotion_decision` | `ready_with_required_promotion_fixes` |
| `promotion_diff_complete` | **true** |
| `provenance_sufficient_for_prototype` | false |
| `qualification_link_plan_consistent` | **true** |
| `qualified_view_plan_consistent` | **true** |
| `rollback_plan_complete` | **true** |
| `strict_default_explicit` | **true** |

## Porte

| Porta | Esito |
|---|---|
| `claim_ids_recomputable` | **true** |
| `frozen_artifacts_unchanged` | **true** |
| `integrated_gate_invariants_hold` | **true** |
| `inventory_consistent` | **true** |
| `lineage_complete` | **true** |
| `novelty_diagnostics_complete` | **true** |
| `operational_query_parity` | **true** |
| `promotion_diff_complete` | **true** |
| `qualification_link_plan_consistent` | **true** |
| `qualified_view_plan_consistent` | **true** |
| `rollback_plan_complete` | **true** |
| `strict_default_explicit` | **true** |

## Finding

| Severita' | ID | Titolo |
|---|---|---|
| `informational` | `CROSS_DISEASE_ASSERTED_ON_ONE_ANCHORED_TERM` | cross_disease viene affermato quando un solo termine e' registrato |
| `informational` | `LEGACY_CLAIMS_WITHOUT_DOCUMENTARY_REVIEW` | 131 claim su 148 non hanno mai avuto una revisione documentale |
| `minor` | `LINK_PLAN_SCHEMA_HETEROGENEOUS` | il piano di link porta tre schemi di riga diversi |
| `minor` | `NO_DISTINCT_FORMULATION_OUTCOME` | una formulazione diversa e' indistinguibile da un farmaco non correlato |
| `major` | `PROPAGATION_POLICY_MISSING_ON_NON_ATOMIC_CLAIMS` | sei claim attivi non dichiarano la propria propagation policy |
| `major` | `SALT_FORM_TABLE_CONTRADICTS_FORMULATION_CAVEAT` | due sali dello stesso principio attivo ottengono esiti opposti |
| `minor` | `UNKNOWN_MODE_REJECTION_NOT_DECLARED` | il rifiuto delle modalita' sconosciute vive solo nel codice |

### Correzioni richieste alla promozione

- aggiungere al manifest promosso `unknown_policy_mode_behaviour: reject` e `fallback_to_broader_mode: false`
- decidere esplicitamente, prima della promozione, se la forma salina sia normalizzazione o entita' distinta, e allineare `SALT_FORM_SUFFIXES` al caveat oppure il caveat alla tabella
- normalizzare le 37 azioni su un solo schema di riga prima di eseguirle
- prevedere un match type `different_formulation` non primario, cosi' che la ragione del rifiuto resti leggibile
- serializzare `propagation_policy: prototype_only` su aggregate_intervention_claim e regimen_claim prima di scrivere il corpus promosso

## Perche' non `ready_for_prototype_promotion`

Nessun finding critico e nessuna porta rossa: l'inventario e' coerente,
gli ID si ricalcolano tutti, la lineage e' completa e reversibile, i gate
reggono in tutte e tre le modalita', la diagnostica di novita' non mostra
nessuna fusione automatica e nessun bypass. Cio' che manca non e' una
verifica ma due decisioni, e sono decisioni che vanno prese *prima* di
scrivere il corpus promosso, non dopo:

1. i sei claim non atomici devono dichiarare la propria propagation
   policy, perche' sono proprio quelli la cui propagazione va impedita;
2. la forma salina deve essere normalizzazione oppure entita' distinta,
   e oggi il repository dice entrambe le cose in due punti diversi.

Nessuna delle due si risolve promuovendo e correggendo dopo: la prima
cambierebbe il contenuto dei record, la seconda cambierebbe quali
risultati entrano nel bucket primario.

## Cosa resta falso, e perche'

`operational_retriever_migration_ready` resta falso finche' il corpus non
e' promosso: migrare un retriever verso un corpus che non esiste ancora
non e' una decisione anticipabile.

`full_exploratory_rerun_ready` resta falso. Rieseguire l'esplorazione
sopra un corpus non promosso misurerebbe una pipeline che non esiste.

