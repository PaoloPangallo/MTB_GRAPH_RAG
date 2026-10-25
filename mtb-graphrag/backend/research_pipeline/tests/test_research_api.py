"""Test degli endpoint REST e SSE del research runtime."""

from __future__ import annotations

import json
import os
import time
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock

from fastapi.testclient import TestClient

from backend.api import research_routes
from backend.api.main import app
from backend.research_pipeline import replay, run_store
from backend.research_pipeline import orchestrator
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod

BASE = "/api/v1/research/pipeline"
DEMO_CASE = "CASE-1-therapy-evaluation-strong-match"
STOPPED_CASE = "CASE-5-casecontext-mismatch-no-match"


class ResearchApiTestBase(TestCase):
    """Prove del contratto REST/SSE, del ledger e della provenienza.

    **Cosa viene sostituito e perché.** Il runtime canonico richiede davvero una
    cache documentale e un endpoint del modello: è la sua semantica, e c'è un
    test dedicato che verifica il 503 quando mancano. Queste prove misurano
    un'altra cosa — forma degli endpoint, ordine degli eventi, catena di hash,
    livelli di provenienza — e per farlo sostituiscono il layer documentale e il
    modello con gli adattatori congelati.

    La sostituzione avviene **dentro il test**, non attraverso l'API: la
    richiesta HTTP non ha alcun campo che possa chiedere il percorso storico, ed
    è esattamente ciò che questi test devono continuare a dimostrare.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {
            "VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "1",
            "RESEARCH_LEDGER_PATH": f"{self._tmp.name}/ledger.sqlite3",
        })
        self._env.start()
        self._patches = [
            # Precondizioni del runtime canonico: qui sono soddisfatte per
            # ipotesi, così il test può arrivare agli stage che vuole osservare.
            mock.patch.object(research_routes.llm_config, "resolve_endpoint",
                              return_value=("http://model.invalid", "test-key")),
            mock.patch.object(research_routes.cache_runtime, "is_available", return_value=True),
            mock.patch.object(run_store.DocumentRuntime, "open", classmethod(lambda cls: None)),
            mock.patch.object(run_store.orchestrator, "run_case", self._frozen_run_case),
        ]
        for patch in self._patches:
            patch.start()
        run_store.reset_store()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for patch in reversed(self._patches):
            patch.stop()
        self._env.stop()
        run_store.reset_store()
        self._tmp.cleanup()

    #: Riferimento alla funzione reale, catturato prima del patching.
    _real_run_case = staticmethod(run_store.orchestrator.run_case)

    @classmethod
    def _frozen_run_case(cls, **kwargs):
        """Esegue la pipeline reale sugli artefatti congelati del pilot."""
        kwargs.update(
            research_frozen_artifacts=True,
            source_units_by_id=run_store.da.load_source_unit_index(),
            retrieve_fn=retrieval_mod.retrieve_frozen_bundles,
            document_runtime=None,
            call_parser_fn=replay.parser_fn,
            call_enricher_fn=replay.enricher_fn,
            select_papers_fn=lambda a, u, **kw: replay.selection_fn(a, u, case_id=kw["case_id"]),
            validate_fn=lambda t, e, **kw: replay.validation_fn(
                t, e, case_id=kw["case_id"], paper_id=kw["paper_id"]),
            call_narrator_fn=replay.narrator_fn,
        )
        return cls._real_run_case(**kwargs)

    def run_demo(self, case_id: str = DEMO_CASE) -> str:
        """Avvia una run. Il corpo della richiesta contiene soltanto il caso."""
        response = self.client.post(f"{BASE}/runs", json={"demo_case_key": case_id})
        self.assertEqual(response.status_code, 201, response.text)
        run_id = response.json()["run_id"]
        for _ in range(300):
            snapshot = self.client.get(f"{BASE}/runs/{run_id}").json()
            if snapshot["status"] not in ("CREATED", "RUNNING"):
                return run_id
            time.sleep(0.1)
        self.fail("la run non si è conclusa entro il tempo previsto")


class FlagGatingTest(TestCase):
    """Con il flag disattivo il runtime non deve rivelare la propria esistenza."""

    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ, {"VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "0"})
        self._env.start()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._env.stop()

    def test_every_route_is_404_when_disabled(self) -> None:
        for path in (f"{BASE}/cases", f"{BASE}/config", f"{BASE}/runs",
                     f"{BASE}/runs/whatever", f"{BASE}/runs/whatever/events",
                     f"{BASE}/runs/whatever/dossier", f"{BASE}/runs/whatever/metrics",
                     f"{BASE}/runs/whatever/provenance"):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_creating_a_run_is_404_when_disabled(self) -> None:
        response = self.client.post(f"{BASE}/runs", json={"demo_case_key": DEMO_CASE})
        self.assertEqual(response.status_code, 404)

    def test_disabled_runtime_answers_404_and_not_403(self) -> None:
        self.assertNotEqual(self.client.get(f"{BASE}/cases").status_code, 403)

    def test_existing_endpoints_are_unaffected(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})


class ExistingApiIsUntouchedTest(ResearchApiTestBase):
    def test_health_still_works_with_the_research_runtime_enabled(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"status": "ok"})

    def test_openapi_still_builds(self) -> None:
        self.assertEqual(self.client.get("/openapi.json").status_code, 200)

    def test_v3_retrieve_route_is_still_registered(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/v1/v3/retrieve", paths)


class CacheGateRoutingTest(TestCase):
    def test_run_creation_defers_cache_requirement_until_branch_routing(self) -> None:
        client = TestClient(app)
        handle = SimpleNamespace(run_id="RUN-1", case_id="CASE-1", status="RUNNING")
        with (
            mock.patch.dict(os.environ, {"VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "1"}),
            mock.patch.object(research_routes.llm_config, "resolve_endpoint",
                              return_value=("http://model.invalid", "test-key")),
            mock.patch.object(research_routes.cache_runtime, "is_available", return_value=False),
            mock.patch.object(research_routes, "get_store") as store,
        ):
            store.return_value.start.return_value = handle
            response = client.post(f"{BASE}/runs", json={
                "case_id": "CASE-1", "clinical_text": "testo clinico valido",
            })

        self.assertEqual(response.status_code, 201, response.text)
        store.return_value.start.assert_called_once_with(
            case_id="CASE-1", clinical_text="testo clinico valido",
        )


class DemoCasesTest(ResearchApiTestBase):
    def test_five_synthetic_cases_are_offered(self) -> None:
        payload = self.client.get(f"{BASE}/cases").json()
        self.assertEqual(len(payload["cases"]), 5)
        self.assertTrue(payload["no_mock_outputs"])

    def test_config_reports_data_and_llm_state_without_the_key(self) -> None:
        payload = self.client.get(f"{BASE}/config").json()
        self.assertIn("stages_6_to_10_mode", payload["data"])
        self.assertNotIn("api_key", json.dumps(payload).lower().replace("credentials_configured", ""))

    def test_config_declares_no_unimplemented_stage(self) -> None:
        payload = self.client.get(f"{BASE}/config").json()
        self.assertEqual(payload["stages_not_implemented"], [])

    def test_config_declares_the_presentation_stages(self) -> None:
        """Narrator e verifier sono dichiarati come vista, non come evidenza."""
        payload = self.client.get(f"{BASE}/config").json()
        self.assertEqual(payload["presentation_stages"],
                         ["stage_14_narrator", "stage_15_narrative_verifier"])

    def test_config_declares_the_narrator_as_an_llm_stage(self) -> None:
        payload = self.client.get(f"{BASE}/config").json()
        self.assertIn("stage_14_narrator", payload["llm_stages"])
        self.assertNotIn("stage_15_narrative_verifier", payload["llm_stages"])

    def test_config_reports_narrator_disabled_by_default(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_NARRATOR_ENABLED": "0"}):
            payload = self.client.get(f"{BASE}/config").json()

        self.assertFalse(payload["runtime"]["narrator_enabled"])

    def test_config_reports_explicitly_enabled_narrator(self) -> None:
        with mock.patch.dict(os.environ, {"RESEARCH_NARRATOR_ENABLED": "1"}):
            payload = self.client.get(f"{BASE}/config").json()

        self.assertTrue(payload["runtime"]["narrator_enabled"])


class RunLifecycleTest(ResearchApiTestBase):
    def test_a_demo_run_completes_and_exposes_every_stage(self) -> None:
        run_id = self.run_demo()
        snapshot = self.client.get(f"{BASE}/runs/{run_id}").json()

        self.assertIn(snapshot["status"], ("COMPLETED", "PARTIAL"))
        from backend.research_pipeline.contracts import STAGE_SEQUENCE
        self.assertEqual(len(snapshot["stages"]), len(STAGE_SEQUENCE))

    def test_every_response_declares_the_research_framing(self) -> None:
        run_id = self.run_demo()
        notice = self.client.get(f"{BASE}/runs/{run_id}").json()["research_notice"]

        self.assertFalse(notice["clinically_validated"])
        self.assertTrue(notice["not_for_clinical_decision_making"])

    def test_a_stopped_run_is_not_a_failed_run(self) -> None:
        run_id = self.run_demo(STOPPED_CASE)
        snapshot = self.client.get(f"{BASE}/runs/{run_id}").json()

        self.assertEqual(snapshot["status"], "STOPPED")
        self.assertIsNotNone(snapshot["stopped_at"])

    def test_a_stopped_run_returns_a_clean_canonical_dossier(self) -> None:
        run_id = self.run_demo(STOPPED_CASE)
        response = self.client.get(f"{BASE}/runs/{run_id}/dossier")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["technical_run_status"], "STOPPED")
        dossier = response.json()["dossier"]
        self.assertIn(dossier["run_status"], {
            "INSUFFICIENT_CASE_CONTEXT", "NEEDS_CLARIFICATION", "NO_RELEVANT_KG_EVIDENCE",
        })
        self.assertEqual([], dossier["paper_evidence"])
        self.assertEqual([], dossier["clinical_trials"])
        self.assertEqual([], dossier["kg_only_relations"])

    def test_unknown_run_is_404(self) -> None:
        self.assertEqual(self.client.get(f"{BASE}/runs/does-not-exist").status_code, 404)

    def test_unknown_demo_case_is_404(self) -> None:
        response = self.client.post(f"{BASE}/runs", json={"demo_case_key": "CASE-99"})
        self.assertEqual(response.status_code, 404)

    def test_empty_request_is_rejected(self) -> None:
        self.assertEqual(self.client.post(f"{BASE}/runs", json={}).status_code, 422)

    def test_verified_dossier_response_exposes_deterministic_presentation(self) -> None:
        def valid_narrator(case_id, narrator_input, run_index=0):
            entries = []
            for candidate in narrator_input["candidates"]:
                entries.append({
                    "candidate_id": candidate["candidate_id"],
                    "text": (f"La candidate relativa a {candidate['drug']} mantiene stato "
                             f"{candidate['canonical_status']} e direzione "
                             f"{candidate['support_direction']}."),
                })
            narrative = {
                "narrative_summary": "Il sistema descrive il caso.",
                "candidate_narratives": entries,
                "limitations_summary": "Restano le limitazioni del dossier.",
                "closing_note": "Descrizione non prescrittiva.",
                "narrative_hash": "api-test-hash",
            }
            return {"transport_result": "FORCED_TOOL_VALID", "narrative": narrative}

        with mock.patch.object(replay, "narrator_fn", valid_narrator):
            run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()
        presentation = payload["presentation"]
        candidate = presentation["candidates"][0]

        assert presentation["presentation_mode"] == "VERIFIED_NARRATIVE", payload["narrative_verification"]
        paper = payload["dossier"]["paper_evidence"][0]
        assert candidate["canonical_status"] == "DOCUMENTARY_OBSERVATIONS"
        assert paper["legacy_aggregate"]["role"] == "COMPATIBILITY_ONLY_NOT_SCIENTIFIC_ENDPOINT"
        assert candidate["generated_explanation"]


class EventsTest(ResearchApiTestBase):
    def test_events_are_append_only_and_the_chain_verifies(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/events").json()

        self.assertTrue(payload["append_only"])
        self.assertTrue(payload["hash_chain_valid"])

    def test_events_are_ordered_by_sequence(self) -> None:
        run_id = self.run_demo()
        events = self.client.get(f"{BASE}/runs/{run_id}/events?limit=500").json()["events"]
        sequences = [e["sequence"] for e in events]

        self.assertEqual(sequences, sorted(sequences))

    def test_pagination_advances(self) -> None:
        run_id = self.run_demo()
        first = self.client.get(f"{BASE}/runs/{run_id}/events?limit=3").json()

        self.assertEqual(len(first["events"]), 3)
        self.assertTrue(first["has_more"])

        second = self.client.get(
            f"{BASE}/runs/{run_id}/events?after_sequence={first['next_after_sequence']}&limit=3").json()
        self.assertGreater(second["events"][0]["sequence"], first["events"][-1]["sequence"])

    def test_events_carry_stage_identity_and_producer(self) -> None:
        run_id = self.run_demo()
        events = self.client.get(f"{BASE}/runs/{run_id}/events?limit=500").json()["events"]
        stage_events = [e for e in events if e["stage_id"]]

        self.assertTrue(stage_events)
        self.assertTrue(all(e["producer"] for e in stage_events))

    def test_no_event_exposes_document_text_or_reasoning(self) -> None:
        run_id = self.run_demo()
        body = self.client.get(f"{BASE}/runs/{run_id}/events?limit=500").text

        for forbidden in ('"full_text"', '"thinking"', '"reasoning"', '"source_properties"'):
            self.assertNotIn(forbidden, body)


class StageAndProvenanceTest(ResearchApiTestBase):
    def test_v3_accepted_quote_is_document_grounded(self) -> None:
        snapshot = {
            "run_id": "RUN-v3", "case_id": "CASE-v3", "status": "COMPLETED",
            "stages": [
                {"stage_id": "stage_2_casecontext_parser", "output_preview": {"case_context": {}}},
                {"stage_id": "stage_3_casecontext_match", "output_preview": {"records": []}},
                {"stage_id": "stage_5_kg_retrieval", "output_preview": {"associations": [{
                    "candidate_id": "GCA-v3", "candidate": {}, "available_bundles": [],
                }]}},
                {"stage_id": "stage_6_document_resolution", "artifact_origin": "GENERATED_NOW",
                 "output_preview": {"documents": []}},
                {"stage_id": "stage_7_source_units", "output_preview": {"source_units": []}},
                {"stage_id": "stage_8_paper_selection", "output_preview": {"selections": [{
                    "candidate_id": "GCA-v3", "selected_papers": [],
                }]}},
                {"stage_id": "stage_9_paper_context_enricher", "output_preview": {"calls": [{
                    "candidate_id": "GCA-v3", "paper_id": "pmcid:PMC1",
                    "enrichment": {"source_unit_id": "SU-1", "author_claim_quote": "literal quote"},
                }]}},
                {"stage_id": "stage_10_enrichment_validation", "output_preview": {"validations": [{
                    "candidate_id": "GCA-v3", "paper_id": "pmcid:PMC1",
                    "outcome": "ENRICHMENT_V3_ACCEPTED",
                }]}},
                {"stage_id": "stage_11_deterministic_gates", "output_preview": {"checks_by_candidate": []}},
                {"stage_id": "stage_12_status", "output_preview": {"statuses": []}},
            ],
        }

        with mock.patch.object(research_routes, "_snapshot_or_404", return_value=snapshot):
            item = research_routes.get_provenance("RUN-v3")["items"][0]

        self.assertTrue(item["document_grounded"])
        self.assertEqual(item["provenance_level"], "DOCUMENT_GROUNDED")
        quote_level = next(level for level in item["chain"] if level["level"] == "AUTHOR_QUOTE")
        self.assertEqual(len(quote_level["accepted_quotes"]), 1)

    def test_a_single_stage_can_be_inspected_with_its_events(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/stages/stage_11_deterministic_gates").json()

        self.assertEqual(payload["stage"]["producer"]["kind"], "DETERMINISTIC")
        self.assertTrue(payload["events"])

    def test_unknown_stage_is_404(self) -> None:
        run_id = self.run_demo()
        response = self.client.get(f"{BASE}/runs/{run_id}/stages/stage_99")
        self.assertEqual(response.status_code, 404)

    def test_provenance_never_exposes_source_unit_text(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/provenance").json()

        for item in payload["items"]:
            for level in item["chain"]:
                if level["level"] == "SOURCE_UNIT":
                    self.assertTrue(level["text_never_exposed"])
                    for unit in level["units"]:
                        self.assertIsNone(unit["text"])

    def test_provenance_marks_candidates_as_not_documentary_proof(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/provenance").json()
        levels = [l for item in payload["items"] for l in item["chain"]
                  if l["level"] == "GRAPH_CANDIDATE_ASSERTION"]

        self.assertTrue(levels)
        self.assertTrue(all(l["graph_derived"] and not l["documentary_proof"] for l in levels))

    def test_the_chain_runs_from_casecontext_to_dossier_item(self) -> None:
        """Il relatore deve poter risalire un esito fino al campo del
        CaseContext senza uscire dalla catena."""
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/provenance").json()

        self.assertTrue(payload["items"])
        for item in payload["items"]:
            self.assertEqual(
                [level["level"] for level in item["chain"]],
                ["CASE_CONTEXT", "GRAPH_CANDIDATE_ASSERTION", "DOCUMENT",
                 "SOURCE_UNIT", "AUTHOR_QUOTE", "ENRICHMENT_VALIDATION",
                 "DETERMINISTIC_CHECK", "DOSSIER_ITEM"],
            )

    def test_a_candidate_without_an_accepted_quote_is_parent_level_only(self) -> None:
        """Senza quote accettata non c'è ancoraggio documentale, e presentarlo
        come document-grounded sarebbe la lettura che l'architettura impedisce."""
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/provenance").json()

        for item in payload["items"]:
            quote_level = next(l for l in item["chain"] if l["level"] == "AUTHOR_QUOTE")
            if item["document_grounded"]:
                self.assertTrue(quote_level["accepted_quotes"])
            else:
                self.assertEqual(item["provenance_level"], "PARENT_LEVEL_ONLY")
                self.assertFalse(quote_level["accepted_quotes"])

    def test_deterministic_check_level_carries_the_origin_of_each_axis(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/provenance").json()
        level = next(l for l in payload["items"][0]["chain"]
                     if l["level"] == "DETERMINISTIC_CHECK")
        checks = {c["check_id"]: c for c in level["checks"]}

        self.assertEqual(checks["disease"]["source"], "INHERITED_VERIFIED_RESULT")
        self.assertEqual(checks["direction"]["source"], "COMPUTED_HERE")

    def test_source_units_carry_locators_and_never_text(self) -> None:
        """Un'unità con il solo identificativo non è distinguibile da un'unità
        non risolta; una con il testo violerebbe il confine dei documenti."""
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}").json()
        stage = next(s for s in payload["stages"] if s["stage_id"] == "stage_7_source_units")
        units = stage["output_preview"]["source_units"]

        self.assertTrue(units)
        for unit in units:
            self.assertIn("unit_type", unit)
            self.assertIn("content_hash", unit)
            self.assertIn("document_id", unit)
            for forbidden in ("text", "content", "body"):
                self.assertNotIn(forbidden, unit)

    def test_the_quote_level_never_carries_source_unit_text(self) -> None:
        run_id = self.run_demo()
        body = self.client.get(f"{BASE}/runs/{run_id}/provenance").text

        for forbidden in ('"full_text"', '"thinking"', '"reasoning"'):
            self.assertNotIn(forbidden, body)


class MetricsTest(ResearchApiTestBase):
    def test_metrics_are_computed_by_the_backend(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/metrics").json()
        self.assertEqual(payload["computed_by"], "backend")

    def test_unmeasured_values_are_null_not_zero(self) -> None:
        """Uno zero al posto di un dato mancante sarebbe una misura falsa."""
        run_id = self.run_demo(STOPPED_CASE)
        payload = self.client.get(f"{BASE}/runs/{run_id}/metrics").json()
        self.assertIsNone(payload["tokens_input"])

    def test_duration_is_reported_per_stage(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/metrics").json()
        self.assertIn("stage_5_kg_retrieval", payload["duration_ms_by_stage"])


class SseTest(ResearchApiTestBase):
    def _stream(self, run_id: str, headers: dict[str, str] | None = None) -> str:
        with self.client.stream("GET", f"{BASE}/runs/{run_id}/stream",
                                headers=headers or {}) as response:
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            return "".join(response.iter_text())

    def test_stream_replays_the_whole_history_and_closes(self) -> None:
        run_id = self.run_demo()
        body = self._stream(run_id)

        self.assertIn("event: RUN_CREATED", body)
        self.assertIn("event: RUN_COMPLETED", body)

    def test_stream_ids_are_monotonic_sequences(self) -> None:
        run_id = self.run_demo()
        ids = [int(line.split(": ", 1)[1]) for line in self._stream(run_id).splitlines()
               if line.startswith("id: ")]

        self.assertTrue(ids)
        self.assertEqual(ids, sorted(ids))

    def test_last_event_id_resumes_instead_of_repeating(self) -> None:
        run_id = self.run_demo()
        full = [int(l.split(": ", 1)[1]) for l in self._stream(run_id).splitlines() if l.startswith("id: ")]
        resumed = [int(l.split(": ", 1)[1]) for l in
                   self._stream(run_id, {"Last-Event-ID": str(full[2])}).splitlines()
                   if l.startswith("id: ")]

        self.assertTrue(all(i > full[2] for i in resumed))

    def test_stream_of_a_stopped_run_closes_normally(self) -> None:
        """Un arresto corretto è una conclusione, non un guasto del trasporto."""
        run_id = self.run_demo(STOPPED_CASE)
        self.assertIn("event: RUN_COMPLETED", self._stream(run_id))

    def test_stream_data_matches_the_rest_event_shape(self) -> None:
        run_id = self.run_demo()
        body = self._stream(run_id)
        first = json.loads(next(l for l in body.splitlines() if l.startswith("data: "))[6:])
        rest = self.client.get(f"{BASE}/runs/{run_id}/events?limit=1").json()["events"][0]

        self.assertEqual(set(first), set(rest))
        self.assertEqual(first["event_id"], rest["event_id"])

    def test_stream_of_unknown_run_is_404(self) -> None:
        self.assertEqual(self.client.get(f"{BASE}/runs/nope/stream").status_code, 404)


class DossierContentTest(ResearchApiTestBase):
    def test_presentation_builder_failure_keeps_dossier_api_available(self) -> None:
        with mock.patch.object(orchestrator.narrative_presentation,
                               "build_narrative_presentation",
                               side_effect=RuntimeError("presentation exploded")):
            run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/dossier")
        self.assertEqual(payload.status_code, 200, payload.text)
        body = payload.json()
        self.assertTrue(body["dossier"]["paper_evidence"])
        self.assertIsNone(body["presentation"])
        self.assertIsNone(body["narrative"])
        self.assertEqual(body["presentation_mode"], "STRUCTURED_DOSSIER_FALLBACK")
        self.assertIn("NARRATIVE_PRESENTATION_INTERNAL_ERROR",
                      body["narrative_verification"]["reason_codes"])

    """Il dossier deve essere servito davvero, non soltanto contato."""

    def test_dossier_carries_the_three_sections(self) -> None:
        run_id = self.run_demo()
        dossier = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()["dossier"]

        for section in ("case_summary", "paper_evidence", "clinical_trials",
                        "kg_only_relations", "limitations"):
            self.assertIn(section, dossier)

    def test_dossier_response_exposes_a_deterministic_narrative_trace(self) -> None:
        run_id = self.run_demo()
        response = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()

        trace = response["narrative_trace"]
        self.assertEqual(trace["contract_version"], "dossier-narrative-trace/1.1")
        self.assertTrue(trace["trace_hash"])
        self.assertIsInstance(trace["candidates"], list)

    def test_each_candidate_separates_deterministic_evidence_from_author_context(self) -> None:
        run_id = self.run_demo()
        response = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()
        entry = response["legacy_dossier"]["candidate_therapies"][0]

        # Evidenza deterministica e contesto d'autore restano campi distinti:
        # l'author context non può essere scambiato per la claim.
        for deterministic in ("graph_relation", "document_support", "gate_results", "status"):
            self.assertIn(deterministic, entry)
        self.assertIn("author_context", entry)

    def test_dossier_declares_that_gemma_never_decides(self) -> None:
        run_id = self.run_demo()
        response = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()
        provenance = response["legacy_dossier"]["provenance"]

        self.assertEqual(provenance["gemma_role"], "paper_context_enricher_only")
        for decision in ("support_status", "direction", "gate", "score", "bucket"):
            self.assertIn(decision, provenance["gemma_never_decides"])

    def test_dossier_exposes_no_redacted_field(self) -> None:
        run_id = self.run_demo()
        body = self.client.get(f"{BASE}/runs/{run_id}/dossier").text

        for forbidden in ('"source_properties"', '"full_text"', '"thinking"', '"reasoning"'):
            self.assertNotIn(forbidden, body)
