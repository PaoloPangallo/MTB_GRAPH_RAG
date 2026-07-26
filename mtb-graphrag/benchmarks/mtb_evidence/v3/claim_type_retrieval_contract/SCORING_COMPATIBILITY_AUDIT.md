# Audit di compatibilita' dello scoring

Venti componenti del retriever e della configurazione di scoring, classificati rispetto
al nuovo modello. Nessun peso e' stato definito, ritarato o proposto in forma numerica.

- `incompatible_with_new_schema`: 1
- `requires_claim_type_branch`: 5
- `requires_new_feature`: 2
- `reusable_unchanged`: 5
- `reusable_with_typed_input`: 3
- `should_be_removed`: 4

## Il difetto strutturale

Quattro voci sono classificate `should_be_removed` e sono la stessa cosa vista quattro
volte: un vincolo espresso come peso. `penalty_pending_terminology` -3,
`penalty_not_separable` -2, `penalty_unresolved` -1 e `penalty_invalid` -50 servono a
impedire qualcosa, ma essendo numeri restano compensabili da altri numeri. Con
`native_biomarker` a 40 le prime tre non impediscono nulla in pratica.

`penalty_invalid` a -50 e' il caso limite: un valore scelto abbastanza grande da
comportarsi come un vincolo. Funziona finche' nessuno ritara i pesi.

## Cosa regge

La struttura a quattro bucket esiste gia' ed e' quella giusta. La scomposizione del
punteggio in parte nativa e qualificata regge e il contratto vi aggiunge un livello che
viene prima. `provenance.graph_record_ids` e' gia' una lista e sostiene il legame
claim-parent senza modifiche. Biomarcatore e disease sono indipendenti dal tipo di claim.

## Dettaglio

| id | componente | classificazione |
| --- | --- | --- |
| `SA-01` | qualified_retriever._candidates check 'intervention' | `incompatible_with_new_schema` |
| `SA-02` | _native_match | `requires_claim_type_branch` |
| `SA-03` | X_INTERVENTION_MISMATCH | `requires_new_feature` |
| `SA-04` | weights.native_intervention | `requires_claim_type_branch` |
| `SA-05` | weights.penalty_pending_terminology | `should_be_removed` |
| `SA-06` | weights.penalty_not_separable | `should_be_removed` |
| `SA-07` | weights.penalty_unresolved | `should_be_removed` |
| `SA-08` | weights.penalty_invalid | `should_be_removed` |
| `SA-09` | weights.penalty_negative_mismatch | `requires_claim_type_branch` |
| `SA-10` | thresholds.prototype_only_positive_cap | `reusable_with_typed_input` |
| `SA-11` | weights.native_biomarker e native_disease | `reusable_unchanged` |
| `SA-12` | RetrievalScoreBreakdown native/qualified split | `reusable_unchanged` |
| `SA-13` | QualifiedRetrievalOutput buckets | `reusable_unchanged` |
| `SA-14` | evidence_statement_id come identita' del candidato | `reusable_with_typed_input` |
| `SA-15` | repository.all() come sorgente dei candidati | `requires_claim_type_branch` |
| `SA-16` | provenance.graph_record_ids | `reusable_unchanged` |
| `SA-17` | campo 'regimen' dello schema statement | `requires_new_feature` |
| `SA-18` | missing_field_policy.unknown = neutral | `requires_claim_type_branch` |
| `SA-19` | tie_break_rules con statement_id_asc | `reusable_with_typed_input` |
| `SA-20` | match_disease hard match | `reusable_unchanged` |
