from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.v3_presentation import present_retrieval_outcome
from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline


def _query(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "query_id": "PRODUCT-TEST-01",
        "claim_domain": "therapeutic",
        "biomarker": "FGFR2::v Fusion OR FGFR2::? Fusion",
        "disease": "Intrahepatic Cholangiocarcinoma",
        "interventions": ["derazantinib"],
        "direction": "sensitivity",
        "policy_mode": "strict_verified",
        "include_warning": True,
        "include_audit": True,
        "include_rejected": True,
        "result_limit": 20,
    }
    payload.update(overrides)
    return payload


class V3ProductPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = EvidenceRetrievalPipeline.from_config(
            {
                "retrieval_backend": "qualified_claim_v3",
                "qualified_claim_policy_mode": "strict_verified",
            }
        )

    def run_query(self, **overrides: object):
        return self.pipeline.run(
            _query(**overrides), retrieval_backend="qualified_claim_v3"
        )

    def test_direct_match_separates_claims_from_technical_records(self) -> None:
        response = present_retrieval_outcome(self.run_query())
        self.assertGreaterEqual(response["summary"]["primary"], 1)
        self.assertEqual(response["summary"]["total_records"], 311)
        self.assertEqual(
            len(response["technical_records"]["provenance_containers"]), 147
        )
        self.assertTrue(
            all(item["candidate_kind"] == "evidence_claim" for item in response["evidence"]["primary"])
        )

    def test_resistance_direction_is_preserved(self) -> None:
        response = present_retrieval_outcome(
            self.run_query(
                query_id="PRODUCT-TEST-02",
                biomarker="ALK G1202R AND v::ALK Fusion",
                disease="Non-Small Cell Lung Cancer",
                interventions=["alectinib hydrochloride"],
                direction="resistance",
            )
        )
        self.assertEqual(response["case_context"]["direction"], "resistance")
        self.assertEqual(response["summary"]["primary"], 1)

    def test_no_direct_match_is_explicit_abstention(self) -> None:
        response = present_retrieval_outcome(
            self.run_query(
                query_id="PRODUCT-TEST-04",
                biomarker="RMI2",
                disease="Non-Small Cell Lung Cancer",
                interventions=[],
                direction="",
            )
        )
        self.assertEqual(response["summary"]["primary"], 0)
        self.assertTrue(response["abstention"])
        self.assertGreater(response["summary"]["technical_records"], 0)

    def test_claim_fields_do_not_invent_subject_relation_or_object(self) -> None:
        response = present_retrieval_outcome(self.run_query())
        primary = response["evidence"]["primary"][0]
        self.assertIsNone(primary["subject"])
        self.assertIsNone(primary["relation"])
        self.assertIsNone(primary["object"])
        self.assertFalse(primary["structured_tuple_complete"])
        self.assertTrue(primary["gate_trace"])
        self.assertIn("code", primary["reason_codes"][0])
        self.assertIn("human_message", primary["reason_codes"][0])


class V3ProductEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_endpoint_returns_structured_v3_without_agentic_report(self) -> None:
        response = self.client.post("/api/v1/v3/retrieve", json=_query())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["metadata"]["backend_name"], "qualified_claim_v3")
        self.assertNotIn("report", payload)
        self.assertEqual(payload["summary"]["total_records"], 311)

    def test_endpoint_does_not_call_agentic_planner_or_llm(self) -> None:
        with patch("backend.api.routes.run_pipeline", side_effect=AssertionError("planner called")):
            response = self.client.post("/api/v1/v3/retrieve", json=_query())
        self.assertEqual(response.status_code, 200)

    def test_rmi2_endpoint_exposes_abstention(self) -> None:
        response = self.client.post(
            "/api/v1/v3/retrieve",
            json=_query(
                query_id="PRODUCT-TEST-04",
                biomarker="RMI2",
                disease="Non-Small Cell Lung Cancer",
                interventions=[],
                direction="",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["abstention"])


if __name__ == "__main__":
    unittest.main()
