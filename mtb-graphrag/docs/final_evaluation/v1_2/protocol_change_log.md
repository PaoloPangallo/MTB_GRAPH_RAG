# Protocol 1.2 change log

This document is explanatory only. JSON files under
`evaluation/final_protocol_v1_2/` are the sole normative source of truth.

| Area | Classification | Protocol 1.2 treatment |
|---|---|---|
| Runtime, 1.1 lineage, A01, S01 | INHERITED_UNCHANGED | Referenced by exact IDs and hashes; no content copied or rewritten. |
| Success-criterion identifiers | INHERITED_UNCHANGED | H/R IDs remain stable; retired IDs are not reused. |
| D02 denominators and completeness | SUPERSEDED_BY_V1_2 | Candidate, path, 16-field, identity, and negative units are explicitly separated. |
| D03 ranking formulas | SUPERSEDED_BY_V1_2 | Positive N=9 primary, N=20 direct-hit companion, N=11 zero-direct report, K=5 and hit-only mean rank. |
| D04 GOLD arm | CLARIFIED | Full annotated context, no truncation, explicitly not equal-budget. |
| D05–D07 ablations | CLARIFIED | Exact stages and downstream contracts are harness-side only. |
| D08 reliability | CLARIFIED | Two strata and cache/network initialization are explicit and never aggregated. |
| D09 retry/lifecycle | CLARIFIED | Scientific repetitions, infrastructure attempts, and orphan reconciliation are distinct. |
| D10 statistics | SUPERSEDED_BY_V1_2 | Wilson and percentile bootstrap are used; `p_values_planned=false` globally. |
| D11 latency stages | SUPERSEDED_BY_V1_2 | Sixteen records are normative; 3b resolves the 15/16 ambiguity. |
| D12 latency pair | CLARIFIED | Fixed GCA/document identity; operational A/B is not reused. |
| D13 identifiers | CLARIFIED | Canonical JSON and outcome-independent hashes are normative. |
| D14 dataset identity | CLARIFIED | Every artifact carries a dataset hash map, never one singular hash. |
| D15 raw lifecycle | CLARIFIED | Append-only raw and reconciliation recovery are mandatory. |
| D16 frozen precedence | CLARIFIED | Structured signed records and commits supersede stale pre-freeze prose. |
