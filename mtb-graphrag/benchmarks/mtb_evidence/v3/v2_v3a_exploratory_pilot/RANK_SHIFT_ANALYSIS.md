# Rank shift analysis

Rank-shift relevance uses the explicit gold-claim projection shared by both representations: biomarker, intervention, direction, assertion polarity, and source. It does not claim disease/context applicability. Historical V2-only relevant graph evidence is retained as
`absent_from_candidates`, not mislabeled as a demotion.

| Identity | Query | V2 rank | Native rank | Qualified rank | Classification |
|---|---|---:|---:|---:|---|
| evidence:100000 | ALK G1202R | 8 | 17 | 2 | promoted_by_prototype_qualifier |
| evidence:11219 | EGFR L858R | 47 | — | — | absent_from_candidates |
| evidence:11598 | EGFR L858R | 78 | — | — | absent_from_candidates |
| evidence:11599 | EGFR L858R | 52 | — | — | absent_from_candidates |
| evidence:1867 | EGFR L858R | 66 | — | — | absent_from_candidates |
| evidence:8173 | FGFR2 fusion | 23 | — | — | absent_from_candidates |

For `evidence:100000`, the qualified breakdown contains
`penalty_unresolved=-1` and `qualified_first_review=+1`; its stored warnings
include unresolved dimensions, prototype-only review, pending terminology, and
a qualifier mismatch observed but not hard-filtered. No causal label is emitted
without a non-zero stored score component.

The five historical-only rows explain gold-relevant coverage losses and have no
invented V3 score, warning, profile unit, or propagation status.
