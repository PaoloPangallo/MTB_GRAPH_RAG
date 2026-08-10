# Dataset Supplement S01

`SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01` preserves, byte for byte, the
pre-final temporary artifact containing the complete text of the 1,697
SourceUnits in `SOURCEUNIT_SELECTOR_INDEPENDENT_20`.

This is a `PRE_FINAL_DATASET_SUPPLEMENT`, not a new dataset and not a
reconstruction or re-curation. The raw JSONL was copied without parsing,
sorting, newline normalization, re-encoding, or re-serialization. Its exact
SHA-256 is `83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99`
and its exact size is 731,754 bytes.

The package is **frozen**. Paolo Pangallo accepted the preservation review on
2026-08-10. The freeze timestamp is `2026-08-10T13:13:06.3467147Z` and the
scope is `DATASET_SUPPLEMENT_S01_FINAL_FREEZE`.

Every future final-evaluation artifact that uses this SourceUnit text must
record the runtime commit, parent protocol SHA, A01 SHA, S01 ID, raw-source
SHA, and frozen S01 package SHA. No protected S01 material may be changed
silently; such a change requires S02 or an explicit protocol-level change.

## Files

- `sourceunits_1697.jsonl`: preserved raw artifact.
- `supplement_manifest.json`: identity and structural contract.
- `provenance.json`: source, generator, parser, and per-document payload provenance.
- `validation_report.json`: preservation, structure, and join results.
- `hash_supplement.py`: exact-byte package digest builder.
- `check_supplement.py`: fail-closed read-only consistency checker.
- `supplement_hash.json`: generated package seal; excluded from its own digest.

## Verification

From the repository root:

```text
python evaluation/final_protocol/supplements/S01/check_supplement.py
```

To regenerate only the seal after an explicitly authorized metadata change:

```text
python evaluation/final_protocol/supplements/S01/hash_supplement.py --write
```

Neither command executes the runtime, selector, models, or network operations.
