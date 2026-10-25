from backend.research_pipeline.casecontext.match_verifier import verify_case_context


def alteration_record(biomarker, text):
    return next(record for record in verify_case_context({'biomarkers': [biomarker]}, text)
                if record.field == 'alteration[0]')


def test_alteration_uses_its_own_grounded_span_instead_of_first_gene_span():
    text = 'Molecular profiling reports MET Exon 14 Skipping Mutation.'
    biomarker = {
        'raw_value': 'MET Exon 14 Skipping Mutation', 'normalized_value': 'MET Exon 14 Skipping Mutation',
        'gene': 'MET', 'alteration': 'Exon 14 Skipping Mutation',
        'source_spans': [{'quote': 'MET'}, {'quote': 'Exon 14 Skipping Mutation'}],
        'gene_source_spans': [{'quote': 'MET'}],
        'alteration_source_spans': [{'quote': 'Exon 14 Skipping Mutation'}],
    }
    record = alteration_record(biomarker, text)
    assert record.status == 'MATCH'
    assert record.supporting_text == 'Exon 14 Skipping Mutation'
    assert text[record.start_offset:record.end_offset] == record.supporting_text


def test_explicit_empty_alteration_spans_cannot_fall_back_to_gene_context():
    biomarker = {'raw_value': 'MET amplification', 'normalized_value': 'MET amplification',
                 'alteration': 'amplification', 'source_spans': [{'quote': 'MET amplification'}],
                 'alteration_source_spans': []}
    record = alteration_record(biomarker, 'MET amplification')
    assert record.status == 'MISMATCH'
    assert record.reason_code == 'VALUE_WITHOUT_SOURCE_SPAN'


def test_legacy_combined_span_still_verifies_without_explicit_field_spans():
    biomarker = {'raw_value': 'KRAS G12D', 'normalized_value': 'KRAS G12D',
                 'alteration': 'G12D', 'source_spans': [{'quote': 'KRAS G12D'}]}
    assert alteration_record(biomarker, 'KRAS G12D').status == 'MATCH'


def test_specific_alteration_quote_must_still_be_literal_in_original_text():
    biomarker = {'raw_value': 'MET amplification', 'normalized_value': 'MET amplification',
                 'alteration': 'amplification', 'source_spans': [{'quote': 'MET'}],
                 'alteration_source_spans': [{'quote': 'amplification'}]}
    record = alteration_record(biomarker, 'MET overexpression')
    assert record.status == 'MISMATCH'
    assert record.reason_code == 'QUOTE_NOT_IN_TEXT'
