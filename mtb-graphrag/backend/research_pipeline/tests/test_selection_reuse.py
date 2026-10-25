from backend.research_pipeline.retrieval.live_sourceunit_selection import SelectionIndex


def test_selection_index_owns_run_local_cache():
    first = SelectionIndex({}, {})
    second = SelectionIndex({}, {})
    first.selection_cache['one'] = 'value'
    assert not second.selection_cache
