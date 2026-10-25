# Annotation protocol

Annotation was performed from the temporary fresh-parser review view and the GCA fields only. The selector ranking, BM25 ranking, pilot bundle IDs, expected quotes, Gemma output, validator output and canonical status were not shown.

Every parsed SourceUnit receives one label. The primary retrieval gold is `DIRECTLY_RELEVANT`; the secondary gold is `DIRECTLY_RELEVANT + PARTIALLY_RELEVANT`. Unmatched units are retained as `CONTEXT_ONLY` or `NOT_RELEVANT` rather than silently discarded.

The annotation file was written and SHA-256 hashed before the selector phase. `gold_annotation_manifest.json` records the freeze timestamp and all blinding checks. The annotation is a first independent protocol pass, not a double-adjudicated clinical gold; this remains a limitation.
