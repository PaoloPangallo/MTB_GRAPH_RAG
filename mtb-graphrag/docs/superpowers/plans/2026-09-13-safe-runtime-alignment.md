# Safe Runtime Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct eight presentation, provenance, persistence, cache-gating and budget inconsistencies without changing scientific runtime semantics.

**Architecture:** Keep `relation_aware_report` as the canonical structured dossier. Make API/persistence projections faithfully preserve its document provenance, make presentation explicitly optional, and align infrastructure preconditions with the branches that consume them.

**Tech Stack:** Python 3, FastAPI, pytest, SQLite event ledger.

**Spec:** `docs/superpowers/specs/2026-09-13-safe-runtime-alignment-design.md`

## Global Constraints

- Do not change GCA retrieval matching, PAPER Reader, Validator, Relation Support, SourceUnit selector, TRIAL resolver or KG_ONLY semantics.
- Do not make provider calls or run scientific evaluations.
- Preserve `API.dossier = relation_aware_report`.
- Use tests before every production change.

---

### Task 1: Current v3 provenance and resolved PAPER identity

**Files:**
- Modify: `backend/api/research_routes.py`
- Modify: `backend/research_pipeline/orchestrator.py`
- Modify: `backend/research_pipeline/dossier/builder.py`
- Test: `backend/research_pipeline/tests/test_research_api.py`
- Test: `backend/research_pipeline/tests/test_deterministic_report.py`

**Interfaces:**
- Consumes: validator outcome and `ResolvedDocument.document_id`.
- Produces: correct `document_grounded`, `requested_document_id`, and actual `document_id`.

- [x] Add a failing API test proving `ENRICHMENT_V3_ACCEPTED` is document-grounded.
- [x] Add a failing dossier test where requested PMID differs from resolved PMCID.
- [x] Run both tests and confirm the expected failures.
- [x] Add the v3 outcome and propagate actual/requested identifiers with minimal changes.
- [x] Run the focused tests and confirm they pass.

### Task 2: Persistence-equivalent canonical dossier

**Files:**
- Modify: `backend/research_pipeline/rehydration.py`
- Test: `backend/research_pipeline/tests/test_run_persistence.py`

**Interfaces:**
- Consumes: stage-13 `output_preview.relation_aware_report`.
- Produces: top-level rehydrated `relation_aware_report`.

- [x] Add a failing test comparing in-memory and rehydrated canonical reports.
- [x] Run it and confirm the top-level field is missing.
- [x] Restore the report from successful stage 13.
- [x] Run persistence tests.

### Task 3: Accurate optional-stage trace

**Files:**
- Modify: `backend/research_pipeline/orchestrator.py`
- Test: `backend/research_pipeline/tests/test_narrator_does_not_regress_runtime.py`

**Interfaces:**
- Consumes: absence of `call_narrator_fn`.
- Produces: skipped presentation stages with `NARRATOR_NOT_CONFIGURED`.

- [x] Add a failing test requiring the explicit not-configured reason.
- [x] Run it and confirm the current `NOT_IMPLEMENTED` result.
- [x] Add the minimal optional-stage completion path.
- [x] Run orchestrator and narrative regression tests.

### Task 4: Three-branch prompt terminology

**Files:**
- Modify: `backend/research_pipeline/narrative/prompt.py`
- Test: `backend/research_pipeline/tests/test_unified_narrator_projection.py`

**Interfaces:**
- Consumes: canonical PAPER support vocabulary.
- Produces: concise instructions using `FULL_SUPPORT` consistently.

- [x] Add a failing prompt-contract test rejecting `STRONG_SUPPORT`.
- [x] Run it and observe the obsolete term.
- [x] Replace only the obsolete terminology.
- [x] Run narrative prompt/verifier tests.

### Task 5: Branch-aware document-cache gate

**Files:**
- Modify: `backend/api/research_routes.py`
- Modify: `backend/research_pipeline/run_store.py`
- Modify: `backend/research_pipeline/orchestrator.py`
- Test: `backend/research_pipeline/tests/test_research_api.py`
- Test: `backend/research_pipeline/tests/test_canonical_runtime_invariants.py`

**Interfaces:**
- Consumes: optional `DocumentRuntime` and routed associations.
- Produces: KG_ONLY execution without cache; PAPER/TRIAL fail closed.

- [x] Add failing tests for KG_ONLY without cache and PAPER without cache.
- [x] Confirm KG_ONLY is currently rejected before routing.
- [x] Defer the hard cache requirement until document-bearing associations exist.
- [x] Run API and runtime integration tests.

### Task 6: Reachable-call budget alignment

**Files:**
- Modify: `backend/research_pipeline/run_store.py`
- Test: `backend/research_pipeline/tests/test_canonical_runtime_invariants.py`

**Interfaces:**
- Consumes: candidate-per-family and document-per-association caps.
- Produces: a budget of at least parser plus maximum PAPER document calls.

- [x] Add a failing invariant test deriving the reachable maximum.
- [x] Confirm the current value 6 is insufficient.
- [x] Derive or set the minimum compatible budget without changing selection caps.
- [x] Run call-budget and orchestrator tests.

### Task 7: Explicit optional Narrator wiring

**Files:**
- Modify: `backend/research_pipeline/run_store.py`
- Modify: `backend/api/research_routes.py`
- Test: `backend/research_pipeline/tests/test_research_api.py`
- Test: `backend/research_pipeline/tests/test_narrator_does_not_regress_runtime.py`

**Interfaces:**
- Consumes: explicit environment configuration.
- Produces: `call_narrator_fn` only when enabled; default remains structured-only.

- [x] Add failing tests for default-disabled and explicitly-enabled provider wiring.
- [x] Add an explicit boolean configuration parser and expose its state.
- [x] Wire `live_providers.narrator_fn` only when enabled.
- [x] Verify disabled, success and verifier-failure paths preserve the canonical dossier.

### Task 8: Integrated verification and review

**Files:**
- Review only: every file changed above.

**Interfaces:**
- Consumes: all seven independently passing changes.
- Produces: evidence that scientific components and API dossier schema are unchanged.

- [x] Run all focused tests for API, persistence, dossier and narrative.
- [x] Run the full `backend/research_pipeline/tests` suite (7 pre-existing/stale failures remain; see verification report).
- [x] Run `git diff --check`.
- [x] Confirm no diff in retrieval matching, selector, Reader, Validator, Relation Support, TRIAL resolver or KG_ONLY projection semantics.
- [x] Perform Python code review and address only in-scope findings.
