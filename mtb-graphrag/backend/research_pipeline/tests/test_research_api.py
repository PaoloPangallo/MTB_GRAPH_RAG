"""Test degli endpoint REST e SSE del research runtime."""

from __future__ import annotations

import json
import os
import time
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.research_pipeline import run_store

BASE = "/api/v1/research/pipeline"
DEMO_CASE = "CASE-1-therapy-evaluation-strong-match"
STOPPED_CASE = "CASE-5-casecontext-mismatch-no-match"


class ResearchApiTestBase(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {
            "VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "1",
            "RESEARCH_LEDGER_PATH": f"{self._tmp.name}/ledger.sqlite3",
        })
        self._env.start()
        run_store.reset_store()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._env.stop()
        run_store.reset_store()
        self._tmp.cleanup()

    def run_demo(self, case_id: str = DEMO_CASE) -> str:
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


class DemoCasesTest(ResearchApiTestBase):
    def test_five_synthetic_cases_are_offered(self) -> None:
        payload = self.client.get(f"{BASE}/cases").json()
        self.assertEqual(len(payload["cases"]), 5)
        self.assertTrue(payload["no_mock_outputs"])

    def test_config_reports_data_and_llm_state_without_the_key(self) -> None:
        payload = self.client.get(f"{BASE}/config").json()
        self.assertIn("stages_6_to_10_mode", payload["data"])
        self.assertNotIn("api_key", json.dumps(payload).lower().replace("credentials_configured", ""))

    def test_config_declares_the_not_implemented_stages(self) -> None:
        payload = self.client.get(f"{BASE}/config").json()
        self.assertIn("stage_14_narrator", payload["stages_not_implemented"])


class RunLifecycleTest(ResearchApiTestBase):
    def test_a_demo_run_completes_and_exposes_every_stage(self) -> None:
        run_id = self.run_demo()
        snapshot = self.client.get(f"{BASE}/runs/{run_id}").json()

        self.assertIn(snapshot["status"], ("COMPLETED", "PARTIAL"))
        self.assertEqual(len(snapshot["stages"]), 15)

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

    def test_a_stopped_run_has_no_dossier_and_says_why(self) -> None:
        run_id = self.run_demo(STOPPED_CASE)
        response = self.client.get(f"{BASE}/runs/{run_id}/dossier")

        self.assertEqual(response.status_code, 409)
        self.assertIn("STOPPED", response.json()["detail"])

    def test_unknown_run_is_404(self) -> None:
        self.assertEqual(self.client.get(f"{BASE}/runs/does-not-exist").status_code, 404)

    def test_unknown_demo_case_is_404(self) -> None:
        response = self.client.post(f"{BASE}/runs", json={"demo_case_key": "CASE-99"})
        self.assertEqual(response.status_code, 404)

    def test_empty_request_is_rejected(self) -> None:
        self.assertEqual(self.client.post(f"{BASE}/runs", json={}).status_code, 422)


class EventsTest(ResearchApiTestBase):
    def test_events_are_append_only_and_the_chain_verifies(self) -> None:
        run_id = self.run_demo()
        payload = self.client.get(f"{BASE}/runs/{run_id}/events").json()

        self.assertTrue(payload["append_only"])
        self.assertTrue(payload["hash_chain_valid"])

    def test_events_are_ordered_by_sequence(self) -> None:
        run_id = self.run_demo()
        events = self.client.get(f"{BASE}/runs/{run_id}/events?limit=1000").json()["events"]
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
        events = self.client.get(f"{BASE}/runs/{run_id}/events?limit=1000").json()["events"]
        stage_events = [e for e in events if e["stage_id"]]

        self.assertTrue(stage_events)
        self.assertTrue(all(e["producer"] for e in stage_events))

    def test_no_event_exposes_document_text_or_reasoning(self) -> None:
        run_id = self.run_demo()
        body = self.client.get(f"{BASE}/runs/{run_id}/events?limit=1000").text

        for forbidden in ('"full_text"', '"thinking"', '"reasoning"', '"source_properties"'):
            self.assertNotIn(forbidden, body)


class StageAndProvenanceTest(ResearchApiTestBase):
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
    """Il dossier deve essere servito davvero, non soltanto contato."""

    def test_dossier_carries_the_three_sections(self) -> None:
        run_id = self.run_demo()
        dossier = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()["dossier"]

        self.assertIn("case_context", dossier)
        self.assertIn("candidate_therapies", dossier)
        self.assertIn("limitations", dossier)

    def test_each_candidate_separates_deterministic_evidence_from_author_context(self) -> None:
        run_id = self.run_demo()
        dossier = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()["dossier"]
        entry = dossier["candidate_therapies"][0]

        # Evidenza deterministica e contesto d'autore restano campi distinti:
        # l'author context non può essere scambiato per la claim.
        for deterministic in ("graph_relation", "document_support", "gate_results", "status"):
            self.assertIn(deterministic, entry)
        self.assertIn("author_context", entry)

    def test_dossier_declares_that_gemma_never_decides(self) -> None:
        run_id = self.run_demo()
        dossier = self.client.get(f"{BASE}/runs/{run_id}/dossier").json()["dossier"]
        provenance = dossier["provenance"]

        self.assertEqual(provenance["gemma_role"], "paper_context_enricher_only")
        for decision in ("support_status", "direction", "gate", "score", "bucket"):
            self.assertIn(decision, provenance["gemma_never_decides"])

    def test_dossier_exposes_no_redacted_field(self) -> None:
        run_id = self.run_demo()
        body = self.client.get(f"{BASE}/runs/{run_id}/dossier").text

        for forbidden in ('"source_properties"', '"full_text"', '"thinking"', '"reasoning"'):
            self.assertNotIn(forbidden, body)
