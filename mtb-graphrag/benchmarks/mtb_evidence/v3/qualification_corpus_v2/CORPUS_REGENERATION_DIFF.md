# Diff della rigenerazione del qualification corpus

**qualification_corpus/1.0 → qualification_corpus/2.0**

| | prima | dopo |
|---|---|---|
| flag serializzati obsoleti | 99 | 0 |
| unita' totali | 102 | 123 |
| unita' attive | — | 109 |
| unita' storiche | — | 14 |
| link | 10 | 201 |
| view | 147 | 147 |
| gold | 94 | 94 |
| unita' final | — | 0 |
| qualificatori hard-filterable | — | 0 |

## Impronte

```
frozen_kg_snapshot_fingerprint   ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae  (invariata)
qualification_corpus_fingerprint 70601662488ba16dea2f416a18156e8886405e08b004cd4308889e065318c104  (prima)
                                 d831c9737cb808739848d63cc052a0a37bfab3b89e926e29dbb60406f1600fc7  (dopo)
```

L'impronta del grafo congelato non cambia: nessun dato viene scritto nel KG.
L'impronta del corpus cambia perche' cambiano unita', stati e flag.

## Unita' per stato di revisione

| review status | unita' |
|---|---|
| `awaiting_first_review` | 31 |
| `awaiting_source_review` | 65 |
| `first_review_complete` | 15 |
| `human_reviewed` | 6 |
| `rejected` | 2 |
| `rejected_as_active_unit_due_to_insufficient_source_resolution` | 2 |
| `replaced_by_author_approved_consolidation` | 2 |

## Unita' per livello di propagazione

| eligibility | totali | attive |
|---|---|---|
| `none` | 102 | 92 |
| `prototype_only` | 21 | 17 |
| `final` | 0 | 0 |

## Classificazione delle differenze

| classe | numero |
|---|---|
| `expected_author_approval` | 5 |
| `expected_hash_change` | 1 |
| `expected_history_update` | 27 |
| `expected_policy_migration` | 87 |
| `expected_unit_restructure` | 22 |
| `unexpected_change` | 0 |
| `unresolved_conflict` | 0 |

**`unexpected_change` = 0** · **`unresolved_conflict` = 0** · **`obsolete_serialized_flags` = 0**

La rigenerazione e' accettabile soltanto con tutti e tre a zero.

## Differenze registrate

| entita' | modifica | classe | prima | dopo |
|---|---|---|---|---|
| `PU-PMID-22235099-baf3-engineered` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-clinical-cohort` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-clinical-component` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-cuto1-comparative` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-engineered-isogenic-models` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-h3122-kras-engineered` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-nih3t3-engineered` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22235099-preclinical-component` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22277784-baf3-17aag` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22277784-baf3-crizotinib-panel` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22277784-baf3-next-generation-alk-inhibitors` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-22277784-clinical-crizotinib-resistant` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-23344087-clinical-cohort` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-23344087-clinical-component` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-23344087-engineered-clones` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-23344087-patient-derived` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-23344087-preclinical-component` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-23344087-preclinical-unresolved-panel` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-31358542-clinical-cohort` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-31358542-clinical-component` | unit_added | `expected_unit_restructure` | — | — |
| `PU-PMID-31358542-preclinical-component` | unit_added | `expected_unit_restructure` | — | — |
| `PU-DOI-10.1182/blood-2022-163099-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-15118125-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-15329413-cohort-1` | review_status | `expected_history_update` | awaiting_source_review | awaiting_first_review |
| `PU-PMID-160559-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-16818618-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-17177598-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-17877814-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-18089823-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-18408761-cohort-1` | review_status | `expected_history_update` | awaiting_source_review | awaiting_first_review |
| `PU-PMID-18509184-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-18757403-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-18923525-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-19147750-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-20038723-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-20942962-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-20979473-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-20979473-cohort-1` | review_status | `expected_history_update` | awaiting_source_review | awaiting_first_review |
| `PU-PMID-21030459-cohort-1` | review_status | `expected_history_update` | awaiting_source_review | awaiting_first_review |
| `PU-PMID-21132006-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-21531810-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-21791641-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-22034911-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-22072639-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-22235099-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-22235099-cohort-1` | review_status | `expected_author_approval` | awaiting_source_review | first_review_complete |
| `PU-PMID-22277784-cohort-1` | review_status | `expected_author_approval` | awaiting_source_review | first_review_complete |
| `PU-PMID-22285168-cohort-1` | review_status | `expected_history_update` | awaiting_source_review | awaiting_first_review |
| `PU-PMID-22370314-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-22452895-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-23344087-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-23344087-cohort-1` | review_status | `expected_author_approval` | awaiting_source_review | first_review_complete |
| `PU-PMID-23598171-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-23658459-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-23786770-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-23816960-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-23982599-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-24122810-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| `PU-PMID-24122810-cohort-1` | review_status | `expected_history_update` | awaiting_source_review | awaiting_first_review |
| `PU-PMID-24263064-cohort-1` | is_propagatable | `expected_policy_migration` | True | False |
| … | altre 82 differenze | | | |
