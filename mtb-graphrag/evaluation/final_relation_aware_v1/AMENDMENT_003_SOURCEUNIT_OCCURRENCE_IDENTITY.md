# Amendment 003 — SourceUnit occurrence identity

A pre-prediction correctness defect was discovered: content-derived SourceUnit
IDs were not unique for repeated identical text at different canonical document
positions.  Twenty-seven collision groups were observed in the pre-fix frozen
material.  The runtime now finalizes occurrence-aware IDs from document ID,
final parser-list ordinal, and canonical SourceUnit content, while preserving
the parser-generated `content_hash`.

The sealed GCA samples, sampling weights, acquisition targets, frozen cache,
document manifest, payload hashes, and source freeze are unchanged.  No network
access, model/provider call, selector run, Reader run, relation-support
prediction, or data-dependent parameter choice was used to select the fix.

All SourceUnit-derived artifacts are invalidated and rebuilt from the same
frozen documents.  Because the selector uses `source_unit_id` for deterministic
tie-breaking, only exact-score ties may receive a different deterministic order;
the selector formula and its weights are unchanged.
