from evaluation.sourceunit_retrieval_benchmark_v2_1.benchmark import (
    ARMS,
    TOP_K,
    build_plan,
    selector_identity,
    validate_inputs,
    verify_input_hashes,
)
import json
from pathlib import Path


REMOVED_PAIR = "GCA-002decb1b8be445d9dad8730|pmid:231047"
REPLACEMENT_PAIR = "GCA-00e16c83d9144ac87139b7a3|pmid:15928335"


def test_v21_dataset_and_plan_invariants_are_frozen():
    assert validate_inputs() == {
        "pair_count": 20,
        "sourceunit_count": 1706,
        "strict_positive_pairs": 9,
        "broad_positive_pairs": 10,
        "broad_negative_pairs": 10,
        "label_counts": {
            "DIRECTLY_RELEVANT": 30,
            "PARTIALLY_RELEVANT": 51,
            "CONTEXT_ONLY": 364,
            "NOT_RELEVANT": 1261,
        },
        "replacement_annotation_counts": {
            "DIRECTLY_RELEVANT": 3,
            "PARTIALLY_RELEVANT": 2,
            "CONTEXT_ONLY": 9,
            "NOT_RELEVANT": 0,
        },
        "retained_gold_label_changes": 0,
    }
    plan = build_plan()
    assert len(plan) == len({row["unit_id"] for row in plan}) == 60
    assert {row["retrieval_method"] for row in plan} == set(ARMS)
    assert {method: sum(row["retrieval_method"] == method for row in plan) for method in ARMS} == {
        "FIRST_K": 20, "BM25": 20, "DETERMINISTIC_SELECTOR": 20,
    }
    pair_ids = {row["pair_id"] for row in plan}
    assert REMOVED_PAIR not in pair_ids and REPLACEMENT_PAIR in pair_ids
    assert all(row["top_k"] == TOP_K == 5 for row in plan)
    assert not any("GOLD" in row["unit_id"] or "FULL_DOCUMENT" in row["unit_id"] for row in plan)


def test_v21_imports_the_frozen_production_selector_identity():
    identity = selector_identity()
    assert identity["version"] == "deterministic-sourceunit-selector/1.0"
    assert identity["bm25_k1"] == 1.5
    assert identity["bm25_b"] == 0.75
    assert identity["functions"] == {
        "FIRST_K": "select_first_k", "BM25": "select_bm25", "DETERMINISTIC_SELECTOR": "select",
    }


def test_v21_hashes_plan_determinism_and_protocol_rules_are_sealed():
    here = Path(__file__).parent
    plan = json.loads((here / "sealed_plan.json").read_text(encoding="utf-8"))
    assert plan == build_plan()
    assert verify_input_hashes() is True
    protocol = (here / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "Broad Hit@5" in protocol
    assert "FIRST_K < BM25 < DETERMINISTIC_SELECTOR" in protocol
    assert "WEIGHT_TUNING_LEAKAGE=POSSIBLE" in protocol
    assert "score_total > min_score" in protocol
    assert "results_20260831T000000Z" in protocol
    assert "GOLD" not in {row["retrieval_method"] for row in plan}


def test_replacement_annotation_provenance_is_manual_and_blind_to_retrievers():
    root = Path(__file__).parents[2]
    dataset = root / "evaluation" / "sourceunit_selector_external_validation_20_v2"
    manifest = json.loads((dataset / "gold_annotation_manifest.json").read_text(encoding="utf-8"))
    corpus = json.loads((dataset / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["annotation_method"] == "MANUAL_REVIEW"
    assert manifest["annotation_completed"] is True
    assert manifest["replacement_selected_before_annotation"] is True
    assert all(manifest[key] is False for key in (
        "retriever_output_visible_to_annotator", "bm25_output_visible_to_annotator",
        "selector_output_visible_to_annotator", "first_k_output_visible_to_annotator",
    ))
    assert corpus["ranking_evaluations_executed"] == 0
    assert corpus["first_k_executions"] == corpus["bm25_executions"] == corpus["deterministic_selector_executions"] == 0
