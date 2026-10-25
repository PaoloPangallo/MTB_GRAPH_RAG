from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
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
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]) as td:
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
        repo = root.parents[2]
        systems = json.loads((root / "systems_v1.json").read_text(encoding="utf-8"))
        prefix = subprocess.check_output(
            ["git", "rev-parse", "--show-prefix"], cwd=repo, text=True
        ).strip()
        with tempfile.TemporaryDirectory(dir=repo) as td:
            frozen_repo = Path(td)
            frozen_root = frozen_repo / "benchmarks" / "mtb_evidence" / "final_experiment"
            shutil.copytree(root, frozen_root)
            for name, expected in systems["source_manifest"].items():
                blob = subprocess.check_output(
                    ["git", "show", f"{systems['base_commit']}:{prefix}{name}"], cwd=repo
                )
                # Git stores LF; the seal may hash Windows checkout CRLF bytes.
                lf = blob.replace(b"\r\n", b"\n")
                candidates = (blob, lf, lf.replace(b"\n", b"\r\n"))
                matching = next(
                    (data for data in candidates if hashlib.sha256(data).hexdigest() == expected),
                    None,
                )
                self.assertIsNotNone(matching, f"sealed Git source unavailable: {name}")
                target = frozen_repo / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(matching)
            counts = validate_frozen_inputs(frozen_root)
            self.assertEqual(counts["jsonl_rows"], 238)
            self.assertGreaterEqual(counts["json_files"], 9)
            self.assertEqual(counts["text_files"], 5)

            target = frozen_repo / next(iter(systems["source_manifest"]))
            original = target.read_bytes()
            target.write_bytes(original + b"\n# tampered\n")
            with self.assertRaisesRegex(ValueError, "runtime source bundle digest mismatch"):
                validate_frozen_inputs(frozen_root)
            target.unlink()
            with self.assertRaisesRegex(ValueError, "runtime source missing"):
                validate_frozen_inputs(frozen_root)
            target.write_bytes(original)

            # The current checkout is acceptable only when its exact bytes still match.
            current_matches = all(
                (repo / name).is_file()
                and hashlib.sha256((repo / name).read_bytes()).hexdigest() == digest
                for name, digest in systems["source_manifest"].items()
            )
            if current_matches:
                self.assertEqual(validate_frozen_inputs(root), counts)
            else:
                with self.assertRaisesRegex(ValueError, "runtime source (bundle digest mismatch|missing)"):
                    validate_frozen_inputs(root)

if __name__ == "__main__":
    unittest.main()
