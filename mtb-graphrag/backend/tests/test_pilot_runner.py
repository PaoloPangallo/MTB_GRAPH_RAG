"""Test del runner del pilota: mappatura dei casi, estrazione, precondizioni.

Offline: nessun Neo4j, nessun modello.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase

from benchmarks.mtb_evidence.evaluation import case_mapping, pilot_extraction
from benchmarks.mtb_evidence.evaluation.clinical_gold import load_clinical_gold
from benchmarks.mtb_evidence.evaluation.contracts import BRANCH_VERIFIED
from benchmarks.mtb_evidence.pilot.audit_lib.aliases import build_alias_table

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD = PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "data" / "clinical_gold_v1.jsonl"


def _runner_module():
    path = (
        PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "scripts"
        / "run_pilot_evaluation.py"
    )
    spec = importlib.util.spec_from_file_location("_pilot_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Collection:
    def __init__(self, **kwargs):
        self.terminal_state = kwargs.get("terminal_state", {})
        self.tool_path = kwargs.get("tool_path", ())
        self.tool_call_timings = kwargs.get("tool_call_timings", ())
        self.planning_mode = kwargs.get("planning_mode", "fixed_plan")
        self.fallback_reason = kwargs.get("fallback_reason")
        self.planner_calls = kwargs.get("planner_calls", 0)
        self.planner_elapsed_ms = kwargs.get("planner_elapsed_ms", 0)
        self.mandatory_tools = kwargs.get("mandatory_tools", ())
        self.missing_mandatory_tools = kwargs.get("missing_mandatory_tools", ())


class _Verdict:
    def __init__(self, violations=()):
        self.violations = tuple(violations)


class _Result:
    def __init__(self, **kwargs):
        self.run_id = "run-1"
        self.architecture_id = kwargs.get("architecture_id", "deterministic")
        self.orchestration_mode = "deterministic"
        self.case = type("C", (), {"case_id": "PILOT-K1-FGFR2-iCCA"})()
        self.collection = kwargs.get("collection", _Collection())
        self.canonical_view = type("V", (), {"replay_fidelity": 1.0, "records_in": 0,
                                             "records_out": 0})()
        self.candidate_report = kwargs.get("candidate_report", "candidato")
        self.report = kwargs.get("report", "verificato")
        self.candidate_verdict = _Verdict()
        self.final_verdict = kwargs.get("final_verdict", _Verdict())
        self.dossier_verdict = _Verdict()
        self.claim_checks = kwargs.get("claim_checks", ())
        self.evidence_items = kwargs.get("evidence_items", ())
        self.repair_attempts = 0
        self.escalation = kwargs.get("escalation")
        self.ledger_valid = True


class CaseMappingTest(TestCase):
    def test_every_development_case_has_a_declared_mapping(self):
        for case in load_clinical_gold(GOLD):
            with self.subTest(case=case.case_id):
                mapping = case_mapping.mapping_for(case.case_id)
                self.assertTrue(mapping.rationale, "ogni mappatura va motivata")

    def test_unknown_case_is_rejected_not_guessed(self):
        with self.assertRaises(case_mapping.MissingCaseMapping) as ctx:
            case_mapping.mapping_for("CASO-INVENTATO")
        self.assertIn("dichiarata", str(ctx.exception))

    def test_fusion_case_uses_the_fusion_traversal(self):
        """alteration_type sceglie il percorso: sbagliarlo cambia l'esperimento."""
        self.assertEqual(
            case_mapping.mapping_for("PILOT-K1-FGFR2-iCCA").alteration_type, "fusion"
        )

    def test_first_line_case_has_no_prior_therapies(self):
        mapping = case_mapping.mapping_for("PILOT-C1-EGFR-L858R-CONTEXT")
        self.assertEqual(mapping.therapy_line, "first-line")
        self.assertEqual(mapping.prior_therapies, ())
        self.assertEqual(mapping.disease_setting, "metastatic")

    def test_post_progression_case_declares_prior_therapy(self):
        mapping = case_mapping.mapping_for("PILOT-A2-ALK-G1202R")
        self.assertEqual(mapping.therapy_line, "later-line")
        self.assertTrue(mapping.prior_therapies)

    def test_request_is_built_from_the_mapping(self):
        case = {c.case_id: c for c in load_clinical_gold(GOLD)}["PILOT-K1-FGFR2-iCCA"]
        request = case_mapping.build_request(case)
        self.assertEqual(request.gene, "FGFR2")
        self.assertEqual(request.alteration_type, "fusion")

    def test_manifest_exposes_every_mapping(self):
        manifest = case_mapping.mapping_manifest()
        self.assertEqual(len(manifest["mappings"]), 4)


class RetrievalExtractionTest(TestCase):
    def setUp(self):
        self.aliases = build_alias_table()

    def test_records_are_found_however_they_are_nested(self):
        state = {
            "variant_data": {"evidence_records": [
                {"drug": "PEMIGATINIB", "citation_id": ["32203698"], "evidence_id": 1}
            ]},
            "drug_candidates": [{"drug_name": "FUTIBATINIB"}],
        }
        result = _Result(collection=_Collection(
            terminal_state=state, tool_path=("interpret_variant", "identify_targets")
        ))
        prediction = pilot_extraction.retrieval_from_result(result, self.aliases)
        self.assertIn("pemigatinib", prediction.therapies)
        self.assertIn("futibatinib", prediction.therapies)
        self.assertIn("32203698", prediction.pmids)
        self.assertEqual(prediction.tools_called, ("interpret_variant", "identify_targets"))

    def test_empty_collection_is_an_abstention(self):
        prediction = pilot_extraction.retrieval_from_result(_Result(), self.aliases)
        self.assertTrue(prediction.abstained)
        self.assertEqual(prediction.therapies, ())

    def test_retrieval_reads_collection_not_report(self):
        """Il report e' lo stadio dopo: usarlo qui confonderebbe due misure."""
        result = _Result(report="osimertinib e' indicato", collection=_Collection())
        prediction = pilot_extraction.retrieval_from_result(result, self.aliases)
        self.assertEqual(prediction.therapies, ())

    def test_planner_calls_are_carried_through(self):
        result = _Result(collection=_Collection(planner_calls=5))
        self.assertEqual(
            pilot_extraction.retrieval_from_result(result, self.aliases).planner_calls, 5
        )


class ReportExtractionTest(TestCase):
    def setUp(self):
        self.aliases = build_alias_table()

    def test_claims_come_from_evidence_items(self):
        item = type("E", (), {"claim_id": "c1", "subject": "EGFR L858R",
                              "relation": "predicts", "object": "OSIMERTINIB",
                              "context": "advanced NSCLC", "source_id": "29151359"})()
        report = pilot_extraction.report_from_result(
            _Result(evidence_items=(item,)), BRANCH_VERIFIED, self.aliases
        )
        self.assertEqual(len(report.claims), 1)
        self.assertIn("osimertinib", report.mentioned_therapies)
        self.assertIn("29151359", report.cited_pmids)
        self.assertFalse(report.abstained)

    def test_no_evidence_is_an_abstention(self):
        report = pilot_extraction.report_from_result(
            _Result(), BRANCH_VERIFIED, self.aliases
        )
        self.assertTrue(report.abstained)

    def test_violations_request_human_review(self):
        report = pilot_extraction.report_from_result(
            _Result(final_verdict=_Verdict(violations=("claim non ancorata",))),
            BRANCH_VERIFIED, self.aliases,
        )
        self.assertTrue(report.requested_human_review)

    def test_telemetry_records_what_the_protocol_requires(self):
        telemetry = pilot_extraction.run_telemetry(
            _Result(collection=_Collection(
                tool_path=("interpret_variant",), planner_calls=3,
                tool_call_timings=({"tool": "interpret_variant", "elapsed_ms": 12},),
            )),
            elapsed_ms=1234.5,
        )
        for key in ("run_id", "architecture", "tool_path", "planner_calls",
                    "retrieval_tool_calls", "latency_by_stage", "structural_verdict",
                    "source_verifications", "ledger_valid"):
            self.assertIn(key, telemetry)
        self.assertEqual(telemetry["planner_calls"], 3)


class SnapshotPreconditionTest(TestCase):
    """Il guardrail nato da un errore reale durante lo sviluppo del runner.

    Con Neo4j giu' ogni strumento falliva, la raccolta restava vuota, e il caso N1
    risultava `correctly_abstained` — corretto per il motivo sbagliato.
    """

    def test_unreachable_graph_blocks_the_run(self):
        module = _runner_module()

        class _Down:
            def run(self, cypher, params=None):
                from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import (
                    GraphUnavailable,
                )

                raise GraphUnavailable("connessione rifiutata")

        import benchmarks.mtb_evidence.pilot.audit_lib.graph_client as gc

        original = gc.Neo4jGraphClient
        gc.Neo4jGraphClient = _Down
        try:
            ok, detail = module.check_snapshot_preconditions("abc")
        finally:
            gc.Neo4jGraphClient = original
        self.assertFalse(ok)
        self.assertIn("non raggiungibile", detail)
        self.assertIn("motivo sbagliato", detail)

    def test_missing_expected_fingerprint_skips_the_comparison(self):
        module = _runner_module()

        class _Up:
            def run(self, cypher, params=None):
                return [{"ok": 1}]

        import benchmarks.mtb_evidence.pilot.audit_lib.graph_client as gc

        original = gc.Neo4jGraphClient
        gc.Neo4jGraphClient = _Up
        try:
            ok, detail = module.check_snapshot_preconditions("")
        finally:
            gc.Neo4jGraphClient = original
        self.assertTrue(ok)
        self.assertIn("saltato", detail)


class PipelineReuseTest(TestCase):
    def test_runner_uses_build_run_and_defines_no_pipeline(self):
        """Nessun runner parallelo: la differenza deve venire solo dalla strategia."""
        source = (
            PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "scripts"
            / "run_pilot_evaluation.py"
        ).read_text(encoding="utf-8")
        self.assertIn("from backend.comparison.live_runs import build_run", source)
        self.assertNotIn("run_verified_pipeline(", source)
        self.assertNotIn("FixedPlanStrategy(", source)
        self.assertNotIn("AgenticPlanStrategy(", source)
