# Architectural implications

The experiment supports a clean boundary: `DocumentParser -> SourceUnitSelectionInput -> deterministic selector -> top-K SourceUnits`. The selector can run after live API acquisition without changing the GCA or canonical state.

The selector should remain a routing component. Support direction, quote validity, gates, dossier status and narrative claims remain downstream responsibilities. Replay can continue to use frozen bundles while LIVE can be evaluated with the selector once the downstream gate is closed.

No orchestrator, paper selection, DocumentRuntime, GCA runtime, cache-miss behavior, enricher, quote validator, canonical gate or historical artifact was changed.
