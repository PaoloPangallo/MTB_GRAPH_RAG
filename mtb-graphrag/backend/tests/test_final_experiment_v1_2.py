from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import validate
from benchmarks.mtb_evidence.final_experiment.harness import canonical_sha256, run_key


class FinalExperimentV12ArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.path = cls.root / 'benchmarks/mtb_evidence/final_experiment/v1_2'

    def _json(self, name: str) -> dict:
        return json.loads((self.path / name).read_text(encoding='utf-8'))

    def _jsonl(self, name: str) -> list[dict]:
        return [json.loads(line) for line in
                (self.path / name).read_text(encoding='utf-8').splitlines()]

    def test_v3_only_query_and_slot_counts(self) -> None:
        core = self._jsonl('v3_core_queries_v1_2.jsonl')
        advanced = self._jsonl('v3_advanced_queries_v1_2.jsonl')
        all_rows = self._jsonl('all_queries_v1_2.jsonl')
        self.assertEqual(9, len(core))
        self.assertEqual(13, len(advanced))
        self.assertEqual(22, len(all_rows))
        self.assertEqual(set(row['query_id'] for row in all_rows),
                         set(row['query_id'] for row in core + advanced))
        self.assertTrue(all(row['system'] == 'S3' and not row['comparative'] for row in all_rows))
        plan = self._jsonl('run_plan_v1_2.jsonl')
        self.assertEqual(132, len(plan))
        self.assertEqual(132, len({row['run_id'] for row in plan}))
        self.assertEqual(132, len({row['run_key'] for row in plan}))
        run_ids = {row['run_id'] for row in plan}
        for row in plan:
            if row.get('source_structured_run_id'):
                self.assertIn(row['source_structured_run_id'], run_ids)
            if row['slot_type'] == 'minimax_judge':
                self.assertIn(row['source_structured_run_id'], run_ids)
        self.assertEqual(44, sum(row['slot_type'] == 'structured_retrieval' for row in plan))
        self.assertEqual(44, sum(row['slot_type'] == 'gemma_rendering' for row in plan))
        self.assertEqual(22, sum(row['slot_type'] == 'minimax_judge' for row in plan))
        self.assertEqual(22, sum(row['slot_type'] == 'nemotron_rendering' for row in plan))
        self.assertTrue(all(row['system'] == 'S3' for row in plan))

    def test_plan_schema_hashes_and_resume_identity(self) -> None:
        schema = self._json('run_plan_schema_v1_2.json')
        for row in self._jsonl('run_plan_v1_2.jsonl'):
            validate(instance=row, schema=schema)
            self.assertEqual(row['run_key'], run_key(row['run_spec']))
        for name in ('protocol_v1_2.json', 'metrics_v1_2.json', 'models_v1_2.json',
                     'official_ledger_manifest_v1_2.json', 'readiness_report_v1_2.json',
                     'run_plan_schema_v1_2.json'):
            payload = self._json(name)
            self.assertEqual(payload['content_sha256'], canonical_sha256(payload))

    def test_endpoint_and_authorization_state(self) -> None:
        protocol = self._json('protocol_v1_2.json')
        self.assertEqual('macro-averaged bucket decision accuracy', protocol['primary_endpoint']['name'])
        self.assertEqual(22, protocol['primary_endpoint']['query_count'])
        self.assertFalse(protocol['gold_opening_authorized'])
        self.assertFalse(protocol['official_runs_authorized'])
        self.assertEqual(0, protocol['gold_read_count'])
        readiness = self._json('readiness_report_v1_2.json')
        self.assertTrue(readiness['final_experiment_protocol_frozen'])
        self.assertEqual(0, readiness['blocker_count'])

    def test_no_comparative_or_v2_slots(self) -> None:
        rows = self._jsonl('run_plan_v1_2.jsonl')
        self.assertTrue(all(row['system'] == 'S3' for row in rows))
        self.assertTrue(all('S1' not in row['run_id'] and 'S2' not in row['run_id'] for row in rows))
        self.assertTrue(all(not row['comparative'] for row in rows))


if __name__ == '__main__':
    unittest.main()
