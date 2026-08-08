# Safety regression

The selector remains a retrieval component only. Gemma remains restricted to `QUOTE` or `ABSTAIN`; deterministic validation remains the authority for quote acceptance. Narrator output remains presentation-only and is verified after dossier construction.

The new LIVE path does not change negative-source polarity, canonical gates, or historical replay artifacts.

## Migrated architecture invariant

`RuntimeSelectorBoundaryTest` replaces the historical `SeparationFromRuntimeTest.test_no_runtime_module_imports_the_selector` assertion.

- `OLD_INVARIANT`: the canonical runtime must not import or mention the experimental SourceUnit Selector.
- `NEW_INVARIANT`: LIVE may and must use the deterministic selector; REPLAY must use frozen bundle routing and must not call the LIVE selector.
- `WHY_CHANGED`: the approved architecture deliberately promotes the evaluated selector only into LIVE execution while preserving exact replay semantics.

The replacement tests mode-specific behavior, frozen-bundle routing, cache-miss acquisition, network isolation, and the absence of frozen source-unit IDs in LIVE. It does not use a lexical blacklist and does not weaken the old safety objective; it refines it to the LIVE/REPLAY boundary.
