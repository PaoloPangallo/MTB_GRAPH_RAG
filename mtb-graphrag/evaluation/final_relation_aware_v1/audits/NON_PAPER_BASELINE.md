# Non-PAPER baseline: controlled-stop narrator test

`backend/research_pipeline/tests/test_narrator_does_not_regress_runtime.py::ClosedBlockersDoNotReopenTest::test_iss_001_controlled_stop_still_works`

The test expects `STOPPED` and currently observes `PARTIAL` for
`CASE-5-casecontext-mismatch-no-match`.

The failure was reproduced before the current uncommitted PAPER changes and
the test file has no diff in the current worktree. The changed files are
limited to the PAPER enrichment/determinism path, its tests, and the paired
runner; no narrator, contracts, or controlled-stop implementation is changed.
The elevated global run reproduced the same assertion after the PAPER tests
passed (`376 passed, 19 skipped, then this failure`).

Therefore:

```text
PRE_EXISTING=YES
PAPER_CAUSED=NO
```

This is a non-PAPER baseline failure and does not alter the scientific validity
of the paired PAPER benchmark. It remains recorded and is not fixed here.
