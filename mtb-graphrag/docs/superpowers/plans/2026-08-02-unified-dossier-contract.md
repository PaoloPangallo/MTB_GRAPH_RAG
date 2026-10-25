# Unified V3 Dossier Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, read-only canonical V3 dossier contract that aggregates frozen V3 core output with provenance, document support, ontology shadow evidence, diagnostic context, and ESCAT actionability without changing upstream decisions.

**Architecture:** A new package under `benchmarks/mtb_evidence/unified_dossier_contract/` will expose a pure builder. It accepts an opaque `core_result` snapshot, joins claim extensions only by exact `claim_id`, and returns additive dossier fields. It reuses the existing ESCAT shadow adapter and ontology shadow evaluator without promoting either module into V3 decisions.

**Tech Stack:** Python 3.12, standard library JSON/dataclasses/hashlib, existing local shadow modules, `unittest`.

## Global Constraints

- Work from `research/v3-escat-shadow-dossier` at `c408df6`; create `research/v3-unified-dossier-contract`.
- Do not push or merge.
- Do not modify runtime, production endpoints, frontend, knowledge graph, qualified-claim repository, gate, score, bucket, claim order, abstention, official ledgers, or pre-existing untracked files.
- ESCAT remains `RESEARCH_DRAFT`, `available=false`, shadow-only, with no automatic tier/subtier assignment.
- Ontology remains shadow-only and cannot alter core V3 fields.
- CompanionDiagnostic records remain outside `claims` and `claim_extensions`.
- Use only `unittest`; do not read gold artifacts; keep `gold_read_count=0`.

### Task 1: Branch and failing tests

**Files:** create the new package, its `tests/` package, and `test_contract.py`, `test_preview.py`, `test_scope.py`.

- [ ] Create the branch and package scaffolding.
- [ ] Write failing tests for the canonical schema, exact claim-id joins, orphan extensions, module maturity, and immutable core snapshots.
- [ ] Run `python -m unittest discover -s benchmarks/mtb_evidence/unified_dossier_contract/tests -p 'test*.py' -v` and confirm failures identify missing builders.

### Task 2: Canonical contract and module status

**Files:** create `contract.py` and `module_status.py`; update contract tests.

- [ ] Implement `build_module_status()` with the six required module declarations and separate maturity, execution mode, status, data scope, and limitations.
- [ ] Implement `core_snapshot_fingerprint()` using canonical JSON and SHA-256.
- [ ] Implement `build_dossier()` with `dossier_version`, `run`, `case_context`, opaque `core_result`, `claim_extensions`, `diagnostic_context`, `technical_records`, `module_status`, `limitations`, and `generated_at`.
- [ ] Verify before/after core hashes and structural equality.

### Task 3: Claim extensions

**Files:** create `modules.py`; update contract tests.

- [ ] Implement pure provenance, document-support, ontology, and ESCAT extension builders.
- [ ] Preserve claim-level versus parent/source-unit provenance; never promote a parent PMID.
- [ ] Return `NOT_ASSESSED` for unexecuted document support, never `NO_SUPPORT_FOUND` by default.
- [ ] Preserve ontology match types and mark all ontology output `shadow_only=true`.
- [ ] Delegate ESCAT presentation to the existing adapter and exclude fixture records from real previews.
- [ ] Detect orphan extension IDs and missing references without altering the core.

### Task 4: Diagnostic context and preview

**Files:** create `preview.py` and `data/unified_dossier_preview.json`; update preview tests.

- [ ] Build four offline cases: FGFR2/iCCA/derazantinib, ALK G1202R/NSCLC/alectinib, EGFR L858R/NSCLC/osimertinib, and RMI2/NSCLC.
- [ ] Keep diagnostic records in a separate graph-identifier section with explicit missing disease, provenance, and regulatory fields.
- [ ] Preserve pilot ESCAT `INCOMPLETE`, ALK/EGFR/RMI2 `NOT_ASSESSED`, and RMI2 abstention.
- [ ] Verify no fixture assessment or tier appears in real preview dossiers.

### Task 5: Documentation

**Files:** create all requested files under `docs/unified_dossier_contract/`.

- [ ] Document architecture, canonical schema, module maturity, claim extensions, diagnostic context, association rules, core invariants, previews, future runtime/API boundaries, and future agent behavior.
- [ ] State that the 15 pilot drafts and four exploratory cases are different populations.
- [ ] Record coverage, missing data, invariants, and non-integration flags in `unified_dossier_summary.json`.

### Task 6: Verification and commit

- [ ] Run the new suite and existing ESCAT suites with `unittest`.
- [ ] Verify only additive new paths are staged and run `git diff --check`.
- [ ] Confirm no runtime, endpoint, frontend, graph, repository, gate, score, bucket, order, abstention, fixture promotion, or automatic ESCAT assignment changes.
- [ ] Commit exactly `research: define a unified evidence dossier contract`.
- [ ] Verify no push or merge.
