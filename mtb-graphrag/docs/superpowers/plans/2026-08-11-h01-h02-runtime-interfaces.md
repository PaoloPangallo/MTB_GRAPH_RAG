# H01/H02 Runtime Prerequisites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Freeze a candidate H01 held-out observation contract and expose only the public runtime seams required by RQ3 B/C/D.

**Architecture:** H01 is an isolated candidate-only JSON contract consumed after immutable raw inference. H02 adds selector-strategy injection, validator semantic injection, and an explicit narrative-verifier bypass while preserving canonical defaults.

**Tech Stack:** Python, dataclasses, JSON artifacts, pytest.

## Global Constraints

- Base runtime: `79867435acd59b830dae1d0fbab272c2bea2427b`.
- Do not modify Protocol 1.5, harness, datasets, gold, A01 or S01.
- Do not call providers, network, runtime scientific execution or Final Evaluation.
- Default canonical behavior must remain semantically equivalent.

### Task 1: H01 candidate artifacts

**Files:**
- Create: `evaluation/final_protocol_v1_6_candidates/rq4/*.json`
- Test: static JSON/vector validation command

- [x] Record finite eligibility, stage, run-state and forbidden-call vocabularies.
- [x] Record explicit null policy and conjunctive/adversarial verdict rules.
- [x] Record five hard-observable predicates and 35 case vectors.
- [x] Hash the complete candidate artifact set twice.

### Task 2: Selector strategy seam

**Files:**
- Modify: `backend/research_pipeline/orchestrator.py`
- Modify: `backend/research_pipeline/retrieval/live_sourceunit_selection.py`
- Test: `backend/research_pipeline/tests/test_final_evaluation_interfaces.py`

- [x] Add optional `source_unit_selector_fn(selection, *, top_k)`.
- [x] Keep document grouping, bundle construction, metadata and failure semantics in runtime.
- [x] Verify default path uses the existing `select` callable.

### Task 3: Validator semantic seam

**Files:**
- Modify: `backend/research_pipeline/enrichment/validator_v2.py`
- Test: `backend/research_pipeline/tests/test_final_evaluation_interfaces.py`

- [x] Keep transport gate unchanged.
- [x] Add optional `semantic_validator` after transport acceptance.
- [x] Provide `identity_semantic_validator` for D06 while preserving ABSTAIN checks.

### Task 4: Narrative verifier bypass

**Files:**
- Modify: `backend/research_pipeline/orchestrator.py`
- Test: `backend/research_pipeline/tests/test_final_evaluation_interfaces.py`

- [x] Add explicit `narrative_verifier_mode` with canonical default.
- [x] In bypass mode skip verifier invocation and emit only bypass telemetry/presentation state.
- [x] Ensure no synthetic PASS verdict is emitted.

### Task 5: Verification and isolated commit

**Files:** runtime files above plus candidate artifacts and tests.

- [ ] Run the complete relevant runtime test suite and new interface tests.
- [ ] Recalculate H01 artifact identity twice.
- [ ] Confirm Protocol 1.5, harness, datasets and Final Evaluation remain untouched/absent.
- [ ] Commit the focused runtime/H01 changes without pushing or merging.
