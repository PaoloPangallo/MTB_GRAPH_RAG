from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.api.v3_presentation import _claim_record, present_retrieval_outcome
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
    def test_pipeline_projection_preserves_native_counts_and_order(self) -> None:
        response = present_retrieval_outcome(self.run_query())
        pipeline = response['pipeline']
        stage_ids = [stage['id'] for stage in pipeline['stages']]

        self.assertEqual(stage_ids[0], 'clinical_input')
        self.assertEqual(stage_ids[1], 'case_normalization')
        self.assertEqual(
            pipeline['stages'][2]['details']['repository_version'],
            'qualified_claim_repository/1.4',
        )
        self.assertEqual(pipeline['stages'][2]['output_count'], 311)
        self.assertEqual(
            pipeline['stages'][4]['details']['buckets']['primary'],
            response['summary']['primary'],
        )
        self.assertEqual(
            sum(item['count'] for item in pipeline['provenance_summary'].values()),
            response['summary']['claim_records'],
        )
        self.assertEqual(pipeline['gate_summary'][0]['gate'], 'active_claim_loading')
        self.assertEqual(pipeline['gate_summary'][1]['gate'], 'claim_status_gate')

    def test_pipeline_stage_and_trace_details_are_real(self) -> None:
        response = present_retrieval_outcome(self.run_query())
        provenance_stage = response['pipeline']['stages'][5]
        self.assertEqual(
            provenance_stage['details']['status_counts']['PARENT_ONLY'],
            response['pipeline']['provenance_summary']['PARENT_ONLY']['count'],
        )
        trace = response['evidence']['primary'][0]['gate_trace']
        biomarker = next(item for item in trace if item['gate'] == 'biomarker')
        self.assertEqual(biomarker['case_value'], 'FGFR2::v Fusion OR FGFR2::? Fusion')
        self.assertTrue(biomarker['claim_value'])

    def test_pipeline_exposes_native_score_without_coercion(self) -> None:
        response = present_retrieval_outcome(self.run_query())
        primary = response['evidence']['primary'][0]
        self.assertEqual(primary['score']['total'], 108.0)
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
        self.assertEqual(response["evidence"]["primary"], [])
        self.assertTrue(all(item["bucket"] == "rejected" for item in response["evidence"]["rejected"]))
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

    def test_claim_contract_separates_source_claim_decision_and_case_comparison(self) -> None:
        response = present_retrieval_outcome(
            self.run_query(
                query_id="AUDIT-PILOT-EGFR-NO-INTERVENTION",
                gene="EGFR",
                alteration="L858R",
                biomarker="",
                disease="Lung Adenocarcinoma",
                interventions=[],
                direction="",
            )
        )
        claim = next(
            item
            for bucket in response["evidence"].values()
            for item in bucket
            if item["claim_id"] == "CLM-e565f65d73cb1d4aa67b"
        )
        self.assertIsNone(claim["claim"]["claim_text"])
        self.assertFalse(claim["claim"]["structured_tuple_complete"])
        self.assertEqual(claim["claim"]["direction"], "sensitivity")
        self.assertEqual(claim["decision"]["bucket"], "primary")
        self.assertIsNone(claim["decision"]["applicability"])
        self.assertEqual(claim["decision"]["structural_score"], 0.0)
        self.assertFalse(claim["decision"]["structural_score_eligible"])

        biomarker = claim["case_comparison"]["biomarker"]
        self.assertEqual(biomarker["query_value_original"], "L858R")
        self.assertEqual(biomarker["query_value_normalized"], "EGFR L858R")
        self.assertEqual(biomarker["claim_value"], "EGFR L858R")
        self.assertEqual(biomarker["comparison_result"], "exact")
        self.assertIsNone(biomarker["not_applicable_reason"])

        intervention = claim["case_comparison"]["intervention"]
        self.assertEqual(intervention["claim_value"], "gefitinib")
        self.assertEqual(intervention["not_applicable_reason"], "NOT_PROVIDED_BY_CASE")
        direction = claim["case_comparison"]["direction"]
        self.assertEqual(direction["claim_value"], "sensitivity")
        self.assertEqual(direction["comparison_result"], "not_constrained")
        self.assertEqual(direction["not_applicable_reason"], "NOT_PROVIDED_BY_CASE")
        self.assertIsNone(claim["source_unit"])
        self.assertEqual(
            claim["provenance"]["parent_record_id"],
            "GEP-5f6e4a0e89277128ca53",
        )

    def test_claim_contract_keeps_real_score_and_reason_gate_origin(self) -> None:
        response = present_retrieval_outcome(
            self.run_query(
                query_id="AUDIT-PILOT-EGFR-WITH-INTERVENTION",
                gene="EGFR",
                alteration="L858R",
                biomarker="",
                disease="Lung Adenocarcinoma",
                interventions=["gefitinib"],
                direction="sensitivity",
            )
        )
        claim = next(
            item
            for bucket in response["evidence"].values()
            for item in bucket
            if item["claim_id"] == "CLM-e565f65d73cb1d4aa67b"
        )
        self.assertEqual(claim["decision"]["structural_score"], 108.0)
        self.assertTrue(claim["decision"]["structural_score_eligible"])
        self.assertNotEqual(
            claim["decision"]["applicability"],
            claim["decision"]["bucket"],
        )
        reason_by_code = {item["code"]: item for item in claim["reason_codes"]}
        self.assertEqual(
            reason_by_code["BIOMARKER_EXACT_LITERAL_MATCH"]["gate"],
            "biomarker",
        )
        self.assertEqual(
            reason_by_code["DISEASE_EXACT_MATCH"]["gate"],
            "disease",
        )

    def test_manual_egfr_osimertinib_payload_keeps_three_primary_scores(self) -> None:
        response = present_retrieval_outcome(
            self.run_query(
                query_id="manual-03-egfr-limitation",
                gene="EGFR",
                alteration="L858R",
                biomarker="",
                disease="Non-Small Cell Lung Cancer",
                interventions=["osimertinib"],
                direction="sensitivity",
                result_limit=50,
            )
        )
        self.assertEqual(response["summary"]["primary"], 3)
        self.assertEqual(response["summary"]["warning"], 0)
        self.assertEqual(
            [item["claim_id"] for item in response["evidence"]["primary"]],
            [
                "CLM-382985ec558808784e70",
                "CLM-d4bee44e07efb6ccca9f",
                "CLM-1ee5f9a16a678cebf993",
            ],
        )
        self.assertEqual(
            [item["decision"]["structural_score"] for item in response["evidence"]["primary"]],
            [108.0, 108.0, 108.0],
        )
        self.assertEqual(response["case_context"]["original"]["disease"], "Non-Small Cell Lung Cancer")
        self.assertEqual(response["case_context"]["original"]["gene"], "EGFR")
        self.assertEqual(response["case_context"]["original"]["alteration"], "L858R")
        self.assertEqual(response["case_context"]["original"]["interventions"], ["osimertinib"])

    def test_source_claim_text_and_tuple_are_preserved_without_derivation(self) -> None:
        result = SimpleNamespace(
            claim_id="CLM-SOURCE-PROJECTION",
            claim_type="atomic_intervention_claim",
            biomarker="EGFR L858R",
            disease_scope="Lung Adenocarcinoma",
            canonical_intervention="gefitinib",
            intervention_members=(),
            parent_id="GEP-SOURCE",
            graph_evidence_id="evidence:source",
            bucket="primary_ranked_results",
            score={"total": 108.0, "eligibility": {"structural_score_eligible": True}},
            rank=1,
            reason_codes=(),
            warnings=(),
            provenance={},
            gate={},
        )
        source = {
            "claim_text": "EGFR L858R predicts response to gefitinib",
            "subject": "EGFR L858R",
            "relation": "predicts response to",
            "object": "gefitinib",
            "biomarker": "EGFR L858R",
            "disease_scope": "Lung Adenocarcinoma",
            "intervention": "gefitinib",
            "direction": "sensitivity",
            "claim_type": "atomic_intervention_claim",
            "applicability": "primary",
        }
        with patch("backend.api.v3_presentation._source_record", return_value=source):
            projected = _claim_record(result, _query(), "qualified_claim_repository/1.4")
        self.assertEqual(projected["claim"]["claim_text"], source["claim_text"])
        self.assertEqual(projected["claim"]["subject"], source["subject"])
        self.assertEqual(projected["claim"]["relation"], source["relation"])
        self.assertEqual(projected["claim"]["object"], source["object"])
        self.assertTrue(projected["claim"]["structured_tuple_complete"])
        self.assertEqual(projected["decision"]["applicability"], "primary")


class V3ProductEndpointTests(unittest.TestCase):
    def test_endpoint_contains_pipeline_projection(self) -> None:
        response = self.client.post('/api/v1/v3/retrieve', json=_query())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('pipeline', payload)
        self.assertIn('stages', payload['pipeline'])
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
