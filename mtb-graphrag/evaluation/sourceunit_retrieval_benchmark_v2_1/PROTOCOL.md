# RQ2 SourceUnit Retrieval Benchmark v2.1 — frozen protocol

`PROTOCOL_VERSION=sourceunit-retrieval-benchmark/2.1`
`DATASET_VERSION=SOURCEUNIT_SELECTOR_EXTERNAL_VALIDATION_20_V2`

## Scope and remediation identity

RQ2 v2.1 compares First-K, BM25, and the historical deterministic
relation-aware selector for top-5 SourceUnit retrieval. The experimental unit
is GCA–PAPER pair × retrieval method. The 60 planned units are exactly 20
pairs × `FIRST_K`, `BM25`, and `DETERMINISTIC_SELECTOR`; GOLD is ground truth
only. No Reader, validator, relation-support, provider, network, or full
document arm belongs to execution.

This corpus replaces exactly one provenance-invalid v2.0 pair:
`GCA-002decb1b8be445d9dad8730|pmid:231047`. Its candidate evidence describes
RET/selpercatinib/LIBRETTO-121, while its identifiers resolve to PMID 231047,
a 1979 HSV-1/immunoglobulin article. The replacement is
`GCA-00e16c83d9144ac87139b7a3|pmid:15928335`, selected first under the frozen
16-candidate order before annotation and without retrieval output.

`REMEDIATION_REASON=ONE_PROVENANCE_INVALID_PAIR_REPLACED`
`REMEDIATION_RESULT_INDEPENDENT=TRUE`
`POSTHOC_RETRIEVER_TUNING=FALSE`

RQ2 v2.0 and `results_20260831T000000Z` remain immutable and reproducible
historical artifacts. They are not deleted and are not final v2.1 results.

## Inputs and ground truth

The v2 dataset has 19 verbatim retained provenance-valid pairs plus the manual
replacement review: 20 pairs and 1,706 SourceUnits. Strict relevance is
`DIRECTLY_RELEVANT`; broad relevance is `DIRECTLY_RELEVANT` or
`PARTIALLY_RELEVANT`. `CONTEXT_ONLY` and `NOT_RELEVANT` are non-relevant.

Replacement annotation method: `MANUAL_REVIEW`; input was GCA fields, document
text, and SourceUnit text. FIRST_K, BM25, selector, and other retriever output
were not visible; the replacement was selected before annotation. No dual
annotation or inter-annotator agreement is claimed.

The input hashes and production selector identity are sealed in
`input_hashes.json`. The selector is the production module
`backend.research_pipeline.experimental.sourceunit_selector`, version
`deterministic-sourceunit-selector/1.0`.

## Retrieval methods — unchanged from v2.0

All methods use the same v2 SourceUnits and `TOP_K=5`.

- `FIRST_K`: production `select_first_k`, parser order.
- `BM25`: production `select_bm25`; `k1=1.5`, `b=0.75`; query fields are
  alterations, genes, interventions, disease; tokenization and tie-breaking
  are unchanged.
- `DETERMINISTIC_SELECTOR`: production `select`, with unchanged weights,
  length factor, section priors, threshold (`score_total > min_score`),
  tie-breaking, and top-k. No v2.0 result changed this selector.

## Metrics and decision rule — unchanged from v2.0

Primary endpoint: Broad Hit@5 macro mean over the broad-positive pairs,
reported with its explicit denominator. Secondary endpoints: Strict Hit@5;
strict/broad Precision@5, Recall@5, and MRR@5; and Broad nDCG@5 with gains
DIRECT=2, PARTIAL=1, all others=0. Broad-negative pairs remain a separate
descriptive non-evidential-exposure cohort: fraction CONTEXT_ONLY, fraction
NOT_RELEVANT, and maximum relevance grade in top-5.

The winner rule is unchanged: highest Broad Hit@5; under substantive
equivalence, paired effect, uncertainty/CI, Broad nDCG@5, Broad MRR@5, Broad
Recall@5, then simplicity (`FIRST_K < BM25 < DETERMINISTIC_SELECTOR`).

## Historical caveat and no-post-hoc rule

`WEIGHT_TUNING_LEAKAGE=POSSIBLE`. This is
`EXTERNAL_VALIDATION_TEST_WITH_CAVEAT`, not a strict held-out test. The
replacement does not remove this historical caveat.

After the sealed 60 units execute, do not change BM25 parameters, selector
weights, length factor, section priors, threshold, TOP_K, query construction,
relevance definitions, metrics, or winner rule based on the results. A later
variant is a separate experiment and cannot use this corpus as independent
confirmation.
