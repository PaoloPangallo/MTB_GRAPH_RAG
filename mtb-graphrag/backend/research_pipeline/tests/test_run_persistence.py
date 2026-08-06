"""Una run deve poter essere riaperta dopo un riavvio del backend.

``RunStore`` è in memoria: il riavvio si simula scartandolo con
``reset_store()`` mantenendo lo stesso file di ledger, che è esattamente ciò che
accade a un processo riavviato. Un test che riusasse lo stesso store non
proverebbe nulla, perché la vista arriverebbe ancora dalla memoria.
"""

from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from fastapi.testclient import TestClient

from backend.api.main import app
from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import rehydration, run_store
from backend.research_pipeline.contracts import STAGE_SEQUENCE

BASE = "/api/v1/research/pipeline"
DEMO_CASE = "CASE-1-therapy-evaluation-strong-match"


class RunPersistenceTest(TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self._env = mock.patch.dict("os.environ", {
            "VERIFIABLE_PIPELINE_RESEARCH_ENABLED": "1",
            "RESEARCH_LEDGER_PATH": str(Path(self._tmp.name) / "research.sqlite3"),
        })
        self._env.start()
        run_store.reset_store()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._env.stop()
        run_store.reset_store()
        self._tmp.cleanup()

    def _completed_run(self, case_id: str = DEMO_CASE) -> str:
        response = self.client.post(
            f"{BASE}/runs", json={"demo_case_key": case_id, "execution_mode": "REPLAY"})
        self.assertEqual(response.status_code, 201, response.text)
        run_id = response.json()["run_id"]
        for _ in range(300):
            if self.client.get(f"{BASE}/runs/{run_id}").json()["status"] not in ("CREATED", "RUNNING"):
                return run_id
            time.sleep(0.1)
        self.fail("la run non si è conclusa entro il tempo previsto")

    def _restart_backend(self) -> None:
        """Scarta il registro in memoria; il ledger su disco resta."""
        run_store.reset_store()

    # --- Riapertura ---------------------------------------------------------

    def test_a_run_is_still_readable_after_a_restart(self) -> None:
        run_id = self._completed_run()
        before = self.client.get(f"{BASE}/runs/{run_id}").json()

        self._restart_backend()
        after = self.client.get(f"{BASE}/runs/{run_id}")

        self.assertEqual(after.status_code, 200, after.text)
        rebuilt = after.json()
        self.assertTrue(rebuilt["rehydrated"])
        self.assertEqual(rebuilt["status"], before["status"])
        self.assertEqual(rebuilt["case_id"], before["case_id"])

    def test_every_stage_is_rebuilt_in_order(self) -> None:
        run_id = self._completed_run()
        self._restart_backend()

        stages = self.client.get(f"{BASE}/runs/{run_id}").json()["stages"]

        self.assertEqual([s["stage_id"] for s in stages], list(STAGE_SEQUENCE))
        self.assertEqual([s["sequence"] for s in stages], list(range(1, 16)))
        self.assertNotIn("PENDING", {s["status"] for s in stages})

    def test_execution_mode_and_origins_survive(self) -> None:
        """Senza queste, una run reidratata non direbbe più come è stata eseguita."""
        run_id = self._completed_run()
        before = self.client.get(f"{BASE}/runs/{run_id}").json()
        self._restart_backend()
        after = self.client.get(f"{BASE}/runs/{run_id}").json()

        self.assertEqual(after["execution_mode"], before["execution_mode"])
        self.assertEqual(after["requested_mode"], before["requested_mode"])
        self.assertEqual(after["replay_artifacts_used"], before["replay_artifacts_used"])
        self.assertEqual(
            [s["artifact_origin"] for s in after["stages"]],
            [s["artifact_origin"] for s in before["stages"]],
        )

    def test_the_llm_call_count_is_the_same_read_from_either_side(self) -> None:
        """Era ricalcolato in lettura, e dava due numeri per la stessa run.

        La somma delle metriche di stage escludeva il parser — che non
        contribuisce ad alcuna metrica — e in REPLAY contava come reali le
        chiamate rigiocate. Il valore canonico lo scrive l'orchestratore.
        """
        run_id = self._completed_run()
        before = self.client.get(f"{BASE}/runs/{run_id}").json()
        self._restart_backend()
        after = self.client.get(f"{BASE}/runs/{run_id}").json()

        self.assertEqual(after["llm_calls"], before["llm_calls"])

    def test_a_replay_run_reports_zero_real_model_calls(self) -> None:
        run_id = self._completed_run()
        self._restart_backend()

        snapshot = self.client.get(f"{BASE}/runs/{run_id}").json()

        self.assertEqual(snapshot["execution_mode"], "REPLAY")
        self.assertEqual(snapshot["llm_calls"], 0)

    def test_the_dossier_is_rebuilt(self) -> None:
        run_id = self._completed_run()
        self._restart_backend()

        response = self.client.get(f"{BASE}/runs/{run_id}/dossier")

        self.assertEqual(response.status_code, 200, response.text)
        dossier = response.json()["dossier"]
        for section in ("candidate_therapies", "limitations"):
            self.assertIn(section, dossier)

    def test_provenance_is_rebuilt(self) -> None:
        run_id = self._completed_run()
        self._restart_backend()

        items = self.client.get(f"{BASE}/runs/{run_id}/provenance").json()["items"]

        self.assertTrue(items)
        levels = [level["level"] for level in items[0]["chain"]]
        self.assertEqual(levels[0], "CASE_CONTEXT")
        self.assertEqual(levels[-1], "DOSSIER_ITEM")

    def test_events_are_readable_after_a_restart(self) -> None:
        """Prima rispondevano 404: la rotta passava dal registro in memoria."""
        run_id = self._completed_run()
        self._restart_backend()

        payload = self.client.get(f"{BASE}/runs/{run_id}/events").json()

        self.assertTrue(payload["events"])
        self.assertTrue(payload["hash_chain_valid"])

    def test_a_restarted_run_still_appears_in_the_list(self) -> None:
        run_id = self._completed_run()
        self._restart_backend()

        rows = self.client.get(f"{BASE}/runs").json()["runs"]

        row = next((r for r in rows if r["run_id"] == run_id), None)
        self.assertIsNotNone(row)
        self.assertTrue(row["rehydrated"])

    # --- Integrità e recupero ----------------------------------------------

    def test_the_hash_chain_is_verified_on_rehydration(self) -> None:
        run_id = self._completed_run()
        self._restart_backend()

        self.assertTrue(self.client.get(f"{BASE}/runs/{run_id}").json()["hash_chain_valid"])

    def test_an_interrupted_run_is_marked_recovered_incomplete(self) -> None:
        """Una run senza RUN_COMPLETED non è né riuscita né conclusa.

        Si costruisce scrivendo sul ledger gli eventi di apertura e di un solo
        stage, come farebbe un processo ucciso a metà.
        """
        ledger = EventLedger(run_store.research_ledger_path())
        run_id = "interrupted-run"
        ledger.append(run_id, "RUN_CREATED", "orchestrator",
                      {"case_id": DEMO_CASE, "input_text": "…",
                       "requested_execution_mode": "LIVE"},
                      tool_name="orchestrator", tool_version="test")
        ledger.append(run_id, "STAGE_COMPLETED", "orchestrator",
                      {"stage_id": "stage_1_case_input", "stage_type": "CASE_INPUT",
                       "producer": {"kind": "DETERMINISTIC", "component": "case_input",
                                    "version": "test", "model": None,
                                    "prompt_version": None, "transport_version": None},
                       "status": "SUCCEEDED", "execution_mode": "LIVE",
                       "artifact_origin": "GENERATED_NOW", "sequence": 1},
                      tool_name="orchestrator", tool_version="test")

        snapshot = rehydration.rehydrate(ledger, run_id)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["recovery_status"], rehydration.RECOVERED_INCOMPLETE)
        self.assertEqual(snapshot["stages_recorded"], 1)
        self.assertIn("stage_13_dossier", snapshot["stages_missing"])

    def test_an_unknown_run_is_still_404(self) -> None:
        self._restart_backend()
        self.assertEqual(self.client.get(f"{BASE}/runs/nope").status_code, 404)

    # --- Cosa non deve finire su disco -------------------------------------

    def test_no_document_text_or_credentials_are_persisted(self) -> None:
        """La persistenza eredita il filtro del ledger invece di ridichiararlo."""
        run_id = self._completed_run()
        self._restart_backend()

        raw = Path(run_store.research_ledger_path()).read_bytes()

        for forbidden in (b'"full_text"', b'"document_text"', b'"source_text"',
                          b'"thinking"', b'"reasoning"', b"Bearer ", b"OLLAMA_API_KEY"):
            self.assertNotIn(forbidden, raw, f"{forbidden!r} non deve essere persistito")
        self.assertIn(run_id.encode(), raw)
