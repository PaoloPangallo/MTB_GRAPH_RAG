"""
Test di integrazione per gli endpoint V3 (/api/v1/v3).
"""

from __future__ import annotations

import unittest
from fastapi.testclient import TestClient

from backend.api.main import app


class TestV3API(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_get_v3_metadata(self) -> None:
        response = self.client.get("/api/v1/v3/metadata")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["backend_identifier"], "qualified_claim_v3")
        self.assertEqual(data["corpus_version"], "qualified_claim_repository/1.4")
        self.assertEqual(data["gate_version"], "qualified_claim_structural_gate/1.3")
        self.assertEqual(data["service_status"], "healthy")

    def test_retrieve_v3_evidence_real(self) -> None:
        payload = {
            "domain": "therapeutic",
            "biomarker": "EGFR L858R",
            "disease": "Non-Small Cell Lung Cancer",
            "intervention": "Osimertinib",
        }
        response = self.client.post("/api/v1/v3/retrieve", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("summary", data)
        self.assertIn("buckets", data)
        self.assertIn("metadata", data)

        summary = data["summary"]
        self.assertGreater(summary["total"], 0)
        self.assertIn("primary", data["buckets"])
        self.assertIn("warning", data["buckets"])
        self.assertIn("audit", data["buckets"])
        self.assertIn("rejected", data["buckets"])

        metadata = data["metadata"]
        self.assertEqual(metadata["corpus_version"], "qualified_claim_repository/1.4")
        self.assertEqual(metadata["gate_version"], "qualified_claim_structural_gate/1.3")

    def test_render_v3_narrative_real(self) -> None:
        # 1. Retrieval
        ret_payload = {
            "domain": "therapeutic",
            "biomarker": "EGFR L858R",
            "disease": "Non-Small Cell Lung Cancer",
        }
        ret_res = self.client.post("/api/v1/v3/retrieve", json=ret_payload)
        self.assertEqual(ret_res.status_code, 200)
        ret_data = ret_res.json()

        primary_claims = ret_data["buckets"]["primary"]
        self.assertGreater(len(primary_claims), 0)

        # 2. Render
        render_payload = {
            "query_id": ret_data["query_id"],
            "claims": primary_claims,
        }
        render_res = self.client.post("/api/v1/v3/render", json=render_payload)
        self.assertEqual(render_res.status_code, 200)
        render_data = render_res.json()

        self.assertIn("rendered_report", render_data)
        self.assertIn("claim_ids_used", render_data)
        self.assertIn("cited_pmids", render_data)
        self.assertIn("disclaimer", render_data)


if __name__ == "__main__":
    unittest.main()
