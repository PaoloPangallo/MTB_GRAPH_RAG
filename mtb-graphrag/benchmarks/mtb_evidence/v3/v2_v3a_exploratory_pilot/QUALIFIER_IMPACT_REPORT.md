# Qualifier impact report

## Frozen classification rule

`affected_fraction = unique affected query-candidates / candidate universe`

- zero changes: no measurable impact;
- fraction up to 0.10: limited;
- fraction up to 0.30: moderate;
- above 0.30: substantial.

This rule is versioned as `qualifier-impact/1.0`.

## Observed impact

- Candidate universe: 50
- Candidates with a non-zero qualified component: 49
- Gold-claim projections with a qualified contribution: 1
- Ranking swaps: 31
- Unique query-candidates with a top-k membership change: 19
- Raw membership changes by k: 2 at k=1, 6 at k=3, 8 at k=5, 18 at k=10
- Warning-only changes: 18
- Signed contribution total: -164
- Absolute contribution total: 196
- Classification: `substantial ranking impact`

Components actually used were unresolved (49), first-review bonus (16),
conflicting (10), partial (3), abstract-only (2), not-separable (2), and
ambiguous (1). Source-derived fields present include disease setting,
population, prior therapies, regimen, stage, and therapy line; resection status
is absent from contributing results.

The classification describes internal ranking movement, not clinical quality.
Because only one gold-claim projection is affected, qualification coverage is
too sparse to justify immediate expansion.
