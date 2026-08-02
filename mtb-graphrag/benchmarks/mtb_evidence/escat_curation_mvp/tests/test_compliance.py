from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from benchmarks.mtb_evidence.escat_curation_mvp.audit import read_events
from benchmarks.mtb_evidence.escat_curation_mvp.models import (
    EscatAssessmentRecord,
    EscatRuleSet,
)
from benchmarks.mtb_evidence.escat_curation_mvp.pilot import (
    generate_pilot,
    partially_assignable_claim_ids,
)
from benchmarks.mtb_evidence.escat_curation_mvp.prefill import (
    create_draft,
    load_availability,
    repository_root,
)
from benchmarks.mtb_evidence.escat_curation_mvp.validation import (
    validate_assessment,
)
from benchmarks.mtb_evidence.escat_curation_mvp.workbench import main


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "test_fixture_ruleset.json"
CLAIM_ID = "CLM-0e59264facd7b2df0e67"


class EscatComplianceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = Path(__file__).resolve().parents[1] / f".compliance_test_{uuid.uuid4().hex}"
        self.workspace.mkdir(parents=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.workspace, ignore_errors=True)

    def run_cli(self, *args: str) -> tuple[int, dict]:
        output = StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--workspace",
                    str(self.workspace),
                    "--repo-root",
                    str(repository_root()),
                    *args,
                ]
            )
        text = output.getvalue().strip()
        return code, json.loads(text) if text else {}

    def create_assessment(self) -> tuple[str, dict]:
        code, value = self.run_cli("create-draft", CLAIM_ID)
        self.assertEqual(code, 0)
        return value["assessment"]["assessment_id"], value

    def load_record(self, assessment_id: str) -> dict:
        path = self.workspace / "assessments" / f"{assessment_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_real_pilot_has_fifteen_therapeutic_incomplete_drafts(self) -> None:
        output = Path(__file__).resolve().parents[1] / f".compliance_pilot_{uuid.uuid4().hex}"
        try:
            drafts = generate_pilot(output, repository_root())
        finally:
            shutil.rmtree(output, ignore_errors=True)
        partial_ids = partially_assignable_claim_ids(repository_root())
        availability = load_availability(repository_root())
        self.assertEqual(len(partial_ids), 15)
        self.assertTrue(all(availability[item]["claim_domain"] == "therapeutic" for item in partial_ids))
        self.assertEqual(len(drafts), 15)
        self.assertTrue(all(item["assessment"]["assessment_status"] == "INCOMPLETE" for item in drafts))
        self.assertTrue(all(item["assessment"]["tier"] is None for item in drafts))
        self.assertTrue(all(item["assessment"]["subtier"] is None for item in drafts))
        self.assertTrue(all(item["assessment"]["claim_id"] for item in drafts))
        self.assertTrue(all(item["assessment"]["assessment_status"] != "NOT_APPLICABLE" for item in drafts))

    def test_create_show_and_edit_workflow_emits_audit_events(self) -> None:
        assessment_id, _ = self.create_assessment()
        code, shown = self.run_cli("show-draft", assessment_id)
        self.assertEqual(code, 0)
        self.assertEqual(shown["assessment_id"], assessment_id)

        code, _ = self.run_cli("edit-field", assessment_id, "biomarker", '"EGFR L858R"', "--actor", "curator")
        self.assertEqual(code, 0)
        code, _ = self.run_cli("set-curator", assessment_id, "curator", "--actor", "curator")
        self.assertEqual(code, 0)
        code, _ = self.run_cli("set-rationale", assessment_id, "manual review", "--actor", "curator")
        self.assertEqual(code, 0)
        code, _ = self.run_cli("attach-source", assessment_id, '{"source_id":"SU-test"}', "--actor", "curator")
        self.assertEqual(code, 0)
        code, _ = self.run_cli("attach-passage", assessment_id, '{"text":"support","locator":"p.1"}', "--actor", "curator")
        self.assertEqual(code, 0)

        events = read_events(self.workspace / "assessment_events.jsonl", assessment_id)
        actions = [event.action for event in events]
        self.assertIn("DRAFT_CREATED", actions)
        self.assertIn("FIELD_PREFILLED", actions)
        self.assertIn("FIELD_EDITED", actions)
        self.assertIn("CURATOR_SET", actions)
        self.assertIn("RATIONALE_SET", actions)
        self.assertIn("SOURCE_ATTACHED", actions)
        self.assertIn("PASSAGE_ATTACHED", actions)
        for event in events:
            value = event.to_dict()
            self.assertTrue(value["event_id"])
            self.assertTrue(value["timestamp"])
            self.assertTrue(value["actor"])
            self.assertIn("field", value)
            self.assertIn("previous_value", value)
            self.assertIn("new_value", value)
            self.assertIn("rationale", value)

    def test_status_transitions_reject_invalid_transition_without_corruption(self) -> None:
        assessment_id, _ = self.create_assessment()
        code, _ = self.run_cli("set-status", assessment_id, "READY_FOR_REVIEW", "--actor", "curator")
        self.assertEqual(code, 0)
        code, _ = self.run_cli("set-status", assessment_id, "DRAFT", "--actor", "curator")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.load_record(assessment_id)["assessment_status"], "READY_FOR_REVIEW")
        events = read_events(self.workspace / "assessment_events.jsonl", assessment_id)
        self.assertTrue(any(event.reason == "INVALID_STATUS_TRANSITION" for event in events))

    def test_reject_invalid_transition_is_audited_without_corruption(self) -> None:
        assessment_id, _ = self.create_assessment()
        self.run_cli("reject-assessment", assessment_id, "first rejection", "--actor", "curator")
        self.run_cli("supersede-assessment", assessment_id, "--new-assessment-id", "ESCAT-AS-invalid-reject")
        code, _ = self.run_cli("reject-assessment", assessment_id, "invalid second rejection", "--actor", "curator")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.load_record(assessment_id)["assessment_status"], "SUPERSEDED")
        events = read_events(self.workspace / "assessment_events.jsonl", assessment_id)
        self.assertTrue(any(event.reason == "INVALID_STATUS_TRANSITION" for event in events))

    def test_validate_and_reject_emit_events(self) -> None:
        assessment_id, _ = self.create_assessment()
        code, result = self.run_cli("validate-assessment", assessment_id)
        self.assertEqual(code, 0)
        self.assertTrue(result["valid"])
        code, _ = self.run_cli("reject-assessment", assessment_id, "insufficient evidence", "--actor", "curator")
        self.assertEqual(code, 0)
        self.assertEqual(self.load_record(assessment_id)["assessment_status"], "REJECTED")
        actions = [event.action for event in read_events(self.workspace / "assessment_events.jsonl", assessment_id)]
        self.assertIn("ASSESSMENT_VALIDATED", actions)
        self.assertIn("ASSESSMENT_REJECTED", actions)
        self.assertIn("STATUS_CHANGED", actions)

    def test_supersede_preserves_previous_record(self) -> None:
        assessment_id, _ = self.create_assessment()
        self.run_cli("reject-assessment", assessment_id, "not sufficient", "--actor", "curator")
        previous = self.load_record(assessment_id)
        replacement_id = "ESCAT-AS-replacement"
        code, replacement = self.run_cli(
            "supersede-assessment",
            assessment_id,
            "--new-assessment-id",
            replacement_id,
            "--actor",
            "curator",
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.load_record(assessment_id)["assessment_status"], "SUPERSEDED")
        self.assertEqual(replacement["supersedes_assessment_id"], assessment_id)
        self.assertEqual(replacement["assessment_status"], "DRAFT")
        snapshots = list((self.workspace / "assessment_versions" / assessment_id).glob("*.json"))
        self.assertTrue(snapshots)
        self.assertEqual(json.loads(snapshots[-1].read_text(encoding="utf-8")), previous)

    def test_export_dossier_preserves_non_tier_statuses(self) -> None:
        from benchmarks.mtb_evidence.escat_curation_mvp.workbench import export_dossier

        for status in ("NOT_APPLICABLE", "CONFLICTING_EVIDENCE", "REJECTED", "SUPERSEDED", "INCOMPLETE"):
            record = EscatAssessmentRecord(assessment_id=f"EA-{status}", claim_id="CLM-test", assessment_status=status)
            self.assertEqual(export_dossier(record)["clinical_actionability"]["status"], status)

    def fixture_ruleset(self) -> EscatRuleSet:
        return EscatRuleSet.from_dict(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))

    def fixture_record(self, **changes: object) -> EscatAssessmentRecord:
        values = dict(
            assessment_id="EA-fixture",
            claim_id="CLM-test",
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
            rule_ids=["TEST-R1"],
            rationale="technical fixture validation",
            curator="test-curator",
            curated_at=datetime.now(timezone.utc),
        )
        values.update(changes)
        return EscatAssessmentRecord(**values)

    def test_fixture_positive_validation_is_technical_only(self) -> None:
        ruleset = self.fixture_ruleset()
        self.assertFalse(ruleset.available)
        self.assertEqual(ruleset.status, "TEST_FIXTURE_ONLY")
        result = validate_assessment(self.fixture_record(), ruleset)
        self.assertTrue(result.valid)
        self.assertIn("TEST_FIXTURE_ONLY", result.warnings)

    def test_fixture_rejects_unknown_rule_and_version_mismatch(self) -> None:
        ruleset = self.fixture_ruleset()
        self.assertIn("RULE_ID_NOT_FOUND", validate_assessment(self.fixture_record(rule_ids=["missing"]), ruleset).errors)
        self.assertIn("FRAMEWORK_VERSION_MISMATCH", validate_assessment(self.fixture_record(framework_version="wrong"), ruleset).errors)

    def test_fixture_rejects_rule_source_version_mismatch(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        payload["rules"][0]["source"]["version"] = "WRONG"
        result = validate_assessment(self.fixture_record(), EscatRuleSet.from_dict(payload))
        self.assertIn("RULE_SOURCE_FRAMEWORK_VERSION_MISMATCH", result.errors)

    def test_select_rule_and_export_dossier_via_cli(self) -> None:
        assessment_id, _ = self.create_assessment()
        code, selected = self.run_cli("select-rule", assessment_id, "TEST-R1", "--ruleset", str(FIXTURE_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(selected["framework_version"], "TEST-1")
        self.assertEqual(selected["tier"], None)
        code, dossier = self.run_cli("export-dossier", assessment_id)
        self.assertEqual(code, 0)
        self.assertEqual(dossier["clinical_actionability"]["status"], "INCOMPLETE")

    def test_fixture_checks_required_fields_alternatives_exclusions_and_subtier(self) -> None:
        ruleset = self.fixture_ruleset()
        self.assertIn("MISSING_REQUIRED_FIELD:study_design", validate_assessment(self.fixture_record(study_design=None), ruleset).errors)
        self.assertIn("REQUIRED_CONDITION_UNSATISFIED", validate_assessment(self.fixture_record(study_design="retrospective"), ruleset).errors)
        self.assertIn("ALTERNATIVE_CONDITION_UNSATISFIED", validate_assessment(self.fixture_record(tumour_context_relation="unknown"), ruleset).errors)
        self.assertIn("EXCLUSION_CONDITION_MATCHED", validate_assessment(self.fixture_record(direction="resistance"), ruleset).errors)
        self.assertIn("SUBTIER_REQUIREMENTS_INCOMPLETE", validate_assessment(self.fixture_record(outcome_basis=[]), ruleset).errors)

    def test_rule_source_must_be_distinct_and_pmid_only_is_insufficient(self) -> None:
        ruleset = self.fixture_ruleset()
        same_source = self.fixture_record(supporting_sources=[{"source_id": "fixture-rule"}])
        self.assertIn("RULE_SOURCE_MUST_BE_DISTINCT", validate_assessment(same_source, ruleset).errors)
        pmid_only = self.fixture_record(supporting_sources=[{"source_id": "PMID:123"}], supporting_passages=[])
        self.assertIn("PMID_ALONE_INSUFFICIENT", validate_assessment(pmid_only, ruleset).errors)

    def test_missing_official_ruleset_blocks_curated_tier_and_legacy_is_rejected(self) -> None:
        record = self.fixture_record(tier="I-A", subtier=None, rule_ids=["R-legacy"], assessment_origin="LEGACY_DERIVED")
        result = validate_assessment(record, EscatRuleSet())
        self.assertFalse(result.valid)
        self.assertIn("OFFICIAL_RULESET_NOT_AVAILABLE", result.errors)
        self.assertIn("LEGACY_OR_UNVERIFIED_TIER_NOT_ALLOWED", result.errors)

    def test_commit_scope_does_not_touch_production_paths(self) -> None:
        repo = repository_root().parent
        names = subprocess.check_output(["git", "diff", "--name-only", "6cd4cd4", "HEAD"], cwd=repo, text=True).splitlines()
        forbidden = ("/backend/", "/frontend/", "/runtime/", "qualified_claim_repository", "/gate", "/scoring", "/bucket")
        self.assertFalse(any(any(token in name.replace("\\", "/") for token in forbidden) for name in names), names)

    def test_evidence_level_does_not_assign_tier(self) -> None:
        draft = create_draft(CLAIM_ID, root=repository_root())
        self.assertIsNone(draft.assessment.tier)
        self.assertNotIn("evidence_level", draft.prefilled_fields)


if __name__ == "__main__":
    unittest.main()
