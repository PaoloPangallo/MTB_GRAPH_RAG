# Final Evaluation Harness 1.3

Status: `PROTOCOL_1_3_ALIGNED_NOT_STARTED`

The execution adapters are wired to frozen runtime components but no real
Final Evaluation execution has occurred.

This package is an executor for frozen Protocol 1.3. Normative execution
identity is loaded from `evaluation/final_protocol_v1_3/*.json`; D02–D16 are
loaded from the frozen Protocol 1.2 parent. The effective model is
`gemma4:31b-cloud`.

Provider metadata PRE/POST snapshots are mandatory at the future START
boundary. They verify observable metadata only; provider-side digest and exact
weights remain explicitly not pinned.

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

The start boundary is explicit and non-interactive. All four confirmations
are required; the gate remains disarmed otherwise:

```powershell
python -m evaluation.final_evaluation_harness.start `
  --arm `
  --confirm-evaluation-id <FINAL_EVALUATION_ID> `
  --confirm-plan-sha 131921296897f7aa07498c02578ad82b95a4acb718d77e2eb0653c0f38bb5e29 `
  --confirm-start FINAL_EVALUATION_1_3
```

Resume uses the same confirmations plus `--resume`:

```powershell
python -m evaluation.final_evaluation_harness.start `
  --resume --arm `
  --confirm-evaluation-id <FINAL_EVALUATION_ID> `
  --confirm-plan-sha 131921296897f7aa07498c02578ad82b95a4acb718d77e2eb0653c0f38bb5e29 `
  --confirm-start FINAL_EVALUATION_1_3
```

The actual execution command is not run in this phase. PRE/POST provider
metadata snapshots, append-only campaign lifecycle, plan sealing and resume
reconciliation are enforced at the future boundary.

**START FINAL EVALUATION creates the immutable final result corpus. After this
command no protocol or harness semantic changes are permitted.**
