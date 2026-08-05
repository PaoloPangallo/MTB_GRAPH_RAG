"""Test del vocabolario eventi e delle regole di redazione del payload."""

from __future__ import annotations

from unittest import TestCase

from backend.research_pipeline.contracts import StageProducer
from backend.research_pipeline.events import (
    DOMAIN_EVENT_TYPES,
    EVENT_TYPES,
    NEVER_EMITTED,
    REPLAYABLE_EVENT_TYPES,
    ForbiddenPayloadField,
    assert_payload_is_publishable,
    stage_payload,
)


class VocabularyTest(TestCase):
    def test_event_types_are_unique(self) -> None:
        self.assertEqual(len(set(EVENT_TYPES)), len(EVENT_TYPES))

    def test_narration_events_exist_but_are_never_emitted(self) -> None:
        self.assertEqual(NEVER_EMITTED, frozenset({"NARRATION_GENERATED", "NARRATION_VERIFIED"}))
        for event_type in NEVER_EMITTED:
            self.assertIn(event_type, EVENT_TYPES)
            self.assertNotIn(event_type, DOMAIN_EVENT_TYPES)

    def test_domain_events_are_the_replayable_set(self) -> None:
        self.assertEqual(REPLAYABLE_EVENT_TYPES, frozenset(DOMAIN_EVENT_TYPES))


class ChainOfThoughtIsRefusedTest(TestCase):
    def test_thinking_field_is_refused(self) -> None:
        with self.assertRaises(ForbiddenPayloadField):
            assert_payload_is_publishable({"thinking": "prima considero…"})

    def test_reasoning_is_refused_when_nested(self) -> None:
        with self.assertRaises(ForbiddenPayloadField) as ctx:
            assert_payload_is_publishable({"enrichment": {"reasoning": "…"}})
        self.assertIn("enrichment.reasoning", str(ctx.exception))

    def test_reasoning_is_refused_inside_a_list(self) -> None:
        with self.assertRaises(ForbiddenPayloadField):
            assert_payload_is_publishable({"calls": [{"ok": True}, {"chain_of_thought": "…"}]})

    def test_authorised_llm_fields_are_allowed(self) -> None:
        assert_payload_is_publishable({
            "prompt_version": "paper-context-enricher-prompt/2.0",
            "decision": "ABSTAIN",
            "abstention_reason": "nessuna frase letterale a supporto",
            "author_claim_quote": None,
            "reason_codes": ["ENRICHMENT_V2_ABSTAINED"],
        })


class DocumentTextIsRefusedTest(TestCase):
    def test_full_text_is_refused(self) -> None:
        with self.assertRaises(ForbiddenPayloadField):
            assert_payload_is_publishable({"full_text": "…"})

    def test_abstract_is_refused(self) -> None:
        with self.assertRaises(ForbiddenPayloadField):
            assert_payload_is_publishable({"document": {"abstract": "…"}})

    def test_locators_and_hash_are_allowed(self) -> None:
        """L'indice SourceUnit non contiene testo: esporlo non espone documento."""
        assert_payload_is_publishable({
            "source_unit_id": "su-123",
            "document_id": "d-456",
            "section": "results",
            "paragraph_index": 3,
            "char_start": 120,
            "char_end": 268,
            "content_hash": "a" * 64,
        })


class StagePayloadTest(TestCase):
    def test_payload_carries_stage_identity(self) -> None:
        payload = stage_payload(
            stage_id="stage_3_casecontext_match",
            stage_type="CASECONTEXT_MATCH_VERIFIER",
            producer=StageProducer(kind="DETERMINISTIC", component="verifier", version="1.0"),
            essential_fields_pass=True,
        )

        self.assertEqual(payload["stage_id"], "stage_3_casecontext_match")
        self.assertEqual(payload["producer"]["kind"], "DETERMINISTIC")
        self.assertTrue(payload["essential_fields_pass"])

    def test_llm_producer_is_refused_on_a_deterministic_stage(self) -> None:
        with self.assertRaises(ValueError):
            stage_payload(
                stage_id="stage_11_deterministic_gates",
                stage_type="DETERMINISTIC_GATES",
                producer=StageProducer(
                    kind="LLM", component="gemma", version="2.0",
                    model="gemma4:cloud", prompt_version="p/2.0",
                ),
            )

    def test_stage_payload_refuses_hidden_reasoning(self) -> None:
        with self.assertRaises(ForbiddenPayloadField):
            stage_payload(
                stage_id="stage_9_paper_context_enricher",
                stage_type="PAPER_CONTEXT_ENRICHER",
                producer=StageProducer(
                    kind="LLM", component="enricher_v2", version="2.0",
                    model="gemma4:cloud", prompt_version="p/2.0",
                ),
                thinking="…",
            )
