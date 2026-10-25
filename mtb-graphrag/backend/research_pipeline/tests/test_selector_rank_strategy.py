import pytest

from backend.research_pipeline.experimental import sourceunit_selector as selector
from backend.research_pipeline.tests.test_sourceunit_selector import make_input, unit


def test_bm25_strategy_preserves_identity_exclusions():
    selection = make_input([
        unit('wrong', 'ABL1 V299M dasatinib dasatinib dasatinib.'),
        unit('right', 'ABL1 V299L showed sensitivity to dasatinib in Chronic Myeloid Leukemia.')],
        candidate={'candidate_id': 'test', 'biomarkers': [{'type': 'Variant', 'gene': 'ABL1', 'alteration': 'V299L'}],
                   'interventions': [{'label': 'dasatinib'}], 'disease': [{'label': 'Chronic Myeloid Leukemia'}]})
    result = selector.select(selection, top_k=2, ranking_strategy='BM25')
    assert 'right' in result.selected_source_unit_ids
    assert 'wrong' not in result.selected_source_unit_ids
    assert result.selector_version.endswith('/BM25')


def test_strategy_must_be_explicitly_supported():
    with pytest.raises(ValueError):
        selector.select(make_input([]), ranking_strategy='typo')


def test_bm25_scores_not_clinical_feature_scores():
    selection = make_input([unit('right', 'ABL1 V299L sensitivity to dasatinib.')])
    ranked = selector.rank(selection, ranking_strategy='BM25')
    assert ranked[0].score_total == ranked[0].score_lexical
