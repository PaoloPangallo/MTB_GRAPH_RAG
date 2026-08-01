# V3 Provenance Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruct and document, read-only, the provenance chain of every active qualified claim used by the V3 runtime.

**Architecture:** Read the promoted repository and its registry/manifest, follow claim-to-parent and parent-to-source references, inspect only existing source metadata and local identifiers, and emit auditable CSV/JSON/Markdown artifacts. No application or data asset is changed.

**Tech Stack:** Python standard library for read-only JSON/JSONL/CSV analysis; Markdown; Git.

## Global Constraints

- Do not modify runtime V3, corpus, Knowledge Graph, gate, scoring, bucket, backend, frontend, ledger, gold, or official benchmarks.
- Do not invent PMID, DOI, NCT, URL, locator, or source values.
- Do not read gold or write ledger data.
- Use only the repository at commit 93fb997 as the analysis baseline.
- Include only documentation, CSV/JSON audit outputs, and explicitly read-only analysis tooling in the commit.

---

### Task 1: Freeze baseline and audit universe

**Files:**
- Create: docs/provenance_audit/README.md
- Create: docs/provenance_audit/provenance_audit.md

- [ ] Record branch, commit, initial Git state, protected paths, and exact corpus registry path.
- [ ] Enumerate repository files without opening gold, ledger databases, or official benchmark inputs.
- [ ] Derive record, claim, technical, active, deprecated, aggregate, atomic, and domain counts from the current promoted repository.

### Task 2: Reconstruct claim provenance

**Files:**
- Create: docs/provenance_audit/provenance_inventory.csv
- Create: docs/provenance_audit/broken_provenance_links.csv

- [ ] Parse every qualified claim once and preserve null when a field is absent.
- [ ] Follow claim → parent → source unit → original record → identifier → locator/text.
- [ ] Mark each edge PRESENT, MISSING, BROKEN_REFERENCE, NOT_APPLICABLE, or USAGE_UNCERTAIN.
- [ ] Assign provenance status and first missing link with evidence-based confidence.

### Task 3: Produce aggregate statistics and pilot inspection

**Files:**
- Create: docs/provenance_audit/provenance_summary.json
- Create: docs/provenance_audit/source_identifier_distribution.csv
- Create: docs/provenance_audit/domain_provenance_summary.csv
- Create: docs/provenance_audit/pilot_claims.md

- [ ] Compute identifier and provenance distributions without deduplicating away claim-level rows.
- [ ] Select pilot claims by observed claim/domain/bucket fields only, including primary FGFR2, ALK G1202R, EGFR/osimertinib, audit, rejected, aggregate, source-missing, and best-available provenance examples.
- [ ] Document the first missing edge and the likely loss phase for every pilot claim.

### Task 4: Recommend non-applied repairs

**Files:**
- Create: docs/provenance_audit/recommended_repairs.md

- [ ] Separate mapping, propagation, documentation enrichment, no-source-expected, and manual-review proposals.
- [ ] For each proposal record affected claim count, risk, benefit, and whether semantic preservation is plausible.

### Task 5: Verify and commit

- [ ] Validate row uniqueness, parent/source references, local paths, count consistency, identifier non-invention, and protected-file exclusion.
- [ ] Confirm no application, corpus, ledger, gold, or benchmark files changed.
- [ ] Run documentation/link/CSV validation and any safe import check.
- [ ] Create the local commit: docs: audit V3 claim provenance.
