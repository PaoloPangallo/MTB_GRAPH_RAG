# Verified disease alias fix readiness

## Status

| Check | State | Evidence |
|---|---|---|
| `verified_alias_matching_fixed` | `true` | The retriever uses typed match categories and permits only exact, normalized-exact, and verified aliases. |
| `NSCLC_alias_gap_resolved` | `true` | The frozen EGFR alias-safe set contains 32 graph evidence IDs and is reproduced exactly. |
| `hierarchy_policy_implemented` | `false` | Parent, child, and sibling relations are audit-only and cannot hard-match. |
| `multi_intervention_adapter_resolved` | `false` | The adapter was not modified in this phase. |
| `ready_for_multi_intervention_review` | `true` | Disease matching is now isolated, typed, deterministic, and independently auditable. |
| `ready_for_full_exploratory_rerun` | `false` | The separate multi-intervention architecture decision is still open. |

## Technical decision

The safe local correction is complete. It uses only the verified disease alias
table already present in the repository and introduces no new clinical
equivalence. The conjunctive gene-and-alteration constraint remains mandatory.

The next step is a separate, read-only review and architectural decision for
the multi-intervention adapter. No disease hierarchy policy or complete
exploratory evaluation should be implemented before that review.
