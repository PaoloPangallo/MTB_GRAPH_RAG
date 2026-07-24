# Atomicity decision report

## Decisioni per gruppo

- `aggregate_parent_only`: 4
- `atomic_children_supported`: 2
- `combination_regimen_required`: 3
- `insufficient_for_atomicity_decision`: 1
- `mixed_parent_and_children`: 1
- `should_not_materialize_missing_interventions`: 2

## Classificazioni intervention-level

- `directly_tested_in_combination_regimen`: 6
- `directly_tested_in_shared_aggregate_result`: 6
- `directly_tested_with_separate_result`: 11
- `mentioned_background_only`: 2
- `possible_alias_not_verified`: 3

## Regole applicate

Un child è autorizzato solo con intervento, risultato, direzione/polarità,
fonte e locator distinti. Risultati aggregati, componenti di regimen,
comparatori, menzioni e alias non verificati non diventano child.
