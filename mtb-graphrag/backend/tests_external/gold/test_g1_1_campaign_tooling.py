import json
import hashlib
import unittest
from pathlib import Path

from benchmarks.mtb_evidence.evaluation.scripts import campaign_tooling_g1_1 as tooling


class G11CampaignToolingTests(unittest.TestCase):
    def test_manifest_binds_reviewer_and_batch(self):
        manifest = tooling.load_runtime_manifest(tooling.DEFAULT_RUNTIME_MANIFEST)
        batch = tooling.resolve_batch(manifest, "reviewer_A", "batch_001")
        self.assertEqual(batch["reviewer_id"], "reviewer_A")
        with self.assertRaises(tooling.ToolingError) as ctx:
            tooling.resolve_batch(manifest, "reviewer_A", "batch_001", reviewer_root="reviewer_B")
        self.assertEqual(ctx.exception.failure_class, "REVIEWER_BATCH_MISMATCH")

    def test_packet_integrity_detects_unit_set_change(self):
        manifest = tooling.load_runtime_manifest(tooling.DEFAULT_RUNTIME_MANIFEST)
        batch = tooling.resolve_batch(manifest, "reviewer_A", "batch_001")
        rows = tooling.read_jsonl(Path(tooling.REPO_ROOT) / batch["packet_path"])
        rows[-1]["annotation_unit_id"] = "unexpected"
        with self.assertRaises(tooling.ToolingError) as ctx:
            tooling.verify_packet(batch, rows=rows)
        self.assertEqual(ctx.exception.failure_class, "PACKET_UNIT_SET_MISMATCH")

    def test_partial_response_validation_and_complete_missing(self):
        manifest = tooling.load_runtime_manifest(tooling.DEFAULT_RUNTIME_MANIFEST)
        batch = tooling.resolve_batch(manifest, "reviewer_A", "batch_001")
        rows = tooling.read_jsonl(Path(tooling.REPO_ROOT) / batch["packet_path"])
        response = tooling.response_fixture(rows[0]["annotation_unit_id"], "reviewer_A")
        output = tooling.REPO_ROOT / "g11_test_responses.jsonl"
        audit = tooling.REPO_ROOT / "g11_test_audit.jsonl"
        try:
            tooling.write_jsonl(output, [response])
            tooling.write_jsonl(audit, [{"event": "annotation_saved", "annotation_unit_id": response["annotation_unit_id"], "reviewer_id": "reviewer_A"}])
            partial = tooling.validate_responses(batch, output, audit, mode="partial")
            self.assertTrue(partial["passed"])
            complete = tooling.validate_responses(batch, output, audit, mode="complete")
            self.assertFalse(complete["passed"])
            self.assertEqual(complete["missing_units"], 149)
        finally:
            output.unlink(missing_ok=True); audit.unlink(missing_ok=True)

    def test_forbidden_prediction_field_fails_response_validation(self):
        manifest = tooling.load_runtime_manifest(tooling.DEFAULT_RUNTIME_MANIFEST)
        batch = tooling.resolve_batch(manifest, "reviewer_A", "batch_001")
        output = tooling.REPO_ROOT / "g11_test_responses.jsonl"
        audit = tooling.REPO_ROOT / "g11_test_audit.jsonl"
        try:
            response = tooling.response_fixture("not-used", "reviewer_A")
            response["predicted_bucket"] = "primary"
            tooling.write_jsonl(output, [response])
            tooling.write_jsonl(audit, [])
            result = tooling.validate_responses(batch, output, audit, mode="partial")
            self.assertFalse(result["passed"])
            self.assertGreater(result["schema_errors"], 0)
        finally:
            output.unlink(missing_ok=True); audit.unlink(missing_ok=True)

    def _batch(self):
        manifest = tooling.load_runtime_manifest(tooling.DEFAULT_RUNTIME_MANIFEST)
        return manifest, tooling.resolve_batch(manifest, "reviewer_A", "batch_001")

    def test_reviewer_b_correct_batch_passes(self):
        manifest = tooling.load_runtime_manifest(tooling.DEFAULT_RUNTIME_MANIFEST)
        batch = tooling.resolve_batch(manifest, "reviewer_B", "batch_001")
        self.assertEqual(batch["reviewer_id"], "reviewer_B")

    def test_packet_checksum_mismatch(self):
        _, batch = self._batch(); altered = dict(batch); altered["packet_sha256"] = "0" * 64
        with self.assertRaises(tooling.ToolingError) as ctx: tooling.verify_packet(altered)
        self.assertEqual(ctx.exception.failure_class, "PACKET_CHECKSUM_MISMATCH")

    def test_packet_unit_count_mismatch(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"])[:-1]
        with self.assertRaises(tooling.ToolingError) as ctx: tooling.verify_packet(batch, rows=rows)
        self.assertEqual(ctx.exception.failure_class, "PACKET_UNIT_COUNT_MISMATCH")

    def _write_response_case(self, rows, responses, audit):
        output = tooling.REPO_ROOT / "g11_test_responses.jsonl"; audit_path = tooling.REPO_ROOT / "g11_test_audit.jsonl"
        tooling.write_jsonl(output, responses); tooling.write_jsonl(audit_path, audit)
        return output, audit_path

    def test_wrong_response_reviewer_fails(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); r = tooling.response_fixture(rows[0]["annotation_unit_id"], "reviewer_B")
        output, audit = self._write_response_case(rows, [r], []); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_extra_response_unit_fails(self):
        _, batch = self._batch(); r = tooling.response_fixture("G1.1-EXTRA", "reviewer_A")
        output, audit = self._write_response_case([], [r], []); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_duplicate_response_fails(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); r = tooling.response_fixture(rows[0]["annotation_unit_id"], "reviewer_A")
        output, audit = self._write_response_case(rows, [r, dict(r)], []); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_incomplete_schema_fails(self):
        _, batch = self._batch(); output, audit = self._write_response_case([], [{"annotation_unit_id": "x"}], []); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_evaluable_false_bucket_fails(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); r = tooling.response_fixture(rows[0]["annotation_unit_id"], "reviewer_A"); r["evaluable"] = False; r["bucket"] = "audit"
        output, audit = self._write_response_case(rows, [r], [{"event":"annotation_saved","annotation_unit_id":r["annotation_unit_id"],"reviewer_id":"reviewer_A"}]); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_source_flag_incoherence_fails(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); r = tooling.response_fixture(rows[0]["annotation_unit_id"], "reviewer_A"); r["source_checked"] = True; r["source_available"] = False
        output, audit = self._write_response_case(rows, [r], [{"event":"annotation_saved","annotation_unit_id":r["annotation_unit_id"],"reviewer_id":"reviewer_A"}]); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_complete_batch_passes(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); responses = [tooling.response_fixture(row["annotation_unit_id"], "reviewer_A") for row in rows]; audit = [{"event":"annotation_saved","annotation_unit_id":r["annotation_unit_id"],"reviewer_id":"reviewer_A"} for r in responses]
        output, audit_path = self._write_response_case(rows, responses, audit); result = tooling.validate_responses(batch, output, audit_path, mode="complete"); self.assertTrue(result["passed"]); output.unlink(); audit_path.unlink()

    def test_resume_existing_response_is_partial_valid(self):
        self.test_partial_response_validation_and_complete_missing()

    def test_corrupted_response_fails(self):
        _, batch = self._batch(); output, audit = self._write_response_case([], [{"annotation_unit_id":"bad","reviewer_id":"reviewer_A","annotation_protocol_version":"G1.1"}], []); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_manifest_path_escape_fails(self):
        _, batch = self._batch(); altered = dict(batch); altered["packet_path"] = "../../outside.jsonl"
        with self.assertRaises(tooling.ToolingError) as ctx: tooling.verify_packet(altered)
        self.assertIn(ctx.exception.failure_class, {"MANIFEST_PATH_ESCAPE", "MANIFEST_PATH_SCOPE_MISMATCH"})

    def test_nested_blinding_field_fails(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); rows[0]["query_structured"]["score"] = 1
        with self.assertRaises(tooling.ToolingError) as ctx: tooling.verify_packet(batch, rows=rows)
        self.assertEqual(ctx.exception.failure_class, "BLINDING_FAILURE")

    def test_response_types_and_nested_fields_fail(self):
        _, batch = self._batch(); rows = tooling.read_jsonl(tooling.REPO_ROOT / batch["packet_path"]); r = tooling.response_fixture(rows[0]["annotation_unit_id"], "reviewer_A"); r["evaluable"] = "false"; r["rationale_codes"] = [{"score": 1}]
        output, audit = self._write_response_case(rows, [r], [{"event":"annotation_saved","annotation_unit_id":r["annotation_unit_id"],"reviewer_id":"reviewer_A"}]); result = tooling.validate_responses(batch, output, audit); self.assertFalse(result["passed"]); output.unlink(); audit.unlink()

    def test_calibration_packet_blinding_leak_zero(self):
        for reviewer in ("A", "B"):
            packet = tooling.build_calibration_packet(tooling.PILOT_GOLD_PATH, reviewer, seed=20260801)
            self.assertEqual(sum(bool(tooling.FORBIDDEN_BLIND_FIELDS & set(row)) for row in packet), 0)

    def test_calibration_packet_is_blind_and_separate(self):
        packet = tooling.build_calibration_packet(tooling.PILOT_GOLD_PATH, "A", seed=20260801)
        self.assertTrue(packet)
        self.assertTrue(all(row["pilot_only"] and not row["final_evaluable"] for row in packet))
        forbidden = tooling.FORBIDDEN_BLIND_FIELDS
        self.assertFalse(any(forbidden & set(row) for row in packet))
        self.assertTrue(all(row["annotation_unit_id"].startswith("CAL-G1.1-") for row in packet))
        serialized = json.dumps(packet, ensure_ascii=False).lower()
        self.assertNotIn("gold_rationale", serialized)
        self.assertNotIn("documentary_status", serialized)
        self.assertNotIn("expected_therapies", serialized)
        self.assertNotIn("review_status", serialized)


if __name__ == "__main__":
    unittest.main()
