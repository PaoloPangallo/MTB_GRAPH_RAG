# V3 Provenance Repair Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a conservative, non-default provenance materialization pilot that propagates only already-documented claim-to-source mappings and records unresolved parent provenance explicitly.

**Architecture:** Keep `qualified_claim_repository/1.4` and the operational V3 path unchanged. Add an isolated propagation policy helper, a pilot materializer that copies 1.4 into `qualified_claim_repository_1_5_provenance_pilot`, and documentation/CSV reports comparing unchanged and newly eligible fields. Parent identifiers are never promoted without an explicit claim-level mapping or a single-source proof.

**Tech Stack:** Python 3.12, JSON/JSONL, pytest/unittest, Markdown, CSV.

## Global Constraints

- Do not change claim meaning, gate, scoring, bucket, Knowledge Graph, official experiments, ledgers, gold, or frozen outputs.
- Do not invent PMID, DOI, NCT, URL, source unit, locator, title, or text passage.
- Do not make repository 1.5 the default runtime repository.
- Do not read gold or official ledgers during implementation or verification.

---

### Task 1: Materialization trace and safe policy

**Files:**
- Create: `backend/pipeline/evidence/corpus/provenance_repair_pilot.py`
- Create: `docs/provenance_repair/provenance_materialization_trace.md`
- Create: `docs/provenance_repair/safe_propagation_rules.md`

- [ ] **Step 1: Write the failing policy tests** for explicit mapping, single-source proof, multi-source ambiguity, aggregate ambiguity, and no-invention behavior.
- [ ] **Step 2: Run the focused tests and confirm they fail** because the pilot policy module does not exist.
- [ ] **Step 3: Implement the minimal pure policy functions** returning the requested provenance states and never fabricating fields.
- [ ] **Step 4: Run the focused tests and confirm they pass.**
- [ ] **Step 5: Document the actual path** `1.4 row → rehydration → materializer → 1.5 row`, including the observed loss in `promoted_claims()` and the boundaries not modified.

### Task 2: Pilot repository and before/after inventory

**Files:**
- Create: `backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_5_provenance_pilot/` (copy of 1.4 with pilot-only provenance metadata)
- Create: `docs/provenance_repair/pilot_claims_before_after.csv`
- Create: `docs/provenance_repair/ambiguous_claims.csv`
- Create: `docs/provenance_repair/repository_version_diff.md`

- [ ] **Step 1: Select 12–20 representative claims** from existing explicit mappings plus parent-only EGFR/osimertinib, FGFR2, ALK, resistance, aggregate, preclinical, diagnostic, DOI-parent, and ambiguous cases.
- [ ] **Step 2: Record baseline values** from repository 1.4 and the non-official exploratory case responses without changing those artifacts.
- [ ] **Step 3: Apply only explicit mapping rows** already present in the repository’s review artifacts; leave ambiguous and parent-only claims unpromoted.
- [ ] **Step 4: Create the new version directory** without changing the registry default or repository 1.4.
- [ ] **Step 5: Validate IDs, source identifiers, locators, and claim payload equality** except for explicitly documented provenance metadata.

### Task 3: Regression and compatibility tests

**Files:**
- Create: `backend/tests/test_provenance_repair_pilot.py`
- Create: `docs/provenance_repair/provenance_repair_report.md`
- Create: `docs/provenance_repair/README.md`

- [ ] **Step 1: Add tests** for source-unit preservation, unique PMID propagation, real locator propagation, multi-source refusal, aggregate refusal, 1.4 byte/hash stability, and unchanged bucket/score snapshots.
- [ ] **Step 2: Run focused tests and then the existing V3 retriever binding tests.**
- [ ] **Step 3: Generate the final report** with repaired, publication-only, parent-publication, and ambiguous counts, plus extension risk for 131 claims.

### Task 4: Verification and commit

- [ ] **Step 1: Validate JSON/JSONL/CSV and all report counts.**
- [ ] **Step 2: Confirm no protected paths changed** relative to `38f9035` and no gold/ledger files were read by the verification script.
- [ ] **Step 3: Run `git diff --check`, inspect the staged path list, and create** `fix: preserve claim-level provenance during V3 materialization`.
