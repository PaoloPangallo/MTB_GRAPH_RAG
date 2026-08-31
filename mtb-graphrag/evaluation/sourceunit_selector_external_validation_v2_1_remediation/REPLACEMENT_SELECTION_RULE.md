# RQ2 v2.1 — replacement selection rule (frozen before selection)

Status: `FROZEN_PRE_SELECTION`
Rule version: `rq2-replacement-selection/1.0`

## Purpose

Select exactly one replacement for the provenance-invalid RQ2 v2.0 pair,
without observing, computing, or using retrieval rankings or relevance labels.

## Candidate universe and ordering

The universe is the deterministic 36-item candidate pool returned by
`scripts/evaluate_independent_sourceunit_selector.py::select_candidate_pool()`
from the frozen `graph_candidate_repository/2.0` corpus. Its historical
ordering, including intervention preference and direction quotas, is retained.

Candidates are considered in that order. The first candidate satisfying every
eligibility rule below is the replacement. No criterion may be relaxed after
the audit begins.

## Eligibility rules

1. The record has exactly one PMID provenance and PAPER provenance.
2. The candidate and its resolved document are absent from the historical pilot
   candidate/document exclusion sets.
3. The candidate and document are absent from the 19 retained RQ2 pairs.
4. A local, read-only document payload is present; the original parser can
   deterministically create SourceUnits with non-empty text from it.
5. The resolved document has a valid, coherent identifier chain.
6. A provenance audit based only on the candidate raw record, evidence
   statement, source properties, local document identifiers, and local text
   returns `PROVENANCE_VALID`. Any material contradiction returns ineligible.

## Blinding and exclusions

The selection process must not invoke or inspect FIRST_K, BM25, the
deterministic selector, RQ2 gold labels, RQ2 result files, Hit@K, or any other
retrieval outcome. The candidate must not be selected for expected ease of
retrieval or expected relevance.

`RETRIEVER_RESULTS_USED_FOR_REPLACEMENT_SELECTION=FALSE`

## Stop rule

If no candidate satisfies every rule, no replacement is selected and no v2.1
dataset, gold, SourceUnit corpus, sealed plan, or evaluation is created. A
new locally available, compatible document corpus is then required before this
rule may be applied again.
