from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import validate

from benchmarks.mtb_evidence.final_experiment.harness import (
    GoldClosedError,
    canonical_sha256,
    decide_resume,
    guard_official_mode,
    run_key,
    validate_frozen_inputs,
)


class FinalExperimentHarnessTests(unittest.TestCase):
    def test_hash_ignores_only_its_own_slot(self) -> None:
        payload = {"schema_version": "x/1", "value": 1, "content_sha256": "old"}
        digest = canonical_sha256(payload)
        self.assertEqual(digest, canonical_sha256(payload | {"content_sha256": "new"}))
        self.assertNotEqual(digest, canonical_sha256(payload | {"value": 2}))

    def test_run_key_is_stable_and_replica_sensitive(self) -> None:
        spec = {"system": "S3", "query_id": "Q01", "model": "m", "replica": 1}
        self.assertEqual(run_key(spec), run_key(dict(reversed(list(spec.items())))))
        self.assertNotEqual(run_key(spec), run_key(spec | {"replica": 2}))

    def test_resume_rejects_same_key_with_incompatible_spec(self) -> None:
        spec = {"system": "S3", "query_id": "Q01", "model": "m", "replica": 1}
        result = {"value": "ok", "content_sha256": ""}
        digest = canonical_sha256(result)
        result["content_sha256"] = digest
        complete = {"run_key": run_key(spec), "run_spec": spec, "status": "complete", "result_content_sha256": digest, "result": result}
        self.assertEqual(decide_resume(spec, [complete]), "skip_complete")
        incompatible = complete | {"run_spec": spec | {"model": "other"}}
        with self.assertRaises(ValueError):
            decide_resume(spec, [incompatible])

    def test_resume_rejects_stored_key_spec_mismatch(self) -> None:
        spec = {"system": "S3", "query_id": "Q01", "model": "m", "replica": 1}
        record = {"run_key": "f" * 64, "run_spec": spec, "status": "failed"}
        with self.assertRaises(ValueError):
            decide_resume(spec, [record])

    def test_resume_rejects_complete_record_without_result(self) -> None:
        spec = {"system": "S3", "query_id": "Q01", "model": "m", "replica": 1}
        record = {"run_key": run_key(spec), "run_spec": spec, "status": "complete", "result_content_sha256": "0" * 64}
        with self.assertRaises(ValueError):
            decide_resume(spec, [record])

    def test_official_guard_fails_before_expected_gold_file_is_touched(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marker = root / "must_not_be_read.jsonl"
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "state": "NOT_OPENED_FOR_FINAL_EXPERIMENT",
                "expected_files": [marker.name],
            }), encoding="utf-8")
            with self.assertRaises(GoldClosedError):
                guard_official_mode(manifest)
            self.assertFalse(marker.exists())

    def test_run_plan_rows_and_completed_resume_record_match_schema(self) -> None:
        root = Path(__file__).resolve().parents[2] / "benchmarks" / "mtb_evidence" / "final_experiment"
        schema = json.loads((root / "run_manifest_schema.json").read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in (root / "run_plan_v1.jsonl").read_text(encoding="utf-8").splitlines()]
        for row in rows:
            validate(instance=row, schema=schema)
        result = {"value": "ok", "content_sha256": ""}
        digest = canonical_sha256(result)
        result["content_sha256"] = digest
        completed = dict(rows[0])
        completed.update({"status": "complete", "result_content_sha256": digest, "result": result})
        validate(instance=completed, schema=schema)

    def test_every_frozen_input_validates(self) -> None:
        root = (
            Path(__file__).resolve().parents[2]
            / "benchmarks" / "mtb_evidence" / "final_experiment"
        )
        counts = validate_frozen_inputs(root)
        self.assertEqual(counts["jsonl_rows"], 238)
        self.assertGreaterEqual(counts["json_files"], 9)
        self.assertEqual(counts["text_files"], 5)

if __name__ == "__main__":
    unittest.main()
