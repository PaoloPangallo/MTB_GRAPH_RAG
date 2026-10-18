"""Offline checks for extraction, artifacts and navigation of the prompt guide."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import unittest
import sys
from html import escape

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
SPEC = importlib.util.spec_from_file_location('prompt_guide', BASE / 'build-prompts.py')
GUIDE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GUIDE)


class PromptGuideTests(unittest.TestCase):
    def test_multistudy_examples_show_coverage_and_comparisons(self):
        page = (BASE / 'Prove_narratore_per_il_relatore.html').read_text(encoding='utf-8')
        self.assertIn('Una spiegazione per ogni osservazione', page)
        self.assertIn('Confronto tra gli studi', page)
        self.assertIn('Risultati contrastanti', page)
        self.assertIn('href="Audit_semantico_del_dossier.html"', page)
        report = json.loads((BASE / 'verifica/narratore-multistudio.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report['cases']), 10)
        for row in report['cases']:
            for candidate in row['call']['narrative']['candidate_narratives']:
                for observation in candidate['observation_narratives']:
                    self.assertIn(escape(observation['case_relevance']), page)
            for mutation in row['omission_mutations']:
                self.assertEqual(mutation['verification']['status'], mutation['expected_status'])

    def test_real_source_cards_precede_commentary_and_synthetic_tests(self):
        page = (BASE / 'Prove_narratore_per_il_relatore.html').read_text(encoding='utf-8')
        self.assertIn('Scheda della fonte', page)
        self.assertIn('Adjuvant Dabrafenib plus Trametinib', page)
        self.assertLess(page.index('Scheda della fonte'), page.index('Test storici del contratto'))
        report = json.loads((BASE / 'verifica/narratore-fonti-documentate.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report['cases']), 3)
        self.assertTrue(all(row['call']['narrative']['canonical_sources'] for row in report['cases']))

    def test_four_readable_responses_are_traceable(self):
        examples = json.loads((BASE / 'prompt-sistema/esempi-risposte.json').read_text(encoding='utf-8'))
        self.assertEqual(set(examples), {'parser', 'reader', 'semantica', 'narratore'})
        self.assertEqual(examples['parser']['rows'][2][1], 'V600K')
        self.assertEqual(examples['semantica']['raw_response']['relation_alignment'], 'SAME')
        self.assertEqual(examples['semantica']['kind'], 'SYNTHETIC_CONTRACT_TEST_EXPECTED_RESPONSE')
        for example in examples.values():
            source = GUIDE.ROOT / example['source']['file']
            self.assertEqual(sha256(source.read_bytes()).hexdigest(), example['source']['sha256'])
        html = (BASE / 'Prompt_di_sistema_per_il_relatore.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('class="prompt-response"'), 4)
        self.assertIn('Risposta effettiva del modello', html)

    def test_narrator_report_separates_real_calls_and_contract_checks(self):
        report = json.loads((BASE / 'verifica/narratore-dieci-casi.json').read_text(encoding='utf-8'))
        self.assertEqual(report['mode'], 'LIVE_MODEL')
        self.assertEqual(report['case_count'], 10)
        self.assertEqual(report['model_narratives_passing_checks'], 8)
        self.assertEqual(report['model_narratives_failing_checks'], 2)
        mutations = [m for row in report['cases'] if row['verification']['status'] == 'PASS'
                     for m in row['mutations']]
        self.assertEqual(len(mutations), 48)
        self.assertTrue(all(m['status'] == 'FAIL' for m in mutations))
        self.assertTrue(all(row['fallback_verification']['status'] == 'PASS' for row in report['cases']))
        prompt = (BASE / 'prompt-sistema/narratore.txt').read_text(encoding='utf-8')
        self.assertIn('Write the explanation in Italian', prompt)
        self.assertTrue(prompt.startswith('ROLE AND PURPOSE'))

    def test_literal_prompts_match_backend(self):
        records = json.loads((BASE / 'prompt-sistema/provenienza.json').read_text(encoding='utf-8'))
        self.assertEqual(len(records), 4)
        for record in records:
            source = GUIDE.ROOT / record['source']
            self.assertEqual(sha256(source.read_bytes()).hexdigest(), record['source_sha256'])
            prompt = (BASE / 'prompt-sistema' / (record['role'] + '.txt')).read_text(encoding='utf-8')
            self.assertEqual(sha256(prompt.encode()).hexdigest(), record['prompt_sha256'])
        parser = BASE / 'prompt-sistema/parser.txt'
        self.assertIn('A bare hyphenated gene symbol', parser.read_text(encoding='utf-8'))

    def test_navigation_and_downloads(self):
        page = (BASE / 'Prompt_di_sistema_per_il_relatore.html').read_text(encoding='utf-8')
        for anchor in re.findall(r'href="#([^"]+)"', page):
            self.assertIn('id="' + anchor + '"', page)
        for relative in re.findall(r'href="([^"]+)"[^>]*download', page):
            self.assertTrue((BASE / relative).is_file(), relative)
        self.assertNotIn('<script src=', page)
        for edition in ('index.html', 'Architettura_per_il_relatore.html',
                        'Architettura_per_il_relatore_breve.html', 'System_design_architettura.html'):
            self.assertIn('href="Prompt_di_sistema_per_il_relatore.html"',
                          (BASE / edition).read_text(encoding='utf-8'))

    def test_reader_example_is_valid_against_current_schema(self):
        # Schema construction uses module constants; imports are safe and local.
        import sys
        sys.path.insert(0, str(GUIDE.BACKEND.parent))
        from research_pipeline.enrichment.prompt_v3 import TOOL_SCHEMA
        from jsonschema import validate
        validate({'decision': 'ABSTAIN', 'abstain_reason': 'NO_RELEVANT_EVIDENCE'}, TOOL_SCHEMA)


if __name__ == '__main__':
    unittest.main()
