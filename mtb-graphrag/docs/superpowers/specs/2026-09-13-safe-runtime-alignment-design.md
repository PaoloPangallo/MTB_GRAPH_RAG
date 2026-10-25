# Safe Runtime Alignment Design

## Goal

Correct eight non-scientific runtime inconsistencies without changing GCA retrieval, PAPER Reader semantics, validation, relation support, selector behavior, TRIAL resolution, or KG_ONLY semantics.

## Scope

1. Treat `ENRICHMENT_V3_ACCEPTED` as document-grounded in the API provenance projection.
2. Preserve both requested and actually resolved PAPER document identities in `relation_aware_report`.
3. Rehydrate the top-level `relation_aware_report` so persisted and in-memory snapshots share one contract.
4. Record unconfigured optional narrative stages as `NOT_CONFIGURED`, never `NOT_IMPLEMENTED`.
5. Use `FULL_SUPPORT`, not the legacy `STRONG_SUPPORT`, in the Narrator prompt.
6. Permit KG_ONLY-only runs without requiring document-cache availability; PAPER/TRIAL still fail closed before any document-dependent processing.
7. Make the per-run LLM budget compatible with the maximum reachable parser and PAPER Reader calls.
8. Wire the Narrator through explicit configuration, disabled by default, with structured-dossier fallback on every presentation failure.

## Non-goals

- No change to `_match_candidate()` or GCA retrieval semantics.
- No post-resolution TRIAL compatibility scoring.
- No SourceUnit failure-policy change.
- No selector, prompt 4.8 Reader, Validator, Relation Support, or canonical support-state change.
- No scientific evaluation rerun.

## Design

### Provenance and PAPER identity

The API provenance accepted-outcome set will include the current v3 accepted outcome. PAPER orchestration will persist `requested_document_id` and `resolved_document_id`; the canonical `document_id` will mean the document actually delivered to the Reader. Existing PMID/PMCID fields remain available for compatibility.

### Persistence

`rehydrate()` will recover `relation_aware_report` from the successful stage-13 output preview and expose it at the same top-level key as `PipelineRun.to_dict()`.

### Optional presentation stages

When no Narrator is configured, stages 14 and 15 will be skipped with `NARRATOR_NOT_CONFIGURED`. When enabled explicitly, `RunStore` will pass `live_providers.narrator_fn`; failures remain presentation-only and cannot mutate or remove the canonical dossier.

The configuration surface will use an explicit boolean environment setting, defaulting to disabled. The endpoint configuration response will expose the resulting state without exposing credentials.

### Branch-aware cache precondition

The API will no longer reject every run solely because the document cache is unavailable. The orchestrator will determine whether selected associations contain PAPER or TRIAL documents. Such branches remain fail-closed if no `DocumentRuntime` can be opened. A KG_ONLY-only run may proceed without it.

Because branch identity is known only after parsing and retrieval, `RunStore` will open the document runtime lazily or tolerate cache absence until the orchestrator reaches a document-bearing branch.

### Budget

The maximum evidence-building call budget will equal one CaseContext Parser call plus the configured maximum PAPER candidates per family multiplied by the maximum selected documents per association. Narrator calls remain outside the scientific budget because they occur after canonical state closure.

## Failure behavior

- Missing cache + PAPER/TRIAL candidate: deterministic failure before Reader.
- Missing cache + KG_ONLY-only candidates: continue and build KG_ONLY dossier.
- Narrator disabled: canonical dossier returned; presentation stages marked not configured.
- Narrator/provider/verifier failure: canonical dossier returned unchanged with structured fallback.
- Budget exhaustion despite the derived cap: visible run failure, never silent truncation.

## Testing

Every production change follows a red-green TDD cycle. Required regression coverage:

- v3 accepted quote appears document-grounded in `/provenance`;
- requested PMID and resolved PMCID remain distinct and the canonical document ID equals Reader input;
- rehydrated and in-memory snapshots expose equal `relation_aware_report` values;
- disabled Narrator stages use a configuration reason, not `NOT_IMPLEMENTED`;
- prompt contract contains `FULL_SUPPORT` and no `STRONG_SUPPORT`;
- KG_ONLY-only run works without cache; PAPER/TRIAL do not;
- maximum reachable PAPER selection does not exceed budget;
- Narrator disabled/enabled/failing leaves the canonical dossier structurally identical.

## Evaluation impact

These changes repair API projection, provenance, persistence, optional presentation and infrastructure reachability. They do not change scientific comparison logic. No full scientific rerun is required; unit, integration, API and narrative regression tests are required.
