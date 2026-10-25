"""Offline checks for the independent frozen-selector evaluation artifacts."""

import csv
import json
from pathlib import Path


REPORT = Path(__file__).resolve().parents[3] / "evaluation" / "sourceunit_selector_independent"


def _load_json(name: str) -> dict:
    return json.loads((REPORT / name).read_text(encoding="utf-8"))


def test_independent_corpus_is_large_and_disjoint_from_pilot() -> None:
    corpus = _load_json("corpus_inventory.json")
    assert corpus["valid_pair_count"] >= 15
    assert corpus["document_count"] >= 15
    assert corpus["overlap_with_pilot_candidates"] == []
    assert corpus["overlap_with_pilot_documents"] == []
    assert corpus["full_text_persisted_in_artifacts"] is False


def test_gold_is_frozen_before_selector_and_has_no_text_column() -> None:
    manifest = _load_json("gold_annotation_manifest.json")
    assert manifest["selector_started_after_gold_frozen"] is True
    assert manifest["selector_ranking_seen_during_annotation"] is False
    assert manifest["expected_quote_seen_during_annotation"] is False
    with (REPORT / "gold_annotations.csv").open(encoding="utf-8", newline="") as handle:
        fields = set(csv.DictReader(handle).fieldnames or ())
    assert "text" not in fields
    assert {"candidate_id", "document_id", "source_unit_id", "relevance_label"} <= fields


def test_selector_has_zero_gold_access_and_zero_invented_units() -> None:
    leakage = _load_json("leakage_audit.json")
    scorecard = _load_json("final_scorecard.json")
    assert leakage["selector_gold_access_count"] == 0
    assert leakage["independent_gold_access_during_inference"] == 0
    assert leakage["selector_uses_llm"] is False
    assert scorecard["invented_source_unit_count"] == 0


def test_equivalent_input_ranking_drift_is_zero() -> None:
    robustness = _load_json("robustness.json")
    assert robustness["ranking_drift"] == 0
    assert robustness["ranking_drift_invariant_variants"] == 0
    assert robustness["repeat_count"] == 10
    assert robustness["repeated_hash_drift"] == 0
    assert robustness["checks"]["duplicate_permutation_stable"] is True
    assert robustness["checks"]["empty_permutation_stable"] is True


def test_retrieval_artifact_contains_all_required_strategies() -> None:
    metrics = _load_json("selector_metrics.json")
    assert metrics["gold_frozen_before_selector"] is True
    assert {"baseline_first_k:direct", "baseline_bm25:direct", "feature_selector:direct"} <= set(metrics["strategies"])
    assert metrics["strategies"]["feature_selector:direct"]["hit_rate@5"] >= metrics["strategies"]["baseline_first_k:direct"]["hit_rate@5"]
