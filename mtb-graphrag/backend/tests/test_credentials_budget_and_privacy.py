"""Test di credenziali, rate limit, budget del contesto, privacy e risposte parziali.

Tutto offline: nessuna chiamata di rete, attese iniettate.
"""

from __future__ import annotations

import json
import os
from unittest import TestCase

from backend.pipeline.llm.context_budget import (
    DEFAULT_RESERVED_OUTPUT_TOKENS,
    REDUCTION_NONE,
    REDUCTION_RECORD_DROP,
    check_budget,
    effective_context_window,
    estimate_tokens,
    reduce_records,
    screen_for_personal_data,
    screen_messages,
)
from backend.pipeline.llm.credentials import (
    MAX_ATTEMPTS_RATE_LIMIT,
    MAX_ATTEMPTS_SERVER_ERROR,
    ROTATE_ON_RATE_LIMIT_VAR,
    CredentialPool,
    NoCredentialsAvailable,
    backoff_seconds,
    classify_http_failure,
    parse_retry_after,
    redact_headers,
    rotation_on_rate_limit_allowed,
)
from backend.pipeline.llm.ollama_adapter import (
    StreamingResponseError,
    _parse_response_body,
)


class CredentialPoolTest(TestCase):
    def setUp(self):
        self._saved = {
            name: os.environ.get(name)
            for name in ("OLLAMA_API_KEYS", "OLLAMA_API_KEY", ROTATE_ON_RATE_LIMIT_VAR)
        }

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_pool_from_comma_separated_keys(self):
        os.environ["OLLAMA_API_KEYS"] = "alpha, beta ,gamma"
        pool = CredentialPool.from_env()
        self.assertEqual(len(pool), 3)
        self.assertEqual(pool.slots, (0, 1, 2))

    def test_falls_back_to_single_key(self):
        os.environ.pop("OLLAMA_API_KEYS", None)
        os.environ["OLLAMA_API_KEY"] = "solo"
        self.assertEqual(len(CredentialPool.from_env()), 1)

    def test_invalidation_moves_to_next_slot(self):
        os.environ["OLLAMA_API_KEYS"] = "a,b,c"
        pool = CredentialPool.from_env()
        self.assertEqual(pool.current().slot, 0)
        pool.invalidate_current("HTTP 401")
        self.assertEqual(pool.current().slot, 1)
        self.assertEqual(pool.active_slots, (1, 2))

    def test_exhaustion_yields_no_credential(self):
        os.environ["OLLAMA_API_KEYS"] = "a,b"
        pool = CredentialPool.from_env()
        pool.invalidate_current("x")
        pool.invalidate_current("x")
        self.assertIsNone(pool.current())
        self.assertEqual(pool.active_slots, ())

    def test_report_never_contains_key_material(self):
        os.environ["OLLAMA_API_KEYS"] = "supersegreto1,supersegreto2"
        pool = CredentialPool.from_env()
        pool.invalidate_current("HTTP 401")
        serialized = json.dumps(pool.report())
        self.assertNotIn("supersegreto1", serialized)
        self.assertNotIn("supersegreto2", serialized)
        self.assertNotIn("super", serialized)
        self.assertIn("credential_slot", serialized)

    def test_report_exposes_only_slots(self):
        os.environ["OLLAMA_API_KEYS"] = "a,b"
        report = CredentialPool.from_env().report()
        self.assertEqual(report["credential_count"], 2)
        self.assertEqual(report["active_slots"], [0, 1])

    def test_authorization_header_is_redacted(self):
        headers = [("Authorization", "Bearer segretissimo"), ("User-Agent", "mtb")]
        redacted = dict(redact_headers(headers))
        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertEqual(redacted["User-Agent"], "mtb")


class RetryPolicyTest(TestCase):
    def setUp(self):
        self._saved = os.environ.get(ROTATE_ON_RATE_LIMIT_VAR)
        os.environ.pop(ROTATE_ON_RATE_LIMIT_VAR, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ROTATE_ON_RATE_LIMIT_VAR, None)
        else:
            os.environ[ROTATE_ON_RATE_LIMIT_VAR] = self._saved

    def test_401_invalidates_and_rotates(self):
        outcome = classify_http_failure(401, 1, pool_size=3)
        self.assertTrue(outcome.invalidate)
        self.assertTrue(outcome.rotate)
        self.assertTrue(outcome.should_retry)

    def test_401_with_single_key_fails_immediately(self):
        self.assertFalse(classify_http_failure(401, 1, pool_size=1).should_retry)

    def test_429_respects_retry_after(self):
        outcome = classify_http_failure(429, 1, retry_after=12, pool_size=2)
        self.assertTrue(outcome.should_retry)
        self.assertEqual(outcome.wait_seconds, 12.0)

    def test_429_does_not_rotate_by_default(self):
        """Ruotare chiave su 429 aggirerebbe la quota del provider."""
        outcome = classify_http_failure(429, 1, pool_size=3)
        self.assertFalse(outcome.rotate)
        self.assertIn("non usata per non aggirare", outcome.reason)

    def test_429_rotates_only_when_explicitly_allowed(self):
        os.environ[ROTATE_ON_RATE_LIMIT_VAR] = "1"
        self.assertTrue(rotation_on_rate_limit_allowed())
        self.assertTrue(classify_http_failure(429, 1, pool_size=3).rotate)

    def test_429_gives_up_after_max_attempts(self):
        self.assertFalse(
            classify_http_failure(429, MAX_ATTEMPTS_RATE_LIMIT, pool_size=2).should_retry
        )

    def test_5xx_retries_with_backoff_then_stops(self):
        self.assertTrue(classify_http_failure(503, 1).should_retry)
        self.assertGreater(classify_http_failure(503, 1).wait_seconds, 0)
        self.assertFalse(
            classify_http_failure(503, MAX_ATTEMPTS_SERVER_ERROR).should_retry
        )

    def test_client_errors_are_not_retried(self):
        for status in (400, 404, 422):
            self.assertFalse(classify_http_failure(status, 1).should_retry)

    def test_backoff_grows_and_is_capped(self):
        self.assertLess(backoff_seconds(1), backoff_seconds(5))
        self.assertLessEqual(backoff_seconds(50), 60.0)

    def test_retry_after_parsing(self):
        self.assertEqual(parse_retry_after("30"), 30.0)
        self.assertIsNone(parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT"))
        self.assertIsNone(parse_retry_after(None))


class PartialResponseTest(TestCase):
    def test_plain_json_is_accepted(self):
        parsed = _parse_response_body('{"message": {"content": "ok"}}', "e", "/p")
        self.assertEqual(parsed["message"]["content"], "ok")

    def test_ndjson_error_object_fails_the_run(self):
        with self.assertRaises(StreamingResponseError):
            _parse_response_body('{"a": 1}\n{"error": "upstream"}', "e", "/p")

    def test_truncated_body_is_not_parsed(self):
        """Il testo parziale non va analizzato: il modello non ha finito di scriverlo."""
        with self.assertRaises(StreamingResponseError) as ctx:
            _parse_response_body('{"a": 1}\n{"b": tronc', "e", "/p")
        self.assertIn("non viene analizzat", str(ctx.exception))

    def test_done_false_is_incomplete(self):
        with self.assertRaises(StreamingResponseError):
            _parse_response_body('{"done": false}', "e", "/p")

    def test_error_field_in_plain_json_fails(self):
        with self.assertRaises(StreamingResponseError):
            _parse_response_body('{"error": "model not found"}', "e", "/p")

    def test_empty_body_is_empty_dict(self):
        self.assertEqual(_parse_response_body("", "e", "/p"), {})

    def test_ndjson_sequence_uses_last_object(self):
        parsed = _parse_response_body(
            '{"done": false}\n{"done": true, "message": {"content": "fine"}}', "e", "/p"
        )
        self.assertEqual(parsed["message"]["content"], "fine")


class ContextBudgetTest(TestCase):
    def test_effective_window_is_the_smaller_of_the_two(self):
        self.assertEqual(effective_context_window(16384, 8192), 8192)
        self.assertEqual(effective_context_window(16384, 32768), 16384)
        self.assertEqual(effective_context_window(16384, None), 16384)

    def test_small_prompt_fits(self):
        decision = check_budget([{"role": "user", "content": "ciao"}], num_ctx=16384)
        self.assertTrue(decision.fits)
        self.assertEqual(decision.reduction_reason, REDUCTION_NONE)

    def test_oversized_prompt_is_detected_not_truncated(self):
        decision = check_budget(
            [{"role": "user", "content": "x" * 100_000}], num_ctx=16384
        )
        self.assertFalse(decision.fits)
        self.assertEqual(decision.initial_tokens, decision.final_tokens)

    def test_reserved_output_counts_against_the_window(self):
        """Lo stesso prompt sta o non sta a seconda di quanto output si riserva."""
        content = "x" * (16_000 * 4)  # ~16.000 token, sotto la finestra da 16.384
        messages = [{"role": "user", "content": content}]
        self.assertTrue(check_budget(messages, num_ctx=16384, reserved_output_tokens=0).fits)
        self.assertFalse(
            check_budget(
                messages,
                num_ctx=16384,
                reserved_output_tokens=DEFAULT_RESERVED_OUTPUT_TOKENS,
            ).fits
        )

    def test_reduction_records_everything_required(self):
        records = [{"record_id": f"r{i}", "payload": "y" * 3000} for i in range(40)]
        kept, decision = reduce_records(records, overhead_tokens=500, num_ctx=16384)
        self.assertEqual(decision.reduction_reason, REDUCTION_RECORD_DROP)
        self.assertEqual(decision.initial_records, 40)
        self.assertEqual(decision.kept_records, len(kept))
        self.assertTrue(decision.excluded_records)
        self.assertGreater(decision.initial_tokens, decision.final_tokens)
        for key in ("initial_records", "kept_records", "excluded_records",
                    "initial_tokens", "final_tokens", "reduction_reason"):
            self.assertIn(key, decision.as_dict())

    def test_reduction_is_deterministic_across_models(self):
        """Stessa finestra, stesso input: due modelli ricevono record identici."""
        records = [{"record_id": f"r{i}", "payload": "z" * 2500} for i in range(30)]
        first, _ = reduce_records(records, overhead_tokens=400, num_ctx=16384)
        second, _ = reduce_records(records, overhead_tokens=400, num_ctx=16384)
        self.assertEqual(first, second)

    def test_smaller_window_keeps_fewer_records_and_says_so(self):
        records = [{"record_id": f"r{i}", "payload": "z" * 2500} for i in range(30)]
        _, wide = reduce_records(records, overhead_tokens=400, num_ctx=16384)
        _, narrow = reduce_records(records, overhead_tokens=400, num_ctx=4096)
        self.assertGreater(wide.kept_records, narrow.kept_records)
        self.assertTrue(narrow.excluded_records)

    def test_no_records_needs_no_reduction(self):
        kept, decision = reduce_records([], overhead_tokens=10, num_ctx=16384)
        self.assertEqual(kept, [])
        self.assertEqual(decision.reduction_reason, REDUCTION_NONE)

    def test_token_estimate_is_monotonic(self):
        self.assertLess(estimate_tokens("breve"), estimate_tokens("breve" * 100))


class CloudPrivacyTest(TestCase):
    def test_synthetic_clinical_case_is_allowed(self):
        text = (
            "Adulto con colangiocarcinoma intraepatico non resecabile, fusione FGFR2, "
            "progressione dopo una linea sistemica."
        )
        decision = screen_for_personal_data(text)
        self.assertTrue(decision.allowed)
        self.assertFalse(decision.cloud_input_rejected)

    def test_email_is_rejected(self):
        decision = screen_for_personal_data("scrivere a mario.rossi@ospedale.it")
        self.assertTrue(decision.cloud_input_rejected)
        self.assertIn("email", decision.detections)

    def test_patient_identifier_is_rejected(self):
        self.assertTrue(
            screen_for_personal_data("paziente: MRN-99213").cloud_input_rejected
        )

    def test_fiscal_code_is_rejected(self):
        self.assertTrue(
            screen_for_personal_data("RSSMRA85M01H501Z").cloud_input_rejected
        )

    def test_detection_records_category_never_the_value(self):
        decision = screen_for_personal_data("email: segreto.personale@example.com")
        serialized = json.dumps(decision.as_dict())
        self.assertNotIn("segreto.personale", serialized)
        self.assertIn("email", serialized)

    def test_screening_covers_every_message(self):
        messages = [
            {"role": "system", "content": "istruzioni innocue"},
            {"role": "user", "content": "contatto: paziente@dominio.it"},
        ]
        self.assertTrue(screen_messages(messages).cloud_input_rejected)

    def test_pmids_and_nct_are_not_mistaken_for_identifiers(self):
        """Un PMID a otto cifre non deve far scattare il rilevatore di telefono."""
        decision = screen_for_personal_data("PMID 29151359 e NCT02296125")
        self.assertTrue(decision.allowed, f"falso positivo: {decision.detections}")
