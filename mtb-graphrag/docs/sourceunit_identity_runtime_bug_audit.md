# SourceUnit occurrence identity correctness audit

The former content-derived `source_unit_id` could collide when identical text
occurred at distinct positions in one canonical document.  The frozen pre-fix
evaluation material contained 27 parser-level collision groups (54 rows).

`AuthorizedDocumentCache.source_units_for_record` now finalizes IDs after each
canonical parser has returned its complete ordered list and before
`live_resolution.load_source_units` constructs its ID-indexed map:

`SU-<sha256(document_id, final_ordinal, canonical_sourceunit_content)[:24]>`.

`content_hash` remains exactly parser-produced; only `source_unit_id` changes.
The fix was made before RQ3 gold annotation or predictions.  It changes no
document acquisition, sample membership, text, segmentation, order, type,
section, selector formula, Reader prompt, support semantics, or dossier schema.

Offline acceptance replays all 27 historical collision groups and all 215
available frozen documents.  The selector uses `source_unit_id` solely as a
deterministic tie-break after equal scores; this correctness fix can therefore
change rank only for exact score ties.  No weights or selector behavior were
tuned or rerun to choose this fix.
