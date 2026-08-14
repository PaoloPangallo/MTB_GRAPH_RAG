# Runtime policy

The evaluated system exposes one canonical operational path:

```text
RunStore.start()
  -> DocumentRuntime.open()
  -> cache-first document resolution
  -> deterministic parsing and LIVE SourceUnit selection
  -> enrichment, validation, gates and dossier
```

The research/regression harness may explicitly inject replay adapters:

```text
frozen recorded parser/document/bundle artifacts
  -> replay providers
  -> no network and no LIVE selector
```

This replay path is not user-selectable and is not a silent fallback from the
operational runtime. A cache read during the canonical path is a current
`DETERMINISTIC_CACHE` source read, not a replayed model output.
