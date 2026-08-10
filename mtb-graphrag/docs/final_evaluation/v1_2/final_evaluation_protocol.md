# Final Evaluation Protocol 1.2 — approved design

Status: `DRAFT_FOR_HUMAN_REVIEW`
Frozen: `false`
Protocol ID: `mtb-graphrag-final-evaluation/1.2`

This document explains the approved design for protocol 1.2. The structured
JSON artifacts under `evaluation/final_protocol_v1_2/` will be the sole
normative source of truth. This Markdown document must never override them.

## Purpose and pre-final status

Version 1.2 resolves specification ambiguities D02–D16 identified before any
final result was observed or any final run was executed. It does not rewrite
the history of protocol 1.1, amendment A01, or supplement S01.

The protocol inherits:

- runtime `3d2251f82a586535f79f3d0b3725c16330c365ba`;
- protocol 1.1 SHA `83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889`;
- A01 SHA `48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf`;
- S01 raw SHA `83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99`;
- S01 package SHA `b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15`.

`final_results_observed_before_v1_2` and
`final_runs_executed_before_v1_2` are both `false`.

## Document architecture

The structured protocol is a separate sibling directory. No 1.1 artifact is
overwritten. Each JSON file owns one concern:

- `protocol_manifest.json`: version, status, classification, and table plan;
- `lineage.json`: inherited immutable identities and precedence;
- `metric_registry.json`: exact RQ1/RQ2 metric units and denominators;
- `success_criteria.json`: stable H/R criterion identifiers;
- `result_schemas.json`: required scientific payloads and common envelope;
- `statistical_plan.json`: Wilson and paired percentile bootstrap;
- `execution_contract.json`: identifiers, attempts, retry, raw lifecycle;
- `latency_contract.json`: 16-stage model and same-document latency pair;
- `ablation_contract.json`: exact A–D interventions;
- `reliability_contract.json`: two reliability strata and 30 executions;
- `dataset_registry.json`: unambiguous per-testbed hash map.

`check_consistency.py` will fail closed on missing, ambiguous, or divergent
fields. `hash_protocol.py` will seal every normative file except the generated
`protocol_hash.json`, which cannot include itself.

## D01 — inherited S01 resolution

RQ2 text comes only from frozen
`evaluation/final_protocol/supplements/S01/sourceunits_1697.jsonl`. S01 is a
pre-final preservation supplement, not a new dataset. Reconstruction from the
original versioned artifacts is false; pre-final provenance and byte-identical
preservation are verified.

## D02 — RQ1 metric units

`candidate_structural_precision` uses materialized GCA candidates. Its
numerator is the number of non-spurious, structurally valid materialized
candidates and its denominator is the number of materialized candidates.

`materialization_recall`, also reported as `path_coverage`, uses eligible KG
paths. Its numerator is eligible paths with a corresponding candidate and its
denominator is 46,864.

The semantic core contains exactly 16 fields. Both completeness metrics are
required and reported separately:

- `core_field_completeness_micro`: correct core-field cells divided by
  `46,864 × 16`;
- `all_16_core_fields_correct_rate`: candidates with all 16 fields correct
  divided by 46,864.

`payload_identity` and `expected_payload_identity` are separate integrity and
provenance controls, never semantic completeness fields.

H-E (`does_not_support_promoted`) and H-F
(`negative_source_primary_bucket`) use the 1,936 negative-source candidates as
their primary denominators and target `0/1,936`. A `0/46,864` full-corpus
diagnostic may accompany H-E but cannot replace its primary denominator.

## D03 — RQ2 ranking metrics

The primary population is the nine candidate-document pairs containing at
least one `DIRECTLY_RELEVANT` SourceUnit. Per pair:

- HitRate@K is one when TopK intersects Direct, otherwise zero;
- Recall@K is `|TopK ∩ Direct| / |Direct|`;
- Precision@K is `|TopK ∩ Direct| / K`, even for documents with fewer than K
  units;
- MRR is reciprocal first-direct rank, with zero for a miss;
- Mean First Relevant Rank is computed on hits only and must report `N_hits`;
- FullCoverage@K is one exactly when Direct is non-empty and contained in TopK.

Primary aggregation is a macro-average over the nine pairs. A companion
`overall direct-hit coverage` reports HitRate@K over all 20 pairs, where the
11 zero-direct pairs contribute zero. Zero-direct behavior is a separate
N=11 report covering selection production, QUOTE/ABSTAIN, and validation; it
must not claim that the selector detects absence of relevance.

First-K, BM25, and Deterministic Selector all use K=5, the same pair, corpus,
and gold. Tie-breaking is inherited exactly from the frozen pre-final
behavior. There is no rejection threshold.

## D04 — GOLD downstream arm

GOLD is full oracle context, not an equal-budget ranking baseline. Positive
cases receive every directly relevant unit. Zero-direct cases receive every
directly or partially relevant unit, which means every partially relevant
unit in practice. IDs are ordered lexicographically and never truncated; the
observed pre-final maximum is 13.

GOLD and Selector use the same Gemma provider, prompt, schema, validator,
model configuration, and output-token limit. Only supplied context changes.
Every report must state: “Full annotated GOLD context vs bounded K=5 selector
context; not an equal-context-budget comparison.”

## D05 — pre-retrieval authority ablation

`PRE_RETRIEVAL_AUTHORITY_BOUNDARY_BYPASS` passes unchanged parser output
directly to retrieval, bypassing stage 3 Match Verifier and stage 3b
Eligibility Gate. It neither forces MATCH nor changes retrieval.

## D06 — quote-validator ablation

`QUOTE_VALIDATOR_BYPASS` retains transport and schema validation. A
transport-valid, schema-valid QUOTE passes through an identity semantic
validator without deterministic quote semantics. ABSTAIN, transport failure,
and schema-invalid output keep their original classifications.

## D07 — narrative-verifier ablation

`NARRATIVE_VERIFIER_BYPASS` executes Narrator normally but does not call the
Narrative Verifier for a transport-valid narrative. Only the offline ablated
view marks it `PRESENTED_IN_OFFLINE_ABLATION`; the canonical dossier remains
unchanged and structured fallback does not replace it because of the removed
verifier. Provider or transport failure never fabricates output.

## Ablation B — selector replacement

Ablation B replaces only Selector with First-K or BM25 on the same document,
SourceUnit corpus, gold, and K=5.

All ablations are harness-side stage bypasses or injections. Runtime source is
immutable.

## D08 — reliability

Reliability contains ten frozen IDs and three repetitions (`r01`, `r02`,
`r03`), totaling 30 executions in three rounds. Within a round, cases run in
lexicographic `case_id` order with identical runtime, model, prompt, selector,
cache initialization, and protocol identities.

The seven held-out architectural cases form stratum A and use the canonical
full system. The three selector pairs form stratum B and use Deterministic
Selector K=5, the same Gemma contract, and the same Quote Validator contract.
The strata are never aggregated into one accuracy. Exact-output, criterion,
output-hash, and event-path agreement are reported separately with no new
success threshold.

Stratum A measures canonical end-to-end execution reliability under an
identical initial cache state. Every individual run creates a fresh isolated
ephemeral cache initialized from `AUTHORIZED_DOCUMENT_CACHE_43`, with
operational corpus SHA
`d9e4d9d680b30ed2e7d8463bd708c4f83518472624fd3b5c37ec56bb06bf35e9`
and manifest SHA
`ece9d25d74b3050f222343d3f31dc22d20d39d1883957f431c4280ef9326006b`.
No cache is shared between cases or repetitions, and no output from one run
enters another run's initial state. Network policy is
`CANONICAL_RUNTIME_POLICY`: cache hits perform zero fetches; authorized API
acquisition is allowed on cache miss; runtime-native retries are unchanged;
infrastructure failures are preserved under D09. Network is not globally
disabled in this stratum.

Stratum B measures selector/enrichment downstream reliability on immutable
evidence input. SourceUnits are loaded directly from
`SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01`, raw SHA
`83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99`
and package SHA
`b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15`.
Cache is `NOT_APPLICABLE`, the document resolver is `NOT_CALLED`, and network
is `PROHIBITED`.

The two strata are reported separately and are never aggregated into one
reliability or accuracy rate.

## D09 — retry and failure preservation

A scientific repetition always gets a new repetition ID and run ID. An
infrastructure attempt keeps the same run ID and gets a new attempt ID.

Runtime-native retry for network timeout or HTTP 5xx remains inside the same
attempt and contributes latency. Terminal HTTP 4xx/404 is retained without a
semantic retry. Provider unavailable becomes `INFRASTRUCTURE_FAILED`; process
crash becomes `INCOMPLETE`; schema-invalid model output remains a scientific
transport-invalid result. Canonical controlled failure is valid and is not
retried.

Every failed attempt remains in the append-only ledger. No later attempt may
delete, overwrite, or replace it.

## D10 — statistics

Paired comparisons use a percentile bootstrap with 10,000 samples, seed
20260809, and 95% intervals. The resampling unit is the natural paired unit:
candidate-document pair for selector and GOLD comparisons, and case within the
same testbed/failure mode for full-versus-ablation comparisons. The statistic
is the mean paired difference of the appropriate per-case contribution. Ties
contribute zero. Infrastructure-failed pairs are excluded without imputation,
preserved separately, and reduce the reported `N_effective`.

Proportions use Wilson 95% intervals. Zero events are always printed as `0/N`.
`p_values_planned = false` for the entire Final Evaluation 1.2. It uses Wilson
confidence intervals and paired percentile bootstrap intervals without
hypothesis-test p-values, regardless of arm size.

## D11 — latency

The canonical runtime emits 16 stage records: `1`, `2`, `3`, `3b`, `4`, `5`,
`6`, `7`, `8`, `9`, `10`, `11`, `12`, `13`, `14`, `15`. The legacy count of
15 refers to nominal numbering 1–15 plus stage 3b.

Primary `end_to_end_latency_ms` is monotonic wall-clock time immediately before
canonical runtime entry through terminal return. Summed stage duration is
diagnostic only. Network, Gemma, Narrator, stage, and end-to-end time remain
separate. Retry time belongs to its originating component and end-to-end.

System latency includes cache lookup, document resolution, network wait,
parsing, runtime processing, and model calls. Harness overhead excludes cache
materialization, raw writing, hashing, report building, and aggregation.

A transparent harness-side monotonic wrapper may measure document-resolver API
calls without changing payload, control flow, or retry behavior.

## D12 — same-document latency pair

The dedicated fixture is labeled `SAME-DOCUMENT CACHE LATENCY PAIR` and uses
the fixed binding `GCA-0000980ba01970f893f8e4d7` plus `pmid:15705718` for
both LAT-HIT and LAT-MISS. LAT-HIT seeds that target; LAT-MISS uses the same
ephemeral cache plan with only that target excluded. Document, runtime,
case/GCA binding, model, network environment, and harness are identical. This
fixture does not replace A01 scenarios A or B.

If LAT-MISS fails infrastructure acquisition, neither member enters the paired
latency statistic; both attempts remain raw and `N_effective` is reported. No
replacement document may be selected after observing the outcome.

## D13 — execution identifiers

Canonical JSON uses UTF-8, sorted keys, and compact separators. Hashes are
lowercase SHA-256 hex.

`evaluation_id` is `fe_` plus the hash of runtime commit, protocol version,
protocol SHA, inherited A01 SHA, S01 package SHA, and harness commit.

`repetition_id` is `primary`, `r01`, `r02`, or `r03` as applicable. `run_id`
is `run_` plus the hash of evaluation ID, testbed, case ID, arm, and repetition
ID. Attempts are `<run_id>/a0001`, then monotonically increasing ordinals.
Timestamps never enter identifiers and are stored as UTC RFC3339 `Z` values.
Attempt ordinals are reserved in the append-only ledger before execution, so
outcomes cannot affect identity.

## D14 — dataset hashes

Every execution envelope contains `dataset_hashes`, never one ambiguous
`dataset_hash`. The dataset bundle SHA
`8ab387cbe65d0231e37be8f27a9b5ca81a29b14ae8d12e5df1b316695e553991`
is universal; exact testbed hashes are supplied by the normative dataset
registry. That registry contains every hash explicitly approved for GCA2,
GCA3 shadow, RQ2/S01, RQ4, quote/narrator corpora, held-out, reliability,
operational data, A01 cache contract, and historical regression.

## D15 — envelope and raw lifecycle

The common execution envelope is infrastructural and wraps, rather than
replaces, scientific result schemas. It contains schema version; execution
identity; normative identity; dataset hashes; model and selector
configuration; timestamps; status/failure/reason; input/output hashes; call
counts; immutable raw pointer/hash; and the scientific payload.

Before execution the ledger appends `ATTEMPT_RESERVED`. Raw per-attempt files
are immutable create-if-absent; duplicate attempt IDs hard-fail. A completed
run is never rerun automatically. Explicit infrastructure retry creates a new
attempt with the same run ID. After a process crash, a reconciliation/recovery
pass detects an orphan `ATTEMPT_RESERVED` and appends `INCOMPLETE`; the crashed
process is not assumed capable of writing that event. A new attempt is then
permitted. Crash after raw commit verifies the hash and appends new completion
events without rewriting raw. Scientific repeat creates a new repetition and
run ID. Aggregates remain derivable and versionable.

## D16 — frozen-state precedence

For 1.1 freeze/review state, precedence is:

1. `evaluation/final_protocol/protocol_hash.json`;
2. freeze commit `7b0b396b10d10794ac802325f8e7e2ff5ce33e28`;
3. generated held-out and reliability manifests;
4. the frozen A01 record.

Residual `frozen:false`, `READY FOR HUMAN REVIEW`, or future-tense freeze prose
inside sealed 1.1 documents is `STALE_PRE_FREEZE_PROSE` and has no current
normative force. The 1.1 files remain untouched.

## Stable criteria and operational inheritance

H-A through H-H remain active HARD criteria. H-I and H-J remain
`RETIRED_FROM_PRIMARY`. H-K, H-L, H-M, H-N, H-O, and H-P retain their
established meanings. R-1 and R-2 remain historical regression only. No ID is
renumbered.

The nine operational bindings are read directly from frozen A01, identified
by its SHA. They remain `OPERATIONAL CONFORMANCE / PROPERTY TESTS`; 9/9 means
nine pre-specified properties conformed, never 100% operational accuracy.

## Reports and no-execution boundary

The table plan remains Tables 1–12 plus historical Appendix A1. RQ1 separates
candidate precision, path coverage, 16-field completeness, payload identity,
and polarity invariants. RQ2 separates positive-only primary ranking, overall
direct-hit companion, zero-direct behavior, and full-context GOLD comparison.
RQ3, RQ4 development/held-out, narrative, operational, and latency remain
separate scientific sections.

Protocol creation, checking, and sealing must not create
`evaluation/final_evaluation/`, execute runtime or selector code, call Gemma or
Narrator, or access the network. Version 1.2 remains `frozen=false` and
`DRAFT_FOR_HUMAN_REVIEW` until a later explicit review and freeze phase.
