# Canonical runtime and artifact provenance

**VERIFIABLE RESEARCH PIPELINE — NOT CLINICALLY VALIDATED.**

The operational system has one canonical runtime. `RunStore.start()` opens
`DocumentRuntime.open()` and runs the modern orchestrator. It is not a user
choice between LIVE and REPLAY, and a failed canonical run is never silently
replaced by recorded output.

## Operational path

The canonical runtime performs cache-first document resolution, authorized
acquisition on a cache miss, persistence of the document snapshot, deterministic
parsing, LIVE document-aware SourceUnit selection, enrichment, validation,
gating and dossier construction. A document read from the authorized cache is
`DETERMINISTIC_CACHE`, not replayed model output.

## Research-only replay

The vocabulary below remains in persisted metadata so historical runs and
research harnesses can be decoded:

| Origin | Meaning |
|---|---|
| `GENERATED_NOW` | produced during the current run |
| `DETERMINISTIC_CACHE` | source document read during the current canonical run |
| `RECORDED_REAL_RUN` | output recorded in an earlier run and replayed by research infrastructure |
| `NOT_APPLICABLE` | stage does not apply |
| `NOT_EXECUTED` | stage skipped or failed |

`REPLAY` is a research/regression label, not an operational fallback. The
replay adapters are explicitly injected by the harness and are not reachable
from the operational API. `HYBRID` remains a historical classification for
ledger decoding; it is not requestable.

The distinction is therefore about provenance, not a second product mode:
`DETERMINISTIC_CACHE` is a current source read, while
`RECORDED_REAL_RUN` is a prior output reused by research replay.
