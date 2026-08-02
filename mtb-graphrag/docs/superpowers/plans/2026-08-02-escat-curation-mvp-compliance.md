# ESCAT Curation MVP Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the offline ESCAT curation MVP compliance fixes without creating an official rule set or changing V3 runtime behavior.

**Architecture:** Keep the existing dataclass model and JSON/JSONL workspace. Add explicit state-transition and rule-set validation helpers, route every CLI mutation through them, and preserve prior records on supersession. Keep pilot generation sourced only from the existing feasibility CSV.

**Tech Stack:** Python 3, stdlib `unittest`, dataclasses, JSON/JSONL, CSV, PowerShell/Git verification.

## Global Constraints

- Do not modify the 37 pre-existing untracked files.
- Do not create or import an official ESCAT rule set.
- Do not use legacy tiers, `evidence_level`, keyword inference, PMID-only inference, or LLM assignment.
- Do not modify runtime, frontend, knowledge graph, qualified claims, gate, score, bucket, official experiment, or official ledgers.
- Do not install pytest.
- Do not push or merge.

### Task 1: Add red tests for compliance behavior

**Files:**
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/tests/test_unittest.py`
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/tests/test_validation.py`

- [ ] Add unittest cases for the real 15-claim pilot counts, all required CLI commands, append-only event fields, status-preserving exports, fixture rule checks, and production-path invariants.
- [ ] Run `python -m unittest ...` and confirm new tests fail for missing commands/validation before implementation.

### Task 2: Implement audited workflow and rule validation

**Files:**
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/models.py`
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/audit.py`
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/validation.py`
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/workbench.py`
- Create: `benchmarks/mtb_evidence/escat_curation_mvp/test_fixture_ruleset.json`

- [ ] Add explicit state transitions and field-value validation.
- [ ] Add CLI commands for draft display, field editing, curator/rationale/status updates, rejection, supersession, and dossier export.
- [ ] Emit the requested audit actions with field, previous value, new value, actor, timestamp, and reason.
- [ ] Validate selected rule IDs, framework/version, rule source, required fields/conditions, exclusions, alternatives, subtier requirements, and distinct supporting/rule sources.
- [ ] Run the red tests and confirm they pass.

### Task 3: Correct pilot artefacts and documentation

**Files:**
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/data/pilot_drafts.jsonl`
- Modify: `benchmarks/mtb_evidence/escat_curation_mvp/data/pilot_missing_requirements.csv`
- Modify: `docs/escat_curation_mvp/README.md`
- Modify: `docs/escat_curation_mvp/curation_workflow.md`
- Modify: `docs/escat_curation_mvp/pilot_drafts_report.md`
- Modify: `docs/escat_curation_mvp/assessment_schema.md`
- Modify: `docs/escat_curation_mvp/audit_event_schema.md`
- Modify: `docs/escat_curation_mvp/escat_curation_summary.json`
- Create: `docs/escat_curation_mvp/mvp_compliance_report.md`

- [ ] Regenerate only from the existing feasibility CSV and document zero diagnostic/NOT_APPLICABLE pilot drafts.
- [ ] Document the corrected CLI, transitions, fixture boundary, and residual official-rule-set limitation.

### Task 4: Verify and commit

- [ ] Run all unittest cases and direct CLI smoke tests.
- [ ] Check pilot counts, event append-only behavior, diff isolation, and unchanged pre-existing untracked path inventory.
- [ ] Commit exactly `fix: complete ESCAT curation MVP compliance`.
