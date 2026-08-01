from __future__ import annotations

import csv
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO_14 = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
REPO_15 = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_5_provenance_pilot"
REPORT = ROOT / "docs/provenance_repair/pilot_claims_before_after.csv"


def rows(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class ProvenanceRepairPilotArtifactsTest(unittest.TestCase):
    def test_overlay_preserves_claim_semantics(self) -> None:
        before = {row["claim_id"]: row for row in rows(REPO_14 / "evidence_claims.jsonl")}
        after = {row["claim_id"]: row for row in rows(REPO_15 / "evidence_claims.jsonl")}
        self.assertEqual(set(before), set(after))
        semantic_fields = {
            key
            for key in before[next(iter(before))]
            if key != "provenance_repair"
        }
        for claim_id in before:
            self.assertEqual(
                {key: before[claim_id].get(key) for key in semantic_fields},
                {key: after[claim_id].get(key) for key in semantic_fields},
                claim_id,
            )

    def test_only_pilot_claims_receive_repair_metadata(self) -> None:
        manifest = json.loads((REPO_15 / "provenance_repair_manifest.json").read_text(encoding="utf-8"))
        pilot_ids = set(manifest["pilot_claim_ids"])
        after = rows(REPO_15 / "evidence_claims.jsonl")
        annotated = {row["claim_id"] for row in after if "provenance_repair" in row}
        self.assertEqual(annotated, pilot_ids)
        self.assertFalse(manifest["operational_retriever_bound"])

    def test_bucket_and_score_parity_columns_are_identity_mappings(self) -> None:
        with REPORT.open(encoding="utf-8", newline="") as handle:
            report_rows = list(csv.DictReader(handle))
        self.assertEqual(len(report_rows), 18)
        for row in report_rows:
            for observation in filter(None, row["bucket_score_before_after"].split("|")):
                before, after = observation.split("=")
                self.assertEqual(before, after, row["claim_id"])

    def test_parent_only_rows_do_not_receive_claim_source_ids(self) -> None:
        after = rows(REPO_15 / "evidence_claims.jsonl")
        for row in after:
            repair = row.get("provenance_repair")
            if not isinstance(repair, dict):
                continue
            if repair["status"] in {"PARENT_PUBLICATION_AVAILABLE", "AMBIGUOUS_PARENT_PROVENANCE"}:
                self.assertEqual(row.get("source_unit_ids"), [])
                self.assertEqual(row.get("locators"), [])


if __name__ == "__main__":
    unittest.main()
