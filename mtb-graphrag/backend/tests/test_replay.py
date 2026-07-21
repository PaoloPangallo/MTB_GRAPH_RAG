"""Test del replay e della canonicalizzazione con conservazione della genealogia."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.control.canonical import (
    canonical_record_id,
    detect_conflicts,
    identity_key,
    normalize,
    weakest_completeness,
)
from backend.pipeline.control.contracts import ProvenanceRef, RecordObservation
from backend.pipeline.control.events import tool_completed_payload
from backend.pipeline.control.recorder import ActionRecorder
from backend.pipeline.control.replay import replay_to_canonical_view

_EVIDENCE = {
    "subject": "Osimertinib",
    "relation": "SENSITIVITY",
    "object": "EGFR L858R",
    "context": "Lung Adenocarcinoma",
    "pmid": 27959700,
    "evidence_level": "A",
}


def _record_tool(recorder: ActionRecorder, tool: str, kind: str, records: list[dict]) -> None:
    payload = tool_completed_payload(tool=tool, record_kind=kind, records=records)
    recorder.record(
        "tool_completed", tool, payload,
        action_id=recorder.new_action_id(), tool_name=tool, tool_version="1.0",
        completeness_status=payload["completeness_status"],
    )


class IdentityTest(TestCase):
    def test_normalization_collapses_case_and_whitespace(self) -> None:
        self.assertEqual(normalize("  OSIMERTINIB  "), "osimertinib")
        self.assertEqual(normalize("EGFR   L858R"), "egfr l858r")

    def test_case_variants_of_the_same_fact_share_an_identity(self) -> None:
        upper = identity_key("evidence", {**_EVIDENCE, "subject": "OSIMERTINIB"})
        lower = identity_key("evidence", {**_EVIDENCE, "subject": "osimertinib"})

        self.assertEqual(upper, lower)

    def test_trials_are_identified_by_nct_id_alone(self) -> None:
        first = identity_key("trial", {"nct_id": "NCT02296125", "phase": "Phase 3"})
        second = identity_key("trial", {"nct_id": "NCT02296125", "phase": "Fase 3"})

        self.assertEqual(first, second)

    def test_canonical_id_is_stable_across_runs(self) -> None:
        key = identity_key("evidence", _EVIDENCE)

        self.assertEqual(canonical_record_id(key), canonical_record_id(key))
        self.assertNotEqual(
            canonical_record_id(key),
            canonical_record_id(identity_key("evidence", {**_EVIDENCE, "pmid": 1})),
        )


class CompletenessPropagationTest(TestCase):
    def test_weakest_status_wins(self) -> None:
        self.assertEqual(weakest_completeness(["complete", "truncated"]), "truncated")
        self.assertEqual(weakest_completeness(["complete", "unknown"]), "unknown")
        self.assertEqual(weakest_completeness(["complete", "complete"]), "complete")

    def test_absent_status_is_unknown_not_complete(self) -> None:
        self.assertEqual(weakest_completeness([]), "unknown")


class ConflictDetectionTest(TestCase):
    def _observation(self, level: str, event_id: str) -> RecordObservation:
        return RecordObservation(
            provenance=ProvenanceRef(event_id=event_id, sequence=1),
            payload={**_EVIDENCE, "evidence_level": level},
        )

    def test_disagreeing_observations_produce_an_annotation(self) -> None:
        conflicts = detect_conflicts(
            "evidence", [self._observation("A", "e1"), self._observation("B", "e2")]
        )

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].field_name, "evidence_level")
        self.assertEqual(conflicts[0].values, ("A", "B"))

    def test_agreeing_observations_produce_no_annotation(self) -> None:
        conflicts = detect_conflicts(
            "evidence", [self._observation("A", "e1"), self._observation("A", "e2")]
        )

        self.assertEqual(conflicts, ())

    def test_a_single_observation_cannot_conflict(self) -> None:
        self.assertEqual(detect_conflicts("evidence", [self._observation("A", "e1")]), ())


class ReplayTest(TestCase):
    def test_view_is_reconstructed_from_the_ledger_alone(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            recorder.record("run_started", "controller", {})
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])
            _record_tool(recorder, "match_trials", "trial", [{"nct_id": "NCT02296125"}])

            view = replay_to_canonical_view(recorder.events())

            self.assertEqual(view.run_id, recorder.run_id)
            self.assertEqual(view.records_out, 2)
            self.assertEqual(len(view.by_kind("evidence")), 1)
            self.assertEqual(len(view.by_kind("trial")), 1)

    def test_replay_is_deterministic_for_the_same_events(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])

            first = replay_to_canonical_view(recorder.events())
            second = replay_to_canonical_view(recorder.events())

            self.assertEqual(
                [r.canonical_record_id for r in first.records],
                [r.canonical_record_id for r in second.records],
            )

    def test_duplicates_are_merged_while_keeping_every_generating_event(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            # Lo stesso fatto osservato da due azioni distinte.
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])

            view = replay_to_canonical_view(recorder.events())

            self.assertEqual(view.records_in, 2)
            self.assertEqual(view.records_out, 1)
            record = view.records[0]
            # La genealogia sopravvive alla deduplicazione: entrambe le azioni
            # restano attribuibili, cosa che il "tieni il primo" perdeva.
            self.assertEqual(record.occurrence_count, 2)
            self.assertEqual(len(record.source_event_ids), 2)
            self.assertEqual(len(set(record.source_event_ids)), 2)
            self.assertEqual(len(record.source_action_ids), 2)

    def test_original_claim_is_pinned_to_the_first_observation(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])
            _record_tool(
                recorder, "interpret_variant", "evidence",
                [{**_EVIDENCE, "evidence_statement": "riformulazione successiva"}],
            )

            record = replay_to_canonical_view(recorder.events()).records[0]

            # La claim originale non viene mai riscritta da un'osservazione
            # successiva: la contestualizzazione è un artefatto derivato.
            self.assertIsNone(record.original_claim.evidence_statement)

    def test_conflicting_duplicates_are_annotated_not_silently_resolved(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])
            _record_tool(
                recorder, "interpret_variant", "evidence",
                [{**_EVIDENCE, "evidence_level": "B"}],
            )

            record = replay_to_canonical_view(recorder.events()).records[0]

            self.assertEqual(len(record.conflict_annotations), 1)
            self.assertEqual(record.conflict_annotations[0].values, ("A", "B"))

    def test_trials_are_deduplicated_by_nct_id(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            _record_tool(
                recorder, "match_trials", "trial",
                [{"nct_id": "NCT07183189", "drug_tested": "Osimertinib"},
                 {"nct_id": "NCT07183189", "drug_tested": "Lazertinib"}],
            )

            view = replay_to_canonical_view(recorder.events())

            self.assertEqual(len(view.by_kind("trial")), 1)
            self.assertEqual(view.by_kind("trial")[0].occurrence_count, 2)

    def test_truncated_collection_degrades_view_completeness(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            records = [{**_EVIDENCE, "pmid": i, "note": "x" * 500} for i in range(400)]
            _record_tool(recorder, "interpret_variant", "evidence", records)

            view = replay_to_canonical_view(recorder.events())

            self.assertEqual(view.completeness_status, "truncated")
            self.assertEqual(view.replay_fidelity, "partial")

    def test_v2_event_missing_structured_records_is_unreplayable(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            recorder.record("tool_completed", "match_trials",
                            {"record_kind": "trial", "observation": {"trial_candidates": []}})

            view = replay_to_canonical_view(recorder.events())

            self.assertEqual(view.records_out, 0)
            self.assertEqual(len(view.unreplayable_event_ids), 1)
            self.assertEqual(view.replay_fidelity, "partial")

    def test_historical_v1_run_is_reported_as_degraded_not_full(self) -> None:
        # Un run interamente storico non deve presentarsi come vista completa
        # con zero record: l'assenza di dati va distinta dall'impossibilità di
        # ricostruirli.
        events = [
            {
                "event_id": "e1", "run_id": "run-v1", "sequence": 1,
                "event_type": "tool_completed", "actor": "match_trials",
                "schema_version": 1, "created_at": "2026-01-01T00:00:00+00:00",
                "payload": {"step": 1, "observation": {"trial_candidates": [{"nct_id": "NCT1"}]}},
            }
        ]

        view = replay_to_canonical_view(events)

        self.assertEqual(view.records_out, 0)
        self.assertEqual(view.replay_fidelity, "degraded_v1_events")
        self.assertEqual(view.unreplayable_event_ids, ("e1",))

    def test_tools_producing_no_records_do_not_degrade_fidelity(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            _record_tool(recorder, "assess_complexity", "", [])
            _record_tool(recorder, "interpret_variant", "evidence", [_EVIDENCE])

            view = replay_to_canonical_view(recorder.events())

            self.assertEqual(view.replay_fidelity, "full")
            self.assertEqual(view.unreplayable_event_ids, ())

    def test_empty_event_list_yields_an_empty_view(self) -> None:
        view = replay_to_canonical_view([])

        self.assertEqual(view.records_out, 0)
        self.assertEqual(view.run_id, "")

    def test_records_without_a_kind_are_ignored(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "l.sqlite3"))
            _record_tool(recorder, "assess_complexity", "", [])

            self.assertEqual(replay_to_canonical_view(recorder.events()).records_out, 0)
