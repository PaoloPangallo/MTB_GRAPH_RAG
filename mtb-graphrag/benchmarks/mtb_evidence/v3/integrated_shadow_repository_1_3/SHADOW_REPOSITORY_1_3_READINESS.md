# Shadow repository 1.3 readiness

Repository: `qualified_claim_repository/1.3`
Stato: `shadow_not_promoted`

| Gate | Valore |
|---|---:|
| `audit_all_available` | **true** |
| `claim_ids_recomputed` | **true** |
| `corpus_promotion_ready` | **false** |
| `disease_gate_implemented` | **true** |
| `full_exploratory_rerun_ready` | **false** |
| `integrated_gate_implemented` | **true** |
| `ontology_warning_available` | **true** |
| `operational_retriever_migration_ready` | **false** |
| `pre_promotion_audit_ready` | **true** |
| `replacement_lineage_complete` | **true** |
| `shadow_repository_v1_3_ready` | **true** |
| `source_literals_preserved` | **true** |
| `strict_policy_default` | **true** |
| `terminology_mapping_applied` | **true** |
| `unresolved_terminology_preserved` | **true** |

La 1.3 è pronta come repository shadow riproducibile e come base per un audit
pre-promozione, non come corpus operativo.

Le tre voci chiuse lo restano per la stessa ragione delle fasi precedenti. Il
mapping applicato è verificato ma la review resta non indipendente e la
propagazione resta `prototype_only`. La coda terminologica non è chiusa:
AUY922 attende una revisione esterna. Il gate integrato è
implementato e simulato nel percorso shadow, non nel retriever operativo, che
resta invariato e continua a usare la propria nozione binaria di disease match.

Promuovere il corpus, migrare il retriever e rieseguire l'esplorazione sono tre
decisioni successive e distinte. Questa fase le prepara e non ne prende nessuna.
