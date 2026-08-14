# LIVE / REPLAY provenance separation

The operational runtime is single-path: `RunStore.start()` ->
`DocumentRuntime.open()` -> modern orchestrator. A caller does not select a
product mode between LIVE and REPLAY, and an operational failure never falls
back silently to recorded output.

The LIVE selector is used by the canonical runtime after document resolution
and SourceUnit parsing. The replay provider is an explicit research/regression
adapter only; it uses frozen recorded artifacts, does not access the network,
and does not call the LIVE selector. The two paths are therefore separate
provenance contexts, not two user-facing operational modes.
