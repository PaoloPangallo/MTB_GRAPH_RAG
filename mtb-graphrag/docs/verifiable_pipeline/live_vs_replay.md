# Canonical LIVE runtime and research replay

The system exposes one canonical operational runtime. A user run is started by
`RunStore.start()`, which opens `DocumentRuntime.open()` and executes the modern
orchestrator. There is no user-selectable operational LIVE/REPLAY switch and
there is no silent replay fallback.

Replay adapters exist only in the research and regression harness. They are
explicitly injected for frozen-artifact tests and are not reachable as a
fallback from the operational API. A failed LIVE run remains a failed run; a
research replay is a separate execution with separate provenance.

## Boundary

| Context | Document/source behavior | Purpose |
|---|---|---|
| canonical operational runtime | cache-first resolution, authorized acquisition on miss, real parsing and LIVE SourceUnit selection | operational execution |
| research/regression replay | frozen recorded artifacts, no network discovery, recorded selection/output adapters | reproducibility and regression |

`DETERMINISTIC_CACHE` means that a document source was read from the authorized
cache during a canonical run. `RECORDED_REAL_RUN` means a prior output was
replayed. These are distinct provenance states.

The execution-mode vocabulary remains in the ledger to decode historical runs,
but it is metadata, not an operational routing choice. `REPLAY` is a research
label and `HYBRID` is a historical classification; neither is a user-facing
fallback mode.
