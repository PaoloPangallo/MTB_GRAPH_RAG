# Dataset Supplement S01

`SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01` preserves, byte for byte, the
pre-final temporary artifact containing the complete text of the 1,697
SourceUnits in `SOURCEUNIT_SELECTOR_INDEPENDENT_20`.

This is a `PRE_FINAL_DATASET_SUPPLEMENT`, not a new dataset and not a
reconstruction or re-curation. The raw JSONL was copied without parsing,
sorting, newline normalization, re-encoding, or re-serialization. Its exact
SHA-256 is `83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99`
and its exact size is 731,754 bytes.

The package is intentionally **not frozen**. Its review state is
`READY_FOR_HUMAN_REVIEW`. Freezing requires a separate explicit human-review
action.

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
