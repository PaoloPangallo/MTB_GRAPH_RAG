# MTB-GraphRAG Final Comparative Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Freeze and smoke-test the final three-system comparative evaluation without opening gold or executing official runs.

**Architecture:** Thin adapters call the existing V2 verified comparison runner and the explicit V3 retrieval backend. A fail-closed experiment harness validates immutable JSON/JSONL artifacts, run identities, schemas, resume behavior, and the gold boundary.

**Tech Stack:** Python 3.12, unittest, dataclasses, jsonschema-compatible JSON Schema, existing Neo4j/LangChain/Ollama adapters, SHA-256.

## Global Constraints

- Base commit is exactly `84bcecaafdee60206799fd0a245cb78f816b257e`.
- Do not modify promoted corpus, claims, gate 1.3, disease hierarchy, terminology or formulation mappings, scoring, retriever semantics, legacy backend, history artifacts, or prior errata.
- Do not merge, push, read gold, or run the official experiment.
- Smoke outputs must declare `pilot_only=true` and `final_evaluable=false`.
- Official mode must fail closed while gold state is `NOT_OPENED_FOR_FINAL_EXPERIMENT`.

---

### Task 1: Freeze discovery and environment contracts

**Files:**
- Create: `benchmarks/mtb_evidence/final_experiment/protocol_v1.md`
- Create: `benchmarks/mtb_evidence/final_experiment/protocol_v1.json`
- Create: `benchmarks/mtb_evidence/final_experiment/systems_v1.json`
- Create: `benchmarks/mtb_evidence/final_experiment/models_v1.json`
- Create: `benchmarks/mtb_evidence/final_experiment/prompts_v1/`

**Interfaces:**
- Consumes: repository SHA, promoted corpus manifest, retrieval contracts, model registry, environment inventory.
- Produces: frozen identifiers and configuration hashes consumed by all later tasks.

- [ ] Record the exact V2 fixed-plan, V2 agentic, and V3 entry points and their LLM/deterministic boundaries.
- [ ] Record Python, dependencies, OS, CPU, memory, GPU, external-service state, corpus/gate/retriever/generator versions and hashes.
- [ ] Freeze hypotheses H1-H6, endpoints, run counts, timeouts, retry rules, stop rules, missing-data rules, and failure taxonomy.
- [ ] Freeze the actual planner and source-verifier prompt versions; add only a V3 post-retrieval rendering prompt, never a structural-decision prompt.
- [ ] Validate that every frozen artifact carries common metadata and a declared content-hash convention.

### Task 2: Audit and freeze the 21 queries

**Files:**
- Create: `benchmarks/mtb_evidence/final_experiment/queries_candidate_audit.jsonl`
- Create: `benchmarks/mtb_evidence/final_experiment/queries_v1.jsonl`

**Interfaces:**
- Consumes: V2 API schema, V3 query schema, promoted corpus 1.4 and native V3 gate traces; no gold.
- Produces: `query_id`, family, original/final forms, V2/V3 payloads, capability class, comparative inclusion, expected structural buckets, candidate claim and graph-record identifiers.

- [ ] Encode all original candidates literally and validate each against both schemas.
- [ ] Measure corpus concepts and candidate objects without reading any gold artifact.
- [ ] Replace only invalid/confounded queries using the predefined criteria and record the comparability effect.
- [ ] Require exactly 7 families × 3 queries and reject duplicate final semantic forms.
- [ ] Mark boolean, intervention, regimen, diagnostic and prognostic inputs that V2 cannot express as `v3_specific_capability_test` and exclude them from unfair paired metrics.

### Task 3: Implement the fail-closed harness with TDD

**Files:**
- Create: `benchmarks/mtb_evidence/final_experiment/__init__.py`
- Create: `benchmarks/mtb_evidence/final_experiment/harness.py`
- Create: `benchmarks/mtb_evidence/final_experiment/run_final_experiment.py`
- Create: `backend/tests/test_final_experiment_harness.py`

**Interfaces:**
- Produces: `canonical_sha256(payload)`, `run_key(run_spec)`, `validate_frozen_inputs(root)`, `plan_runs(config)`, `assert_gold_closed(manifest)`, and CLI modes `plan|smoke|official`.

- [ ] Write a failing test proving canonical hashes ignore only the `content_sha256` slot and change for every other mutation.
- [ ] Run the focused test and confirm the expected failure.
- [ ] Implement canonical hashing and make the test pass.
- [ ] Write failing tests for stable run identity, duplicate incompatibility, and safe resume.
- [ ] Implement run identity and resume decisions; run focused tests green.
- [ ] Write a failing test proving official mode refuses before opening any expected gold file.
- [ ] Implement the guard so it checks manifest state before constructing readers or systems; run focused tests green.
- [ ] Write failing schema/output tests for S1, S2, and S3 native result envelopes.
- [ ] Implement thin adapters that call existing entry points without changing their semantics; run focused tests green.

### Task 4: Freeze schemas, metrics, and analysis

**Files:**
- Create: `benchmarks/mtb_evidence/final_experiment/run_manifest_schema.json`
- Create: `benchmarks/mtb_evidence/final_experiment/result_schema.json`
- Create: `benchmarks/mtb_evidence/final_experiment/metrics_v1.json`
- Create: `benchmarks/mtb_evidence/final_experiment/analysis_plan_v1.md`
- Create: `benchmarks/mtb_evidence/final_experiment/analysis.py`
- Create: `backend/tests/test_final_experiment_analysis.py`

**Interfaces:**
- Produces: metric registry with numerator/denominator semantics; `paired_differences`, `bootstrap_interval`, `agentic_summary`, and failure-stage classification.

- [ ] Write failing tests with hand-computed paired effects, bootstrap edge cases, and five-run agentic summaries.
- [ ] Implement deterministic analysis functions and make focused tests pass.
- [ ] Freeze retrieval, claim, bucket, abstention, provenance, efficiency and report metric definitions; disable nDCG without graded gold.
- [ ] Define schemas that preserve native candidates, claims, buckets, ranks, provenance, warnings, gate traces, latency, tool calls, tokens, costs, and failure stage.

### Task 5: Freeze the external gold boundary

**Files:**
- Create: `benchmarks/mtb_evidence/final_experiment/gold_external_manifest.json`

**Interfaces:**
- Consumes: existing external-input manifest metadata only.
- Produces: external identifier, expected filenames/checksums/schema, and closed state.

- [ ] Read only the existing external manifest, never an expected payload.
- [ ] Write `NOT_OPENED_FOR_FINAL_EXPERIMENT` and verify no file-content access is performed by plan or smoke modes.
- [ ] Record post-opening immutability and `post_hoc` rules in the protocol.

### Task 6: Execute smoke tests only

**Files:**
- Create: `benchmarks/mtb_evidence/final_experiment/smoke_test_report.json`
- Create: `benchmarks/mtb_evidence/final_experiment/readiness_report.json`

**Interfaces:**
- Consumes: synthetic V2 fixtures, scripted planner/verifier, excluded V3 pilot query, minimal model probes.
- Produces: schema-valid smoke evidence with no final metrics.

- [ ] Run S1 and S2 through the real shared runner with isolated temporary ledger/cache paths.
- [ ] Run S3 twice on the excluded pilot query and compare canonical payloads excluding latency.
- [ ] Verify timeout, complete logging, serializable provenance, safe resume, run isolation, deterministic S1/S3, legacy-backend isolation, and zero gold reads.
- [ ] Probe exact model identifiers with one minimal non-experimental call each and record digest/revision/endpoint/latency/token metadata if exposed.
- [ ] Label every smoke record `pilot_only=true`, `final_evaluable=false`.

### Task 7: Freeze, review, and verify

**Files:**
- Modify: all files under `benchmarks/mtb_evidence/final_experiment/` only to fill measured metadata and hashes.

**Interfaces:**
- Produces: one protocol-freeze commit and readiness decision.

- [ ] Generate all content hashes deterministically and validate them independently.
- [ ] Run focused final-experiment tests, schema validation, the four closure generator checks, and a final frozen-path diff audit.
- [ ] Run code review and address only findings inside the experiment harness/artifacts.
- [ ] Verify branch, SHA ancestry, clean index/working tree after commit, no merge, no push, gold closed, and official-run guard closed.
- [ ] Commit the frozen protocol and report `gold_opening_authorized` and `official_runs_authorized` as false unless every non-gold readiness gate is green; never change gold state in this phase.
