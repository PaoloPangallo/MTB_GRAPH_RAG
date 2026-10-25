import pytest

from backend.research_pipeline.documents.sentence_spans import sentence_spans
from backend.research_pipeline.documents.parsers import JatsXmlParser, PubMedAbstractParser


@pytest.mark.parametrize('text, expected', [
    ('P = 0.004. Median survival was 9.4 months.', ['P = 0.004.', 'Median survival was 9.4 months.']),
    ('BRAF p.V600E was detected. See Fig. 2 for results.', ['BRAF p.V600E was detected.', 'See Fig. 2 for results.']),
    ('Dr. Smith et al. observed benefit. No response occurred.', ['Dr. Smith et al. observed benefit.', 'No response occurred.']),
    ('Dose 0.5 μM; P < .001. No benefit!', ['Dose 0.5 μM; P < .001.', 'No benefit!']),
])
def test_sentences_keep_biomedical_notation(text, expected):
    spans = sentence_spans(text)
    assert [text[a:b] for a, b in spans] == expected
    assert ''.join(text[a:b] for a, b in spans).replace(' ', '') == text.replace(' ', '')


def test_parsers_keep_decimals_and_local_offsets():
    text = 'P = 0.004. Median survival was 9.4 months.'
    pubmed = PubMedAbstractParser().parse('pmid:1', None, text)
    xml = f'<article><body><sec><title>Results</title><p>{text}</p></sec></body></article>'
    jats = JatsXmlParser().parse('pmcid:PMC1', xml)
    for units in (pubmed, jats):
        sentences = [u for u in units if u.unit_type.endswith('SENTENCE')]
        assert len(sentences) == 2
        assert all(text[u.char_start:u.char_end] == u.text for u in sentences)
