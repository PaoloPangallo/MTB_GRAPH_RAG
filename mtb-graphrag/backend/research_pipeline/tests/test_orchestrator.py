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
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod


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
            # RESEARCH / REGRESSION. Questi test rigiocano gli output congelati
            # del parser sul corpus congelato del pilot: vanno dichiarati come
            # tali, perché il runtime canonico senza cache documentale fallisce —
            # che è esattamente il comportamento voluto.
            "research_frozen_artifacts": True,
            "retrieve_fn": retrieval_mod.retrieve_frozen_bundles,
        }
        kwargs.update(overrides)
        return orchestrator.run_case(**kwargs)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        return self.ledger.events(run_id)


class EveryStageIsAccountedForTest(OrchestratorTestBase):
    def test_all_stages_appear_in_declared_order(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")

        self.assertEqual([s.stage_id for s in run.stages], list(STAGE_SEQUENCE))
        self.assertEqual([s.sequence for s in run.stages],
                         list(range(1, len(STAGE_SEQUENCE) + 1)))

    def test_the_eligibility_gate_is_executed(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        gate = next(s for s in run.stages
                    if s.stage_id == "stage_3b_pre_retrieval_eligibility_gate")
        self.assertNotEqual(gate.status, "SKIPPED")
        self.assertEqual(gate.output_preview["eligibility_status"], "ELIGIBLE_FOR_RETRIEVAL")
        self.assertEqual(gate.output_preview["producer"], "DETERMINISTIC")

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


class NarrationStagesTest(OrchestratorTestBase):
    """Gli stage 14-15 sono eseguiti e restano una vista di presentazione."""

    def test_narration_stages_are_executed_not_skipped(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}

        for stage_id in ("stage_14_narrator", "stage_15_narrative_verifier"):
            self.assertNotEqual(by_id[stage_id].status, "SKIPPED")

    def test_canonical_dossier_is_built_before_narration(self) -> None:
        """L'ordine e' il contratto: il dossier esiste prima del Narrator."""
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        order = [s.stage_id for s in run.stages]
        self.assertLess(order.index("stage_13_dossier"), order.index("stage_14_narrator"))
        self.assertLess(order.index("stage_14_narrator"),
                        order.index("stage_15_narrative_verifier"))

        events = [e["event_type"] for e in self.events(run.run_id)]
        self.assertIn(ev.DOSSIER_BUILT, events)
        narration = [e for e in events if e.startswith("NARRATION")]
        if narration:
            self.assertLess(events.index(ev.DOSSIER_BUILT), events.index(narration[0]))

    def test_narration_failure_does_not_invalidate_the_canonical_dossier(self) -> None:
        """Senza narratore configurato il dossier resta intatto."""
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        dossier = by_id["stage_13_dossier"].output_preview["dossier"]

        self.assertEqual(by_id["stage_13_dossier"].status, "SUCCEEDED")
        self.assertTrue(dossier["candidate_therapies"])
        verification = by_id["stage_15_narrative_verifier"].output_preview
        self.assertEqual(verification["presentation_mode"], "STRUCTURED_DOSSIER_FALLBACK")
        self.assertIsNone(verification["verified_narrative"])

    def test_no_event_vocabulary_entry_is_unemittable(self) -> None:
        self.assertEqual(ev.NEVER_EMITTED, frozenset())


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

    def test_retrieval_no_match_skips_every_downstream_stage_with_that_reason(self) -> None:
        run = self.run_case("CASE-5-casecontext-mismatch-no-match")
        by_id = {s.stage_id: s for s in run.stages}

        self.assertEqual(run.stopped_at, "RETRIEVAL_NO_MATCH")
        for stage_id in ("stage_6_document_resolution", "stage_7_source_units",
                         "stage_8_paper_selection", "stage_9_paper_context_enricher",
                         "stage_10_enrichment_validation", "stage_11_deterministic_gates",
                         "stage_12_status", "stage_13_dossier"):
            self.assertEqual(by_id[stage_id].status, "SKIPPED", stage_id)
            self.assertIn("RETRIEVAL_NO_MATCH", by_id[stage_id].reason_codes, stage_id)


class CaseContextMismatchStopTest(OrchestratorTestBase):
    """Il quinto arresto della pipeline non è raggiungibile dai casi dimostrativi.

    ``CASE-5`` fabbrica un gene inesistente, ma il verificatore lo trova
    davvero nel testo — il parser lo ha estratto fedelmente — quindi la run si
    ferma più a valle, su ``RETRIEVAL_NO_MATCH``. Il ramo
    ``CASECONTEXT_MISMATCH`` esiste per un caso diverso: un CaseContext che
    afferma qualcosa che nel testo **non c'è**. Senza un parser che lo produca
    quel ramo resta non esercitato dall'orchestratore, e il fatto che la UI lo
    rappresenti correttamente non sarebbe verificato da nulla.
    """

    class _HallucinatingParser:
        """Restituisce un CaseContext con una malattia assente dal testo."""

        def __call__(self, budget, case_id, clinical_text):  # noqa: ANN001, ANN204
            return {
                "transport_result": "FORCED_TOOL_VALID",
                "model": "gemma4:cloud",
                "prompt_version": "casecontext-parser-prompt/1.0",
                "case_context_raw": {
                    "case_id": case_id,
                    "query_intent": "THERAPY_EVALUATION",
                    "disease": {"raw_value": "pancreatic adenocarcinoma",
                                "normalized_value": "Pancreatic Adenocarcinoma",
                                "source_spans": []},
                    "biomarkers": [],
                    "previous_interventions": [],
                    "target_intervention": None,
                    "uncertainties": [],
                    "clinical_question": "",
                },
            }

    def test_a_field_absent_from_the_text_stops_the_run_before_retrieval(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match",
                            call_parser_fn=self._HallucinatingParser())

        self.assertEqual(run.status, "STOPPED")
        self.assertEqual(run.stopped_at, "CASECONTEXT_MISMATCH")
        self.assertNotEqual(run.status, "FAILED")

    def test_the_graph_is_never_queried_after_a_casecontext_mismatch(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match",
                            call_parser_fn=self._HallucinatingParser())
        by_id = {s.stage_id: s for s in run.stages}

        self.assertEqual(by_id["stage_5_kg_retrieval"].status, "SKIPPED")
        self.assertEqual(self.enricher.calls, [])

    def test_the_mismatched_field_is_visible_with_its_verification_record(self) -> None:
        """Il record di verifica è ciò che rende leggibile l'arresto: senza,
        la run direbbe di essersi fermata senza dire su quale campo."""
        run = self.run_case("CASE-1-therapy-evaluation-strong-match",
                            call_parser_fn=self._HallucinatingParser())
        match = {s.stage_id: s for s in run.stages}["stage_3_casecontext_match"]
        records = match.output_preview["records"]

        self.assertEqual(match.status, "WARNING")
        self.assertFalse(match.output_preview["essential_fields_pass"])
        disease = next(r for r in records if r["field"] == "disease")
        self.assertIn(disease["status"], ("MISMATCH", "MISSING_IN_TEXT", "UNCERTAIN"))


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
        """La marcatura vive nel contratto dello stage, non in una chiave del preview.

        Prima era ``output_preview["replayed"] = True``, scritta dall'orchestratore
        in modo incondizionato: valeva anche quando la cache era disponibile e la
        risoluzione sarebbe stata reale. Ora è ``artifact_origin``, e uno stage
        non può dichiararsi LIVE mentre rigioca un artefatto registrato.
        """
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}

        for stage_id in ("stage_6_document_resolution", "stage_7_source_units"):
            self.assertEqual(by_id[stage_id].artifact_origin, "RECORDED_REAL_RUN")
            self.assertEqual(by_id[stage_id].execution_mode, "REPLAY")

    def test_missing_gates_are_declared_not_silently_absent(self) -> None:
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        preview = by_id["stage_11_deterministic_gates"].output_preview
        checks = {c["check_id"]: c for c in preview["checks_by_candidate"][0]["checks"]}

        self.assertEqual(checks["source_gate"]["source"], "NOT_IMPLEMENTED")
        self.assertIsNone(checks["source_gate"]["source_stage"])

    def test_every_axis_declares_where_it_was_decided(self) -> None:
        """Senza l'origine, `disease: SUPPORTED` e `direction: SUPPORTED` si
        leggono come due controlli equivalenti; solo il secondo è deciso qui."""
        run = self.run_case("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        preview = by_id["stage_11_deterministic_gates"].output_preview
        checks = {c["check_id"]: c for c in preview["checks_by_candidate"][0]["checks"]}

        self.assertEqual(checks["disease"]["source"], "INHERITED_VERIFIED_RESULT")
        self.assertEqual(checks["disease"]["source_stage"], "stage_5_kg_retrieval")
        self.assertEqual(checks["direction"]["source"], "COMPUTED_HERE")
        self.assertEqual(checks["direction"]["source_stage"], "stage_11_deterministic_gates")


class FrozenReplayTest(OrchestratorTestBase):
    """Il replay degli artefatti del pilot deve mostrare il percorso positivo
    reale — 2 quote accettate, 1 rigettata, 4 astensioni — senza spacciarlo per
    un'esecuzione avvenuta ora."""

    def run_replayed(self, case_id: str):
        from backend.research_pipeline import replay
        return self.run_case(
            case_id,
            call_parser_fn=replay.parser_fn,
            call_enricher_fn=replay.enricher_fn,
            select_papers_fn=lambda a, u, **kw: replay.selection_fn(a, u, case_id=kw["case_id"]),
            validate_fn=lambda t, e, **kw: replay.validation_fn(
                t, e, case_id=kw["case_id"], paper_id=kw["paper_id"]),
        )

    def test_replayed_run_reaches_the_dossier(self) -> None:
        run = self.run_replayed("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}

        self.assertIn(run.status, ("COMPLETED", "PARTIAL"))
        self.assertEqual(by_id["stage_13_dossier"].status, "SUCCEEDED")

    def test_an_accepted_quote_reaches_the_gates(self) -> None:
        """CASE-1 ha una quote accettata nel pilot: deve arrivare allo status."""
        run = self.run_replayed("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        statuses = {s["status"] for s in by_id["stage_12_status"].output_preview["statuses"]}

        self.assertTrue(statuses)
        self.assertNotEqual(statuses, {"AMBIGUOUS"})

    def test_abstentions_do_not_reach_the_gates(self) -> None:
        """CASE-4 ha solo astensioni: nessun supporto documentale."""
        run = self.run_replayed("CASE-4-contradicted-or-resistance")
        by_id = {s.stage_id: s for s in run.stages}
        entries = by_id["stage_12_status"].output_preview["statuses"]

        for entry in entries:
            self.assertIn("NO_VALIDATED_ENRICHMENT_AVAILABLE", entry["warnings"])

    def test_replayed_stages_are_labelled(self) -> None:
        run = self.run_replayed("CASE-1-therapy-evaluation-strong-match")
        by_id = {s.stage_id: s for s in run.stages}
        selections = by_id["stage_8_paper_selection"].output_preview["selections"]

        self.assertTrue(all(s.get("replayed") for s in selections))

    def test_the_v2_to_gate_adapter_never_admits_a_rejection(self) -> None:
        from backend.research_pipeline.orchestrator import _accepted_for_gates

        for rejected in ("REJECTED_QUOTE_NOT_FOUND", "ENRICHMENT_V2_ABSTAINED",
                         "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS",
                         "REJECTED_SOURCE_UNIT", "REJECTED_TRANSPORT"):
            self.assertIsNone(_accepted_for_gates(rejected))

    def test_the_v2_to_gate_adapter_admits_only_the_pilot_accepted_set(self) -> None:
        from backend.research_pipeline.orchestrator import _accepted_for_gates

        self.assertEqual(_accepted_for_gates("ENRICHMENT_V2_ACCEPTED"), "ENRICHMENT_ACCEPTED")
        self.assertEqual(_accepted_for_gates("ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY"),
                         "ENRICHMENT_ACCEPTED_WITH_WARNING")
