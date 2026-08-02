from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
import unittest

from benchmarks.mtb_evidence.escat_curation_mvp.models import EscatAssessmentRecord, EscatRuleSet
from benchmarks.mtb_evidence.escat_curation_mvp.validation import validate_assessment
from benchmarks.mtb_evidence.escat_shadow_dossier.adapter import (
    build_shadow_dossier,
    load_pilot_preview,
    present_assessment,
    resolve_assessment,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1].parent / "escat_curation_mvp" / "test_fixture_ruleset.json"
CLAIM_ID = "CLM-example"


def fixture_ruleset() -> EscatRuleSet:
    return EscatRuleSet.from_dict(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))


def fixture_record(**changes: object) -> EscatAssessmentRecord:
    values = dict(
        assessment_id="EA-fixture",
        claim_id=CLAIM_ID,
        assessment_status="CURATED",
        framework_version="TEST-1",
        tier="TEST-TIER-1",
        subtier="A",
        biomarker="BRAF V600E",
        disease="TEST DISEASE",
        intervention="TEST DRUG",
        direction="sensitivity",
        tumour_context_relation="same_tumour",
        study_design="prospective",
        outcome_basis=["response"],
        supporting_sources=[{"source_id": "SU-support"}],
        supporting_passages=[{"text": "technical fixture passage", "locator": "p.1"}],
        rule_ids=["TEST-R1"],
        rationale="technical fixture validation only",
        curator="fixture-curator",
        curated_at=datetime.now(timezone.utc),
    )
    values.update(changes)
    return EscatAssessmentRecord(**values)


class EscatShadowDossierAdapterTests(unittest.TestCase):
    def test_no_assessment_is_not_assessed(self) -> None:
        block = present_assessment("CLM-none", [], ruleset_status="RESEARCH_DRAFT")
        self.assertEqual(block["status"], "NOT_ASSESSED")
        self.assertIsNone(block["assessment_id"])
        self.assertTrue(block["manual_review_required"])

    def test_incomplete_status_is_preserved_and_tier_absence_is_not_the_decision(self) -> None:
        record = EscatAssessmentRecord(assessment_id="EA-1", claim_id=CLAIM_ID, assessment_status="INCOMPLETE")
        block = present_assessment(CLAIM_ID, [record], ruleset_status="RESEARCH_DRAFT")
        self.assertEqual(block["status"], "INCOMPLETE")
        self.assertIsNone(block["tier"])
        self.assertIn("RESEARCH_RULESET_NOT_CLINICALLY_VALIDATED", block["missing_requirements"])

        ready = EscatAssessmentRecord(assessment_id="EA-2", claim_id=CLAIM_ID, assessment_status="READY_FOR_REVIEW")
        self.assertEqual(present_assessment(CLAIM_ID, [ready])["status"], "READY_FOR_REVIEW")

    def test_not_applicable_and_conflict_are_preserved(self) -> None:
        not_applicable = EscatAssessmentRecord(
            assessment_id="EA-na", claim_id=CLAIM_ID, assessment_status="NOT_APPLICABLE"
        )
        self.assertEqual(present_assessment(CLAIM_ID, [not_applicable])["status"], "NOT_APPLICABLE")

        left = EscatAssessmentRecord(assessment_id="EA-left", claim_id=CLAIM_ID, assessment_status="INCOMPLETE")
        right = EscatAssessmentRecord(assessment_id="EA-right", claim_id=CLAIM_ID, assessment_status="REJECTED")
        block = present_assessment(CLAIM_ID, [left, right])
        self.assertEqual(block["status"], "CONFLICTING_EVIDENCE")
        self.assertIsNone(block["assessment_id"])

    def test_superseded_assessment_is_not_current(self) -> None:
        old = EscatAssessmentRecord(assessment_id="EA-old", claim_id=CLAIM_ID, assessment_status="SUPERSEDED")
        current = EscatAssessmentRecord(assessment_id="EA-current", claim_id=CLAIM_ID, assessment_status="INCOMPLETE")
        resolution = resolve_assessment(CLAIM_ID, [old, current])
        self.assertEqual(resolution.current.assessment_id, "EA-current")
        self.assertNotIn("EA-old", resolution.current_ids)

        only_old = resolve_assessment(CLAIM_ID, [old])
        self.assertIsNone(only_old.current)

    def test_association_uses_claim_id_only(self) -> None:
        same_biomarker = EscatAssessmentRecord(
            assessment_id="EA-other", claim_id="CLM-other", assessment_status="INCOMPLETE", biomarker="EGFR L858R"
        )
        block = present_assessment(CLAIM_ID, [same_biomarker])
        self.assertEqual(block["status"], "NOT_ASSESSED")

        unknown = resolve_assessment("CLM-missing", [], known_claim_ids={CLAIM_ID})
        self.assertTrue(unknown.claim_missing)

    def test_provenance_and_assessment_sources_remain_separate(self) -> None:
        record = EscatAssessmentRecord(
            assessment_id="EA-source",
            claim_id=CLAIM_ID,
            assessment_status="INCOMPLETE",
            supporting_sources=[{"source_id": "SU-assessment"}],
            supporting_passages=[{"text": "assessment passage", "locator": "p.2"}],
        )
        claim_sources = [{"source_id": "PMID:999"}]
        dossier = build_shadow_dossier(
            CLAIM_ID,
            claim_relevance={"claim_id": CLAIM_ID, "statement": "claim"},
            claim_sources=claim_sources,
            rule_sources=[{"source_id": "RULE-MATEO"}],
            document_support={"sources": claim_sources, "passages": [{"text": "claim passage"}]},
            assessments=[record],
        )
        self.assertEqual(dossier["provenance"]["claim_sources"], claim_sources)
        self.assertEqual(dossier["provenance"]["rule_sources"], [{"source_id": "RULE-MATEO"}])
        self.assertEqual(dossier["assessment_supporting_sources"], [{"source_id": "SU-assessment"}])
        self.assertEqual(dossier["supporting_passages"], [{"text": "assessment passage", "locator": "p.2"}])
        self.assertEqual(dossier["clinical_actionability"]["supporting_sources"], [{"source_id": "SU-assessment"}])
        self.assertNotIn("PMID:999", json.dumps(dossier["clinical_actionability"]))

    def test_curated_fixture_is_exposed_only_with_label(self) -> None:
        record = fixture_record()
        self.assertTrue(validate_assessment(record, fixture_ruleset()).valid)
        block = present_assessment(CLAIM_ID, [record], ruleset=fixture_ruleset(), ruleset_status="TEST_FIXTURE_ONLY")
        self.assertEqual(block["status"], "CURATED")
        self.assertEqual(block["tier"], "TEST-TIER-1")
        self.assertIn("TEST_FIXTURE_ONLY", block["notes"])
        self.assertIn("NOT_A_CLINICAL_ESCAT_ASSESSMENT", block["notes"])

    def test_shadow_dossier_preserves_bucket_score_gate_order_and_abstention(self) -> None:
        original = {
            "bucket": "primary",
            "score": {"total": 42},
            "gate_trace": [{"gate": "qualified", "passed": True}],
            "evidence": [{"claim_id": CLAIM_ID, "rank": 1}],
            "abstention": {"abstained": False},
        }
        before = copy.deepcopy(original)
        dossier = build_shadow_dossier(
            CLAIM_ID,
            claim_relevance={"claim_id": CLAIM_ID},
            claim_sources=[],
            document_support={},
            assessments=[],
            retrieval_context=original,
        )
        self.assertEqual(original, before)
        for key in original:
            self.assertEqual(dossier[key], before[key])

    def test_pilot_preview_contains_fifteen_unchanged_incomplete_drafts(self) -> None:
        preview = load_pilot_preview()
        self.assertEqual(preview["pilot_draft_count"], 15)
        self.assertEqual(preview["state_counts"], {"INCOMPLETE": 15})
        self.assertEqual(preview["assigned_tier_count"], 0)
        self.assertEqual(preview["assigned_subtier_count"], 0)


if __name__ == "__main__":
    unittest.main()
