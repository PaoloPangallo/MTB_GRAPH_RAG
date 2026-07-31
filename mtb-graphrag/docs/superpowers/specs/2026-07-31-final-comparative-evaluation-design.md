# MTB-GraphRAG Final Comparative Evaluation Design

## Scope

Prepare, freeze, and smoke-test the final comparison protocol without reading the
external gold bundle or executing any official run. The branch is based on
`84bcecaafdee60206799fd0a245cb78f816b257e`; no merge or push is in scope.

## Architecture

The experiment must call the repository's real entry points rather than reproduce
their semantics:

- S1 calls `backend.comparison.live_runs.build_run` with the existing
  `FixedPlanStrategy`.
- S2 calls the same entry point with the existing `AgenticPlanStrategy`; the maximum
  is eight plan-act-observe steps and LangGraph is not on this official path.
- S3 calls `EvidenceRetrievalPipeline` with the explicit
  `qualified_claim_v3` backend, promoted repository 1.4, strict-verified policy,
  structural gate 1.3, and operational scoring 1.0.

The runner stores native outputs. It does not coerce V2 graph records into V3 claims
or V3 claims into V2 records. Comparisons are computed only on explicitly shared
axes. V3-only query capabilities are labelled and excluded from unfair paired
endpoints.

## Frozen inputs and query discipline

Each query has an original candidate, a corpus-derived final form, a V2 projection,
a V3 projection, exercised contracts, comparability class, and a pre-gold structural
audit. Replacements are permitted only for schema non-representability, missing
concept structure, contract confounding, artificiality, or redundancy. All reasons
are recorded before gold access.

The proposed final set remains seven families by three queries. Exact boolean
expressions repeat the gene on every term because that is the implemented parser
contract. Intervention and domain queries are V3-specific capability tests where the
V2 request schema has no equivalent field.

## Gold boundary

The gold manifest contains only an external identifier, expected names, already
known checksums, schema identifiers, and
`NOT_OPENED_FOR_FINAL_EXPERIMENT`. No runner path imports or reads a gold payload in
`plan` or `smoke` mode. Official execution fails closed until a later, explicit
authorization changes the external state; this phase does not provide that state.

## Artifacts and integrity

The versioned directory contains protocol, query audit, final queries, system/model
configurations, metrics, prompts, schemas, analysis plan, smoke evidence, and
readiness. JSON and JSONL files use deterministic serialization. Each artifact
declares common provenance metadata and a `content_sha256` computed over the
canonical payload with that field set to the empty string; Markdown and text hashes retain the metadata line but blank only the content_sha256 value. This convention avoids an impossible
self-referential file hash and is declared in the protocol.

## Runner behavior

The CLI has only safe preparation modes in this phase:

- `plan` validates frozen inputs and emits an exact execution inventory without
  contacting the gold.
- `smoke` runs synthetic or explicitly excluded `pilot_only` cases, uses isolated
  temporary ledgers/caches, validates schemas, checks deterministic replay, and
  records `pilot_only=true`, `final_evaluable=false`.
- `official` is present only as a fail-closed guard and exits before reading gold or
  running a system while the frozen manifest says `NOT_OPENED_FOR_FINAL_EXPERIMENT`.

Resume identity is a hash of system, query, model, replica, frozen configuration,
corpus, and code versions. Complete compatible records are skipped; incompatible or
duplicated identities fail rather than being silently reused.

## Metrics and analysis

The primary endpoint is paired claim-level precision on the comparative query
subset. Secondary endpoints cover retrieval, qualifier preservation, buckets,
abstention, provenance, efficiency, and report fidelity. The analysis keeps failure
stages separate and reports paired differences, effect sizes, and query-level 95%
bootstrap intervals. V2 agentic receives mean, standard deviation, minimum, and
maximum over five runs. nDCG is disabled unless valid graded gold exists. Conclusions
are exploratory and not general clinical validation.

## Smoke strategy

S1 and S2 use synthetic tool outputs and a scripted source verifier while traversing
the real shared control runner. S2 uses a scripted planner, proving the dynamic path
without spending experimental model calls. S3 uses a non-final `pilot_only` query on
the real promoted corpus and repeats it to prove canonical determinism. Model probes
are minimal non-experimental calls, recorded separately from system smoke outputs.

## Self-review

- No placeholder or tuning step remains.
- Corpus, gates, mappings, scoring, legacy backend, historical artifacts, and prior
  errata are read-only.
- The design never opens gold and never launches an official run.
- LangGraph is documented as present but outside the official S2 path.
- Model use is recorded per component; V3 structural eligibility, matching, bucket,
  and scoring remain deterministic and LLM-free.
