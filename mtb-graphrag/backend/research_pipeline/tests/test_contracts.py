"""Test dei contratti di run e stage del research runtime.

Questi non sono test di struttura dati: codificano le invarianti che rendono
la pipeline verificabile dal relatore. In particolare la separazione dei ruoli
— quali stage possono essere prodotti da un LLM e quali no — è una proprietà
architetturale, e qui diventa eseguibile.
"""

from __future__ import annotations

import dataclasses
from unittest import TestCase

from backend.research_pipeline.contracts import (
    CORRECT_STOP_REASONS,
    LLM_STAGE_IDS,
    NOT_IMPLEMENTED_STAGE_IDS,
    RUN_STATUSES,
    STAGE_SEQUENCE,
    STAGE_STATUSES,
    STOP_REASONS,
    PipelineRun,
    PipelineStage,
    StageProducer,
    stage_type_for,
)


class StageSequenceTest(TestCase):
    def test_fifteen_stages_in_declared_order(self) -> None:
        self.assertEqual(len(STAGE_SEQUENCE), 15)
        self.assertEqual(STAGE_SEQUENCE[0], "stage_1_case_input")
        self.assertEqual(STAGE_SEQUENCE[-1], "stage_15_narrative_verifier")

    def test_stage_ids_are_unique(self) -> None:
        self.assertEqual(len(set(STAGE_SEQUENCE)), len(STAGE_SEQUENCE))

    def test_every_stage_has_a_type(self) -> None:
        for stage_id in STAGE_SEQUENCE:
            self.assertTrue(stage_type_for(stage_id))

    def test_unknown_stage_id_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            stage_type_for("stage_99_invented")


class RoleSeparationTest(TestCase):
    """L'invariante centrale: Gemma è un enricher, non un decisore."""

    def test_only_parser_and_enricher_are_llm_stages(self) -> None:
        self.assertEqual(
            LLM_STAGE_IDS,
            frozenset({"stage_2_casecontext_parser", "stage_9_paper_context_enricher"}),
        )

    def test_gate_and_status_stages_are_not_llm(self) -> None:
        for stage_id in ("stage_11_deterministic_gates", "stage_12_status"):
            self.assertNotIn(stage_id, LLM_STAGE_IDS)

    def test_llm_producer_is_rejected_on_a_deterministic_stage(self) -> None:
        producer = StageProducer(
            kind="LLM", component="gemma", version="1.0",
            model="gemma4:cloud", prompt_version="p/1.0",
        )
        with self.assertRaises(ValueError) as ctx:
            PipelineStage(
                stage_id="stage_11_deterministic_gates",
                stage_type="DETERMINISTIC_GATES",
                sequence=11, status="SUCCEEDED", producer=producer,
            )
        self.assertIn("stage_11_deterministic_gates", str(ctx.exception))

    def test_llm_producer_is_accepted_on_an_llm_stage(self) -> None:
        stage = PipelineStage(
            stage_id="stage_9_paper_context_enricher",
            stage_type="PAPER_CONTEXT_ENRICHER",
            sequence=9, status="SUCCEEDED",
            producer=StageProducer(
                kind="LLM", component="paper_context_enricher_v2", version="2.0",
                model="gemma4:cloud", prompt_version="paper-context-enricher-prompt/2.0",
            ),
        )
        self.assertEqual(stage.producer.kind, "LLM")

    def test_model_is_forbidden_on_a_deterministic_producer(self) -> None:
        """Un producer deterministico che dichiara un modello sarebbe una
        contraddizione: nessun modello ha contribuito a quel risultato."""
        with self.assertRaises(ValueError):
            StageProducer(kind="DETERMINISTIC", component="gates", version="1.3",
                          model="gemma4:cloud")

    def test_llm_producer_requires_model_and_prompt_version(self) -> None:
        with self.assertRaises(ValueError):
            StageProducer(kind="LLM", component="enricher", version="2.0")


class NotImplementedStagesTest(TestCase):
    def test_narrator_and_verifier_are_declared_not_implemented(self) -> None:
        self.assertEqual(
            NOT_IMPLEMENTED_STAGE_IDS,
            frozenset({"stage_14_narrator", "stage_15_narrative_verifier"}),
        )

    def test_a_not_implemented_stage_cannot_be_reported_as_succeeded(self) -> None:
        """Dichiararli eseguiti sarebbe simulazione: non esiste codice dietro."""
        with self.assertRaises(ValueError):
            PipelineStage(
                stage_id="stage_14_narrator", stage_type="DOSSIER_NARRATOR",
                sequence=14, status="SUCCEEDED",
                producer=StageProducer(kind="DETERMINISTIC", component="n", version="0"),
            )

    def test_a_not_implemented_stage_is_skipped_with_its_reason(self) -> None:
        stage = PipelineStage(
            stage_id="stage_14_narrator", stage_type="DOSSIER_NARRATOR",
            sequence=14, status="SKIPPED", reason_codes=("NOT_IMPLEMENTED",),
            producer=StageProducer(kind="DETERMINISTIC", component="orchestrator", version="1.0"),
        )
        self.assertIn("NOT_IMPLEMENTED", stage.reason_codes)


class SkippedStagesExplainThemselvesTest(TestCase):
    def test_skipped_requires_a_reason_code(self) -> None:
        """Uno stage saltato senza spiegazione è indistinguibile da un difetto."""
        with self.assertRaises(ValueError):
            PipelineStage(
                stage_id="stage_5_kg_retrieval", stage_type="KG_RETRIEVAL",
                sequence=5, status="SKIPPED",
                producer=StageProducer(kind="DETERMINISTIC", component="o", version="1"),
            )


class RunStatusTest(TestCase):
    def test_stopped_is_distinct_from_failed(self) -> None:
        self.assertIn("STOPPED", RUN_STATUSES)
        self.assertIn("FAILED", RUN_STATUSES)

    def test_correct_stops_are_not_failures(self) -> None:
        run = PipelineRun(
            run_id="r1", case_id="c1", status="STOPPED",
            started_at="2026-08-04T00:00:00+00:00",
            stopped_at="CASECONTEXT_MISMATCH", input_text="…",
        )
        self.assertEqual(run.status, "STOPPED")
        self.assertNotEqual(run.status, "FAILED")

    def test_stop_reason_must_be_known(self) -> None:
        with self.assertRaises(ValueError):
            PipelineRun(
                run_id="r1", case_id="c1", status="STOPPED",
                started_at="t", stopped_at="INVENTED_REASON", input_text="…",
            )

    def test_the_four_pilot_stop_reasons_are_preserved(self) -> None:
        """I quattro punti d'arresto del pilot restano, nell'ordine originale."""
        self.assertEqual(
            STOP_REASONS[:4],
            (
                "PARSER_TRANSPORT_FAILED",
                "CASECONTEXT_MISMATCH",
                "RETRIEVAL_NO_MATCH",
                "CALL_BUDGET_EXCEEDED",
            ),
        )

    def test_live_stop_reasons_are_failures_not_correct_outcomes(self) -> None:
        """Una run LIVE che non trova la cache non ha una risposta da mostrare.

        I tre arresti aggiunti con l'esecuzione documentale reale non compaiono
        in ``CORRECT_STOP_REASONS``: renderli come esiti legittimi permetterebbe
        di leggere un guasto di configurazione come un'astensione della pipeline.
        """
        live_stops = ("DOCUMENT_CACHE_UNAVAILABLE", "NO_DOCUMENT_RESOLVED", "LIVE_STAGE_FAILED")
        for reason in live_stops:
            self.assertIn(reason, STOP_REASONS)
            self.assertNotIn(reason, CORRECT_STOP_REASONS)

    def test_unknown_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PipelineRun(run_id="r", case_id="c", status="ALMOST_DONE",
                        started_at="t", input_text="x")

    def test_stage_statuses_include_skipped_and_warning(self) -> None:
        for expected in ("PENDING", "RUNNING", "SUCCEEDED", "WARNING", "FAILED", "SKIPPED"):
            self.assertIn(expected, STAGE_STATUSES)


class ImmutabilityTest(TestCase):
    def test_run_and_stage_are_frozen(self) -> None:
        self.assertTrue(dataclasses.fields(PipelineRun))
        run = PipelineRun(run_id="r", case_id="c", status="RUNNING",
                          started_at="t", input_text="x")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            run.status = "COMPLETED"  # type: ignore[misc]

    def test_advancing_a_run_produces_a_new_object(self) -> None:
        run = PipelineRun(run_id="r", case_id="c", status="RUNNING",
                          started_at="t", input_text="x")
        advanced = run.with_status("COMPLETED", completed_at="t2")

        self.assertEqual(run.status, "RUNNING")
        self.assertEqual(advanced.status, "COMPLETED")
        self.assertEqual(advanced.completed_at, "t2")


class ResearchNoticeTest(TestCase):
    def test_every_run_declares_it_is_not_clinically_validated(self) -> None:
        run = PipelineRun(run_id="r", case_id="c", status="RUNNING",
                          started_at="t", input_text="x")
        notice = run.research_notice()

        self.assertEqual(notice["runtime"], "VERIFIABLE_RESEARCH_RUNTIME")
        self.assertFalse(notice["clinically_validated"])
        self.assertTrue(notice["not_for_clinical_decision_making"])
