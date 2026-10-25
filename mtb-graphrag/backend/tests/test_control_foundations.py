"""Test di contracts, events e recorder: le fondamenta dello strato comune."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.control.contracts import (
    STAGE_NAMES,
    CanonicalRecord,
    CanonicalView,
    CaseContext,
    OriginalClaim,
    Projection,
    ProjectedRecord,
    StageTiming,
    StructuralVerdict,
    Violation,
    stage_timings_dict,
)
from backend.pipeline.control.events import (
    MAX_EVENT_PAYLOAD_BYTES,
    bound_records,
    sanitize_text,
    tool_completed_payload,
)
from backend.pipeline.control.recorder import ActionRecorder


class _Request:
    """Sostituto minimale di ArchitectureComparisonRequest."""

    gene = "EGFR"
    variant = "L858R"
    tumor_type = "Lung Adenocarcinoma"
    alteration_type = "point_mutation"
    therapy_line = "first-line"
    driver_variant = ""
    disease_stage = "IV"
    disease_setting = "metastatic"
    prior_therapies: list[str] = []
    prior_response = None
    ecog_status = 1
    cns_metastases = False
    co_alterations: list[str] = []
    jurisdiction = None
    mtb_goal = "general-review"
    enrich_with_oncokb = False


class CaseContextTest(TestCase):
    def test_from_request_preserves_declared_clinical_context(self) -> None:
        case = CaseContext.from_request(_Request())

        self.assertEqual(case.gene, "EGFR")
        self.assertEqual(case.disease_setting, "metastatic")
        self.assertEqual(case.ecog_status, 1)
        self.assertEqual(case.mtb_goal, "general-review")

    def test_label_is_stable_and_human_readable(self) -> None:
        self.assertEqual(
            CaseContext.from_request(_Request()).label(),
            "EGFR L858R — Lung Adenocarcinoma",
        )

    def test_to_state_does_not_invent_undeclared_fields(self) -> None:
        request = _Request()
        request.disease_stage = None
        request.disease_setting = None

        state = CaseContext.from_request(request).to_state()

        self.assertIsNone(state["disease_stage"])
        self.assertIsNone(state["disease_setting"])
        self.assertEqual(state["prior_therapies"], [])


class SanitizationTest(TestCase):
    def test_credentials_are_redacted_before_reaching_the_ledger(self) -> None:
        raw = "upstream failure token=sekrit123 at postgres://user:pass@internal-host/db"

        clean = sanitize_text(raw)

        self.assertNotIn("sekrit123", clean)
        self.assertNotIn("internal-host", clean)
        self.assertNotIn("user:pass", clean)

    def test_bearer_tokens_and_api_keys_are_redacted(self) -> None:
        self.assertNotIn("abcdef123456", sanitize_text("Authorization: Bearer abcdef123456"))
        self.assertNotIn("sk-live-999", sanitize_text("api_key=sk-live-999"))

    def test_ordinary_clinical_text_is_left_intact(self) -> None:
        text = "Osimertinib è associato a sensibilità nel NSCLC EGFR-mutato (PMID:27959700)."

        self.assertEqual(sanitize_text(text), text)


class PayloadBoundingTest(TestCase):
    def test_abstracts_are_not_persisted_verbatim(self) -> None:
        records = [{"pmid": 27959700, "abstract": "x" * 5000, "subject": "Osimertinib"}]

        payload = tool_completed_payload(
            tool="interpret_variant", record_kind="evidence", records=records
        )

        stored = payload["records"][0]
        self.assertNotIn("x" * 100, json.dumps(stored))
        self.assertTrue(stored["abstract"]["omitted"])
        self.assertEqual(stored["abstract"]["chars"], 5000)
        # Il riferimento risolvibile resta: l'abstract è ri-ottenibile dal PMID.
        self.assertEqual(stored["pmid"], 27959700)

    def test_structured_fields_needed_by_replay_are_preserved(self) -> None:
        records = [
            {
                "subject": "Osimertinib",
                "relation": "SENSITIVITY",
                "object": "EGFR L858R",
                "pmid": 27959700,
                "evidence_level": "A",
            }
        ]

        payload = tool_completed_payload(
            tool="interpret_variant", record_kind="evidence", records=records
        )

        self.assertEqual(payload["records"][0]["subject"], "Osimertinib")
        self.assertEqual(payload["records"][0]["relation"], "SENSITIVITY")
        self.assertEqual(payload["records"][0]["evidence_level"], "A")

    def test_oversized_record_lists_are_truncated_visibly(self) -> None:
        records = [{"subject": "x" * 500, "index": i} for i in range(500)]

        kept, omitted = bound_records(records)

        self.assertGreater(omitted, 0)
        self.assertLess(len(kept), len(records))
        payload = tool_completed_payload(
            tool="match_trials", record_kind="trial", records=records
        )
        # Il troncamento non è mai silenzioso.
        self.assertTrue(payload["payload_truncated"])
        self.assertEqual(payload["completeness_status"], "truncated")

    def test_small_payloads_are_not_flagged_as_truncated(self) -> None:
        payload = tool_completed_payload(
            tool="match_trials", record_kind="trial", records=[{"nct_id": "NCT01"}]
        )

        self.assertNotIn("payload_truncated", payload)
        self.assertEqual(payload["completeness_status"], "complete")

    def test_secrets_inside_tool_records_are_redacted(self) -> None:
        records = [{"note": "connect via postgres://user:pass@internal-host/db"}]

        payload = tool_completed_payload(
            tool="match_trials", record_kind="trial", records=records
        )

        self.assertNotIn("internal-host", json.dumps(payload))


class ActionRecorderTest(TestCase):
    def test_recorder_is_the_single_writer_for_one_run(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger = EventLedger(Path(tmp) / "ledger.sqlite3")
            recorder = ActionRecorder(ledger)

            recorder.record("run_started", "controller", {"gene": "EGFR"})
            recorder.record("run_completed", "controller", {})

            events = recorder.events()
            self.assertEqual([e["sequence"] for e in events], [1, 2])
            self.assertTrue(recorder.chain_valid())

    def test_action_columns_are_persisted_and_readable(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger = EventLedger(Path(tmp) / "ledger.sqlite3")
            recorder = ActionRecorder(ledger)
            action_id = recorder.new_action_id()

            recorder.record(
                "tool_completed",
                "match_trials",
                {"records": []},
                action_id=action_id,
                tool_name="match_trials",
                tool_version="1.0",
                query_or_arguments={"gene": "EGFR"},
                pagination_state={"has_more": False},
                completeness_status="complete",
            )

            event = recorder.events()[0]
            self.assertEqual(event["action_id"], action_id)
            self.assertEqual(event["tool_name"], "match_trials")
            self.assertEqual(event["completeness_status"], "complete")
            self.assertEqual(json.loads(event["query_or_arguments_json"]), {"gene": "EGFR"})

    def test_record_error_sanitizes_before_writing(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger = EventLedger(Path(tmp) / "ledger.sqlite3")
            recorder = ActionRecorder(ledger)

            recorder.record_error(
                "tool_failed",
                "match_trials",
                "boom token=sekrit123 at postgres://user:pass@internal-host/db",
                category="service_unavailable",
            )

            serialized = json.dumps([dict(e) for e in recorder.events()], default=str)
            self.assertNotIn("sekrit123", serialized)
            self.assertNotIn("internal-host", serialized)


class StructuralVerdictTest(TestCase):
    def test_blocking_violation_requires_human_review_and_blocks_repair(self) -> None:
        verdict = StructuralVerdict(
            stage="final",
            violations=(Violation("SPURIOUS_CITATION", "blocking", "citazione non attesa"),),
        )

        self.assertEqual(verdict.status, "violations_blocking")
        self.assertTrue(verdict.requires_human_review)
        self.assertFalse(verdict.requires_repair)

    def test_repairable_violation_requests_repair_without_human_review(self) -> None:
        verdict = StructuralVerdict(
            stage="final",
            violations=(Violation("MISSING_CLAIM", "repairable", "claim assente"),),
        )

        self.assertEqual(verdict.status, "violations_repairable")
        self.assertTrue(verdict.requires_repair)
        self.assertFalse(verdict.requires_human_review)

    def test_warnings_do_not_change_status(self) -> None:
        verdict = StructuralVerdict(
            stage="final",
            warnings=(Violation("LEXICON_VIOLATION", "advisory", "token inatteso"),),
        )

        self.assertEqual(verdict.status, "pass")
        self.assertFalse(verdict.requires_repair)
        self.assertFalse(verdict.requires_human_review)

    def test_incomplete_coverage_escalates_even_without_violations(self) -> None:
        self.assertTrue(StructuralVerdict(stage="final", coverage=0.5).requires_human_review)


class StageTimingsTest(TestCase):
    def test_all_stage_keys_are_present_even_when_unused(self) -> None:
        timings = stage_timings_dict([StageTiming("collection", 12)])

        self.assertEqual(set(timings), set(STAGE_NAMES))
        self.assertEqual(timings["collection"], 12)
        # Una fase non eseguita riporta 0, mai una chiave assente: le metriche
        # devono essere confrontabili senza sapere quale architettura le ha
        # prodotte.
        self.assertEqual(timings["repair"], 0)


class ProjectionShapeTest(TestCase):
    def _record(self, record_id: str, admitted: bool) -> ProjectedRecord:
        return ProjectedRecord(
            canonical_record_id=record_id,
            record_kind="evidence",
            claim=OriginalClaim(subject="Osimertinib", relation="SENSITIVITY", object="EGFR L858R"),
            admitted=admitted,
        )

    def test_admitted_and_excluded_partition_the_projection(self) -> None:
        projection = Projection(
            run_id="r",
            case_label="EGFR L858R",
            records=(self._record("a", True), self._record("b", False)),
        )

        self.assertEqual(projection.admitted_ids, frozenset({"a"}))
        self.assertEqual(projection.excluded_ids, frozenset({"b"}))
        self.assertEqual(len(projection.admitted) + len(projection.excluded), 2)


class CanonicalViewShapeTest(TestCase):
    def test_records_out_reflects_deduplicated_count(self) -> None:
        view = CanonicalView(
            run_id="r",
            records=(
                CanonicalRecord(
                    canonical_record_id="c1",
                    record_kind="evidence",
                    identity_key=("evidence", "osimertinib"),
                    original_claim=OriginalClaim("Osimertinib", "SENSITIVITY", "EGFR L858R"),
                ),
            ),
            records_in=3,
        )

        self.assertEqual(view.records_in, 3)
        self.assertEqual(view.records_out, 1)
        self.assertEqual(len(view.by_kind("evidence")), 1)
        self.assertEqual(len(view.by_kind("trial")), 0)
