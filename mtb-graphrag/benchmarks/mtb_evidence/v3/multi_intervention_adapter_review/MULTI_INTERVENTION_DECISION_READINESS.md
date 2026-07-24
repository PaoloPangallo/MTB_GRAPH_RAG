# Multi-intervention decision readiness

- `multi_intervention_root_causes_identified`: **true**
- `statement_atomicity_decision_ready`: **false**
- `adapter_fix_ready`: **false**
- `adapter_schema_revision_required`: **true**
- `corpus_regeneration_required`: **true**
- `gold_migration_required`: **false**
- `source_review_required`: **true**
- `ready_to_implement_adapter_decision`: **false**
- `ready_for_hierarchy_policy_implementation`: **false**
- `ready_for_full_exploratory_rerun`: **false**

La root cause tecnica e' identificata, ma la decisione di schema non e' pronta:
tutti i gruppi multi-intervento richiedono source review prima di decidere
l'attribuzione. Solo dopo si potra' pianificare corpus, link e view. La policy
gerarchica disease resta separata; il rerun esplorativo rimane bloccato.
