# Multi-intervention source review

Review offline claim-level dei 13 gruppi congelati. Sono stati consultati solo
materiali locali: 1 fonte full-text,
10 abstract-only e
0 non disponibili.

| Graph evidence | PMID | Decisione | Interventi |
|---|---|---|---:|
| `evidence:229` | PMID:24736073 | `atomic_children_supported` | 2 |
| `evidence:275` | PMID:24457318 | `aggregate_parent_only` | 2 |
| `evidence:296` | PMID:24550739 | `atomic_children_supported` | 2 |
| `evidence:841` | PMID:26698910 | `mixed_parent_and_children` | 3 |
| `evidence:1483` | PMID:25393796 | `should_not_materialize_missing_interventions` | 2 |
| `evidence:1484` | PMID:25393796 | `should_not_materialize_missing_interventions` | 2 |
| `evidence:1851` | PMID:24122810 | `aggregate_parent_only` | 2 |
| `evidence:1853` | PMID:24122810 | `aggregate_parent_only` | 2 |
| `evidence:3811` | PMID:19147750 | `insufficient_for_atomicity_decision` | 3 |
| `evidence:4759` | PMID:21531810 | `aggregate_parent_only` | 2 |
| `evidence:11240` | PMID:31591063 | `combination_regimen_required` | 2 |
| `evidence:12131` | PMID:38942080 | `combination_regimen_required` | 2 |
| `evidence:12156` | PMID:37879444 | `combination_regimen_required` | 2 |

## Vincoli

- Gold e metriche di retrieval non sono stati usati per le decisioni.
- Nessun aggregate è stato trasformato in claim specifico.
- Nessun mapping pending è stato promosso.
- Le decisioni sono `prototype_only`, non hard-filterable e non final.

## Esito

La raccomandazione è `mixed_policy`. Sono simulati
8 child statement e sono
preservati 13 parent; il corpus
operativo non è stato modificato.
