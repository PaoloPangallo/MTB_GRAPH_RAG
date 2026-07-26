# Shadow repository 1.2 readiness

Repository: `qualified_claim_repository/1.2`
Motivazione: documentary disease-scope narrowing of reviewed diagnostic claims

| Gate | Valore |
|---|---:|
| `claim_ids_recomputed` | **true** |
| `corpus_promotion_ready` | **false** |
| `diagnostic_scope_narrowing_applied` | **true** |
| `disease_hierarchy_policy_required` | **true** |
| `evidence_347_unchanged` | **true** |
| `full_exploratory_rerun_ready` | **false** |
| `old_diagnostic_claims_retired` | **true** |
| `operational_artifacts_unchanged` | **true** |
| `operational_retriever_migration_ready` | **false** |
| `replacement_claims_created` | **true** |
| `repository_v1_2_ready` | **true** |
| `source_review_status_preserved` | **true** |
| `terminology_review_required` | **true** |

La 1.2 è pronta come repository shadow riproducibile, non come corpus
operativo. Restano richieste una review terminologica, una policy esplicita per
la disease hierarchy e una successiva decisione di promozione. Per questo
promozione del corpus, migrazione del retriever e rerun esplorativo restano
false.
