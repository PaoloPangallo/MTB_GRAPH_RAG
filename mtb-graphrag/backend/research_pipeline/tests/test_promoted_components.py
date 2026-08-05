"""Tests for the end-to-end pipeline interaction pilot. No real network calls
-- CaseContext parser and Paper Context Enricher are exercised via fakes."""
from __future__ import annotations

import ast
import hashlib
import unittest
from pathlib import Path

from backend.research_pipeline.casecontext import match_verifier as verifier
from backend.research_pipeline.casecontext import prompt as casecontext_prompt
from backend.research_pipeline.determinism import gates as detpipe
from backend.research_pipeline.enrichment import validator as enrichment_validator
from backend.research_pipeline.enrichment import prompt_v1 as enricher_prompt
from backend.research_pipeline.retrieval import paper_selection
from backend.research_pipeline import pipeline
from backend.research_pipeline.retrieval import kg_retrieval as retrieval
from backend.research_pipeline.models import case_context_schema_errors

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DOC_GROUNDED = PACKAGE_ROOT.parent / "document_grounded_claims"

FROZEN_HASHES = {
    "llm_claim_extractor/flat_transport_v12.py": "89ff867dc306a5dad8e8fc4eaae4e3e9b7164122151ba9b8cee1c7dcb43cb531",
    "llm_claim_extractor/prompt_v13.py": "e004aacdace8fe1bd70fdebfed437bb2aedca4dd84c295d2507f08622dfade07",
    "llm_claim_extractor/flat_adapter.py": "7c7ec2a84e38539293934b15941cce1a1971c016ea649053ef0681eeba1f3c8a",
    "llm_claim_extractor/schema.py": "ba0148447041cc2035c7bcf9f1ab97d254a8523167d0f4f7d06a7a4b20cb9c0b",
    "llm_claim_extractor/validator.py": "6b98f4e56f9d9046557f2ecd73dcdf9d8cfd2a2dd66173281bdd8c547b153a4b",
    "verification.py": "c857aa185cc7108b36ad0b2ecc24610d69f5d196af3eb9dfee4144898ce5a2c7",
}

FORBIDDEN_DECISION_IMPORTS = ("LlmClaimProposalValidator", "ClaimSupportVerifier", "FlatToolArgumentsAdapter")


def _valid_case_context(**overrides):
    base = {
        "case_id": "CASE-x", "disease": {"raw_value": "colorectal cancer", "normalized_value": "colorectal cancer", "source_spans": [{"quote": "colorectal cancer", "start_offset": 10, "end_offset": 28}]},
        "biomarkers": [{"gene": "KRAS", "alteration": "G12D", "raw_value": "KRAS G12D", "normalized_value": "kras g12d", "source_spans": [{"quote": "KRAS G12D", "start_offset": 50, "end_offset": 59}]}],
        "previous_interventions": [], "target_intervention": {"raw_value": "panitumumab", "normalized_value": "panitumumab", "source_spans": [{"quote": "panitumumab", "start_offset": 90, "end_offset": 101}]},
        "query_intent": "THERAPY_EVALUATION", "clinical_question": "would panitumumab work?", "uncertainties": [],
    }
    base.update(overrides)
    return base


class CaseContextSchemaTests(unittest.TestCase):
    def test_valid_case_context_has_no_errors(self):
        self.assertEqual(case_context_schema_errors(_valid_case_context()), [])

    def test_missing_keys_detected(self):
        errors = case_context_schema_errors({"case_id": "x"})
        self.assertTrue(any("MISSING_KEYS" in e for e in errors))

    def test_therapy_discovery_requires_null_target(self):
        cc = _valid_case_context(query_intent="THERAPY_DISCOVERY")
        errors = case_context_schema_errors(cc)
        self.assertIn("THERAPY_DISCOVERY_MUST_HAVE_NULL_TARGET_INTERVENTION", errors)

    def test_therapy_discovery_with_null_target_is_valid(self):
        cc = _valid_case_context(query_intent="THERAPY_DISCOVERY", target_intervention=None)
        self.assertEqual(case_context_schema_errors(cc), [])

    def test_tool_argument_errors_rejects_extra_key(self):
        cc = _valid_case_context()
        cc["extra_key"] = "x"
        errors = casecontext_prompt.tool_argument_errors(cc)
        self.assertTrue(any("TOP_LEVEL_KEYS" in e for e in errors))


class MatchVerifierTests(unittest.TestCase):
    TEXT = "Patient has colorectal cancer with KRAS G12D mutation, considering panitumumab."

    def test_exact_span_is_match(self):
        payload = {"raw_value": "colorectal cancer", "normalized_value": "colorectal cancer", "source_spans": [{"quote": "colorectal cancer", "start_offset": None, "end_offset": None}]}
        record = verifier._verify_span_field("disease", payload, self.TEXT)
        self.assertEqual(record.status, "MATCH")
        self.assertEqual(record.reason_code, "EXACT_TEXT_MATCH")

    def test_quote_not_in_text_is_mismatch(self):
        payload = {"raw_value": "breast cancer", "normalized_value": "breast cancer", "source_spans": [{"quote": "breast cancer", "start_offset": None, "end_offset": None}]}
        record = verifier._verify_span_field("disease", payload, self.TEXT)
        self.assertEqual(record.status, "MISMATCH")
        self.assertEqual(record.reason_code, "QUOTE_NOT_IN_TEXT")

    def test_slightly_wrong_offsets_do_not_override_a_confirmed_unambiguous_quote(self):
        # Regression: an LLM-reported offset that's off by a few characters must not
        # override a quote that is otherwise unambiguously present exactly once.
        text = "A patient with metastatic colorectal cancer has been found to carry a KRAS G12D mutation."
        actual_offset = text.find("metastatic colorectal cancer")
        payload = {"raw_value": "metastatic colorectal cancer", "normalized_value": "metastatic colorectal cancer", "source_spans": [{"quote": "metastatic colorectal cancer", "start_offset": actual_offset - 2, "end_offset": actual_offset - 2 + len("metastatic colorectal cancer")}]}
        record = verifier._verify_span_field("disease", payload, text)
        self.assertEqual(record.status, "MATCH")
        self.assertEqual(record.start_offset, actual_offset)

    def test_ambiguous_offset_is_uncertain(self):
        text = "KRAS G12D and again KRAS G12D mentioned twice."
        payload = {"raw_value": "KRAS G12D", "normalized_value": "kras g12d", "source_spans": [{"quote": "KRAS G12D", "start_offset": None, "end_offset": None}]}
        record = verifier._verify_span_field("biomarker", payload, text)
        self.assertEqual(record.status, "UNCERTAIN")

    def test_missing_field_is_missing_in_text(self):
        record = verifier._verify_span_field("previous_intervention", None, self.TEXT)
        self.assertEqual(record.status, "MISSING_IN_TEXT")

    def test_essential_fields_pass_blocks_on_mismatch(self):
        records = [
            verifier.MatchVerificationRecord("disease", "x", "MISMATCH", None, None, None, "QUOTE_NOT_IN_TEXT"),
            verifier.MatchVerificationRecord("biomarker", "x", "MATCH", "q", 0, 1, "EXACT_TEXT_MATCH"),
            verifier.MatchVerificationRecord("query_intent", "THERAPY_EVALUATION", "MATCH", None, None, None, "INTENT_TARGET_CONSISTENT"),
        ]
        passed, warnings = verifier.essential_fields_pass(records)
        self.assertFalse(passed)

    def test_essential_fields_pass_allows_uncertain_with_warning(self):
        records = [
            verifier.MatchVerificationRecord("disease", "x", "UNCERTAIN", "q", 0, 1, "AMBIGUOUS_OFFSET_MULTIPLE_OCCURRENCES"),
            verifier.MatchVerificationRecord("biomarker", "x", "MATCH", "q", 0, 1, "EXACT_TEXT_MATCH"),
            verifier.MatchVerificationRecord("query_intent", "THERAPY_EVALUATION", "MATCH", None, None, None, "INTENT_TARGET_CONSISTENT"),
        ]
        passed, warnings = verifier.essential_fields_pass(records)
        self.assertTrue(passed)
        self.assertTrue(any("disease" in w for w in warnings))

    def test_query_intent_target_inconsistency_is_mismatch(self):
        cc = _valid_case_context(query_intent="THERAPY_DISCOVERY")  # target_intervention still populated -> inconsistent
        records = verifier.verify_case_context(cc, self.TEXT)
        intent_record = next(r for r in records if r.field == "query_intent")
        self.assertEqual(intent_record.status, "MISMATCH")


class RetrievalTests(unittest.TestCase):
    def test_therapy_evaluation_finds_expected_candidate(self):
        cc = _valid_case_context()
        result = retrieval.retrieve(cc)
        self.assertFalse(result["no_match"])
        self.assertIn("GCA-008ae3aad1a64c118318ef79", [a["candidate_id"] for a in result["associations"]])

    def test_therapy_discovery_omits_intervention_filter(self):
        cc = _valid_case_context(query_intent="THERAPY_DISCOVERY", target_intervention=None,
                                  biomarkers=[{"gene": "BRAF", "alteration": "V600E", "raw_value": "BRAF V600E", "normalized_value": "braf v600e", "source_spans": []}],
                                  disease={"raw_value": "colorectal cancer", "normalized_value": "colorectal cancer", "source_spans": []})
        result = retrieval.retrieve(cc)
        self.assertFalse(result["no_match"])
        self.assertIn("GCA-0031c17c5ff5ae29ff221b1e", [a["candidate_id"] for a in result["associations"]])

    def test_fabricated_gene_yields_no_match(self):
        cc = _valid_case_context(biomarkers=[{"gene": "ZZTK9", "alteration": "P44R", "raw_value": "ZZTK9 P44R", "normalized_value": "zztk9 p44r", "source_spans": []}])
        result = retrieval.retrieve(cc)
        self.assertTrue(result["no_match"])
        self.assertEqual(result["associations"], [])

    def test_max_three_associations_per_case(self):
        self.assertEqual(retrieval.MAX_ASSOCIATIONS_PER_CASE, 3)

    def test_max_four_source_units_per_document(self):
        cc = _valid_case_context()
        result = retrieval.retrieve(cc)
        for association in result["associations"]:
            for bundle in association["available_bundles"]:
                self.assertLessEqual(len(bundle["source_unit_ids"]), 4)


class PaperSelectionTests(unittest.TestCase):
    def test_max_two_papers_per_association(self):
        self.assertEqual(paper_selection.MAX_PAPERS_PER_ASSOCIATION, 2)

    def test_selects_at_most_two_and_excludes_rest(self):
        association = {
            "candidate_id": "GCA-x", "candidate": {"direction": "Supports"},
            "available_bundles": [
                {"bundle_id": f"EB-{i}", "document_id": f"doc:{i}", "bundle_type": "ABSTRACT_BUNDLE", "source_unit_ids": [f"SU-{i}"]}
                for i in range(4)
            ],
        }
        source_units_by_id = {f"SU-{i}": {"source_unit_id": f"SU-{i}", "text": "some text"} for i in range(4)}
        result = paper_selection.select_papers_for_association(association, source_units_by_id)
        self.assertEqual(len(result["selected_papers"]), 2)
        self.assertEqual(len(result["excluded_papers"]), 2)

    def test_text_unavailable_excludes_bundle(self):
        association = {"candidate_id": "GCA-x", "candidate": {"direction": "Supports"}, "available_bundles": [{"bundle_id": "EB-1", "document_id": "doc:1", "bundle_type": "ABSTRACT_BUNDLE", "source_unit_ids": ["SU-missing"]}]}
        result = paper_selection.select_papers_for_association(association, {})
        self.assertEqual(result["selected_papers"], [])
        self.assertEqual(result["excluded_papers"][0]["reason_codes"], ["TEXT_NOT_AVAILABLE_IN_CACHE"])


class EnrichmentValidatorTests(unittest.TestCase):
    CANDIDATE = {"candidate_id": "GCA-x", "disease": [{"label": "Colorectal Cancer"}], "biomarkers": [{"label": "KRAS"}]}
    PAPER = {"bundle_id": "EB-1", "resolved_source_unit_ids": ["SU-1"], "source_unit_ids": ["SU-1"]}
    UNIT_TEXT = "In patients with colorectal cancer harboring KRAS mutations, panitumumab showed resistance and no clinical benefit."
    UNITS = {"SU-1": {"source_unit_id": "SU-1", "text": UNIT_TEXT}}

    def _enrichment(self, **overrides):
        base = {"candidate_id": "GCA-x", "paper_id": "EB-1", "source_unit_id": "SU-1", "drug": "panitumumab", "author_claim_quote": "panitumumab showed resistance and no clinical benefit", "author_context_summary": "The authors report panitumumab showed resistance and no clinical benefit.", "evidence_kind": "RESISTANCE", "abstain": False, "abstention_reason": None}
        base.update(overrides)
        return base

    def test_accepted_on_literal_grounded_quote(self):
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertIn(result["outcome"], ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING"))

    def test_rejected_transport_short_circuits(self):
        result = enrichment_validator.validate_enrichment("TEXT_RESPONSE", None, candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_TRANSPORT")

    def test_nonexistent_quote_rejected(self):
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(author_claim_quote="this text is not in the source unit at all"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_QUOTE")

    def test_wrong_source_unit_id_rejected(self):
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(source_unit_id="SU-invented"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_SOURCE_UNIT")

    def test_abstention_recorded_as_abstained(self):
        enrichment = {"candidate_id": "GCA-x", "paper_id": "EB-1", "source_unit_id": None, "drug": None, "author_claim_quote": None, "author_context_summary": None, "evidence_kind": None, "abstain": True, "abstention_reason": "no defensible passage"}
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", enrichment, candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "ENRICHMENT_ABSTAINED")

    def test_summary_ungrounded_when_unrelated_to_quote(self):
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(author_context_summary="Unrelated commentary about xylophone manufacturing trends in another century entirely."), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_SUMMARY_UNGROUNDED")

    def test_summary_with_recommendation_rejected(self):
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(author_context_summary="Based on this, patients should receive panitumumab regardless."), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_SUMMARY_UNGROUNDED")

    def test_empty_summary_accepted_with_warning_not_rejected(self):
        # Regression for prompt v1.1: "the summary may be empty ... do not abstain only
        # because the summary is empty" -- an empty summary must not be auto-rejected.
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(author_context_summary=""), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "ENRICHMENT_ACCEPTED_WITH_WARNING")
        self.assertIn("SUMMARY_EMPTY", result["reason_codes"])

    def test_drug_mismatch_is_context_mismatch(self):
        result = enrichment_validator.validate_enrichment("FORCED_TOOL_VALID", self._enrichment(drug="a completely different unrelated drug name"), candidate=self.CANDIDATE, paper_bundle=self.PAPER, source_units_by_id=self.UNITS, requested_drug="panitumumab")
        self.assertEqual(result["outcome"], "REJECTED_CONTEXT_MISMATCH")


class DeterministicPipelineTests(unittest.TestCase):
    def test_contradicted_not_promoted_to_positive(self):
        candidate = {"direction": "Sensitivity/Response"}
        enrichments = [{"validation_outcome": "ENRICHMENT_ACCEPTED", "enrichment": {"evidence_kind": "RESISTANCE"}}]
        result = detpipe.evaluate_association("THERAPY_EVALUATION", candidate, enrichments)
        self.assertEqual(result["status"], "CONTRADICTED")
        self.assertEqual(result["gate_bucket"], "REJECTED_BUCKET")

    def test_conflicting_wins_even_if_some_consistent(self):
        candidate = {"direction": "Sensitivity/Response"}
        enrichments = [
            {"validation_outcome": "ENRICHMENT_ACCEPTED", "enrichment": {"evidence_kind": "RESPONSE"}},
            {"validation_outcome": "ENRICHMENT_ACCEPTED", "enrichment": {"evidence_kind": "RESISTANCE"}},
        ]
        result = detpipe.evaluate_association("THERAPY_EVALUATION", candidate, enrichments)
        self.assertEqual(result["status"], "CONTRADICTED")

    def test_direct_requires_consistent_enrichment(self):
        candidate = {"direction": "Resistance"}
        enrichments = [{"validation_outcome": "ENRICHMENT_ACCEPTED", "enrichment": {"evidence_kind": "RESISTANCE"}}]
        result = detpipe.evaluate_association("THERAPY_EVALUATION", candidate, enrichments)
        self.assertEqual(result["status"], "DIRECT")

    def test_no_validated_enrichment_is_ambiguous_not_direct(self):
        result = detpipe.evaluate_association("THERAPY_EVALUATION", {"direction": "Resistance"}, [])
        self.assertEqual(result["status"], "AMBIGUOUS")
        self.assertNotEqual(result["status"], "DIRECT")

    def test_discovery_never_produces_direct_or_contradicted(self):
        result = detpipe.evaluate_association("THERAPY_DISCOVERY", {"direction": "Supports"}, [])
        self.assertEqual(result["status"], "DISCOVERED")
        self.assertEqual(result["gate_bucket"], "DISCOVERY_BUCKET")


class PaperContextEnricherPromptTests(unittest.TestCase):
    def test_tool_schema_forbids_extra_keys(self):
        args = {"source_unit_id": "SU-1", "drug": "x", "author_claim_quote": "q", "author_context_summary": "s", "evidence_kind": "RESPONSE", "abstain": False, "abstention_reason": None, "extra": 1}
        errors = enricher_prompt.tool_argument_errors(args)
        self.assertTrue(any("TOP_LEVEL_KEYS" in e for e in errors))

    def test_abstain_true_requires_null_fields(self):
        args = {"source_unit_id": "SU-1", "drug": None, "author_claim_quote": None, "author_context_summary": None, "evidence_kind": None, "abstain": True, "abstention_reason": "none found"}
        errors = enricher_prompt.tool_argument_errors(args)
        self.assertTrue(any("ABSTAIN_TRUE_BUT_FIELDS_POPULATED" in e for e in errors))

    def test_non_abstain_requires_quote(self):
        args = {"source_unit_id": "SU-1", "drug": "x", "author_claim_quote": None, "author_context_summary": "s", "evidence_kind": "RESPONSE", "abstain": False, "abstention_reason": None}
        errors = enricher_prompt.tool_argument_errors(args)
        self.assertTrue(any("NON_ABSTAIN_REQUIRES_QUOTE" in e for e in errors))


class PromptV11Tests(unittest.TestCase):
    def test_v1_1_reuses_v1_0_tool_schema_unchanged(self):
        from backend.research_pipeline.enrichment import prompt_v1 as v10
        from backend.research_pipeline.enrichment import prompt_v1_1 as v11
        self.assertIs(v11.TOOL_SCHEMA, v10.TOOL_SCHEMA)
        self.assertEqual(v11.TOOL_NAME, v10.TOOL_NAME)

    def test_v1_1_has_distinct_version_and_system_prompt(self):
        from backend.research_pipeline.enrichment import prompt_v1 as v10
        from backend.research_pipeline.enrichment import prompt_v1_1 as v11
        self.assertEqual(v11.PROMPT_VERSION, "paper-context-enricher-prompt/1.1")
        self.assertNotEqual(v11.SYSTEM_PROMPT, v10.SYSTEM_PROMPT)
        self.assertNotEqual(v11.prompt_hash(), v10.prompt_hash())


class BudgetAndNoUnnecessaryCallTests(unittest.TestCase):
    def test_budget_raises_when_exceeded(self):
        budget = pipeline.CallBudget(maximum=1)
        budget.spend("casecontext_parser", "CASE-1")
        with self.assertRaises(RuntimeError):
            budget.spend("paper_context_enricher", "CASE-1")

    def test_max_real_calls_total_is_20(self):
        self.assertEqual(pipeline.MAX_REAL_CALLS_TOTAL, 20)

    def test_enricher_never_called_when_casecontext_mismatch(self):
        def fake_parser(budget, case_id, text):
            budget.spend("casecontext_parser", case_id)
            cc = _valid_case_context()
            cc["disease"]["source_spans"] = [{"quote": "NOT IN TEXT AT ALL", "start_offset": None, "end_offset": None}]
            return {"case_id": case_id, "transport_result": "FORCED_TOOL_VALID", "case_context_raw": cc}

        def fake_enricher(*args, **kwargs):
            raise AssertionError("enricher must never be called when CaseContext is rejected before retrieval")

        budget = pipeline.CallBudget()
        trace = pipeline.run_case("CASE-mismatch", "some clinical text", budget, fake_parser, fake_enricher, {})
        self.assertEqual(trace["stopped_at"], "CASECONTEXT_MISMATCH")

    def test_enricher_never_called_on_no_match(self):
        text = "Patient with colorectal cancer, research panel found ZZTK9 P44R, considering panitumumab."

        def fake_parser(budget, case_id, text):
            budget.spend("casecontext_parser", case_id)
            cc = _valid_case_context(
                disease={"raw_value": "colorectal cancer", "normalized_value": "colorectal cancer", "source_spans": [{"quote": "colorectal cancer", "start_offset": None, "end_offset": None}]},
                biomarkers=[{"gene": "ZZTK9", "alteration": "P44R", "raw_value": "ZZTK9 P44R", "normalized_value": "zztk9 p44r", "source_spans": [{"quote": "ZZTK9 P44R", "start_offset": None, "end_offset": None}]}],
                target_intervention={"raw_value": "panitumumab", "normalized_value": "panitumumab", "source_spans": [{"quote": "panitumumab", "start_offset": None, "end_offset": None}]},
            )
            return {"case_id": case_id, "transport_result": "FORCED_TOOL_VALID", "case_context_raw": cc}

        def fake_enricher(*args, **kwargs):
            raise AssertionError("enricher must never be called when retrieval finds no candidate")

        budget = pipeline.CallBudget()
        trace = pipeline.run_case("CASE-nomatch", text, budget, fake_parser, fake_enricher, {})
        self.assertEqual(trace["stopped_at"], "RETRIEVAL_NO_MATCH")

    def test_enricher_never_called_when_parser_transport_fails(self):
        def fake_parser(budget, case_id, text):
            budget.spend("casecontext_parser", case_id)
            return {"case_id": case_id, "transport_result": "TEXT_RESPONSE", "case_context_raw": None}

        def fake_enricher(*args, **kwargs):
            raise AssertionError("enricher must never be called when the parser itself fails")

        budget = pipeline.CallBudget()
        trace = pipeline.run_case("CASE-parserfail", "text", budget, fake_parser, fake_enricher, {})
        self.assertEqual(trace["stopped_at"], "PARSER_TRANSPORT_FAILED")
        self.assertEqual(budget.used, 1)


class DossierSeparationTests(unittest.TestCase):
    def test_author_context_key_is_separate_from_status_and_gate(self):
        from backend.research_pipeline.dossier.builder import build_candidate_therapy_entry
        candidate = {"candidate_id": "GCA-x", "interventions": [{"label": "panitumumab"}], "predicate": "targets"}
        evaluation = {"status": "DIRECT", "gate_bucket": "PRIMARY_BUCKET", "support_mask": {}, "warnings": []}
        entry = build_candidate_therapy_entry(candidate, "targets", {}, [{"drug": "panitumumab", "author_claim_quote": "q"}], [], evaluation)
        self.assertIn("author_context", entry)
        self.assertEqual(entry["status"], "DIRECT")
        self.assertNotIn("status", entry["author_context"][0])


class OutputSanitizationTests(unittest.TestCase):
    def test_sanitize_candidate_drops_source_properties(self):
        from backend.research_pipeline.redaction import redact_candidate as _sanitize_candidate
        candidate = {"candidate_id": "GCA-x", "disease": [{"label": "x"}], "source_properties": {"evidence": {"evidence_statement": "a" * 800}}}
        sanitized = _sanitize_candidate(candidate)
        self.assertNotIn("source_properties", sanitized)
        self.assertEqual(sanitized["candidate_id"], "GCA-x")

    def test_sanitize_retrieval_result_strips_nested_candidates(self):
        from backend.research_pipeline.redaction import redact_retrieval_result as _sanitize_retrieval_result
        result = {"no_match": False, "associations": [{"candidate_id": "GCA-x", "candidate": {"candidate_id": "GCA-x", "source_properties": {"profile": {"summary": "b" * 900}}}}]}
        sanitized = _sanitize_retrieval_result(result)
        self.assertNotIn("source_properties", sanitized["associations"][0]["candidate"])


class RuntimeInvariantTests(unittest.TestCase):
    def test_promoted_package_excludes_the_old_claim_extractor(self):
        """Il vecchio Claim Extractor non deve esistere dentro il research runtime.

        Sostituisce il test di hash sui file congelati di
        ``llm_claim_extractor/``: quei file non sono stati promossi, quindi
        qui non c'è nulla di cui verificare l'immutabilità. L'invariante che
        conta in questo contesto è più forte — non ci sono affatto.
        """
        offenders = [
            path.relative_to(PACKAGE_ROOT).as_posix()
            for path in PACKAGE_ROOT.rglob("*.py")
            if "claim_extractor" in path.as_posix()
        ]
        self.assertEqual(offenders, [], f"claim extractor promosso per errore: {offenders}")

    def test_pilot_package_never_imports_claim_extractor_decision_classes(self):
        # ``rglob`` e non ``glob``: dopo la promozione i componenti vivono nei
        # sottopackage (casecontext/, retrieval/, enrichment/, determinism/,
        # dossier/), e uno scan del solo primo livello li mancherebbe tutti,
        # lasciando passare l'import che questo test deve impedire.
        offenders = []
        for py_file in PACKAGE_ROOT.rglob("*.py"):
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = " ".join(getattr(alias, "name", "") for alias in node.names)
                    module = getattr(node, "module", "") or ""
                    combined = f"{module} {names}"
                    if any(forbidden in combined for forbidden in FORBIDDEN_DECISION_IMPORTS):
                        offenders.append((py_file.name, combined))
        self.assertEqual(offenders, [], f"decision-logic import found: {offenders}")


if __name__ == "__main__":
    unittest.main()
