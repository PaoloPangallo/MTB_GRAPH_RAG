# G1.1 annotation campaign operator guide

The frozen CLI supports only the following arguments (verified from `annotate_g1_1.py`):

```powershell
python -m benchmarks.mtb_evidence.evaluation.scripts.annotate_g1_1 --packet <packet.jsonl> --reviewer reviewer_A|reviewer_B|adjudicator_C --output <responses.jsonl> --audit-log <audit.jsonl>
python -m benchmarks.mtb_evidence.evaluation.scripts.annotate_g1_1 --packet <packet.jsonl> --reviewer reviewer_A|reviewer_B|adjudicator_C --output <responses.jsonl> --audit-log <audit.jsonl> --validate-only
```

There are no hidden `start`, `resume`, `progress`, `close`, or `export` CLI flags. Operational resume is achieved by re-running the same command: completed `annotation_unit_id` values in the output are skipped, and a blank response pauses. Use one batch file at a time; never pass the other reviewer packet, the sealed mapping, excluded-unit files, or V3 outputs.

Reviewer A uses only `reviewer_A/batches/`; Reviewer B uses only `reviewer_B/batches/`. Save responses and audit logs under the reviewer-specific directories. A batch is completed only after schema/checksum/duplicate/missing validation passes. Do not expose bucket frequencies or agreement during independent review.

Calibration uses only the four pilot cases and is frozen before final batches. It never enters the 3,256 units, agreement, or scoring.
