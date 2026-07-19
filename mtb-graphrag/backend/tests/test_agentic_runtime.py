import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.runtime import run_agentic_collection
from backend.pipeline.agentic.source_verifier import verify_evidence_items


class _Response:
    def __init__(self, content):
        self.content = content


class _SequencedLLM:
    def __init__(self, payloads):
        self.payloads = iter(payloads)

    def invoke(self, _messages):
        return _Response(json.dumps(next(self.payloads)))


class EventLedgerTest(TestCase):
    def test_ledger_is_hash_chained_and_database_blocks_mutation(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            ledger = EventLedger(path)
            first = ledger.append("run-1", "started", "controller", {"case": "synthetic"})
            second = ledger.append("run-1", "completed", "tool", {"records": 2})

            self.assertEqual(first["sequence"], 1)
            self.assertEqual(second["previous_hash"], first["event_hash"])
            self.assertTrue(ledger.verify_chain("run-1"))

            with sqlite3.connect(path) as connection:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "UPDATE agent_events SET actor = 'tampered' WHERE run_id = 'run-1'"
                    )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM agent_events WHERE run_id = 'run-1'")


class AgenticRuntimeTest(TestCase):
    def test_planner_selects_tools_iteratively_and_logs_each_call(self):
        decisions = [
            {"tool": "interpret_variant", "rationale": "Raccolgo l'evidenza primaria."},
            {"tool": "assess_complexity", "rationale": "Valuto l'ampiezza del caso."},
            {"tool": "check_resistance", "rationale": "Cerco meccanismi di resistenza."},
            {"tool": "identify_targets", "rationale": "Cerco farmaci collegati."},
            {"tool": "match_trials", "rationale": "Cerco studi pertinenti."},
            {"tool": "finish", "rationale": "La raccolta è sufficiente."},
        ]

        def update(**values):
            return lambda state: {**state, **values}

        tools = {
            "assess_complexity": update(complexity="high"),
            "interpret_variant": update(variant_data={"evidence_records": [{"pmid": 1}]}),
            "identify_targets": update(drug_candidates=[{"drug_name": "Drug A"}]),
            "match_trials": update(trial_candidates=[{"nct_id": "NCT1"}]),
            "check_resistance": update(resistance_data=[]),
            "enrich_oncokb": update(oncokb_enrichment=[]),
        }
        initial = {
            "gene": "EGFR",
            "variant": "L858R",
            "tumor_type": "Lung Adenocarcinoma",
            "alteration_type": "point_mutation",
            "therapy_line": "first-line",
            "enrich_with_oncokb": False,
            "complexity": "low",
            "variant_data": {},
            "drug_candidates": [],
            "trial_candidates": [],
            "resistance_data": [],
            "oncokb_enrichment": [],
        }

        with TemporaryDirectory() as directory:
            ledger = EventLedger(Path(directory) / "events.sqlite3")
            result = run_agentic_collection(
                initial,
                ledger=ledger,
                planner_llm=_SequencedLLM(decisions),
                tool_registry=tools,
            )

        self.assertEqual(result.planning_mode, "llm_dynamic")
        self.assertEqual(result.tool_path, [
            "interpret_variant",
            "assess_complexity",
            "check_resistance",
            "identify_targets",
            "match_trials",
        ])
        self.assertTrue(result.ledger_valid)
        self.assertEqual(
            sum(event["event_type"] == "tool_completed" for event in result.events),
            5,
        )


class SourceVerifierTest(TestCase):
    def _item(self):
        return SimpleNamespace(
            subject="EGFR L858R",
            relation="Sensitivity/Response",
            object="EGFR L858R",
            context="Lung Adenocarcinoma",
            source_id="PMID:29151359",
            evidence_statement="Osimertinib improved progression-free survival in untreated EGFR-mutated NSCLC.",
            citation_text="Soria et al., 2018",
            evidence_level="A",
        )

    def test_verifier_requires_semantic_support_from_pubmed(self):
        llm = _SequencedLLM([[
            {"index": 0, "verdict": "supported", "reason": "Variante e tumore coincidono."}
        ]])
        results = verify_evidence_items(
            [self._item()],
            llm_client=llm,
            source_loader=lambda _pmids: {
                29151359: {
                    "title": "Osimertinib in untreated EGFR-mutated NSCLC",
                    "abstract": "The trial enrolled patients with EGFR-mutated advanced NSCLC.",
                }
            },
        )
        self.assertEqual(results[0].verdict, "supported")
        self.assertEqual(results[0].verification_level, "pubmed_abstract")
        self.assertFalse(results[0].requires_human_review)

    def test_missing_original_source_fails_closed(self):
        results = verify_evidence_items(
            [self._item()],
            llm_client=_SequencedLLM([]),
            source_loader=lambda _pmids: {},
        )
        self.assertEqual(results[0].verdict, "uncertain")
        self.assertTrue(results[0].requires_human_review)

    def test_clinical_anchor_mismatch_fails_closed_before_llm(self):
        item = self._item()
        item.object = "unrelated-drug"
        results = verify_evidence_items(
            [item],
            llm_client=_SequencedLLM([]),
            source_loader=lambda _pmids: {
                29151359: {
                    "title": "Osimertinib in untreated EGFR-mutated NSCLC",
                    "abstract": "The trial enrolled patients with EGFR-mutated advanced NSCLC.",
                }
            },
        )
        self.assertEqual(results[0].verdict, "uncertain")
        self.assertEqual(results[0].verification_level, "clinical_rules")
