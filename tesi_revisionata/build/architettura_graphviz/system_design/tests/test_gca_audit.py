"""Audit checks distinguish source records, semantic groups and references."""
from copy import deepcopy
import importlib.util
import json
import sys
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
SPEC = importlib.util.spec_from_file_location('gca_audit', BASE / 'build-gca-audit.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AuditTests(unittest.TestCase):
    def test_source_paths_keep_mixed_and_other_separate(self):
        cases = [([], 'kg'), ([{'pmid': '1'}], 'publication'),
                 ([{'nct': 'NCT00000001'}], 'registry'),
                 ([{'pmid': '1', 'nct': 'NCT00000001'}], 'mixed'),
                 ([{'unknown': 'x'}], 'other')]
        for refs, expected in cases:
            with self.subTest(refs=refs):
                self.assertEqual(MODULE.classify({'document_identifiers': refs}), expected)

    def test_semantic_repetition_is_not_a_duplicate_record(self):
        audit = json.loads((BASE / 'verifica/gca-audit.json').read_text(encoding='utf-8'))
        first = deepcopy(next(iter(audit['examples'].values())))
        second = deepcopy(first)
        second['candidate_id'] += '-other'
        second['source_record_ids'] = ['a-distinct-source-unit']
        first['document_identifiers'] = [{'pmid': '123'}, {'pmid': '123'}]
        second['document_identifiers'] = [{'pmid': '10.1234/example', 'valid_pmid': False}]
        observed = MODULE.census([first, second])
        self.assertEqual(observed['candidate_id_repetitions'], 0)
        self.assertEqual(observed['semantic_key_repetitions'], 1)
        self.assertEqual(observed['semantic_groups_repeated'], 1)
        self.assertEqual(observed['documents']['pmid']['candidate_links'], 2)
        self.assertEqual(len(observed['invalid_references']), 1)
        self.assertTrue(observed['invalid_references'][0]['flagged'])

    def test_real_census_matches_pinned_reports_and_totals(self):
        actual = MODULE.collect()
        saved = json.loads((BASE / 'verifica/gca-audit.json').read_text(encoding='utf-8'))
        self.assertEqual(json.loads(json.dumps(actual)), saved)
        self.assertTrue(all(actual['checks'].values()))
        self.assertEqual(sum(actual['families'].values()), actual['total'])
        self.assertEqual(sum(actual['paths'].values()), actual['total'])
        self.assertEqual(sum(actual['resolution_snapshot']['statuses'].values()), actual['documents']['pmid']['distinct'])
        self.assertEqual(actual['candidate_ids_distinct'], actual['total'])
        self.assertEqual(actual['semantic_keys_distinct'] + actual['semantic_key_repetitions'], actual['total'])
        self.assertEqual(len({row['value'] for row in actual['invalid_references']}), 2)


if __name__ == '__main__':
    unittest.main()
