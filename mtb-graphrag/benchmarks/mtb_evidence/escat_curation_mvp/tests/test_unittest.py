from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from benchmarks.mtb_evidence.escat_curation_mvp.audit import append_event, make_event, read_events
from benchmarks.mtb_evidence.escat_curation_mvp.models import EscatAssessmentRecord, EscatRuleSet
from benchmarks.mtb_evidence.escat_curation_mvp.pilot import generate_pilot
from benchmarks.mtb_evidence.escat_curation_mvp.prefill import create_draft, repository_root
from benchmarks.mtb_evidence.escat_curation_mvp.validation import validate_assessment


TEST_ROOT = Path(__file__).resolve().parents[1] / ".test_tmp"


class EscatCurationMvpTests(unittest.TestCase):
    def test_pilot_creates_fifteen_incomplete_drafts_without_tiers(self) -> None:
        drafts = generate_pilot(TEST_ROOT / "data", repository_root())
        self.assertEqual(len(drafts), 15)
        self.assertTrue(all(item["assessment"]["assessment_status"] == "INCOMPLETE" for item in drafts))
        self.assertTrue(all(item["assessment"]["tier"] is None and item["assessment"]["subtier"] is None for item in drafts))

    def test_diagnostic_claim_is_not_applicable(self) -> None:
        draft = create_draft("CLM-8941c177da91f66ff93a", root=repository_root())
        self.assertEqual(draft.assessment.assessment_status, "NOT_APPLICABLE")
        self.assertIsNone(draft.assessment.tier)

    def test_unavailable_ruleset_blocks_legacy_pmids_and_tier(self) -> None:
        record = EscatAssessmentRecord(
            assessment_id="EA-1", claim_id="CLM-1", assessment_status="CURATED", tier="I-A",
            biomarker="EGFR L858R", disease="NSCLC", intervention="osimertinib",
            rule_ids=["legacy-tier"], supporting_sources=[{"source_id": "PMID:1"}],
            rationale="PMID only", curator="human", curated_at=datetime.now(timezone.utc),
        )
        result = validate_assessment(record, EscatRuleSet())
        self.assertFalse(result.valid)
        self.assertIn("OFFICIAL_RULESET_NOT_AVAILABLE", result.errors)
        self.assertIn("LEGACY_OR_UNVERIFIED_TIER_NOT_ALLOWED", result.errors)

    def test_subtier_requires_tier(self) -> None:
        record = EscatAssessmentRecord(assessment_id="EA-2", claim_id="CLM-2", assessment_status="READY_FOR_REVIEW", subtier="A")
        result = validate_assessment(record, EscatRuleSet())
        self.assertFalse(result.valid)
        self.assertIn("SUBTIER_REQUIRES_TIER", result.errors)

    def test_source_and_passage_are_separate(self) -> None:
        draft = create_draft("CLM-0e59264facd7b2df0e67", root=repository_root())
        self.assertGreaterEqual(len(draft.assessment.supporting_sources), 1)
        self.assertGreaterEqual(len(draft.assessment.supporting_passages), 1)
        self.assertNotEqual(draft.assessment.supporting_sources, draft.assessment.supporting_passages)

    def test_audit_is_append_only_and_supersession_is_explicit(self) -> None:
        path = TEST_ROOT / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        append_event(path, make_event("EA-3", "human", "DRAFT_CREATED", reason="first"))
        append_event(path, make_event("EA-3", "human", "ASSESSMENT_SUPERSEDED", reason="replacement", new_value="EA-4"))
        events = read_events(path, "EA-3")
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].action, "DRAFT_CREATED")
        self.assertEqual(events[1].action, "ASSESSMENT_SUPERSEDED")


if __name__ == "__main__":
    unittest.main()
