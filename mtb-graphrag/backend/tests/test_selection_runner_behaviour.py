"""Test dei comportamenti del runner: esclusioni, abilitazione, budget, privacy.

Offline: il client e' uno stub, nessuna chiamata di rete.
"""

from __future__ import annotations

from unittest import TestCase

from backend.pipeline.llm.ollama_adapter import (
    OllamaUnavailable,
    StreamingResponseError,
    StructuredOutputError,
)
from benchmarks.mtb_evidence.model_selection import harness
from benchmarks.mtb_evidence.model_selection.roles import RoleTask
from benchmarks.mtb_evidence.model_selection.run_identity import RunIdentity

_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def _task(content: str = "domanda innocua sul caso sintetico") -> RoleTask:
    return RoleTask(
        role="planner",
        case_id="PILOT-K1-FGFR2-iCCA",
        task_id="PILOT-K1-FGFR2-iCCA::planner",
        messages=({"role": "user", "content": content},),
        schema=_SCHEMA,
        expectation={},
    )


def _identity() -> RunIdentity:
    return RunIdentity(
        requested_model_tag="m-cloud", effective_api_model="m", model_revision="rev",
        role="planner", case_id="PILOT-K1-FGFR2-iCCA",
        task_id="PILOT-K1-FGFR2-iCCA::planner", seed=13, prompt_version="v1",
        schema_version="v1", case_hash="ch", source_profile_hash="sh",
        temperature=0.0, num_ctx=16384,
    )


class _Client:
    """Client scriptato con slot di credenziale osservabile."""

    def __init__(self, responses, slot: int | None = 0):
        self._responses = list(responses)
        self.last_credential_slot = slot
        self.calls: list[dict] = []

    def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        item = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return {"message": {"content": item}}


class TaskOutcomeTest(TestCase):
    def test_valid_output_carries_identity_and_budget(self):
        outcome = harness.run_task(
            _Client(['{"ok": true}']), "m", _task(), mode="json_schema",
            seed=13, identity=_identity(),
        )
        payload = outcome.as_dict()
        self.assertTrue(payload["valid_output"])
        self.assertTrue(payload["completed"])
        self.assertEqual(payload["run_key"], _identity().run_key)
        self.assertIn("context_budget", payload)
        self.assertEqual(payload["credential_slot"], 0)

    def test_structured_failure_is_completed_not_missing(self):
        """Un fallimento definitivo e' un esito: va registrato, non rieseguito."""
        outcome = harness.run_task(
            _Client(["non json", "ancora no", "no", "no"]), "m", _task(),
            mode="prompt_validated", identity=_identity(),
        )
        self.assertFalse(outcome.valid_output)
        self.assertTrue(outcome.completed)
        self.assertEqual(outcome.error_class, "StructuredOutputError")

    def test_streaming_error_is_a_failed_run(self):
        error = StreamingResponseError("risposta parziale seguita da errore")
        outcome = harness.run_task(
            _Client([error]), "m", _task(), mode="json_schema", identity=_identity()
        )
        self.assertFalse(outcome.valid_output)
        self.assertEqual(outcome.error_class, "StreamingResponseError")
        self.assertEqual(outcome.parsed, None)

    def test_endpoint_failure_is_captured_not_raised(self):
        outcome = harness.run_task(
            _Client([OllamaUnavailable("giu'")]), "m", _task(),
            mode="json_schema", identity=_identity(),
        )
        self.assertFalse(outcome.valid_output)
        self.assertEqual(outcome.error_class, "OllamaUnavailable")


class BudgetGuardTest(TestCase):
    def test_oversized_prompt_is_not_sent(self):
        client = _Client(['{"ok": true}'])
        outcome = harness.run_task(
            client, "m", _task("x" * 200_000), mode="json_schema",
            num_ctx=16384, identity=_identity(),
        )
        self.assertFalse(outcome.valid_output)
        self.assertEqual(outcome.error_class, "ContextBudgetExceeded")
        self.assertEqual(client.calls, [], "il prompt non doveva partire")

    def test_declared_window_smaller_than_num_ctx_wins(self):
        client = _Client(['{"ok": true}'])
        outcome = harness.run_task(
            client, "m", _task("y" * 30_000), mode="json_schema",
            num_ctx=16384, declared_context=2048, identity=_identity(),
        )
        self.assertEqual(outcome.error_class, "ContextBudgetExceeded")
        self.assertEqual(client.calls, [])

    def test_budget_is_recorded_even_on_success(self):
        outcome = harness.run_task(
            _Client(['{"ok": true}']), "m", _task(), mode="json_schema",
            identity=_identity(),
        )
        budget = outcome.as_dict()["context_budget"]
        self.assertTrue(budget["fits"])
        for key in ("initial_tokens", "final_tokens", "effective_context_window",
                    "reduction_reason"):
            self.assertIn(key, budget)


class PrivacyGuardTest(TestCase):
    def test_prompt_with_personal_data_is_not_sent_to_cloud(self):
        client = _Client(['{"ok": true}'])
        outcome = harness.run_task(
            client, "m", _task("contattare mario.rossi@ospedale.it"),
            mode="prompt_validated", identity=_identity(), screen_privacy=True,
        )
        self.assertFalse(outcome.valid_output)
        self.assertEqual(outcome.error_class, "CloudInputRejected")
        self.assertTrue(outcome.as_dict()["cloud_input_rejected"])
        self.assertEqual(client.calls, [], "il prompt non doveva partire")

    def test_synthetic_case_passes_the_screen(self):
        client = _Client(['{"ok": true}'])
        outcome = harness.run_task(
            client, "m",
            _task("Adulto con colangiocarcinoma intraepatico, fusione FGFR2"),
            mode="prompt_validated", identity=_identity(), screen_privacy=True,
        )
        self.assertTrue(outcome.valid_output)
        self.assertEqual(len(client.calls), 1)

    def test_detected_category_is_recorded_without_the_value(self):
        outcome = harness.run_task(
            _Client(['{"ok": true}']), "m", _task("scrivere a tizio.caio@x.it"),
            mode="prompt_validated", identity=_identity(),
        )
        payload = outcome.as_dict()
        self.assertIn("email", payload["detected_categories"])
        self.assertNotIn("tizio.caio", str(payload))

    def test_local_runs_skip_the_cloud_screen(self):
        client = _Client(['{"ok": true}'])
        outcome = harness.run_task(
            client, "m", _task("email interna: a@b.it"), mode="json_schema",
            identity=_identity(), screen_privacy=False,
        )
        self.assertTrue(outcome.valid_output)


class EntitlementProbeTest(TestCase):
    def _probe(self, client, model="m"):
        import importlib.util
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        path = (
            root / "benchmarks" / "mtb_evidence" / "model_selection" / "scripts"
            / "run_model_selection.py"
        )
        spec = importlib.util.spec_from_file_location("_runner_probe", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module._probe_entitlement(client, model)

    def test_authorised_model_passes(self):
        entitled, reason = self._probe(_Client(['{"ok": true}']))
        self.assertTrue(entitled)
        self.assertEqual(reason, "")

    def test_forbidden_model_is_an_operational_exclusion(self):
        """403 su /api/chat: l'account non e' abilitato, il modello non ha fallito."""
        entitled, reason = self._probe(
            _Client([OllamaUnavailable("Ollama ha risposto 403 su /api/chat")])
        )
        self.assertFalse(entitled)
        self.assertIn("non autorizzato", reason)

    def test_unreachable_endpoint_is_also_an_exclusion(self):
        entitled, reason = self._probe(
            _Client([OllamaUnavailable("connessione rifiutata")])
        )
        self.assertFalse(entitled)
        self.assertIn("non utilizzabile", reason)
