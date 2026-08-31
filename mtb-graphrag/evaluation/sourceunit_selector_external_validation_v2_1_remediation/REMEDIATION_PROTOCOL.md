# RQ2 external-validation remediation staging

Dataset identity proposed: `SOURCEUNIT_SELECTOR_EXTERNAL_VALIDATION_20_V2`.
Protocol identity proposed after successful manual annotation:
`sourceunit-retrieval-benchmark/2.1`.

This directory is a staging record, not an executable RQ2 v2.1 dataset.
The historical inputs and results are intentionally untouched:

- v2.0 dataset: `evaluation/sourceunit_selector_independent/`
- v2.0 SourceUnits: `evaluation/final_protocol/supplements/S01/sourceunits_1697.jsonl`
- v2.0 results: `evaluation/sourceunit_retrieval_benchmark_v2/results_20260831T000000Z/`

## Removal

`GCA-002decb1b8be445d9dad8730|pmid:231047` is excluded from any future v2.1
corpus because its candidate evidence statement/GCA describes LIBRETTO-121,
RET alteration, and selpercatinib, whereas its citation/document identifiers
resolve locally to PMID 231047, a 1979 HSV-1/immunoglobulin article. This is
`PROVENANCE_INVALID`.

The decision is independent of BM25, selector, Hit@5, gold labels, and RQ2
winner status: `REMOVAL_DECISION_INDEPENDENT_OF_RETRIEVAL_RESULTS=TRUE`.

## Completion gate

The v2.1 corpus requires 19 retained provenance-valid pairs plus exactly one
replacement that passes the frozen selection rule and receives a new manual,
ranking-blind SourceUnit annotation using the existing four-label schema.
No annotation may be synthesized or inferred from a retriever.

Until these gates pass, there is no v2.1 gold, SourceUnit corpus, sealed plan,
or benchmark execution.

## This staging decision

`replacement_pool_audit.jsonl` records all 36 candidates in their frozen
historical order. The 16 candidates not already retained or removed all lack a
locally present text payload, so none reaches the provenance-audit or manual
annotation gate. `replacement_selection_manifest.json` therefore records a
hard stop with no selected replacement. No review artifact can be honestly
created without SourceUnit text.

## Version history

- RQ2 v2.0: 20 original pairs; one provenance-invalid pair was discovered after
  execution. Its artifacts and results are preserved historically.
- RQ2 v2.1: planned as 19 retained valid pairs plus one independently selected,
  manually annotated replacement. v2.0 results are neither deleted nor reused
  as final v2.1 results.
