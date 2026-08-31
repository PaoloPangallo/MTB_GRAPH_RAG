# RQ2 SourceUnit Retrieval Benchmark v2.0 — frozen protocol

`RQ2_PROTOCOL_VERSION=sourceunit-retrieval-benchmark/2.0`

## Research question and scope

On an external-validation/test-with-caveat corpus of 20 GCA–PAPER-document pairs with manually annotated SourceUnits, how do First-K, BM25, and the historical deterministic relation-aware selector compare for top-5 retrieval of directly or partially relevant evidence, without changing or selecting a retriever from this corpus's results?

The experimental unit is one GCA–document pair × one retrieval method. The sealed plan has 60 units: 20 pairs × exactly `FIRST_K`, `BM25`, and `DETERMINISTIC_SELECTOR`. `GOLD` is ground truth only; it is not an arm. No full-document, Reader, validator, relation-support, Gemma, network, or provider operation belongs to this protocol.

## Inputs and provenance

- Candidate inventory and manual annotations: `evaluation/sourceunit_selector_independent/`.
- SourceUnits: `evaluation/final_protocol/supplements/S01/sourceunits_1697.jsonl`.
- Invariants checked before any future execution: 20 pairs, 1,697 units, 29 DIRECTLY_RELEVANT, 49 PARTIALLY_RELEVANT, 355 CONTEXT_ONLY, 1,264 NOT_RELEVANT; 9 strict-positive, 10 broad-positive, and 10 broad-negative pairs.
- The historical development corpus is `evaluation/sourceunit_selector/dataset.jsonl` (25 bundles: 20 PAPER, 5 TRIAL). It has no exact pair/candidate/document overlap and a different binary-gold schema; it is excluded from the 60 final units and never pooled with these metrics.

Input and selector hashes are sealed in `input_hashes.json`. The production selector identity is `backend.research_pipeline.experimental.sourceunit_selector`, `deterministic-sourceunit-selector/1.0`; the harness imports its existing `select_first_k`, `select_bm25`, and `select` functions directly.

## Retrieval arms

All arms use `TOP_K=5` over the same frozen document SourceUnits.

- `FIRST_K`: production `select_first_k`, parser order.
- `BM25`: production `select_bm25`, BM25 `k1=1.5`, `b=0.75`, query fields alterations, genes, interventions, disease.
- `DETERMINISTIC_SELECTOR`: production `select`; `(BM25 + (3*alteration + 2*gene + 2*intervention + 0.5*disease) * min(1, text_length/80)) * section_prior(unit_type)`.

Gold labels are never an argument to the ranking dispatch. They are joined only after a selected ID list exists.

## Ground truth and metrics

Strict relevance is DIRECTLY_RELEVANT. Broad relevance is DIRECTLY_RELEVANT or PARTIALLY_RELEVANT. CONTEXT_ONLY and NOT_RELEVANT are not relevant.

The primary endpoint is Broad Hit@5, macro-averaged only over the 10 broad-positive pairs and always reported as `hits / 10`. Secondary positive-cohort endpoints are Strict Hit@5 (N=9), strict/broad Precision@5, Recall@5, MRR@5, and Broad nDCG@5. For nDCG, DIRECTLY_RELEVANT=2, PARTIALLY_RELEVANT=1, all other labels=0; `DCG@5=sum((2^gain_i-1)/log2(i+1))` and nDCG is `DCG/IDCG`.

Pairs with zero strict or broad gold are excluded, respectively, from positive-cohort Hit, Recall, MRR, and nDCG aggregation; they are not automatic retrieval failures. Broad-negative pairs are reported separately as non-evidential exposure / selected-context composition: fraction of selected top-5 CONTEXT_ONLY, fraction NOT_RELEVANT, and maximum relevance grade (normally zero).

## Aggregation, paired plan, and winner rule

Keep every per-pair output. For FIRST_K vs BM25, BM25 vs DETERMINISTIC_SELECTOR, and FIRST_K vs DETERMINISTIC_SELECTOR, prepare paired 2×2 Broad-Hit counts and exact McNemar; for Broad nDCG@5, MRR@5, and Recall@5 report paired deltas, mean/median delta, paired-bootstrap 95% CI, and optionally exploratory Wilcoxon. Document-type breakdown is descriptive only (12 PubMed abstracts; 8 PMC full texts).

Primary decision is highest Broad Hit@5. If methods are substantively equivalent on it, use in order: paired difference, uncertainty/CI, Broad nDCG@5, Broad MRR@5, Broad Recall@5, then simplicity (`FIRST_K < BM25 < DETERMINISTIC_SELECTOR`). Do not create an automatic winner under unresolved equivalence.

## Leakage caveat and post-hoc rule

Independent annotation freeze: `2026-08-08T10:34:30Z`. Selector weights entered history at `9025120ce30d1fdef28bb2f43ce1e04923e451f3`. There is no evidence of direct use of these gold labels, but no access-control or pre-registration proof excludes it rigorously: `WEIGHT_TUNING_LEAKAGE=POSSIBLE`. The corpus is therefore **external validation/test-with-caveat**, not a strict held-out test.

After the 60 sealed units execute, results must not change BM25 k1/b, structured weights, length factor, section priors, TOP_K, query construction, relevance definition, primary endpoint, or winner rule. A new variant designed after seeing results is a new experiment and cannot use this corpus as independent confirmation.

## Relation to the previous protocol

Historical RQ2 used 80 units with FIRST_K, BM25, DETERMINISTIC_SELECTOR, and GOLD, where GOLD meant full-document context. It is not used for this RQ2 inference. This protocol has 60 units, three retrieval arms, and gold as labels only. If all unrelated protocol blocks remain unchanged, the provisional total is 202; that is not a re-freeze of other blocks.
