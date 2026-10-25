import pytest

from backend.research_pipeline.tests.test_case_entity_resolution import fixture
from backend.research_pipeline.terminology.case_resolution import (
    compare_disease_context,
    disease_context,
    disease_retrieval_match,
)


@pytest.mark.parametrize('value', ['(colorectal cancer)', '[colorectal cancer]', '(colorectal cancer) metastatic'])
def test_punctuation_does_not_hide_disease(value):
    result = disease_context(value, fixture())
    assert result['status'] == 'RESOLVED'
    span = result['match_span']
    assert value[span['start']:span['end']] == 'colorectal cancer'
    assert result['raw_value'] == value


def test_independent_qualifier_order_does_not_change_scope():
    registry = fixture()
    left = 'recurrent metastatic colorectal cancer'
    right = 'metastatic recurrent colorectal cancer'
    assert disease_retrieval_match(left, right, registry)['eligible']
    assert compare_disease_context(left, right, registry)['classification'] == 'MATCH'
    assert disease_context(left, registry)['raw_residual_context'] == 'recurrent metastatic'


@pytest.mark.parametrize('qualifier', ['non resecabile', 'non resecabili'])
def test_italian_unresectable_phrase(qualifier):
    registry = fixture()
    value = f'colorectal cancer {qualifier}'
    result = disease_context(value, registry)
    assert result['status'] == 'RESOLVED'
    assert result['residual_context'] == 'unresectable'
    assert result['raw_residual_context'] == qualifier
    assert disease_retrieval_match(value, 'unresectable colorectal cancer', registry)['eligible']


@pytest.mark.parametrize('left,right', [
    ('resected', 'unresectable'),
    ('stage iii', 'stage iv'),
    ('stage iii', 'iii stage'),
    ('locally advanced', 'advanced'),
    ('locally advanced recurrent', 'recurrent locally advanced'),
    ('metastatic recurrent recurrent', 'recurrent metastatic'),
    ('not metastatic', 'metastatic'),
    ('non resecabile sospetto', 'unresectable'),
])
def test_distinct_or_unknown_context_is_not_equated(left, right):
    assert not disease_retrieval_match(
        f'colorectal cancer {left}', f'colorectal cancer {right}', fixture()
    )['eligible']


def test_word_boundary_does_not_match_embedded_disease():
    assert disease_context('pseudocolorectal cancer', fixture())['status'] == 'UNMAPPED'


def test_hyphenated_suffix_does_not_become_exact_disease():
    assert disease_context('colorectal cancer-like', fixture())['status'] == 'UNMAPPED'
