from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from benchmarks.mtb_evidence.escat_curation_mvp.models import EscatAssessmentRecord
from benchmarks.mtb_evidence.escat_shadow_dossier.adapter import build_shadow_dossier, present_assessment
from benchmarks.mtb_evidence.escat_shadow_dossier.fixtures import fixture_curated_record, fixture_ruleset
from benchmarks.mtb_evidence.escat_shadow_dossier.preview import generate_preview


class ShadowDossierInvariantTests(unittest.TestCase):
    def test_ready_for_review_can_show_candidate_rules_without_assignment(self) -> None:
        record = EscatAssessmentRecord(
            assessment_id="EA-ready",
            claim_id="CLM-ready",
            assessment_status="READY_FOR_REVIEW",
        )
        block = present_assessment("CLM-ready", [record], candidate_rule_ids=["ESCAT-I-A"])
        self.assertEqual(block["status"], "READY_FOR_REVIEW")
        self.assertEqual(block["candidate_rule_ids"], ["ESCAT-I-A"])
        self.assertIsNone(block["tier"])
        self.assertIsNone(block["subtier"])

    def test_internal_draft_is_presented_as_incomplete_without_using_tier(self) -> None:
        record = EscatAssessmentRecord(
            assessment_id="EA-draft", claim_id="CLM-draft", assessment_status="DRAFT"
        )
        block = present_assessment("CLM-draft", [record], known_claim_ids={"CLM-draft"})
        self.assertEqual(block["status"], "INCOMPLETE")
        self.assertIn("DRAFT_PRESENTED_AS_INCOMPLETE", block["notes"])
        self.assertIsNone(block["tier"])

    def test_superseded_presentation_has_no_current_assessment(self) -> None:
        record = EscatAssessmentRecord(
            assessment_id="EA-old",
            claim_id="CLM-old",
            assessment_status="SUPERSEDED",
        )
        block = present_assessment("CLM-old", [record], known_claim_ids={"CLM-old"})
        self.assertEqual(block["status"], "NOT_ASSESSED")
        self.assertIn("SUPERSEDED_ASSESSMENT_NOT_CURRENT", block["notes"])

    def test_rejected_and_curated_fixture_do_not_change_retrieval_bucket(self) -> None:
        context = {
            "bucket": "primary",
            "score": {"total": 10},
            "gate_trace": [{"name": "qualified", "passed": True}],
            "evidence": [{"claim_id": "CLM-rejected", "rank": 1}],
            "abstention": {"abstained": False},
        }
        before = copy.deepcopy(context)
        rejected = EscatAssessmentRecord(
            assessment_id="EA-rejected",
            claim_id="CLM-rejected",
            assessment_status="REJECTED",
        )
        dossier = build_shadow_dossier(
            "CLM-rejected",
            claim_relevance={"claim_id": "CLM-rejected"},
            claim_sources=[],
            document_support={},
            assessments=[rejected],
            retrieval_context=context,
        )
        self.assertEqual(dossier["clinical_actionability"]["status"], "REJECTED")
        self.assertEqual(context, before)
        self.assertEqual(dossier["bucket"], before["bucket"])
        self.assertEqual(dossier["score"], before["score"])
        self.assertEqual(dossier["gate_trace"], before["gate_trace"])
        self.assertEqual(dossier["evidence"], before["evidence"])
        self.assertEqual(dossier["abstention"], before["abstention"])

    def test_curated_fixture_label_is_not_scientific_validation(self) -> None:
        block = present_assessment(
            "CASE-FIXTURE-CURATED",
            [fixture_curated_record()],
            ruleset=fixture_ruleset(),
            ruleset_status="TEST_FIXTURE_ONLY",
            known_claim_ids={"CASE-FIXTURE-CURATED"},
        )
        self.assertEqual(block["status"], "CURATED")
        self.assertEqual(block["ruleset_status"], "TEST_FIXTURE_ONLY")
        self.assertIn("TEST_FIXTURE_ONLY", block["notes"])
        self.assertIn("NOT_A_CLINICAL_ESCAT_ASSESSMENT", block["notes"])

    def test_preview_has_required_cases_and_no_automatic_assignment(self) -> None:
        preview = generate_preview()
        self.assertEqual(preview["pilot"]["pilot_draft_count"], 15)
        self.assertFalse(preview["automatic_assignment"])
        cases = preview["cases"]
        self.assertEqual(cases["FGFR2_iCCA"]["clinical_actionability"]["status"], "INCOMPLETE")
        self.assertEqual(cases["ALK_G1202R_NSCLC"]["clinical_actionability"]["status"], "NOT_ASSESSED")
        self.assertEqual(cases["EGFR_L858R_NSCLC_osimertinib"]["clinical_actionability"]["status"], "NOT_ASSESSED")
        self.assertEqual(cases["RMI2"]["clinical_actionability"]["status"], "NOT_ASSESSED")
        self.assertIn("CLAIM_NOT_FOUND", cases["RMI2"]["clinical_actionability"]["notes"])
        self.assertEqual(
            cases["diagnostic_explicit_not_applicable"]["clinical_actionability"]["status"],
            "NOT_APPLICABLE",
        )
        self.assertEqual(cases["superseded_fixture"]["clinical_actionability"]["status"], "NOT_ASSESSED")
        self.assertEqual(cases["conflicting_fixture"]["clinical_actionability"]["status"], "CONFLICTING_EVIDENCE")
        self.assertEqual(cases["curated_fixture"]["clinical_actionability"]["status"], "CURATED")


    def test_shadow_dossier_output_contains_four_cases_without_tiers(self) -> None:
        output = Path(__file__).resolve().parents[1] / "data" / "shadow_dossiers.json"
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(
            set(payload["cases"]),
            {"FGFR2_iCCA", "ALK_G1202R_NSCLC", "EGFR_L858R_NSCLC_osimertinib", "RMI2"},
        )
        for dossier in payload["cases"].values():
            self.assertIsNone(dossier["clinical_actionability"]["tier"])
            self.assertIsNone(dossier["clinical_actionability"]["subtier"])
            self.assertFalse(dossier["automatic_assignment"])

    def test_adapter_is_not_connected_to_production_surfaces(self) -> None:
        adapter = Path(__file__).resolve().parents[1] / "adapter.py"
        text = adapter.read_text(encoding="utf-8")
        self.assertNotIn("backend.api", text)
        self.assertNotIn("frontend", text.casefold())
        self.assertIn("qualified_claim_repository_1_4", text)
        self.assertNotIn("write_text", text)

    def test_shadow_artifact_is_json_and_fixture_is_separately_disclaimed(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / ".." / "escat_curation_mvp" / "test_fixture_ruleset.json"
        fixture_payload = json.loads(fixture.resolve().read_text(encoding="utf-8"))
        self.assertEqual(fixture_payload["status"], "TEST_FIXTURE_ONLY")
        self.assertEqual(fixture_payload["disclaimer"], "NOT_AN_OFFICIAL_ESCAT_RULESET")


if __name__ == "__main__":
    unittest.main()
