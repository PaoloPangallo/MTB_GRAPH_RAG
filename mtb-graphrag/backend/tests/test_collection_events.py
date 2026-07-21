"""Test degli eventi di raccolta: colonne v2, record strutturati, sanitizzazione."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.runtime import run_agentic_collection
from backend.pipeline.control.recorder import ActionRecorder
from backend.pipeline.control.strategies.tool_registry import (
    REPAIRABLE_TOOLS,
    records_from_state,
    tool_version,
)


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _SequencedLLM:
    def __init__(self, payloads: list[dict[str, str]]) -> None:
        self._payloads = list(payloads)

    def invoke(self, messages: list[tuple[str, str]]) -> _Response:
        return _Response(json.dumps(self._payloads.pop(0)))


def _tools() -> dict[str, object]:
    return {
        "assess_complexity": lambda state: {**state, "complexity": "moderate"},
        "interpret_variant": lambda state: {
            **state,
            "escat_tier": "I-A",
            "variant_data": {
                "evidence_records": [
                    {
                        "subject": "Osimertinib",
                        "relation": "SENSITIVITY",
                        "object": "EGFR L858R",
                        "pmid": 27959700,
                        "evidence_level": "A",
                        "abstract": "y" * 4000,
                    }
                ]
            },
        },
        "identify_targets": lambda state: {
            **state,
            "drug_candidates": [{"drug_name": "Osimertinib", "evidence_level": "A"}],
        },
        "match_trials": lambda state: {
            **state,
            "trial_candidates": [{"nct_id": "NCT02296125", "phase": "Phase 3"}],
        },
        "check_resistance": lambda state: {
            **state,
            "resistance_data": [{"variant": "T790M", "pmid": 28779021}],
        },
        "enrich_oncokb": lambda state: {**state, "oncokb_enrichment": []},
    }


def _state() -> dict[str, object]:
    return {
        "gene": "EGFR",
        "variant": "L858R",
        "tumor_type": "Lung Adenocarcinoma",
        "alteration_type": "point_mutation",
        "therapy_line": "first-line",
        "mtb_goal": "clinical-trials",
        "enrich_with_oncokb": False,
        "variant_data": {},
        "drug_candidates": [],
        "trial_candidates": [],
        "resistance_data": [],
        "oncokb_enrichment": [],
    }


class ToolRegistryTest(TestCase):
    def test_records_are_routed_by_declared_output_path(self) -> None:
        state = {"variant_data": {"evidence_records": [{"pmid": 1}]}}

        kind, records = records_from_state("interpret_variant", state)

        self.assertEqual(kind, "evidence")
        self.assertEqual(records, [{"pmid": 1}])

    def test_tools_without_records_return_an_empty_list(self) -> None:
        kind, records = records_from_state("assess_complexity", {"complexity": "high"})

        self.assertEqual(records, [])
        self.assertEqual(kind, "")

    def test_missing_state_key_degrades_to_empty_rather_than_raising(self) -> None:
        self.assertEqual(records_from_state("match_trials", {}), ("trial", []))

    def test_repairable_tools_exclude_non_evidence_producers(self) -> None:
        self.assertNotIn("assess_complexity", REPAIRABLE_TOOLS)
        self.assertNotIn("enrich_oncokb", REPAIRABLE_TOOLS)
        self.assertIn("match_trials", REPAIRABLE_TOOLS)

    def test_every_registered_tool_declares_a_version(self) -> None:
        for tool in ("interpret_variant", "identify_targets", "match_trials"):
            self.assertNotEqual(tool_version(tool), "unknown")


class CollectionLedgerIntegrationTest(TestCase):
    def _run(self, tmp: str):
        llm = _SequencedLLM([
            {"tool": "interpret_variant", "rationale": "serve il profilo molecolare"},
            {"tool": "identify_targets", "rationale": "servono i bersagli"},
            {"tool": "match_trials", "rationale": "servono i trial"},
            {"tool": "finish", "rationale": "obiettivo raggiunto"},
        ])
        recorder = ActionRecorder(EventLedger(Path(tmp) / "ledger.sqlite3"))
        result = run_agentic_collection(
            _state(), recorder=recorder, planner_llm=llm, tool_registry=_tools()
        )
        return recorder, result

    def test_collection_writes_to_the_recorder_chain(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder, result = self._run(tmp)

            self.assertEqual(result.run_id, recorder.run_id)
            self.assertTrue(result.ledger_valid)
            report = recorder.chain_report()
            self.assertTrue(report.valid)
            # Tutta la raccolta è v2: una sola catena, un solo scrittore.
            self.assertEqual(report.v1_event_count, 0)

    def test_tool_completed_carries_structured_records_for_replay(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder, _ = self._run(tmp)

            completed = [e for e in recorder.events() if e["event_type"] == "tool_completed"]
            trials = next(e for e in completed if e["tool_name"] == "match_trials")

            self.assertEqual(trials["payload"]["record_kind"], "trial")
            self.assertEqual(trials["payload"]["records"][0]["nct_id"], "NCT02296125")

    def test_tool_events_populate_the_v2_action_columns(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder, _ = self._run(tmp)

            completed = [e for e in recorder.events() if e["event_type"] == "tool_completed"]
            event = completed[0]

            self.assertIsNotNone(event["action_id"])
            self.assertIsNotNone(event["parent_action_id"])
            self.assertEqual(event["tool_version"], tool_version(event["tool_name"]))
            self.assertEqual(event["completeness_status"], "complete")
            self.assertEqual(
                json.loads(event["query_or_arguments_json"])["gene"], "EGFR"
            )

    def test_abstracts_are_not_duplicated_into_the_ledger(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder, _ = self._run(tmp)

            serialized = json.dumps([dict(e) for e in recorder.events()], default=str)

            self.assertNotIn("y" * 200, serialized)
            # Il riferimento risolvibile resta, quindi l'abstract è ri-ottenibile.
            self.assertIn("27959700", serialized)

    def test_plan_decision_records_the_planning_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder, _ = self._run(tmp)

            decisions = [e for e in recorder.events() if e["event_type"] == "plan_decision"]

            self.assertTrue(decisions)
            self.assertEqual(decisions[0]["actor"], "llm_planner")
            self.assertEqual(decisions[0]["payload"]["planning_mode"], "llm_dynamic")

    def test_run_started_declares_the_orchestration_mode(self) -> None:
        with TemporaryDirectory() as tmp:
            recorder, _ = self._run(tmp)

            started = next(e for e in recorder.events() if e["event_type"] == "run_started")

            self.assertEqual(started["payload"]["orchestration_mode"], "agentic")


class FailureSanitizationTest(TestCase):
    def test_enriched_payloads_never_leak_credentials(self) -> None:
        def failing_tool(state: dict[str, object]) -> dict[str, object]:
            raise RuntimeError(
                "upstream failure token=sekrit123 at postgres://user:pass@internal-host/db"
            )

        tools = {**_tools(), "match_trials": failing_tool}
        llm = _SequencedLLM([
            {"tool": "interpret_variant", "rationale": "profilo"},
            {"tool": "identify_targets", "rationale": "bersagli"},
            {"tool": "match_trials", "rationale": "trial"},
        ])

        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "ledger.sqlite3"))
            result = run_agentic_collection(
                _state(), recorder=recorder, planner_llm=llm, tool_registry=tools
            )

            serialized = json.dumps([dict(e) for e in recorder.events()], default=str)
            self.assertNotIn("sekrit123", serialized)
            self.assertNotIn("internal-host", serialized)
            self.assertNotIn("sekrit123", json.dumps(result.errors))

    def test_failed_tool_marks_the_action_as_partial(self) -> None:
        def failing_tool(state: dict[str, object]) -> dict[str, object]:
            raise ConnectionError("KG non raggiungibile")

        tools = {**_tools(), "interpret_variant": failing_tool}
        llm = _SequencedLLM([{"tool": "interpret_variant", "rationale": "profilo"}])

        with TemporaryDirectory() as tmp:
            recorder = ActionRecorder(EventLedger(Path(tmp) / "ledger.sqlite3"))
            run_agentic_collection(
                _state(), recorder=recorder, planner_llm=llm, tool_registry=tools
            )

            failed = next(e for e in recorder.events() if e["event_type"] == "tool_failed")
            self.assertEqual(failed["completeness_status"], "partial")
            self.assertEqual(failed["payload"]["error_category"], "service_unavailable")
