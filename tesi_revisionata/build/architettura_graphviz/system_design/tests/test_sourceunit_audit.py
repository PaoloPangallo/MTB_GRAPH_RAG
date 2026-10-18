"""Occurrence identity, container offsets and locator coverage checks."""
from copy import deepcopy
import csv
import gzip
import json
from pathlib import Path
import sys
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE))
sys.path.insert(0,str(BASE.parents[3]/'mtb-graphrag'))
import sourceunit_audit as audit
from backend.research_pipeline.documents.models import SourceUnit
from backend.research_pipeline.documents.authorized_cache import finalize_source_unit_occurrence_ids


class UnitChecks(unittest.TestCase):
    def test_repeated_cells_keep_occurrence_identity_and_zero_coordinates(self):
        cell=SourceUnit.from_document_text('pmcid:PMC1','TABLE_CELL','Value',row=0,column=0).to_dict()
        units=finalize_source_unit_occurrence_ids('pmcid:PMC1',[cell,deepcopy(cell)])
        summary,rows=audit.audit_units('pmcid:PMC1',units)
        self.assertNotEqual(units[0]['source_unit_id'],units[1]['source_unit_id'])
        self.assertEqual(summary['issues'],{})
        self.assertEqual(summary['same_type_text_repetitions'],1)
        self.assertEqual(summary['locators']['row'],2)
        self.assertEqual(summary['locators']['column'],2)
        self.assertEqual(rows[0]['row'],0)

    def test_sentence_offsets_use_parent_paragraph_not_document(self):
        common={'section':'Results','paragraph_index':1}
        paragraph=SourceUnit.from_document_text('pmcid:PMC1','FULLTEXT_PARAGRAPH','First. Second.',**common).to_dict()
        sentence=SourceUnit.from_document_text('pmcid:PMC1','FULLTEXT_SENTENCE','Second.',char_start=7,char_end=14,**common).to_dict()
        self.assertEqual(audit.offset_check(sentence,[paragraph,sentence]),'CORRISPONDENZA_LETTERALE')
        sentence['char_start']=0
        sentence['char_end']=7
        self.assertEqual(audit.offset_check(sentence,[paragraph,sentence]),'INTERVALLO_DA_ESAMINARE')

    def test_abstract_outer_spaces_are_classified_separately(self):
        abstract={'unit_type':'ABSTRACT','text':'  Alpha.  '}
        section={'unit_type':'ABSTRACT_SECTION','text':'Alpha.','char_start':0,'char_end':10}
        self.assertEqual(audit.offset_check(section,[abstract,section]),'CORRISPONDENZA_CON_SPAZI_ESTERNI')
        self.assertEqual(audit.offset_check({'unit_type':'CONDITION','text':'Melanoma'},[]),'LOCALIZZAZIONE_STRUTTURALE')

    def test_finalized_id_tampering_is_reported(self):
        unit=SourceUnit.from_document_text('nct:NCT00000001','ABSTRACT','Trial').to_dict()
        unit['unit_type']='TRIAL_TITLE'
        unit=finalize_source_unit_occurrence_ids(unit['document_id'],[unit])[0]
        unit['source_unit_id']='SU-'+'0'*24
        summary,_=audit.audit_units(unit['document_id'],[unit])
        self.assertEqual(summary['issues']['IDENTITA_OCCORRENZA_DA_ESAMINARE'],1)


class GeneratedChecks(unittest.TestCase):
    def test_totals_reconcile_with_documents_and_types(self):
        data=json.loads((BASE/'verifica/sourceunit-audit.json').read_text(encoding='utf-8'))
        s=data['summary']
        self.assertEqual(s['units'],sum(row['units'] for row in data['documents']))
        for key in ('types','parsers','confidence','offsets','document_kinds'):
            self.assertEqual(sum(s[key].values()),s['units'])
        self.assertEqual(s['unique_source_unit_ids'],s['units'])
        self.assertEqual(s['issues'],{})
        self.assertEqual(sum(value['count'] for value in s['lengths'].values()),s['units'])
        self.assertEqual(data['historical_index']['with_text'],0)

    def test_full_inventory_is_readable_and_matches_summary(self):
        data=json.loads((BASE/'verifica/sourceunit-audit.json').read_text(encoding='utf-8'))
        count=0
        types={}
        with gzip.open(BASE/'verifica/sourceunit-inventario.csv.gz','rt',encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream)
            self.assertIn('bbox',reader.fieldnames)
            for row in reader:
                self.assertTrue(row['source_unit_id'].startswith('SU-'))
                count+=1
                types[row['unit_type']]=types.get(row['unit_type'],0)+1
        self.assertEqual(count,data['summary']['units'])
        self.assertEqual(types,data['summary']['types'])


if __name__=='__main__':
    unittest.main()
