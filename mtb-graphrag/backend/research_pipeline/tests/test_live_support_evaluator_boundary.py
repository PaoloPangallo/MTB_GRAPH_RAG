from pathlib import Path


def test_live_v3_path_uses_canonical_relation_support_and_legacy_is_fallback_only():
    source = (Path(__file__).parents[1] / "orchestrator.py").read_text(encoding="utf-8")
    canonical_guard = 'if "observed_evidence_type" in call["enrichment"]:'
    assert canonical_guard in source
    canonical_pos = source.index("_assess_v3_quoted_relation(", source.index(canonical_guard))
    helper = source[source.index("def _assess_v3_quoted_relation("):source.index("def _reader_attempt_record(")]
    assert "assess_relation_support(candidate, enrichment, source_unit_text=quote)" in helper
    legacy_pos = source.index("assess_candidate_support(", canonical_pos)
    assert canonical_pos < legacy_pos
    assert source[canonical_pos:legacy_pos].count("else:") == 1
