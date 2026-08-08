# Independent SourceUnit Selector Evaluation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the P0 by evaluating the frozen deterministic SourceUnit selector on at least 15 real GCA/document pairs whose candidates and documents are absent from the pilot.

**Architecture:** Work only in `eval/sourceunit-selector-independent-corpus`. Select real v2 GCA records from provenance, fetch each PMID into an ephemeral independent cache, derive PMCID only from the fresh PubMed response, parse with the existing canonical parsers, and persist metadata only. Freeze a human-readable relevance annotation before running the selector; then compute first-K/BM25/frozen-selector retrieval metrics and, if the local Gemma endpoint is available, compare downstream extraction on gold and selector units. No canonical runtime module or historical artifact is modified.

**Tech Stack:** Python 3.12, existing `AuthorizedDocumentCache`/document parsers, frozen `backend.research_pipeline.experimental.sourceunit_selector`, JSONL/CSV evaluation artifacts, pytest.

## Global Constraints

- The original worktree's untracked files are pre-existing and must not be touched, staged, or deleted.
- The frozen selector at HEAD is used unchanged for the first evaluation: no weights, tokenization, BM25 parameters, section priors, threshold, or top-K logic may be tuned.
- Gold annotations are created and hashed before selector execution and cannot contain selector/BM25/Gemma/downstream fields.
- Full text and quote text must not be written to committed artifacts.
- No orchestrator, GCA runtime, DocumentRuntime, canonical gates, enricher, validator, cache-miss behavior, or historical artifact changes.

---

### Task 1: Define the independent evaluation protocol

**Files:**
- Create: `docs/sourceunit_selector_independent/00_question.md`
- Create: `docs/sourceunit_selector_independent/01_independent_corpus.md`
- Create: `docs/sourceunit_selector_independent/02_annotation_protocol.md`
- Create: `docs/sourceunit_selector_independent/03_relevance_definition.md`

- [ ] **Step 1: Record the independence rules and pilot exclusion sets.**
- [ ] **Step 2: Specify DIRECTLY_RELEVANT, PARTIALLY_RELEVANT, CONTEXT_ONLY, and NOT_RELEVANT without support/status semantics.**
- [ ] **Step 3: State the blinding and gold-freeze procedure and artifact no-full-text rule.**
- [ ] **Step 4: Commit the protocol.**

### Task 2: Acquire and inventory an unseen corpus

**Files:**
- Create: `scripts/evaluate_independent_sourceunit_selector.py`
- Create: `evaluation/sourceunit_selector_independent/corpus_inventory.json`
- Create: `evaluation/sourceunit_selector_independent/candidate_inventory.jsonl`
- Create: `evaluation/sourceunit_selector_independent/document_inventory.jsonl`

- [ ] **Step 1: Add deterministic candidate selection from the real v2 repository, excluding pilot candidate/document IDs and duplicate PMIDs.**
- [ ] **Step 2: Fetch via PMID into an ephemeral cache, derive PMCID from the fresh PubMed response, and attempt PMC retrieval without reading the canonical cache.**
- [ ] **Step 3: Parse fetched records with `ReadOnlyDocumentCache` and record counts, parser versions, unit types, hashes, and retrieval provenance only.**
- [ ] **Step 4: Fail closed if fewer than 15 valid unseen pairs remain.**
- [ ] **Step 5: Commit metadata artifacts and the acquisition script.**

### Task 3: Freeze independent relevance gold before ranking

**Files:**
- Create: `evaluation/sourceunit_selector_independent/gold_annotations.csv`
- Create: `evaluation/sourceunit_selector_independent/gold_annotation_manifest.json`

- [ ] **Step 1: Review only fresh parsed units and GCA fields, assigning the four relevance labels and difficulty/negative-case tags.**
- [ ] **Step 2: Keep ranking, bundle IDs, expected quotes, Gemma output, validator outcomes, and canonical status out of the annotation input.**
- [ ] **Step 3: Hash the annotation CSV and record the freeze timestamp before selector execution.**
- [ ] **Step 4: Commit the frozen gold separately.**

### Task 4: Evaluate baselines and the frozen selector

**Files:**
- Modify: `scripts/evaluate_independent_sourceunit_selector.py`
- Create: `evaluation/sourceunit_selector_independent/selector_rankings.jsonl`
- Create: `evaluation/sourceunit_selector_independent/baseline_first_k.json`
- Create: `evaluation/sourceunit_selector_independent/baseline_bm25.json`
- Create: `evaluation/sourceunit_selector_independent/selector_metrics.json`
- Create: `evaluation/sourceunit_selector_independent/metrics_by_document_type.json`
- Create: `evaluation/sourceunit_selector_independent/metrics_by_difficulty.json`
- Create: `evaluation/sourceunit_selector_independent/negative_cases.json`
- Create: `evaluation/sourceunit_selector_independent/failure_analysis.csv`

- [ ] **Step 1: Run first-K, BM25-only, and frozen feature-aware rankings from GCA plus parsed source units only.**
- [ ] **Step 2: Compute HitRate, Recall, Precision, MRR, first-relevant rank, full coverage, and separate direct-only versus direct-plus-partial metrics at K=1/3/5/10.**
- [ ] **Step 3: Partition results by PubMed abstract versus PMC full text and by negative/long/table/alteration difficulty.**
- [ ] **Step 4: Classify misses without changing the selector.**
- [ ] **Step 5: Commit retrieval results.**

### Task 5: Run robustness and leakage audits

**Files:**
- Modify: `scripts/evaluate_independent_sourceunit_selector.py`
- Create: `evaluation/sourceunit_selector_independent/robustness.json`
- Create: `evaluation/sourceunit_selector_independent/leakage_audit.json`

- [ ] **Step 1: Repeat each ranking with permutations, NFC/NFD text, case/punctuation variants, duplicates, empty text, and deterministic ID tie-breaks.**
- [ ] **Step 2: Assert ranking drift is zero and no selected ID is outside the fetched input units.**
- [ ] **Step 3: Audit imports/read paths and runtime file diffs for zero pilot/gold/quote/Gemma/status access and zero canonical runtime modifications.**
- [ ] **Step 4: Commit robustness and leakage results.**

### Task 6: Evaluate Gemma downstream and architecture policy

**Files:**
- Modify: `scripts/evaluate_independent_sourceunit_selector.py`
- Create: `evaluation/sourceunit_selector_independent/gemma_comparison.json`
- Create: `docs/sourceunit_selector_independent/04_frozen_selector_evaluation.md`
- Create: `docs/sourceunit_selector_independent/05_baselines.md`
- Create: `docs/sourceunit_selector_independent/06_retrieval_results.md`
- Create: `docs/sourceunit_selector_independent/07_failure_analysis.md`
- Create: `docs/sourceunit_selector_independent/08_gemma_downstream.md`
- Create: `docs/sourceunit_selector_independent/09_selector_bundle_policy.md`
- Create: `docs/sourceunit_selector_independent/10_architectural_implications.md`
- Create: `docs/sourceunit_selector_independent/11_limitations.md`
- Create: `docs/sourceunit_selector_independent/12_final_decision.md`
- Create: `evaluation/sourceunit_selector_independent/final_scorecard.json`

- [ ] **Step 1: Compare gold-relevant, selector, and K=3/5/10 prompts where Gemma is available; record only counts, decisions, IDs, token metadata, and validator outcomes.**
- [ ] **Step 2: Report QUOTE/ABSTAIN, validated/rejected quote, wrong quote, unauthorized unit, and prompt token metrics separately from retrieval.**
- [ ] **Step 3: Evaluate replay-bundle versus live-selector policy without implementing either option.**
- [ ] **Step 4: Populate the final scorecard, answer the 18 final questions, and choose one of the four required decisions.**
- [ ] **Step 5: Run all relevant tests and commit the final report.**
