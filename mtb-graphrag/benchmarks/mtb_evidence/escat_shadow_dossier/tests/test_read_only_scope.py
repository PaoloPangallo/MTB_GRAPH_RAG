from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import unittest


class ReadOnlyScopeTests(unittest.TestCase):
    def test_pilot_drafts_are_byte_identical_to_approved_ruleset_commit(self) -> None:
        repo = Path(__file__).resolve().parents[5]
        relative = "mtb-graphrag/benchmarks/mtb_evidence/escat_curation_mvp/data/pilot_drafts.jsonl"
        current = (repo / relative).read_bytes()
        approved = subprocess.check_output(["git", "show", f"5173bb8:{relative}"], cwd=repo)
        self.assertEqual(hashlib.sha256(current).hexdigest(), hashlib.sha256(approved).hexdigest())

    def test_only_additive_dossier_keys_are_defined(self) -> None:
        source = Path(__file__).resolve().parents[1] / "adapter.py"
        text = source.read_text(encoding="utf-8")
        self.assertIn("clinical_actionability", text)
        self.assertIn("claim_relevance", text)
        self.assertIn("document_support", text)
        self.assertNotIn("bucket =", text)
        self.assertNotIn("score =", text)
        self.assertNotIn("gate_trace =", text)


if __name__ == "__main__":
    unittest.main()
