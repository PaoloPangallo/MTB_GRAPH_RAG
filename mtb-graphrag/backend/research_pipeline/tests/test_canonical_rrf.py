from dataclasses import replace

import pytest

from backend.research_pipeline.experimental import sourceunit_selector as selector
from backend.research_pipeline.retrieval.canonical_rrf import select_rrf, rrf_scores


def selection():
    return selector.SourceUnitSelectionInput.from_candidate(
        {"candidate_id": "c", "biomarkers": [{"type": "Gene", "label": "EGFR"}]},
        "d", [{"source_unit_id": str(i), "document_id": "d", "unit_type": "FULLTEXT_PARAGRAPH",
               "text": "EGFR inhibitor response in a different clinical population " + str(i)}
              for i in range(30)])


def test_rrf_depth_and_ties():
    scores = rrf_scores([[str(i) for i in range(30)], ["z"]])
    assert "25" not in scores
    assert scores["0"] == scores["z"] == 1 / 61


def test_exact_fusion_and_canonical_selection():
    item = selection()
    scores = {str(i): float(i) for i in range(30)}
    result = select_rrf(item, dense_scorer=lambda _: (scores, {"cache": "hit"}))
    templates = selector.rank(item, ranking_strategy="BM25")
    structure = sorted(templates, key=lambda r: (-r.score_lexical * r.section_prior * r.section_factor, r.source_unit_id))
    expected = rrf_scores([[r.source_unit_id for r in structure if not r.exclusion_reason and r.score_lexical > 0],
                           sorted(scores, key=lambda uid: (-scores[uid], uid))])
    assert {r.source_unit_id: r.score_total for r in result.ranked_source_units} == expected
    assert result.matched_features["retrieval"]["actual_strategy"] == "RRF_STRUCTURE_MEDCPT"


def test_error_falls_back_auditably():
    def fail(_):
        raise ValueError("cache mismatch")
    item = selection()
    result = select_rrf(item, dense_scorer=fail)
    baseline = selector.select(item, top_k=5, ranking_strategy="BM25_STRUCTURE")
    assert result.selected_source_unit_ids == baseline.selected_source_unit_ids
    assert result.matched_features["retrieval"]["fallback_reason"] == "ValueError: cache mismatch"
    assert result.matched_features["retrieval"]["actual_strategy"] == "BM25_STRUCTURE"


@pytest.mark.parametrize("scores", [{"bad": 1}, {"0": float("nan")}, {}])
def test_invalid_dense_falls_back(scores):
    result = select_rrf(selection(), dense_scorer=lambda _: (scores, {}))
    assert result.matched_features["retrieval"]["actual_strategy"] == "BM25_STRUCTURE"


def test_explicit_baseline_never_calls_dense():
    result = select_rrf(selection(), strategy="BM25_STRUCTURE", dense_scorer=lambda _: pytest.fail("inference"))
    assert result.matched_features["retrieval"]["fallback_reason"] is None
