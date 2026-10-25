from backend.research_pipeline.documents.unit_structure import build_unit_structure


def test_sentence_has_parent_and_is_not_encoded_twice():
    common = {'document_id': 'pmid:1', 'section': 'Results', 'paragraph_index': 0}
    units = [dict(common, source_unit_id='p', unit_type='FULLTEXT_PARAGRAPH', text='P = 0.004. Response occurred.'),
             dict(common, source_unit_id='s', unit_type='FULLTEXT_SENTENCE', text='P = 0.004.')]
    structure = build_unit_structure(units)
    assert structure['s']['parent_id'] == 'p'
    assert structure['p']['indexable'] is True
    assert structure['s']['indexable'] is False


def test_same_paragraph_number_in_another_document_does_not_match():
    units = [{'source_unit_id': 'p', 'document_id': 'pmid:1', 'unit_type': 'FULLTEXT_PARAGRAPH', 'text': 'same'},
             {'source_unit_id': 's', 'document_id': 'pmid:2', 'unit_type': 'FULLTEXT_SENTENCE', 'text': 'same'}]
    assert build_unit_structure(units)['s']['parent_id'] is None
    assert build_unit_structure(units)['s']['indexable'] is True


def test_table_evidence_remains_reachable():
    units = [{'source_unit_id': 'c', 'document_id': 'pmid:1', 'unit_type': 'TABLE_CELL',
              'text': 'BRAF V600E resistance', 'table_id': 't', 'row': 1, 'column': 0}]
    assert build_unit_structure(units)['c']['indexable'] is True
