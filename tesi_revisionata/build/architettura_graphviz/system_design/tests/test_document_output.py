"""Cross-check generated source inventories against the independent GCA census."""
import csv
import json
from pathlib import Path
import unittest

BASE=Path(__file__).resolve().parents[1]/'verifica'


class GeneratedSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit=json.loads((BASE/'fonti-audit.json').read_text(encoding='utf-8'))
        cls.gca=json.loads((BASE/'gca-audit.json').read_text(encoding='utf-8'))

    def test_identifiers_and_links_reconcile_with_gca_census(self):
        a,g=self.audit,self.gca
        self.assertEqual(a['provenance']['corpus_sha256'],g['provenance']['sha256'])
        invalid=a['malformed_references']
        for kind,key,idfield in [('papers','pmid','pmid'),('trials','nct','nct')]:
            rows=a[kind]['inventory']
            self.assertEqual(len(rows)+len({row['value'] for row in invalid if row['field']==key}),g['documents'][key]['distinct'])
            self.assertEqual(sum(row['gca_count'] for row in rows)+sum(row['field']==key for row in invalid),g['documents'][key]['candidate_links'])
            self.assertEqual(len({row[idfield] for row in rows}),len(rows))
            for row in rows:
                self.assertEqual(len(row['candidate_ids']),row['gca_count'])
                self.assertEqual(sum(row['families'].values()),row['gca_count'])

    def test_content_counts_and_csv_inventories_match(self):
        for kind,name in [('papers','paper-audit-inventario.csv'),('trials','nct-audit-inventario.csv')]:
            with (BASE/name).open(encoding='utf-8-sig',newline='') as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),len(self.audit[kind]['inventory']))
        p=self.audit['papers']
        t=self.audit['trials']
        self.assertEqual(sum(row['fulltext_available'] for row in p['inventory']),p['summary']['fulltexts_with_body'])
        self.assertEqual(sum(row.get('has_results') is True for row in t['inventory']),t['summary']['results'].get('RISULTATI_DEPOSITATI',0))
        self.assertEqual(sum(t['summary']['payload_checks'].values()),t['summary']['unique_ncts'])


if __name__=='__main__':
    unittest.main()
