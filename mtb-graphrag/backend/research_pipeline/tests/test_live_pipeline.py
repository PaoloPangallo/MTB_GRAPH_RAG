"""Il percorso LIVE: cache, risoluzione documentale, SourceUnit, selezione,
enrichment, validazione, modalità e budget.

Nessuna chiamata reale al modello avviene qui. Le chiamate reali sono state
eseguite una sola volta e sono registrate in
``docs/verifiable_pipeline/live_end_to_end_report.md``: rifarle a ogni ``pytest``
consumerebbe il budget autorizzato e renderebbe la suite dipendente dalla
raggiungibilità di un servizio esterno. Ciò che questi test verificano è il
**cablaggio** — che lo stage giusto venga eseguito, con gli argomenti giusti,
e che un fallimento non venga sostituito da un artefatto registrato.

La cache documentale è quella reale, quando configurata: i test che la
richiedono si dichiarano saltati se non lo è, invece di costruire una finta
cache che proverebbe soltanto la coerenza della finzione.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock, skipUnless

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline import live_providers, orchestrator, replay
from backend.research_pipeline.documents import cache_runtime
from backend.research_pipeline.documents.live_resolution import (
    DocumentRuntime,
    load_source_units,
    resolve_documents,
)
from backend.research_pipeline.pipeline import CallBudget
from backend.research_pipeline.retrieval import kg_retrieval
from backend.research_pipeline.retrieval.paper_selection import (
    MAX_PAPERS_PER_ASSOCIATION,
    select_papers_for_association,
)

CACHE_AVAILABLE = cache_runtime.is_available()
CACHE_REASON = "cache documentale non configurata (RESEARCH_DOCUMENT_CACHE_PATH)"

CASE_1 = "CASE-1-therapy-evaluation-strong-match"


def _frozen_case_context(case_id: str) -> dict:
    return replay._parser_outputs_by_case()[case_id]["case_context_raw"]


def _case_text(case_id: str) -> str:
    from backend.research_pipeline.cases.definitions import CASES

    return next(case["clinical_text"] for case in CASES if case["case_id"] == case_id)


# --- Modalità e origine -----------------------------------------------------


class ExecutionModeTest(TestCase):
    def test_hybrid_cannot_be_requested(self) -> None:
        """È una constatazione sulla run, non una richiesta del chiamante."""
        with self.assertRaises(em.UnknownExecutionMode):
            em.normalize_requested_mode("HYBRID")

    def test_a_missing_mode_is_not_silently_defaulted(self) -> None:
        for value in (None, "", "  ", 3):
            with self.assertRaises(em.UnknownExecutionMode):
                em.normalize_requested_mode(value)

    def test_one_recorded_artifact_downgrades_a_live_run_to_hybrid(self) -> None:
        origins = [em.GENERATED_NOW] * 12 + [em.RECORDED_REAL_RUN]
        self.assertEqual(em.classify_run_mode(em.LIVE, origins), em.HYBRID)
        self.assertFalse(em.is_fully_live(em.LIVE, origins))

    def test_a_cached_document_does_not_downgrade_a_live_run(self) -> None:
        """Leggere un documento dalla cache è lettura di una fonte, non replay."""
        origins = [em.GENERATED_NOW] * 11 + [em.DETERMINISTIC_CACHE] * 2
        self.assertEqual(em.classify_run_mode(em.LIVE, origins), em.LIVE)
        self.assertEqual(em.count_replay_artifacts(origins), 0)
        self.assertTrue(em.is_fully_live(em.LIVE, origins))

    def test_a_replay_run_is_never_promoted_to_live(self) -> None:
        self.assertEqual(em.classify_run_mode(em.REPLAY, [em.GENERATED_NOW] * 13), em.REPLAY)

    def test_the_summary_counts_replay_artifacts(self) -> None:
        summary = em.summarize(em.LIVE, [em.GENERATED_NOW, em.RECORDED_REAL_RUN])
        self.assertEqual(summary["replay_artifacts_used"], 1)
        self.assertFalse(summary["fully_live"])
        self.assertEqual(summary["execution_mode"], em.HYBRID)


# --- Cache documentale ------------------------------------------------------


class DocumentCacheTest(TestCase):
    def test_an_absent_cache_is_reported_not_invented(self) -> None:
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope"
            available, reasons = cache_runtime.validate_cache(missing)
            self.assertFalse(available)
            self.assertIn("CACHE_PATH_NOT_FOUND", reasons)

    def test_an_empty_directory_is_not_a_cache(self) -> None:
        """Accettarla produrrebbe zero documenti, indistinguibili da assenti."""
        with TemporaryDirectory() as tmp:
            available, reasons = cache_runtime.validate_cache(Path(tmp))
            self.assertFalse(available)
            self.assertTrue(any("CACHE_LAYOUT_INCOMPLETE" in r for r in reasons))

    def test_requiring_an_absent_cache_raises_instead_of_falling_back(self) -> None:
        with TemporaryDirectory() as tmp:
            with self.assertRaises(cache_runtime.DocumentCacheUnavailable):
                cache_runtime.require_cache(Path(tmp) / "nope")

    def test_the_local_path_is_never_exposed_in_full(self) -> None:
        redacted = cache_runtime.redact_path(Path("C:/Users/someone/secret/data_cache/document_grounding"))
        self.assertNotIn("someone", redacted)
        self.assertTrue(redacted.startswith(".../"))

    def test_the_read_only_cache_refuses_to_write_or_fetch(self) -> None:
        cache = cache_runtime.ReadOnlyDocumentCache("/tmp/whatever")
        with self.assertRaises(cache_runtime.CacheIsReadOnly):
            cache._request("https://example.invalid")
        with self.assertRaises(cache_runtime.CacheIsReadOnly):
            cache._write_payload("pubmed/x.xml", b"x")
        with self.assertRaises(cache_runtime.CacheIsReadOnly):
            cache._record({"document_id": "x"})

    def test_opening_read_only_creates_no_directory(self) -> None:
        """``AuthorizedDocumentCache`` ne creava sette: una lettura che scrive."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "cache"
            cache_runtime.ReadOnlyDocumentCache(root)
            self.assertFalse(root.exists())

    @skipUnless(CACHE_AVAILABLE, CACHE_REASON)
    def test_the_descriptor_reports_the_manifest_hash_and_counts(self) -> None:
        descriptor = cache_runtime.describe().to_dict()
        self.assertTrue(descriptor["document_cache_available"])
        self.assertEqual(len(descriptor["manifest_hash"]), 64)
        self.assertGreater(descriptor["document_count"], 0)
        self.assertGreater(descriptor["source_unit_count"], 0)
        self.assertNotIn("Users", descriptor["cache_path_redacted"])


# --- Risoluzione documentale e SourceUnit -----------------------------------


@skipUnless(CACHE_AVAILABLE, CACHE_REASON)
class LiveDocumentResolutionTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = DocumentRuntime.open()
        cls.associations = kg_retrieval.retrieve(_frozen_case_context(CASE_1))["associations"]

    def test_documents_are_resolved_from_the_cache_during_the_run(self) -> None:
        resolution = self.runtime.resolve(self.associations)
        self.assertTrue(resolution.documents)
        for document in resolution.documents:
            self.assertTrue(document.resolved)
            self.assertTrue(document.cache_hit)
            self.assertIn("DOCUMENT_RESOLVED_FROM_CACHE", document.reason_codes)

    def test_resolution_declares_that_no_network_fetch_happened(self) -> None:
        self.assertFalse(self.runtime.resolve(self.associations).to_preview()["network_fetch_used"])

    def test_an_unknown_document_is_unavailable_not_substituted(self) -> None:
        association = [{"candidate_id": "GCA-x", "available_bundles": [
            {"bundle_id": "EB-x", "document_id": "pmid:00000000", "source_unit_ids": []}]}]
        resolution = resolve_documents(association, {}, self.runtime.cache)
        document = resolution.documents[0]
        self.assertFalse(document.resolved)
        self.assertIn("DOCUMENT_UNAVAILABLE", document.reason_codes)
        self.assertEqual(resolution.cache_misses, 1)

    def test_source_units_are_materialized_with_exact_text(self) -> None:
        resolution = self.runtime.resolve(self.associations)
        bundle = self.runtime.load_units(resolution)
        self.assertTrue(bundle.units_by_id)
        self.assertEqual(bundle.with_text, len(bundle.units_by_id))

    def test_rebuilt_units_match_the_committed_index_hashes(self) -> None:
        """Gli ID derivano dall'hash del contenuto: coincidere è la prova."""
        from backend.research_pipeline import data_access as da

        resolution = self.runtime.resolve(self.associations)
        bundle = self.runtime.load_units(resolution)
        index = da.load_source_unit_index()
        shared = set(bundle.units_by_id) & set(index)
        self.assertTrue(shared)
        for unit_id in shared:
            self.assertEqual(
                bundle.units_by_id[unit_id]["content_hash"], index[unit_id]["content_hash"])

    def test_the_preview_carries_locators_and_never_the_full_text(self) -> None:
        resolution = self.runtime.resolve(self.associations)
        bundle = self.runtime.load_units(resolution)
        preview = bundle.to_preview()

        self.assertTrue(preview["text_never_exposed"])
        for unit in preview["source_units"]:
            self.assertNotIn("text", unit)
            self.assertIn("content_hash", unit)
            self.assertIn("locator", unit)
            full = bundle.units_by_id[unit["source_unit_id"]]["text"]
            if len(full) > preview["preview_chars"]:
                self.assertLess(len(unit["text_preview"]), len(full))

    def test_a_document_that_fails_to_parse_is_recorded_not_crashed(self) -> None:
        resolution = self.runtime.resolve(self.associations)
        with mock.patch.object(
            type(self.runtime.cache), "source_units_for_record",
            side_effect=ValueError("broken xml"),
        ):
            bundle = load_source_units(
                resolution, self.runtime.manifest_by_document_id, self.runtime.cache)
        self.assertTrue(bundle.documents_failed)
        self.assertIn("SOURCE_UNIT_PARSE_FAILED", bundle.documents_failed[0]["reason_codes"])


# --- Paper selection --------------------------------------------------------


@skipUnless(CACHE_AVAILABLE, CACHE_REASON)
class LivePaperSelectionTest(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = DocumentRuntime.open()

    def _selection(self, case_id: str) -> list[dict]:
        associations = kg_retrieval.retrieve(_frozen_case_context(case_id))["associations"]
        bundle = self.runtime.load_units(self.runtime.resolve(associations))
        return [select_papers_for_association(a, bundle.units_by_id) for a in associations]

    def test_selection_admits_papers_once_the_text_is_there(self) -> None:
        """Con l'indice nudo ogni paper era escluso per TEXT_NOT_AVAILABLE_IN_CACHE."""
        selections = self._selection(CASE_1)
        self.assertTrue(any(s["selected_papers"] for s in selections))
        for selection in selections:
            for excluded in selection["excluded_papers"]:
                self.assertNotIn("TEXT_NOT_AVAILABLE_IN_CACHE", excluded["reason_codes"])

    def test_never_more_than_two_papers_per_association(self) -> None:
        for case_id in replay.frozen_case_ids():
            for selection in self._selection(case_id):
                self.assertLessEqual(len(selection["selected_papers"]), MAX_PAPERS_PER_ASSOCIATION)

    def test_never_more_than_four_source_units_per_paper(self) -> None:
        for case_id in replay.frozen_case_ids():
            for selection in self._selection(case_id):
                for paper in selection["selected_papers"]:
                    self.assertLessEqual(len(paper["resolved_source_unit_ids"]), 4)

    def test_the_excess_papers_say_why_they_were_dropped(self) -> None:
        for selection in self._selection("CASE-3-partial-incomplete-context"):
            for excluded in selection["excluded_papers"]:
                self.assertTrue(excluded["reason_codes"])


# --- Cablaggio dell'enricher e del validatore -------------------------------


class LiveProviderWiringTest(TestCase):
    def test_the_enricher_receives_its_arguments_in_the_right_order(self) -> None:
        """L'orchestratore passa il budget per primo; ``call_enricher_v2`` no.

        Il difetto precedente faceva scivolare ogni argomento di una posizione,
        e la chiamata sarebbe partita con identificativi sbagliati.
        """
        seen: dict = {}

        def fake(case_id, candidate_id, paper_id, case_context, summary, drug, units, run_index=0):
            seen.update(case_id=case_id, candidate_id=candidate_id, paper_id=paper_id,
                        drug=drug, units=units)
            return {"transport_result": "V2_TRANSPORT_VALID", "enrichment": None}

        budget = CallBudget(5)
        with mock.patch("backend.research_pipeline.enrichment.enricher_v2.call_enricher_v2", fake):
            live_providers.enricher_fn(budget, "CASE-A", "GCA-1", "EB-1", {}, {}, "drugX", [{"a": 1}])

        self.assertEqual(seen["case_id"], "CASE-A")
        self.assertEqual(seen["candidate_id"], "GCA-1")
        self.assertEqual(seen["paper_id"], "EB-1")
        self.assertEqual(seen["drug"], "drugX")

    def test_every_live_call_spends_the_budget(self) -> None:
        budget = CallBudget(2)
        with mock.patch("backend.research_pipeline.enrichment.enricher_v2.call_enricher_v2",
                        return_value={"transport_result": "V2_TRANSPORT_VALID", "enrichment": None}):
            live_providers.enricher_fn(budget, "C", "G", "P", {}, {}, "d", [])
            live_providers.enricher_fn(budget, "C", "G", "P", {}, {}, "d", [])
            self.assertEqual(budget.used, 2)
            with self.assertRaises(RuntimeError):
                live_providers.enricher_fn(budget, "C", "G", "P", {}, {}, "d", [])

    def test_a_provider_failure_becomes_a_live_stage_failure(self) -> None:
        """Non un'astensione: la differenza fra "si è astenuto" e "non ho chiamato"."""
        with mock.patch("backend.research_pipeline.enrichment.enricher_v2.call_enricher_v2",
                        side_effect=ConnectionError("refused")):
            with self.assertRaises(live_providers.LiveStageFailed) as caught:
                live_providers.enricher_fn(CallBudget(2), "C", "G", "P", {}, {}, "d", [])
        self.assertEqual(caught.exception.reason_code, "LIVE_STAGE_FAILED")

    def test_the_v2_validator_is_the_one_that_runs(self) -> None:
        """Il default era il v1, che rigettava ogni enrichment v2 sul transport."""
        units = {"SU-1": {"source_unit_id": "SU-1", "text": "osimertinib improves survival here."}}
        enrichment = {
            "decision": "QUOTE", "source_unit_id": "SU-1",
            "author_claim_quote": "osimertinib improves survival",
            "author_context_summary": "", "abstention_reason": "",
        }
        result = live_providers.validate_fn(
            "V2_TRANSPORT_VALID", enrichment,
            candidate={"candidate_id": "GCA-1", "disease": [], "biomarkers": []},
            paper_bundle={"bundle_id": "EB-1", "resolved_source_unit_ids": ["SU-1"]},
            source_units_by_id=units, requested_drug="osimertinib",
        )
        self.assertEqual(result["validator"], "PaperContextEnrichmentV2Validator")
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")

    def test_a_quote_absent_from_the_source_unit_is_rejected(self) -> None:
        units = {"SU-1": {"source_unit_id": "SU-1", "text": "nothing relevant here"}}
        enrichment = {
            "decision": "QUOTE", "source_unit_id": "SU-1",
            "author_claim_quote": "a sentence the authors never wrote",
            "author_context_summary": "", "abstention_reason": "",
        }
        result = live_providers.validate_fn(
            "V2_TRANSPORT_VALID", enrichment,
            candidate={"candidate_id": "GCA-1"},
            paper_bundle={"bundle_id": "EB-1", "resolved_source_unit_ids": ["SU-1"]},
            source_units_by_id=units, requested_drug="",
        )
        self.assertEqual(result["outcome"], "REJECTED_QUOTE_NOT_FOUND")

    def test_an_invented_source_unit_is_rejected(self) -> None:
        result = live_providers.validate_fn(
            "V2_TRANSPORT_VALID",
            {"decision": "QUOTE", "source_unit_id": "SU-does-not-exist",
             "author_claim_quote": "x", "author_context_summary": "", "abstention_reason": ""},
            candidate={"candidate_id": "GCA-1"},
            paper_bundle={"bundle_id": "EB-1", "resolved_source_unit_ids": []},
            source_units_by_id={}, requested_drug="",
        )
        self.assertEqual(result["outcome"], "REJECTED_SOURCE_UNIT")

    def test_an_accepted_quote_reports_its_offset(self) -> None:
        units = {"SU-1": {"source_unit_id": "SU-1", "text": "prefix. osimertinib works."}}
        result = live_providers.validate_fn(
            "V2_TRANSPORT_VALID",
            {"decision": "QUOTE", "source_unit_id": "SU-1",
             "author_claim_quote": "osimertinib works",
             "author_context_summary": "", "abstention_reason": ""},
            candidate={"candidate_id": "GCA-1"},
            paper_bundle={"bundle_id": "EB-1", "resolved_source_unit_ids": ["SU-1"]},
            source_units_by_id=units, requested_drug="osimertinib",
        )
        self.assertEqual(result["quote_offset"], 8)

    def test_an_abstention_with_populated_fields_is_flagged(self) -> None:
        result = live_providers.validate_fn(
            "V2_TRANSPORT_VALID",
            {"decision": "ABSTAIN", "source_unit_id": "SU-1",
             "author_claim_quote": "", "author_context_summary": "", "abstention_reason": "no data"},
            candidate={"candidate_id": "GCA-1"},
            paper_bundle={"bundle_id": "EB-1", "resolved_source_unit_ids": ["SU-1"]},
            source_units_by_id={}, requested_drug="",
        )
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS")


# --- Nessun fallback --------------------------------------------------------


class NoSilentFallbackTest(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.ledger = EventLedger(Path(self._tmp.name) / "ledger.sqlite3")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, **overrides):
        # Il testo reale del caso: con un testo qualsiasi il verificatore si
        # fermerebbe prima, e il test non raggiungerebbe mai lo stage 6.
        kwargs = {
            "case_id": CASE_1,
            "clinical_text": _case_text(CASE_1),
            "call_parser_fn": lambda *a, **k: {
                **replay._parser_outputs_by_case()[CASE_1], "replayed": False},
            "call_enricher_fn": lambda *a, **k: {
                "transport_result": "V2_TRANSPORT_VALID", "enrichment": None,
                "model": "gemma4:cloud", "prompt_version": "p/2.0", "transport_version": "t/2.0"},
            "source_units_by_id": {},
            "budget": CallBudget(10),
            "ledger": self.ledger,
            "execution_mode": em.LIVE,
            "document_runtime": None,
        }
        kwargs.update(overrides)
        return orchestrator.run_case(**kwargs)

    def test_a_live_run_without_the_cache_fails_and_does_not_replay(self) -> None:
        run = self._run()

        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.stopped_at, "DOCUMENT_CACHE_UNAVAILABLE")
        self.assertEqual(run.mode_summary()["replay_artifacts_used"], 0)
        by_id = {s.stage_id: s for s in run.stages}
        self.assertEqual(by_id["stage_6_document_resolution"].status, "FAILED")
        # Nessuno stage a valle si è "salvato" con un artefatto registrato.
        for stage_id in ("stage_9_paper_context_enricher", "stage_10_enrichment_validation"):
            self.assertEqual(by_id[stage_id].status, "SKIPPED")
            self.assertEqual(by_id[stage_id].artifact_origin, em.NOT_EXECUTED)

    def test_a_failed_live_stage_stops_the_run_with_its_reason(self) -> None:
        def failing(*args, **kwargs):
            raise live_providers.LiveStageFailed(
                "stage_2_casecontext_parser", "LIVE_STAGE_FAILED", "connection refused")

        run = self._run(call_parser_fn=failing)

        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.stopped_at, "LIVE_STAGE_FAILED")
        parser = {s.stage_id: s for s in run.stages}["stage_2_casecontext_parser"]
        self.assertEqual(parser.status, "FAILED")
        self.assertIn("connection refused", parser.errors[0])
        self.assertEqual(parser.artifact_origin, em.NOT_EXECUTED)

    def test_a_stage_cannot_claim_live_while_replaying(self) -> None:
        from backend.research_pipeline.contracts import PipelineStage, StageProducer

        with self.assertRaises(ValueError):
            PipelineStage(
                stage_id="stage_9_paper_context_enricher",
                stage_type="PAPER_CONTEXT_ENRICHER", sequence=9, status="SUCCEEDED",
                producer=StageProducer(kind="LLM", component="e", version="1",
                                       model="m", prompt_version="p"),
                execution_mode=em.LIVE, artifact_origin=em.RECORDED_REAL_RUN,
            )


# --- CASE-6: CaseContext mismatch -------------------------------------------


class CaseContextMismatchTest(TestCase):
    """CASE-6 — ``CASECONTEXT_MISMATCH``.

    Resta un **test automatico** e non una demo live: produrlo dal modello reale
    richiederebbe che il parser inventi un campo che il testo non contiene, cosa
    che non si può chiedere in modo affidabile e che non sarebbe onesto mettere
    in scena. Qui il CaseContext divergente è costruito esplicitamente ed è
    etichettato come scenario di test.

    Ciò che il test verifica è reale: il verificatore, i controlli a valle e gli
    stage saltati sono quelli di produzione.
    """

    TEST_SCENARIO = "TEST SCENARIO — CaseContext non riscontrato nel testo"

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.ledger = EventLedger(Path(self._tmp.name) / "ledger.sqlite3")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _mismatched_parser(self, *args, **kwargs) -> dict:
        """CaseContext che nomina una malattia assente dal testo clinico."""
        frozen = replay._parser_outputs_by_case()[CASE_1]
        context = json.loads(json.dumps(frozen["case_context_raw"]))
        context["disease"] = {"raw_value": "acute myeloid leukemia",
                              "normalized_value": "Acute Myeloid Leukemia"}
        return {**frozen, "case_context_raw": context, "scenario": self.TEST_SCENARIO}

    def test_a_case_context_not_found_in_the_text_stops_the_run(self) -> None:
        run = orchestrator.run_case(
            case_id="CASE-6-casecontext-mismatch",
            clinical_text=("A patient with metastatic colorectal cancer has been found to "
                           "carry a KRAS G12D mutation on molecular testing of the tumor."),
            call_parser_fn=self._mismatched_parser,
            call_enricher_fn=lambda *a, **k: self.fail("Gemma non deve essere chiamato"),
            source_units_by_id={}, budget=CallBudget(10), ledger=self.ledger,
            execution_mode=em.REPLAY,
        )

        self.assertEqual(run.status, "STOPPED")
        self.assertEqual(run.stopped_at, "CASECONTEXT_MISMATCH")

    def test_retrieval_documents_and_gemma_are_all_skipped(self) -> None:
        run = orchestrator.run_case(
            case_id="CASE-6-casecontext-mismatch",
            clinical_text="A patient with metastatic colorectal cancer and a KRAS G12D mutation.",
            call_parser_fn=self._mismatched_parser,
            call_enricher_fn=lambda *a, **k: self.fail("Gemma non deve essere chiamato"),
            source_units_by_id={}, budget=CallBudget(10), ledger=self.ledger,
            execution_mode=em.REPLAY,
        )
        by_id = {s.stage_id: s for s in run.stages}

        for stage_id in ("stage_5_kg_retrieval", "stage_6_document_resolution",
                         "stage_9_paper_context_enricher", "stage_13_dossier"):
            self.assertEqual(by_id[stage_id].status, "SKIPPED", stage_id)
            self.assertIn("CASECONTEXT_MISMATCH", by_id[stage_id].reason_codes)
            self.assertEqual(by_id[stage_id].artifact_origin, em.NOT_EXECUTED)

    def test_the_mismatch_is_a_correct_stop_not_a_failure(self) -> None:
        from backend.research_pipeline.contracts import CORRECT_STOP_REASONS

        self.assertIn("CASECONTEXT_MISMATCH", CORRECT_STOP_REASONS)
