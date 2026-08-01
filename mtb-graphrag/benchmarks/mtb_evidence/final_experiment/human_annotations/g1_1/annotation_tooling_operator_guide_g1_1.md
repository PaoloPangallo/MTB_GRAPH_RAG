# G1.1 tooling operator guide

Use `run_annotation_batch_g1_1.py` with only `--reviewer`, `--batch-id`, and `--mode`. The launcher resolves packet, response, and audit paths from the runtime manifest and verifies packet SHA-256, unit count, ordered unit-ID digest, reviewer scope, protocol, and recursive blinding before invoking the frozen CLI.

`annotate` starts/resumes the existing CLI. A blank response pauses; existing annotation IDs are skipped. `validate-responses` validates partial responses; use `validate_annotation_responses_g1_1.py --mode complete` to close a batch. `status` reports partial progress. No command uses an LLM or exposes V3 predictions.

Calibration packets are under `calibration/`, marked `pilot_only=true` and `final_evaluable=false`; they are excluded from the final gold.
