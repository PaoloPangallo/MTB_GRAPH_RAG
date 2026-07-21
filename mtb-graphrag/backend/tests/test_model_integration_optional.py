"""Integrazioni opzionali verso modelli reali.

Disattivate per default: la suite deve restare eseguibile offline e senza GPU.

    RUN_LLM_INTEGRATION=1          modelli locali (Ollama su localhost)
    RUN_CLOUD_MODEL_INTEGRATION=1  modelli cloud (richiede OLLAMA_API_KEY)

Ogni test salta in modo leggibile se il modello richiesto non e' installato: un
modello assente non e' un fallimento del codice, ed e' esattamente la condizione che
il protocollo prevede di gestire senza interrompere l'esperimento.
"""

from __future__ import annotations

import os
import unittest
from unittest import TestCase

from backend.pipeline.llm.ollama_adapter import (
    JSON_SCHEMA,
    PROMPT_VALIDATED,
    OllamaClient,
    OllamaUnavailable,
    configured_endpoint,
    local_endpoint,
    request_structured,
)

_LOCAL = os.getenv("RUN_LLM_INTEGRATION") == "1"
_CLOUD = os.getenv("RUN_CLOUD_MODEL_INTEGRATION") == "1"

_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}
_MESSAGES = [
    {"role": "user", "content": "Rispondi con un JSON che abbia il campo answer valorizzato a ok."}
]


def _first_available_local(client: OllamaClient) -> str | None:
    try:
        models = client.list_models()
    except OllamaUnavailable:
        return None
    return models[0].get("name") if models else None


@unittest.skipUnless(_LOCAL, "richiede RUN_LLM_INTEGRATION=1 e Ollama in locale")
class LocalModelIntegrationTest(TestCase):
    def setUp(self):
        self.client = OllamaClient(local_endpoint(), timeout=120)
        if not self.client.reachable():
            self.skipTest("Ollama locale non raggiungibile")
        self.model = _first_available_local(self.client)
        if not self.model:
            self.skipTest("nessun modello locale installato")

    def test_json_schema_mode_returns_valid_structured_output(self):
        result = request_structured(
            self.client, self.model, _MESSAGES, _SCHEMA, mode=JSON_SCHEMA, temperature=0.0
        )
        self.assertIn("answer", result.parsed)
        self.assertEqual(result.mode, JSON_SCHEMA)
        self.assertTrue(result.raw_outputs)

    def test_capabilities_are_observed_not_assumed(self):
        show = self.client.show(self.model)
        self.assertIn("details", show)


@unittest.skipUnless(
    _CLOUD, "richiede RUN_CLOUD_MODEL_INTEGRATION=1 e OLLAMA_API_KEY"
)
class CloudModelIntegrationTest(TestCase):
    def setUp(self):
        endpoint = configured_endpoint()
        if not endpoint.is_cloud:
            self.skipTest("OLLAMA_BASE_URL non punta a un endpoint cloud")
        if not endpoint.api_key:
            self.skipTest("OLLAMA_API_KEY non configurata")
        self.client = OllamaClient(endpoint, timeout=180)
        if not self.client.reachable():
            self.skipTest("endpoint cloud non raggiungibile o non autenticato")

    def test_cloud_uses_prompt_validated_mode(self):
        models = self.client.list_models()
        self.assertTrue(models)
        model = models[0].get("name")
        result = request_structured(
            self.client, model, _MESSAGES, _SCHEMA, mode=PROMPT_VALIDATED, temperature=0.0
        )
        self.assertEqual(result.mode, PROMPT_VALIDATED)
        self.assertIn("answer", result.parsed)
        self.assertLessEqual(result.retries, 2)

    def test_unauthenticated_failure_is_readable(self):
        from backend.pipeline.llm.ollama_adapter import OllamaEndpoint

        broken = OllamaClient(
            OllamaEndpoint(configured_endpoint().base_url, api_key="invalid"), timeout=30
        )
        with self.assertRaises(OllamaUnavailable) as ctx:
            broken.list_models()
        self.assertIn("OLLAMA_API_KEY", str(ctx.exception))
        self.assertNotIn("invalid", str(ctx.exception))
