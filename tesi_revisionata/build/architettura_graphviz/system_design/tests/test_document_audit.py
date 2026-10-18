"""Exercise identity, snapshot and content checks on small local fixtures."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys
import shutil
from uuid import uuid4
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
import document_audit as source


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        root = BASE.parents[3] / 'tmp'
        root.mkdir(exist_ok=True)
        self.root = (root / ('document-audit-' + uuid4().hex)).resolve()
        self.root.mkdir()
        self.assertTrue(self.root.is_relative_to(root.resolve()))
        self.addCleanup(shutil.rmtree,self.root)
        self.corpus = self.root / 'candidates.jsonl'
        rows = [
            {'candidate_id':'one','relation_family':'EVIDENCE_STATEMENT','document_identifiers':[{'pmid':'123','pmcid':'PMC456'}],'source_properties':{'evidence':{'evidence_id':'1'}}},
            {'candidate_id':'two','relation_family':'TRIAL_GENE','document_identifiers':[{'nct':'NCT00000001'}],
             'source_properties':{'trial':{'status':'RECRUITING','title':'Trial','phase':'PHASE1, PHASE2'}},'object':{'label':'BRAF'}}]
        self.corpus.write_text('\n'.join(json.dumps(row) for row in rows),encoding='utf-8')
        self.put('pubmed/metadata/123.json',json.dumps({'result':{'123':{'uid':'123','title':'Title','pubdate':'2020','pubtype':['Journal Article'],'articleids':[{'idtype':'pmc','value':'PMC456'}]}}}))
        self.put('pubmed/abstracts/123.xml','<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>123</PMID><Article><Abstract><AbstractText>Abstract text</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>')
        self.pmc = '<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><GetRecord><record><metadata><article><front><article-meta><article-id pub-id-type="pmcid">PMC456</article-id><article-id pub-id-type="pmid">123</article-id></article-meta></front><body><p>Full text.</p></body></article></metadata></record></GetRecord></OAI-PMH>'
        self.put('pmc/xml/PMC456.xml',self.pmc)
        self.nct = {'protocolSection':{'identificationModule':{'nctId':'NCT00000001','briefTitle':'Trial'},'statusModule':{'overallStatus':'COMPLETED'},'designModule':{'studyType':'INTERVENTIONAL','phases':['PHASE1']},'eligibilityModule':{'eligibilityCriteria':'Criteria'}},'hasResults':False}
        nct_bytes = json.dumps(self.nct).encode('utf-8')
        self.put('clinical_trials/NCT00000001.json',nct_bytes)
        manifest = [
            {'document_id':'nct:NCT00000001','local_cache_path':'clinical_trials/NCT00000001.json','content_hash':'old'},
            {'document_id':'nct:NCT00000001','local_cache_path':'clinical_trials/NCT00000001.json','content_hash':sha256(nct_bytes).hexdigest()},
            {'document_id':'pmcid:PMC456','local_cache_path':'pmc/xml/PMC456.xml','content_hash':'mismatch'}]
        self.put('manifests/documents.jsonl','\n'.join(json.dumps(row) for row in manifest))

    def put(self,relative,payload):
        path = self.root / relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(payload if isinstance(payload,bytes) else payload.encode('utf-8'))

    def test_oai_payload_pmcid_and_latest_snapshot(self):
        audit = source.collect(self.corpus,self.root)
        paper = audit['papers']['inventory'][0]
        trial = audit['trials']['inventory'][0]
        self.assertTrue(paper['fulltext_available'])
        self.assertEqual(paper['pmc_checks'][0]['state'],'IDENTITA_CONFORME')
        self.assertEqual(paper['pmc_checks'][0]['manifest_check']['state'],'IMPRONTA_DA_ESAMINARE')
        self.assertEqual(trial['manifest_check']['state'],'IMPRONTA_CONFORME')
        self.assertEqual(trial['status_comparison'],'VALORI_DIVERSI')
        self.assertEqual(audit['trials']['summary']['results'],{'CAMPO_HASRESULTS_FALSE':1})
        spec=importlib.util.spec_from_file_location('gca_renderer',BASE/'build-gca-audit.py')
        renderer=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        html=source.render(audit,'<main class="audit-main" id="main"></main>',renderer.table,renderer.section,renderer.n,renderer.pct)
        self.assertIn('pmc_manifest_check',html)

    def test_identity_mismatch_excluded_from_bibliographic_statistics(self):
        self.put('pubmed/metadata/123.json',json.dumps({'result':{'123':{'uid':'999','title':'Other paper'}}}))
        audit=source.collect(self.corpus,self.root)
        self.assertEqual(audit['papers']['summary']['metadata_checks'],{'IDENTITA_DA_ESAMINARE':1})
        self.assertEqual(audit['papers']['summary']['metadata_fields']['title'],0)

    def test_alternate_pmc_identifier_type_and_missing_file(self):
        self.put('pmc/xml/PMC456.xml',self.pmc.replace('pub-id-type="pmcid">PMC456','pub-id-type="pmc">456'))
        self.assertTrue(source.collect(self.corpus,self.root)['papers']['inventory'][0]['fulltext_available'])
        self.assertEqual(source.check_manifest(source.Inputs(self.root),{'local_cache_path':'absent.json'})['state'],'FILE_ASSENTE')

    def test_manifest_paths_stay_inside_selected_cache(self):
        inputs=source.Inputs(self.root)
        with self.assertRaises(ValueError):
            inputs.read('../outside.json')
        with self.assertRaises(ValueError):
            inputs.read(str(self.root/'absolute.json'))


if __name__=='__main__':
    unittest.main()
