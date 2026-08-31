from evaluation.sourceunit_retrieval_benchmark_v2.benchmark import (
    ARMS,
    TOP_K,
    build_plan,
    build_unit_output,
    evaluate_ranked_ids,
    paired_continuous_summary,
    paired_hit_table,
    selector_identity,
    validate_inputs,
)
import json
from pathlib import Path


def test_plan_has_exactly_three_arms_and_no_gold():
    pairs = ["pair-a", "pair-b"]
    plan = build_plan(pairs)
    assert ARMS == ("FIRST_K", "BM25", "DETERMINISTIC_SELECTOR")
    assert TOP_K == 5
    assert len(plan) == 6
    assert {unit["retrieval_method"] for unit in plan} == set(ARMS)
    assert not any("GOLD" in unit["unit_id"] for unit in plan)


def test_metrics_exclude_zero_gold_from_positive_metrics_and_report_exposure():
    labels = {"u1": "DIRECTLY_RELEVANT", "u2": "PARTIALLY_RELEVANT",
              "u3": "CONTEXT_ONLY", "u4": "NOT_RELEVANT", "u5": "NOT_RELEVANT"}
    positive = evaluate_ranked_ids(["u3", "u2", "u4", "u5"], labels)
    assert positive["strict_hit_at_5"] == 0
    assert positive["broad_hit_at_5"] == 1
    assert positive["broad_mrr_at_5"] == 0.5
    assert positive["broad_ndcg_at_5"] > 0
    negative = evaluate_ranked_ids(["u3", "u4", "u3", "u4"],
                                   {"u3": "CONTEXT_ONLY", "u4": "NOT_RELEVANT"})
    assert negative["broad_positive_pair"] is False
    assert negative["broad_hit_at_5"] is None
    assert negative["negative_pair_metrics"] == {
        "fraction_top5_context_only": 0.5,
        "fraction_top5_not_relevant": 0.5,
        "max_relevance_grade_top5": 0,
    }


def test_frozen_dataset_invariants_and_production_selector_identity():
    assert validate_inputs() == {
        "pair_count": 20, "sourceunit_count": 1697, "strict_positive_pairs": 9,
        "broad_positive_pairs": 10, "broad_negative_pairs": 10,
    }
    identity = selector_identity()
    assert identity["version"] == "deterministic-sourceunit-selector/1.0"
    assert identity["bm25_k1"] == 1.5 and identity["bm25_b"] == 0.75
    assert identity["functions"] == {
        "FIRST_K": "select_first_k", "BM25": "select_bm25", "DETERMINISTIC_SELECTOR": "select"
    }


def test_ndcg_uses_direct_gain_two_and_partial_gain_one():
    labels = {"direct": "DIRECTLY_RELEVANT", "partial": "PARTIALLY_RELEVANT", "none": "NOT_RELEVANT"}
    direct_first = evaluate_ranked_ids(["direct", "partial", "none"], labels)["broad_ndcg_at_5"]
    partial_first = evaluate_ranked_ids(["partial", "direct", "none"], labels)["broad_ndcg_at_5"]
    assert direct_first == 1.0
    assert 0 < partial_first < direct_first


def test_sealed_plan_has_60_unique_offline_only_units():
    plan_path = Path(__file__).with_name("sealed_plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert len(plan) == len({row["unit_id"] for row in plan}) == 60
    assert len({row["pair_id"] for row in plan}) == 20
    assert {method: sum(row["retrieval_method"] == method for row in plan) for method in ARMS} == {
        "FIRST_K": 20, "BM25": 20, "DETERMINISTIC_SELECTOR": 20,
    }
    assert all(row["top_k"] == 5 and row["provider_requirement"] == "PROHIBITED" for row in plan)
    assert not any("GOLD" in row["unit_id"] or "FULL_DOCUMENT" in row["unit_id"] for row in plan)


def test_paired_utilities_keep_raw_counts_and_deterministic_bootstrap_ci():
    table = paired_hit_table([1, 1, 0, 0], [1, 0, 1, 0])
    assert table == {"both_hit": 1, "first_only": 1, "second_only": 1, "both_miss": 1, "mcnemar_exact_pvalue": 1.0}
    summary = paired_continuous_summary([0.1, 0.4, 0.9], [0.0, 0.2, 0.4], bootstrap_samples=100, seed=7)
    assert summary["paired_n"] == 3
    assert summary["mean_delta"] == (0.1 + 0.2 + 0.5) / 3
    assert summary["median_delta"] == 0.2
    assert len(summary["bootstrap_95_ci"]) == 2


def test_output_schema_is_ranking_only_and_labels_top5_after_selection():
    unit = build_plan(["pair-a"])[0]
    output = build_unit_output(unit, candidate_id="candidate", document_id="document", document_type="PUBMED_ABSTRACT",
                               n_sourceunits_document=5, selected_ids=["u1", "u2"],
                               gold_labels={"u1": "DIRECTLY_RELEVANT", "u2": "NOT_RELEVANT"})
    assert output["selected_source_unit_ids"] == ["u1", "u2"]
    assert output["ranked_top5"][0] == {"rank": 1, "source_unit_id": "u1", "relevance_label": "DIRECTLY_RELEVANT", "strict_relevant": True, "broad_relevant": True}
    assert "reader" not in output and "provider" not in output
