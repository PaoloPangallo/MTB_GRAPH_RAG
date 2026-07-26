# Readiness della chiusura terminologica

## Perimetro

- gruppi con terminology review aperta: 4 (attesi 4, trovati 4)
- coppie nella queue congelata: 2
- associazioni pending: 3
- hash della queue congelata: `da5f7252e8ecdb2cd935fda8fda46113bb1dd110c707a0db8d8081b5b10fdfb1`

## Decisioni

| coppia | decisione | scope | canonical | recommendation |
|---|---|---|---|---|
| `TP-AUY922-LUMINESPIB` | `insufficient_authoritative_evidence` | `none` | — | `require_external_review` |
| `TP-BGJ398-INFIGRATINIB` | `verified_development_code_for_same_intervention` | `global` | `infigratinib` | `approve_for_shadow_update` |

## Flag

| flag | valore |
|---|---|
| `all_mapping_candidates_reviewed` | `True` |
| `all_mapping_pairs_decided` | `True` |
| `claim_id_changes_required` | `2` |
| `corpus_promotion_ready` | `False` |
| `disease_hierarchy_policy_ready` | `True` |
| `full_exploratory_rerun_ready` | `False` |
| `operational_retriever_migration_ready` | `False` |
| `rejected_mappings` | `0` |
| `second_review_packets_ready` | `True` |
| `shadow_repository_terminology_update_ready` | `True` |
| `terminology_queue_complete` | `True` |
| `unresolved_mappings` | `1` |
| `verified_global_mappings` | `1` |
| `verified_source_local_mappings` | `0` |

## Che cosa resta chiuso

`corpus_promotion_ready`, `operational_retriever_migration_ready` e `full_exploratory_rerun_ready` restano falsi. Questa fase decide una terminologia; non promuove il corpus, non migra il retriever e non riesegue nulla.

La revisione e' **non indipendente**: un solo revisore reale. I packet ciechi per la seconda revisione sono pronti e non contengono decisioni, raccomandazioni ne' riferimenti valutativi.

## Integrita'

- parita' degli artefatti operativi: `True`
- repository shadow 1.0, 1.1 e 1.2 modificati: `False`
- riferimenti di valutazione deserializzati: `False`
