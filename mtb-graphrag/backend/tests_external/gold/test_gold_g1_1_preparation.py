import json
import subprocess
import sys
import tempfile
import shutil
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEST = ROOT / "benchmarks/mtb_evidence/final_experiment/gold_g1_1"
SCRIPT = "benchmarks.mtb_evidence.evaluation.scripts.annotate_g1_1"


class GoldG11PreparationTests(unittest.TestCase):
    def test_active_universe_and_exclusion_counts(self):
        report = json.loads((DEST / "candidate_universe_audit_g1_1.json").read_text(encoding="utf-8"))
        self.assertTrue(report["active_claim_universe_complete"])
        self.assertEqual(report["active_corpus_claim_count"] * 22, report["active_annotation_unit_count"])
        self.assertEqual(report["counts"], {"deprecated": 88, "provenance_container": 3234, "unresolved": 132, "unsupported": 132})

    def test_packet_sets_and_order_differ(self):
        a = [json.loads(x)["annotation_unit_id"] for x in (DEST / "annotation_packet_A_g1_1.jsonl").read_text(encoding="utf-8").splitlines()]
        b = [json.loads(x)["annotation_unit_id"] for x in (DEST / "annotation_packet_B_g1_1.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(a), 3256)
        self.assertEqual(set(a), set(b))
        self.assertNotEqual(a, b)
        self.assertEqual(len(a), len(set(a)))

    def test_blinding_report(self):
        report = json.loads((DEST / "blinding_validation_report_g1_1.json").read_text(encoding="utf-8"))
        self.assertEqual(report["blinding_leak_count"], 0)
        self.assertTrue(report["packet_A"]["passed"])
        self.assertTrue(report["packet_B"]["passed"])

    def test_cli_schema_and_pause_resume(self):
        packet = DEST / "annotation_packet_A_g1_1.jsonl"
        output = Path(r"C:\tmp\g1_1_test_annotations.jsonl")
        audit = Path(r"C:\tmp\g1_1_test_audit.jsonl")
        output.unlink(missing_ok=True); audit.unlink(missing_ok=True)
        try:
            command = [sys.executable, "-m", SCRIPT, "--packet", str(packet), "--reviewer", "reviewer_A", "--output", str(output), "--audit-log", str(audit)]
            paused = subprocess.run(command, input="\n", text=True, capture_output=True, check=False, timeout=10)
            resumed = subprocess.run(command, input="\n", text=True, capture_output=True, check=False, timeout=10)
            self.assertEqual(paused.returncode, 0)
            self.assertEqual(resumed.returncode, 0)
            self.assertFalse(output.exists())
            self.assertFalse(audit.exists())
        finally:
            output.unlink(missing_ok=True); audit.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
