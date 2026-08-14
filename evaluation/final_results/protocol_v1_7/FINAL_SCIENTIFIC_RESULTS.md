# Final Evaluation Protocol 1.7

Campaign: `fe_d3946016a0e90299b6989b58ac2f7fe34d352fd3269e94ea4d6efe874413477b`; state: `PROMOTED`; accounting: `222/222`.

No scientific execution, LLM, provider, or network call was made by this post-processor.

## RQ1

- materialization precision: 1.0
- materialization recall: 1.0
- field completeness: 1.0
- contract direction inversions: 0

## RQ2

- BM25: overall Hit@5=0.35; positive Hit@5=0.7777777777777778; positive n=9; zero-direct n=11
- DETERMINISTIC_SELECTOR: overall Hit@5=0.4; positive Hit@5=0.8888888888888888; positive n=9; zero-direct n=11
- FIRST_K: overall Hit@5=0.3; positive Hit@5=0.6666666666666666; positive n=9; zero-direct n=11
- GOLD: overall Hit@5=0.15; positive Hit@5=0.3333333333333333; positive n=9; zero-direct n=11

## RQ3

- Ablation comparison: `NOT_COMPUTABLE_FROM_FROZEN_SPEC`; raw arm observations are in `rq3/rq3_final.json`.

## RQ4

- Development correct path: 27/35
- Held-out correct path: 24/35

## Narrative

- Hostile correctly rejected: 14/20
- Hostile incorrectly accepted: 6/20
- Controls accepted: 0/5

## Operational

- Property tests passed: 9/9

## Reliability

- Canonical-state stability: `NOT_COMPUTABLE_FROM_FROZEN_SPEC`.

## Latency

- HIT: 15.000000013969839 ms
- MISS: 30.999999988125637 ms
- Absolute delta: 15.999999974155799 ms

## Integrity / campaign accounting

222/222 canonical raw records indexed; source ledger and raw artifacts were not modified.

## Not computable from frozen spec

- `RQ2.recall_at_10` — raw selector output contains only top-5 IDs
- `RQ2.document_resolution_rate` — RQ2 raw is the selector/enricher result and does not contain the frozen document-resolution denominator
- `RQ2.full_text_availability_rate` — RQ2 raw does not contain the frozen document availability fields
- `RQ2.abstract_degradation_rate` — RQ2 raw does not contain the frozen degradation fields
- `RQ2.parser_success_rate` — RQ2 raw does not contain parser-stage observations
- `RQ2.wrong_document_accepted` — frozen validator field is not present in canonical raw
- `RQ2.wrong_sourceunit_accepted` — frozen validator field is not present in canonical raw
- `RQ2.wrong_quote_accepted` — frozen validator field is not present in canonical raw
- `RQ3.primary_ablation_metrics` — Protocol defines paired invariants, but the five final raw records do not contain the frozen comparison/signature fields needed to evaluate them without a new interpretation.
- `RELIABILITY.canonical_state_stability` — final raw lacks the frozen canonical-state signature/comparison field
