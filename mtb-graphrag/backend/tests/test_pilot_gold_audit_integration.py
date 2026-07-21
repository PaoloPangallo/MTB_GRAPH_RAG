"""Test di integrazione dell'audit contro un'istanza Neo4j reale.

Disattivato per default: la suite deve restare eseguibile offline. Per attivarlo:

    RUN_NEO4J_INTEGRATION=1 PYTHONPATH=. python -m unittest \\
        backend.tests.test_pilot_gold_audit_integration
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import TestCase

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD_PATH = (
    PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "pilot" / "input"
    / "mtb_evidence_gold_pilot_v1.jsonl"
)

_ENABLED = os.getenv("RUN_NEO4J_INTEGRATION") == "1"


@unittest.skipUnless(_ENABLED, "richiede RUN_NEO4J_INTEGRATION=1 e un'istanza Neo4j attiva")
class PilotAuditIntegrationTest(TestCase):
    def test_snapshot_is_reachable_and_the_four_cases_run(self):
        from benchmarks.mtb_evidence.pilot.audit_lib.aliases import build_alias_table
        from benchmarks.mtb_evidence.pilot.audit_lib.compare import compare_case
        from benchmarks.mtb_evidence.pilot.audit_lib.gold import load_gold
        from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import Neo4jGraphClient
        from benchmarks.mtb_evidence.pilot.audit_lib.queries import (
            a2_alk,
            c1_egfr,
            k1_fgfr2,
            n1_rmi2,
        )
        from benchmarks.mtb_evidence.pilot.audit_lib.snapshot import build_snapshot_manifest

        client = Neo4jGraphClient()
        table = build_alias_table()
        cases = {case.case_id: case for case in load_gold(GOLD_PATH)}

        manifest = build_snapshot_manifest(client, repo_root=PROJECT_ROOT.parent)
        self.assertEqual(len(manifest["snapshot_fingerprint"]["value"]), 64)
        self.assertGreater(manifest["total_nodes"], 0)
        self.assertNotIn("@", manifest["neo4j_uri"].split("//", 1)[-1].split("/")[0])

        runners = {
            k1_fgfr2.CASE_ID: k1_fgfr2.run,
            a2_alk.CASE_ID: a2_alk.run,
            c1_egfr.CASE_ID: c1_egfr.run,
            n1_rmi2.CASE_ID: n1_rmi2.run,
        }
        for case_id, runner in runners.items():
            with self.subTest(case=case_id):
                case = cases[case_id]
                outcome = runner(client, case, table)
                comparison = compare_case(
                    case,
                    outcome.graph_claims,
                    alias_table=table,
                    found_pmids=outcome.found_pmids,
                    found_nct_ids=outcome.found_nct_ids,
                    found_therapies=outcome.found_therapies,
                    extra_blockers=outcome.blockers,
                )
                self.assertTrue(outcome.results, "nessuna query eseguita")
                self.assertIn("freeze_ready", comparison)

    def test_rmi2_traversal_is_empty_on_this_snapshot(self):
        """La prova negativa del caso N1 deve reggere sullo snapshot corrente."""
        from benchmarks.mtb_evidence.pilot.audit_lib.aliases import build_alias_table
        from benchmarks.mtb_evidence.pilot.audit_lib.gold import load_gold
        from benchmarks.mtb_evidence.pilot.audit_lib.graph_client import Neo4jGraphClient
        from benchmarks.mtb_evidence.pilot.audit_lib.queries import n1_rmi2

        cases = {case.case_id: case for case in load_gold(GOLD_PATH)}
        outcome = n1_rmi2.run(Neo4jGraphClient(), cases[n1_rmi2.CASE_ID], build_alias_table())
        proof = n1_rmi2.build_negative_path_proof(outcome, snapshot_fingerprint="integration")
        # Se questo test fallisce lo snapshot e' cambiato e il caso N1 non e' piu' un
        # no-answer valido: va segnalato, non aggirato.
        self.assertEqual(proof["therapeutic_path_count"], 0)
        self.assertTrue(proof["is_valid_negative"])
