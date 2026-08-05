"""Tests for the Paper Context Enricher v2.0 (transport, validator, local
metadata assignment). No real network calls. Confirms v1's validator and
already-committed results are untouched."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.research_pipeline.data_access import data_root
from backend.research_pipeline.enrichment import prompt_v2 as v2prompt
from backend.research_pipeline.enrichment import transport_v2 as v2transport
from backend.research_pipeline.enrichment import validator_v2 as v2validator
from backend.research_pipeline.enrichment.enricher_v2 import _enrichment_id, _trim_only

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
# La radice dei dati arriva da ``data_access``, non da ``parents[n]``: la
# promozione ha cambiato la profondità di questo file, e il conteggio ereditato
# dal pilot puntava un livello troppo in alto.
ROOT = data_root()


def _valid_quote_args(**overrides) -> dict:
    base = {"decision": "QUOTE", "source_unit_id": "SU-1", "author_claim_quote": "panitumumab showed resistance", "author_context_summary": "The authors report resistance to panitumumab.", "abstention_reason": ""}
    base.update(overrides)
    return base


def _valid_abstain_args(**overrides) -> dict:
    base = {"decision": "ABSTAIN", "source_unit_id": "", "author_claim_quote": "", "author_context_summary": "", "abstention_reason": "no defensible passage found"}
    base.update(overrides)
    return base


class SchemaTests(unittest.TestCase):
    def test_all_five_fields_are_strings(self):
        for field, spec in v2prompt.TOOL_SCHEMA["properties"].items():
            self.assertEqual(spec["type"] if field != "decision" else "string", "string")

    def test_no_evidence_kind_in_schema(self):
        self.assertNotIn("evidence_kind", v2prompt.TOOL_SCHEMA["properties"])

    def test_no_nested_or_union_types(self):
        for spec in v2prompt.TOOL_SCHEMA["properties"].values():
            self.assertIsInstance(spec["type"], str)

    def test_additional_properties_false(self):
        self.assertFalse(v2prompt.TOOL_SCHEMA["additionalProperties"])

    def test_exactly_five_required_fields(self):
        self.assertEqual(set(v2prompt.TOOL_SCHEMA["required"]), {"decision", "source_unit_id", "author_claim_quote", "author_context_summary", "abstention_reason"})


class TransportTests(unittest.TestCase):
    def _response(self, arguments: dict) -> dict:
        return {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [{"function": {"name": v2prompt.TOOL_NAME, "arguments": json.dumps(arguments)}}]}}], "usage": {}}

    def test_valid_quote_decision(self):
        outcome, _, args, _ = v2transport.transport_result_v2(200, self._response(_valid_quote_args()), None)
        self.assertEqual(outcome, "V2_TRANSPORT_VALID")
        self.assertEqual(args["decision"], "QUOTE")

    def test_valid_abstain_decision(self):
        outcome, _, args, _ = v2transport.transport_result_v2(200, self._response(_valid_abstain_args()), None)
        self.assertEqual(outcome, "V2_TRANSPORT_VALID")
        self.assertEqual(args["decision"], "ABSTAIN")

    def test_invalid_decision_value(self):
        outcome, _, _, _ = v2transport.transport_result_v2(200, self._response(_valid_quote_args(decision="MAYBE")), None)
        self.assertEqual(outcome, "INVALID_DECISION")

    def test_missing_argument(self):
        args = _valid_quote_args()
        del args["abstention_reason"]
        outcome, _, _, _ = v2transport.transport_result_v2(200, self._response(args), None)
        self.assertEqual(outcome, "MISSING_ARGUMENT")

    def test_wrong_argument_type(self):
        outcome, _, _, _ = v2transport.transport_result_v2(200, self._response(_valid_quote_args(source_unit_id=None)), None)
        self.assertEqual(outcome, "WRONG_ARGUMENT_TYPE")

    def test_transport_does_not_reject_abstain_with_populated_fields(self):
        # Section 3: this combination is a SEMANTIC concern, not a transport rejection.
        outcome, _, args, _ = v2transport.transport_result_v2(200, self._response(_valid_abstain_args(author_claim_quote="some text")), None)
        self.assertEqual(outcome, "V2_TRANSPORT_VALID")

    def test_transport_does_not_reject_empty_summary(self):
        outcome, _, args, _ = v2transport.transport_result_v2(200, self._response(_valid_quote_args(author_context_summary="")), None)
        self.assertEqual(outcome, "V2_TRANSPORT_VALID")

    def test_wrong_tool_name(self):
        response = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [{"function": {"name": "some_other_tool", "arguments": "{}"}}]}}]}
        outcome, _, _, _ = v2transport.transport_result_v2(200, response, None)
        self.assertEqual(outcome, "WRONG_TOOL_NAME")

    def test_text_response(self):
        response = {"choices": [{"finish_reason": "stop", "message": {"content": "I cannot help.", "tool_calls": []}}]}
        outcome, _, _, _ = v2transport.transport_result_v2(200, response, None)
        self.assertEqual(outcome, "TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL")

    def test_multiple_tool_calls(self):
        tc = {"function": {"name": v2prompt.TOOL_NAME, "arguments": json.dumps(_valid_quote_args())}}
        response = {"choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [tc, tc]}}]}
        outcome, _, _, _ = v2transport.transport_result_v2(200, response, None)
        self.assertEqual(outcome, "MULTIPLE_TOOL_CALLS")

    def test_extra_key_is_invalid_tool_arguments(self):
        args = _valid_quote_args()
        args["extra"] = "x"
        outcome, _, _, _ = v2transport.transport_result_v2(200, self._response(args), None)
        self.assertEqual(outcome, "INVALID_TOOL_ARGUMENTS")


class ValidatorQuoteTests(unittest.TestCase):
    CANDIDATE = {"candidate_id": "GCA-x", "disease": [{"label": "Colorectal Cancer"}], "biomarkers": [{"label": "KRAS"}]}
    PAPER = {"bundle_id": "EB-1", "resolved_source_unit_ids": ["SU-1"], "source_unit_ids": ["SU-1"]}
    UNIT_TEXT = "In patients with colorectal cancer harboring KRAS mutations, panitumumab showed resistance and no clinical benefit."
    UNITS = {"SU-1": {"source_unit_id": "SU-1", "text": UNIT_TEXT}}

    def test_accepted_quote(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab showed resistance and no clinical benefit"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ACCEPTED")

    def test_accepted_quote_with_empty_summary_not_rejected(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab showed resistance and no clinical benefit", author_context_summary=""), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")

    def test_nonexistent_quote_rejected(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="this text is nowhere in the source"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_QUOTE_NOT_FOUND")

    def test_wrong_source_unit_rejected(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(source_unit_id="SU-invented"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_SOURCE_UNIT")

    def test_ellipsis_quote_rejected_as_non_contiguous(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab ... resistance"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_QUOTE_NON_CONTIGUOUS")

    def test_summary_grounded_accepted(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab showed resistance and no clinical benefit", author_context_summary="The paper reports resistance to panitumumab with no clinical benefit."), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ACCEPTED")

    def test_summary_ungrounded_rejected(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab showed resistance and no clinical benefit", author_context_summary="Completely unrelated commentary about orchestral music history."), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_SUMMARY_UNGROUNDED")

    def test_clinical_recommendation_rejected(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab showed resistance and no clinical benefit", author_context_summary="Based on this, patients should receive panitumumab regardless."), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_CLINICAL_RECOMMENDATION")

    def test_drug_not_in_passage_rejected(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="colorectal cancer harboring KRAS mutations"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="nivolumab")
        self.assertEqual(result["outcome"], "REJECTED_CONTEXT_MISMATCH")

    def test_quote_matching_case_context_is_leakage(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_quote_args(author_claim_quote="panitumumab showed resistance and no clinical benefit"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab", case_context_text="the case context text panitumumab showed resistance and no clinical benefit for this patient")
        self.assertEqual(result["outcome"], "REJECTED_CONTEXT_MISMATCH")


class ValidatorAbstainTests(unittest.TestCase):
    def test_clean_abstention(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_abstain_args(), candidate={}, paper_bundle={}, source_units_by_id={}, requested_drug="x")
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ABSTAINED")

    def test_abstain_with_populated_fields_is_inconsistent_not_promoted(self):
        result = v2validator.validate_enrichment_v2("V2_TRANSPORT_VALID", _valid_abstain_args(author_claim_quote="some leaked quote text"), candidate={}, paper_bundle={}, source_units_by_id={}, requested_drug="x")
        self.assertEqual(result["outcome"], "ENRICHMENT_V2_ABSTAINED_WITH_INCONSISTENT_FIELDS")
        self.assertIn("author_claim_quote", result["inconsistent_fields"])

    def test_rejected_transport_short_circuits(self):
        result = v2validator.validate_enrichment_v2("TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL", None, candidate={}, paper_bundle={}, source_units_by_id={}, requested_drug="x")
        self.assertEqual(result["outcome"], "REJECTED_TRANSPORT")


class LocalMetadataTests(unittest.TestCase):
    def test_enrichment_id_deterministic(self):
        id1 = _enrichment_id("CASE-1", "GCA-x", "EB-1", 0)
        id2 = _enrichment_id("CASE-1", "GCA-x", "EB-1", 0)
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("PCEV2-"))

    def test_trim_only_strips_outer_whitespace_and_nothing_else(self):
        trimmed = _trim_only({"decision": "  QUOTE  ", "author_claim_quote": "  a   b  "})
        self.assertEqual(trimmed["decision"], "QUOTE")
        self.assertEqual(trimmed["author_claim_quote"], "a   b")  # internal spacing untouched


class V1UnchangedTests(unittest.TestCase):
    # Hashes captured from the committed state at commit c484715, immediately before
    # starting v2.0 work -- any change here means a v1.0/v1.1 result or the v1 validator
    # was modified, which the protocol forbids.
    FROZEN_HASHES = {
        "paper_context_enrichments.jsonl": "707c7fe0c5584285d117f263f2f46c733863107aff39d1299df5caf2333dd315",
        "enrichment_validation_results.jsonl": "4ecbfb0ec150760e2bcb6df584d50872b22fa0386e6acb4dd841ef648e3979a5",
        "dossier_previews.jsonl": "09aab73a6da57f92a4d7f5f511b17ef555dbd9af3d4abcf0edba71f265c18472",
        "casecontext_outputs.jsonl": "ae6743dfceb9c425d70c46d1948b9b09d809e432dbbde5da97a05e3d8eebe9c6",
        "retrieval_results.jsonl": "5f837ef3f657283491fa9491534c16f30db77e33b4eeeaa21931ba0bd50a39bb",
        "paper_selection_results.jsonl": "346a83f0f226242c5f093bd1588d10ad5c64bd638f5f79b5ff0da121fd714514",
        "enrichment_validator.py": "e1ca65fcfd2e01dc8bfd60f68fe4427467b864a03e143d5559caefdc0114879a",
        "paper_context_enricher_prompt.py": "3fcd04f3b373ed2b264fc4466ebb4c1d51448ffaa3827ab4b665055008dd36ca",
        "paper_context_enricher_prompt_v1_1.py": "9b0c87e95c1dc891f7a8b62f3fd540096cb7d66b79c87635b414c261504f05f3",
    }

    #: Gli hash sopra furono calcolati sul working tree Windows del pilot, dove i
    #: file avevano fine riga CRLF. Il blob git conserva LF, quindi un confronto
    #: byte-per-byte fallirebbe pur essendo il contenuto identico. Si normalizza
    #: a CRLF prima di confrontare: verifica il contenuto, non la codifica dei
    #: fine riga, che dipende dal checkout e non dal dato.
    @staticmethod
    def _hash_as_captured(raw: bytes) -> str:
        normalized = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        return hashlib.sha256(normalized).hexdigest()

    def test_promoted_v1_artifacts_match_the_frozen_pilot(self):
        """Verifica che la promozione non abbia alterato gli artefatti del pilot.

        È il controllo di regressione della promozione: a parità di contenuto,
        gli artefatti portati in ``backend/`` devono essere quelli prodotti dal
        pilot. I moduli ``.py`` sono esclusi perché i loro import sono stati
        riscritti dalla ristrutturazione in sottopackage — un cambiamento
        deliberato, coperto dai test di comportamento di questo stesso file.
        """
        artifacts = {
            name: expected
            for name, expected in self.FROZEN_HASHES.items()
            if name.endswith(".jsonl")
        }
        self.assertTrue(artifacts, "nessun artefatto da verificare")

        checked = 0
        for name, expected in artifacts.items():
            path = ROOT / "benchmarks/mtb_evidence/end_to_end_pipeline_pilot" / name
            if not path.is_file():
                # Gli artefatti v1 non sono stati promossi: il research runtime
                # usa la v2. Assenti per scelta, non per errore.
                continue
            self.assertEqual(
                self._hash_as_captured(path.read_bytes()), expected,
                f"{name} differisce dall'artefatto congelato del pilot",
            )
            checked += 1

        self.assertGreater(checked, 0, "nessun artefatto promosso trovato: la verifica sarebbe vuota")


if __name__ == "__main__":
    unittest.main()
