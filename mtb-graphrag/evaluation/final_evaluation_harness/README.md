# Final Evaluation Harness 1.4

Status: `PROTOCOL_1_4_ALIGNED_NOT_STARTED`

This package executes the frozen Protocol 1.4 identity and inherits the
scientific contract from Protocol 1.2. The effective model is
`gemma4:31b-cloud`; no real execution has occurred.

## Plan and dry run

```powershell
python -m evaluation.final_evaluation_harness.plan
python -m evaluation.final_evaluation_harness.run_rq1 --dry-run
python -m evaluation.final_evaluation_harness.run_rq2 --dry-run
```

Dry-run validates identities, frozen inputs, schemas, cache plans and counts
without creating `evaluation/final_evaluation/` or calling runtime, selector,
models or network.

## Future start boundary

```powershell
python -m evaluation.final_evaluation_harness.start `
  --arm `
  --confirm-evaluation-id <FINAL_EVALUATION_ID> `
  --confirm-plan-sha <SEALED_PLAN_SHA> `
  --confirm-start FINAL_EVALUATION_1_6
```

The gate remains disarmed during this phase. PRE/POST provider snapshots,
append-only lifecycle, sealed-plan execution and resume reconciliation are
enforced at the future boundary.

**START FINAL EVALUATION creates the immutable final result corpus. After
this command no protocol or harness semantic changes are permitted.**
