# Final Evaluation Harness 1.2

This package is an executor for the frozen Protocol 1.2. Normative values are
loaded from `evaluation/final_protocol_v1_2/*.json`; this code does not define
scientific parameters.

## Plan

```powershell
python -m evaluation.final_evaluation_harness.plan
```

## Dry run

```powershell
python -m evaluation.final_evaluation_harness.run_rq1 --dry-run
python -m evaluation.final_evaluation_harness.run_rq2 --dry-run
```

Dry-run validates identities, frozen inputs, schemas, cache plans, and counts
without creating `evaluation/final_evaluation/` or calling runtime, selector,
models, or network.

## Start boundary

The actual execution command is intentionally not enabled by these dry-run
entry points. A future explicit start command must create
`evaluation/final_evaluation/` only at execution start.

**START FINAL EVALUATION creates the immutable final result corpus. After this
command no protocol or harness semantic changes are permitted.**
