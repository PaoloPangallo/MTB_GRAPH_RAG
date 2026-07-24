# Biomarker matching fix readiness

Source state:
`7d4c623709c01ee69467c8ec615841de745f279e`

Correction:
`fix/v3-conjunctive-biomarker-matching`

## Status

| Check | State | Evidence |
|---|---|---|
| `technical_bug_fixed` | **true** | Alteration-specific matching now requires gene AND alteration. |
| `ALK_overreach_removed` | **true** | ALK-G1202R changed from 32 to 9; all 23 frozen `normalization_overreach` candidates were removed. |
| `disease_normalization_review_required` | **true** | Disease matching was deliberately unchanged; EGFR/FGFR2 gaps remain. |
| `multi_intervention_adapter_decision_required` | **true** | Adapter and V2 traversal semantics were deliberately unchanged. |
| `ready_for_full_exploratory_rerun` | **false** | The two independent open decisions above must be reviewed first. |

## Technical evidence

- `gene_level` remains available for queries without an alteration.
- `alteration_specific` is automatic when an alteration is present; there is
  no silent gene-level fallback.
- A different or missing alteration is excluded with
  `ALTERATION_MISMATCH_WITH_MATCHING_GENE`.
- Each such exclusion includes query and statement gene/alteration values.
- Exact protein variants and the explicitly declared
  `Fusion/Rearrangement` alternatives are preserved.
- Pending terminology mappings do not become exact.
- Multiple biomarkers retain pair identity; single, compound, and deletion
  forms cannot match through one shared token.
- Corpus, scoring, gold, 70 second-review packets, author approvals, prior
  exploratory results, and the prior candidate-coverage audit remain
  byte-identical to their frozen identities.

## Readiness decision

The narrow technical correction is ready for review and acceptance. The system
is not ready for a full exploratory rerun because the disease-normalization and
multi-intervention questions are independent of this fix and remain unresolved.

The next step is a separate, read-only review of disease normalization for
EGFR and FGFR2.
