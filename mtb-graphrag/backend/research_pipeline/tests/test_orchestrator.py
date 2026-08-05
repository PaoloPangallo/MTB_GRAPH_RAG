"""Test dell'orchestratore osservabile.

Verificano ciò di cui l'orchestratore è responsabile — sequenza, eventi,
attribuzione, arresti — non le decisioni, che appartengono ai moduli promossi e
sono coperte da ``test_promoted_components.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import data_access as da
from backend.research_pipeline import events as ev
from backend.research_pipeline import orchestrator
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.contracts import LLM_STAGE_IDS, STAGE_SEQUENCE
from backend.research_pipeline.pipeline import CallBudget


def _frozen_parser_outputs() -> dict[str, dict[str, Any]]:
    path = da.data_root() / "benchmarks/mtb_evidence/end_to_end_pipeline_pilot/casecontext_outputs.jsonl"
    return {row["case_id"]: row for row in da.read_jsonl(path)}


def _case_by_id() -> dict[str, dict[str, Any]]:
    return {case["case_id"]: case for case in CASES}


class _ReplayParser:
    """Rigioca le risposte reali del parser catturate al commit 6ee64c5.

    Non è un mock: sono output effettivi del modello. Il budget non viene speso,
    perché nessuna chiamata di rete nuova avviene.
    """

    def __init__(self, outputs: dict[str, dict[str, Any]]) -> None:
        self.outputs = outputs
        self.calls: list[str] = []

    def __call__(self, budget: Any, case_id: str, clinical_text: str) -> dict[str, Any]:
        self.calls.append(case_id)
        return self.outputs[case_id]


class _FailingParser:
    def __call__(self, budget: Any, case_id: str, clinical_text: str) -> dict[str, Any]:
        return {"transport_result": "TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL"}


class _RecordingEnricher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def __call__(self, budget, case_id, candidate_id, paper_id, *args, **kwargs) -> dict[str, Any]:
        self.calls.append((case_id, paper_id))
        return {"transport_result": "V2_TRANSPORT_VALID", "enrichment": None,
                "model": "gemma4:cloud", "prompt_version": "p/2.0", "transport_version": "t/2.0"}


class OrchestratorTestBase(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.ledger = EventLedger(Path(self._tmp.name) / "research_ledger.sqlite3")
        self.parser = _ReplayParser(_frozen_parser_outputs())
        self.enricher = _RecordingEnricher()
        self.cases = _case_by_id()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_case(self, case_id: str, **overrides: Any):
        case = self.cases[case_id]
        kwargs: dict[str, Any] = {
            "case_id": case_id,
            "clinical_text": case["clinical_text"],
            "call_parser_fn": self.parser,
            "call_enricher_fn": self.enricher,
            "source_units_by_id": {},
            "budget": CallBudget(),
            "ledger": self.ledger,
        }
        kwargs.update(overrides)
        return orchestrator.run_case(**kwargs)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        return self.ledger.events(run_id)


class EveryStageIsAccountedForTest(OrchestratorTestBase):
    def test_all_fifteen_stages_appear_in_declared_order(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")

        self.assertEqual([s.stage_id for s in run.stages], list(STAGE_SEQUENCE))
        self.assertEqual([s.sequence for s in run.stages], list(range(1, 16)))

    def test_no_stage_is_left_pending(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        self.assertNotIn("PENDING", {s.status for s in run.stages})

    def test_every_stage_reports_a_duration(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        executed = [s for s in run.stages if s.status != "SKIPPED"]
        self.assertTrue(all(s.duration_ms is not None for s in executed))


class RoleAttributionTest(OrchestratorTestBase):
    def test_only_parser_and_enricher_are_attributed_to_a_model(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")

        llm_stages = {s.stage_id for s in run.stages if s.producer.kind == "LLM"}
        self.assertTrue(llm_stages <= LLM_STAGE_IDS)

    def test_gates_and_status_are_deterministic(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}

        for stage_id in ("stage_11_deterministic_gates", "stage_12_status"):
            self.assertEqual(by_id[stage_id].producer.kind, "DETERMINISTIC")
            self.assertIsNone(by_id[stage_id].producer.model)


class NotImplementedStagesTest(OrchestratorTestBase):
    def test_narrator_and_verifier_are_always_skipped(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}

        for stage_id in ("stage_14_narrator", "stage_15_narrative_verifier"):
            self.assertEqual(by_id[stage_id].status, "SKIPPED")
            self.assertIn("NOT_IMPLEMENTED", by_id[stage_id].reason_codes)

    def test_narration_events_are_never_emitted(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        emitted = {e["event_type"] for e in self.events(run.run_id)}
        self.assertEqual(emitted & ev.NEVER_EMITTED, set())


class CorrectStopsAreNotFailuresTest(OrchestratorTestBase):
    def test_casecontext_mismatch_stops_the_run_without_failing_it(self) -> None:
        run = self.run_case("CASE-5-casecontext-mismatch-no-match")

        self.assertIn(run.status, ("STOPPED",))
        self.assertIn(run.stopped_at, ("CASECONTEXT_MISMATCH", "RETRIEVAL_NO_MATCH"))
        self.assertNotEqual(run.status, "FAILED")

    def test_downstream_stages_explain_why_they_were_skipped(self) -> None:
        run = self.run_case("CASE-5-casecontext-mismatch-no-match")
        skipped = [s for s in run.stages if s.status == "SKIPPED"]

        self.assertTrue(skipped)
        self.assertTrue(all(s.reason_codes for s in skipped))

    def test_the_enricher_is_never_called_after_a_stop(self) -> None:
        self.run_case("CASE-5-casecontext-mismatch-no-match")
        self.assertEqual(self.enricher.calls, [])


class TransportFailureIsAFailureTest(OrchestratorTestBase):
    def test_parser_transport_failure_fails_the_run(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match",
                            call_parser_fn=_FailingParser())

        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.stopped_at, "PARSER_TRANSPORT_FAILED")

    def test_a_failure_is_distinguishable_from_a_stop(self) -> None:
        failed = self.run_case("CASE-1-therapy-evaluation-strong-match",
                               call_parser_fn=_FailingParser())
        stopped = self.run_case("CASE-5-casecontext-mismatch-no-match")

        self.assertNotEqual(failed.status, stopped.status)


class LedgerIntegrityTest(OrchestratorTestBase):
    def test_the_event_chain_verifies(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        self.assertTrue(self.ledger.verify_chain(run.run_id))

    def test_the_run_opens_and_closes_with_lifecycle_events(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        types = [e["event_type"] for e in self.events(run.run_id)]

        self.assertEqual(types[0], ev.RUN_CREATED)
        self.assertEqual(types[-1], ev.RUN_COMPLETED)

    def test_every_stage_event_carries_its_stage_identity(self) -> None:
        """``stage_id`` viaggia nel payload, che è nel preimage dell'hash."""
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        stage_events = [
            e for e in self.events(run.run_id)
            if e["event_type"] not in (ev.RUN_CREATED, ev.RUN_COMPLETED)
        ]

        self.assertTrue(stage_events)
        for event in stage_events:
            self.assertIn("stage_id", event["payload"])
            self.assertIn("producer", event["payload"])

    def test_two_runs_do_not_share_a_chain(self) -> None:
        first = self.run_case("CASE-1-therapy-evaluation-strong-match")
        second = self.run_case("CASE-2-therapy-discovery")

        self.assertNotEqual(first.run_id, second.run_id)
        self.assertTrue(self.ledger.verify_chain(first.run_id))
        self.assertTrue(self.ledger.verify_chain(second.run_id))


class NothingSensitiveReachesTheLedgerTest(OrchestratorTestBase):
    def test_no_event_carries_candidate_free_text(self) -> None:
        """``source_properties`` porta evidence statement in testo libero."""
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        serialized = json.dumps([e["payload"] for e in self.events(run.run_id)], default=str)
        self.assertNotIn("source_properties", serialized)

    def test_no_event_carries_document_text_or_reasoning(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        serialized = json.dumps([e["payload"] for e in self.events(run.run_id)], default=str)

        for forbidden in ('"full_text"', '"thinking"', '"reasoning"', '"chain_of_thought"'):
            self.assertNotIn(forbidden, serialized)


class ResearchFramingTest(OrchestratorTestBase):
    def test_the_run_declares_it_is_not_clinically_validated(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        notice = run.to_dict()["research_notice"]

        self.assertFalse(notice["clinically_validated"])
        self.assertTrue(notice["not_for_clinical_decision_making"])

    def test_graph_candidates_are_labelled_as_not_documentary_proof(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        preview = by_id["stage_5_kg_retrieval"].output_preview

        self.assertTrue(preview["graph_derived"])
        self.assertFalse(preview["documentary_proof"])

    def test_frozen_document_stages_are_labelled_as_replay(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}

        for stage_id in ("stage_6_document_resolution", "stage_7_source_units"):
            self.assertTrue(by_id[stage_id].output_preview.get("replayed"))

    def test_missing_gates_are_declared_not_silently_absent(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        preview = by_id["stage_11_deterministic_gates"].output_preview

        self.assertIn("source_gate", preview["not_implemented_gates"])
        self.assertIn("disease", preview["inherited_axes"])
