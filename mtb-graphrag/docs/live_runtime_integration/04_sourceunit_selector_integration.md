# LIVE SourceUnit selector

LIVE passes parsed SourceUnits and the GCA-derived candidate to the existing selector. The adapter does not read `available_bundles[*].source_unit_ids`; in LIVE those fields are empty by construction.

The selected paper records contain selector version, input/ranking/selected-ID hashes, matched features, scores, and selected IDs. Runtime K is `5`. No new threshold or rejection mode was introduced.
