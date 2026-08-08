# Live Document Retrieval and SourceUnit Selector Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the evaluated deterministic SourceUnit Selector into LIVE cache-first/API-on-miss execution while preserving exact frozen-bundle REPLAY behavior.

**Architecture:** LIVE will resolve provenance identifiers through an authorized cache that reads valid snapshots first and acquires only from the existing PubMed/PMC/ClinicalTrials resolvers on a miss. Parsed units will be ranked by the frozen selector at K=5 and only those units will reach the unchanged Paper Context Enricher V2 and quote validator. REPLAY will continue using the existing replay selection/enricher/validation adapters and will never construct a live resolver or call the selector.

**Tech Stack:** Python 3.12, existing `AuthorizedDocumentCache`, `DocumentRuntime`, deterministic parser/selector, `orchestrator`, append-only `EventLedger`, pytest, existing frontend test/build commands.

## Global Constraints

- Do not modify selector weights, normalization, BM25, section priorities, tie-breaking, feature set, or K; LIVE K is exactly 5.
- Do not modify Gemma prompt/transport/schema, quote validator semantics, GCA semantics, canonical gates, dossier, narrator, or historical artifacts.
- LIVE must never use frozen `bundle["source_unit_ids"]` for selection and must never silently fall back to REPLAY.
- REPLAY must use frozen document/bundle/source-unit artifacts, never network, and never the live selector.
- Document payloads remain outside Git; evaluation artifacts contain metadata only and no full text.
- Preserve append-only ledger attribution and existing LIVE/REPLAY/HYBRID execution-mode invariants.

---

### Task 1: Baseline and runtime contract

**Files:**
- Create: `docs/live_runtime_integration/00_scope.md`
- Create: `docs/live_runtime_integration/01_runtime_policy.md`
- Create: `evaluation/live_runtime_integration/runtime_contract.json`
- Test: existing `backend/research_pipeline/tests` baseline

**Interfaces:**
- Consumes: evaluated selector commit `2be1caf` and existing execution-mode contracts.
- Produces: immutable LIVE/REPLAY policy and baseline manifest used by later tests.

- [ ] Record branch, base commit, versions, cache descriptor, selector hash/version, and test baseline in the new evaluation directory.
- [ ] Write `runtime_contract.json` with `LIVE_uses_selector=true`, `LIVE_uses_frozen_bundle_for_selection=false`, `REPLAY_uses_frozen_bundle=true`, `REPLAY_uses_live_selector=false`, `LIVE_cache_first=true`, `LIVE_api_on_cache_miss=true`, `LIVE_silent_replay_fallback=false`, and `REPLAY_network_access=false`.
- [ ] Run `python -m pytest backend/research_pipeline/tests -q --disable-warnings` before implementation and record the exact result.
- [ ] Commit `docs: define live document acquisition runtime contract`.

### Task 2: Cache-first authorized acquisition

**Files:**
- Modify: `backend/research_pipeline/documents/authorized_cache.py`
- Modify: `backend/research_pipeline/documents/live_resolution.py`
- Modify: `backend/research_pipeline/documents/cache_runtime.py` only if cache-root validation must distinguish writable live cache from read-only replay access.
- Create: `backend/research_pipeline/documents/live_acquisition.py` if separating acquisition from read-only resolution is needed.
- Test: `backend/research_pipeline/tests/test_document_cache_bootstrap.py`, new `backend/research_pipeline/tests/test_live_document_acquisition.py`

**Interfaces:**
- Consumes: GCA-derived `document_id` values and existing `AuthorizedDocumentCache.resolve_pmid`, `resolve_pmc`, `resolve_nct` methods.
- Produces: `DocumentRuntime.open_live()` or equivalent that returns a single-run runtime with the manifest snapshot and a cache-first `resolve` operation.

- [ ] Add a live resolver path that opens `AuthorizedDocumentCache(root=cache_root, network=True)` once per LIVE run and reads existing manifest rows before network.
- [ ] Resolve only identifiers already present in the GCA/provenance; do not accept manual identifiers or generic search.
- [ ] Preserve PMID→PMCID derivation from the official PubMed response and record resolver version, retrieval mode, retrieval timestamp, raw payload hash, payload size, and cache-relative path.
- [ ] Ensure a cache miss writes the snapshot and manifest record before parsing and that a second resolution of the same identifier is a cache hit with zero network requests.
- [ ] Add explicit `CACHE_HIT`, `CACHE_MISS`, `DOCUMENT_FETCH_STARTED`, `DOCUMENT_FETCH_SUCCEEDED`, `DOCUMENT_FETCH_FAILED`, and degradation reason data without exposing payload text.
- [ ] Commit `feat: add cache-first authorized document resolution`.

### Task 3: Provenance-derived document candidates

**Files:**
- Modify: `backend/research_pipeline/retrieval/kg_retrieval.py`
- Modify: `backend/research_pipeline/documents/live_resolution.py`
- Test: new `backend/research_pipeline/tests/test_live_provenance_resolution.py`

**Interfaces:**
- Consumes: candidate repository GCA records and their `document_identifiers`.
- Produces: LIVE associations whose documents are attributable to the candidate and whose source-unit IDs are not required for acquisition or ranking.

- [ ] Retain frozen bundles only for the existing REPLAY selection path; for LIVE, derive document descriptors from each matched candidate’s normalized provenance identifiers.
- [ ] Preserve deterministic candidate ordering and existing GCA match semantics.
- [ ] Support PMID, PMCID, NCT and currently supported document identifier types; never substitute an alternative paper.
- [ ] Verify a candidate with only a PMID can produce a PMC document when the authorized resolver derives the PMCID.
- [ ] Commit `feat: resolve live documents from GCA provenance`.

### Task 4: LIVE selector routing and REPLAY preservation

**Files:**
- Create: `backend/research_pipeline/retrieval/live_sourceunit_selection.py`
- Modify: `backend/research_pipeline/orchestrator.py`
- Modify: `backend/research_pipeline/run_store.py` only if provider wiring needs an explicit live selector adapter.
- Test: new `backend/research_pipeline/tests/test_live_replay_sourceunit_routing.py`

**Interfaces:**
- Consumes: candidate GCA, resolved document ID, parsed `SourceUnit` map, and frozen selector `select` function.
- Produces: paper-like selection records containing `resolved_source_unit_ids` equal to deterministic top-5 IDs plus selector provenance; REPLAY continues to return `replay.selection_fn` output unchanged.

- [ ] Implement a LIVE selection adapter that never reads `bundle["source_unit_ids"]`; it must build `SourceUnitSelectionInput.from_candidate(candidate, document_id, units)` and call the evaluated selector with `top_k=5`.
- [ ] Return `selector_version`, `input_hash`, selected IDs, ranking hash, score/features preview, and `selection_reason` in redacted output.
- [ ] Do not introduce a new threshold or `NO_RELEVANT_SOURCE_UNIT` status.
- [ ] Keep the existing replay adapter as the only selector path when `execution_mode == REPLAY`.
- [ ] Add assertions/tests that LIVE selector input is all parsed units, frozen IDs are inaccessible, REPLAY selector call count is zero, and REPLAY uses recorded IDs.
- [ ] Commit `feat: promote deterministic source unit selector for live runs`.

### Task 5: Observable stages and failure boundaries

**Files:**
- Modify: `backend/research_pipeline/events.py`
- Modify: `backend/research_pipeline/contracts.py` only when existing stage vocabulary cannot represent source-unit selection.
- Modify: `backend/research_pipeline/orchestrator.py`
- Test: `backend/research_pipeline/tests/test_events.py`, new ledger assertions in routing tests

**Interfaces:**
- Consumes: cache/acquisition/selector results and existing `RunRecorder` stage events.
- Produces: append-only events distinguishable as document resolution, parsing, selection, enrichment, and validation.

- [ ] Emit cache/fetch/parse/selection events as stage-linked domain events or sub-events without adding unowned stages when existing stage IDs suffice.
- [ ] Ensure every event has run ID, stage ID, timestamp, producer/version, artifact origin, and parent linkage through the existing ledger API.
- [ ] Map fetch failure to `DOCUMENT_UNAVAILABLE`, parser failure to `PARSER_FAILED`, and selector failure to `SOURCEUNIT_SELECTION_FAILED`; never call Gemma with incomplete units.
- [ ] Preserve LIVE failure as failure and REPLAY failure as explicit missing-artifact behavior.
- [ ] Commit `feat: expose live document and selector provenance`.

### Task 6: Cache/replay/e2e regression tests

**Files:**
- Create: `evaluation/live_runtime_integration/*.jsonl` and `*.json`
- Create: `backend/research_pipeline/tests/test_live_runtime_integration.py`
- Modify: no historical tests to weaken them.

**Interfaces:**
- Consumes: live runtime path, replay adapters, temporary cache, real GCA provenance, and existing V2 validator.
- Produces: cache hit/miss, PubMed/PMC, abstract fallback, unavailable, unseen-document, replay separation, selector regression, and Gemma/validator regression evidence.

- [ ] Test cache hit: zero network, parser/selector/Gemma/validator reached, no frozen IDs used.
- [ ] Test cache miss: one authorized fetch, persisted snapshot, parser/selector/Gemma/validator reached; repeat is cache hit.
- [ ] Test PMID-only→PMCID→PMC, PMC unavailable→abstract, unavailable document, and no alternate-paper behavior.
- [ ] Test at least one independent unseen document through the entire live chain with temporary cache and no manual identifier input.
- [ ] Test replay with network disabled and selector disabled while frozen IDs and outcomes remain available.
- [ ] Test selector output identity against the evaluated ranking artifacts and verify K=5.
- [ ] Test V2 validator safety: wrong quote/document/source-unit accepted counts remain zero.
- [ ] Commit `test: cover live cache miss and replay separation`.

### Task 7: Full regression and final report

**Files:**
- Create: `docs/live_runtime_integration/02_document_acquisition.md` through `12_freeze_decision.md`
- Modify: `evaluation/live_runtime_integration/final_scorecard.json`
- Test: backend suite, clean-env import, frontend tests/build

**Interfaces:**
- Consumes: all previous task evidence and historical blocker checks.
- Produces: final integration decision and freeze/no-freeze scorecard.

- [ ] Run selector, document cache, parser, enricher, validator, orchestrator, dossier, narrator/verifier, research API, frontend tests, frontend build, and clean-env execution with sufficient timeout.
- [ ] Verify `does_not_support_promoted=0`, `negative_source_primary_bucket=0`, narrator cannot mutate canonical dossier, RQ3 prompt-only/uncontrolled counts remain zero, and historical hashes are unchanged.
- [ ] Write all required evaluation artifacts without full text and document known limitations.
- [ ] Choose `READY_FOR_FINAL_FREEZE`, `READY_FOR_FINAL_FREEZE_WITH_DOCUMENTATION_LIMITATIONS`, `NOT_READY_FOR_FREEZE`, or `ARCHITECTURAL_REGRESSION` only from measured evidence.
- [ ] Commit `docs: report final live integration`.
