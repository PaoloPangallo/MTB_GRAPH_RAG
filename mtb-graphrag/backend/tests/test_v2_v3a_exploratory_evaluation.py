from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.mtb_evidence.evaluation.scripts.v2_v3a_exploratory import (
    EXPECTED_SCORING_HASH,
    IMPACT_THRESHOLDS,
    BlindRetrievalComplete,
    _claim_ranking_metrics,
    GoldAccessViolation,
    classify_qualifier_impact,
    compute_binary_ranking_metrics,
    compute_rank_shifts,
    run_blind_retrieval,
    run_gold_evaluation,
)


ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT.parent / "MTB_Evidence_gold_pilot_v1_bundle"
EXPECTED_GOLD_HASH = (
    "05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133"
)


def test_binary_metrics_have_explicit_denominators_and_no_ndcg() -> None:
    metrics = compute_binary_ranking_metrics(
        ranked_ids=["a", "x", "b"], relevant_ids={"a", "b"}, top_ks=(1, 3, 5)
    )
    assert metrics["precision_at_k"]["3"] == pytest.approx(2 / 3)
    assert metrics["recall_at_k"]["3"] == 1
    assert metrics["hit_rate_at_k"]["1"] == 1
    assert metrics["mrr"] == 1
    assert metrics["relevant_denominator"] == 2
    assert metrics["retrieved_denominator_at_k"]["5"] == 3
    assert metrics["ndcg"] == "not_computed_no_graded_relevance"


def test_proposition_match_requires_biomarker_direction_polarity_therapy_and_source() -> None:
    result = {
        "statement_id": "s1",
        "evaluation_projection": {
            "biomarker": "ALK G1202R AND EML4::ALK Fusion",
            "intervention": "lorlatinib",
            "direction": "resistance",
            "assertion_polarity": "supports",
            "source_ids": ["PUBMED:1"],
        },
        "source_ids": ["PUBMED:1"],
    }
    claim = {
        "claim_id": "c1",
        "subject": "ALK G1202R",
        "relation": "predicts resistance to",
        "object": "lorlatinib",
        "direction": "supports",
        "pmid": "1",
        "documentary_status": "supported_as_written",
    }
    metrics = _claim_ranking_metrics([result], {"claims": [claim]})
    assert metrics["precision_at_k"]["1"] == 1
    assert metrics["recall_at_k"]["1"] == 1
    wrong = json.loads(json.dumps(result))
    wrong["evaluation_projection"]["biomarker"] = "EGFR L858R"
    wrong_metrics = _claim_ranking_metrics([wrong], {"claims": [claim]})
    assert wrong_metrics["precision_at_k"]["1"] == 0
    assert wrong_metrics["recall_at_k"]["1"] == 0


def test_claim_precision_cannot_exceed_one_when_one_row_matches_two_claims() -> None:
    result = {
        "statement_id": "s1",
        "evaluation_projection": {
            "biomarker": "ALK G1202R",
            "intervention": "lorlatinib",
            "direction": "resistance",
            "assertion_polarity": "supports",
            "source_ids": ["PUBMED:1"],
        },
    }
    claim = {
        "subject": "ALK G1202R",
        "relation": "resistance",
        "object": "lorlatinib",
        "direction": "supports",
        "pmid": "1",
        "documentary_status": "supported_as_written",
    }
    metrics = _claim_ranking_metrics(
        [result],
        {"claims": [{**claim, "claim_id": "c1"}, {**claim, "claim_id": "c2"}]},
    )
    assert metrics["precision_at_k"]["1"] == 1
    assert metrics["recall_at_k"]["1"] == 1

def test_rank_shift_never_invents_a_qualifier_cause() -> None:
    shifts = compute_rank_shifts(
        query_id="q",
        relevant_ids={"a", "b"},
        v2_ids=["a"],
        native_rows=[{"statement_id": "a", "rank": 2, "score_breakdown": []}],
        qualified_rows=[
            {
                "statement_id": "a",
                "rank": 1,
                "score_breakdown": [
                    {"category": "native", "name": "native_disease", "contribution": 30}
                ],
            }
        ],
    )
    assert shifts[0]["classification"] == "promoted_by_native_match"
    assert shifts[1]["classification"] == "absent_from_candidates"
    historical_only = compute_rank_shifts(
        query_id="q",
        relevant_ids={"evidence:lost"},
        v2_ids=["evidence:lost"],
        native_rows=[],
        qualified_rows=[],
    )
    assert historical_only[0]["rank_v2"] == 1
    assert historical_only[0]["classification"] == "absent_from_candidates"


def test_qualifier_impact_thresholds_are_frozen_before_results() -> None:
    assert IMPACT_THRESHOLDS["version"] == "qualifier-impact/1.0"
    assert classify_qualifier_impact(0, 100) == "no measurable ranking impact"
    assert classify_qualifier_impact(1, 100) == "limited ranking impact"
    assert classify_qualifier_impact(20, 100) == "moderate ranking impact"
    assert classify_qualifier_impact(31, 100) == "substantial ranking impact"


def test_gold_evaluator_refuses_unfrozen_retrieval(tmp_path: Path) -> None:
    with pytest.raises(BlindRetrievalComplete):
        run_gold_evaluation(
            root=ROOT,
            output=tmp_path,
            gold_bundle=GOLD,
            expected_gold_hash=EXPECTED_GOLD_HASH,
        )


@pytest.mark.skipif(not GOLD.exists(), reason="bundle gold esterno non disponibile")
def test_blind_then_gold_is_deterministic_and_separated(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    run_blind_retrieval(ROOT, first, run_count=2)
    before = json.loads((first / "retrieval_result_hashes.json").read_text("utf-8"))
    run_gold_evaluation(
        root=ROOT,
        output=first,
        gold_bundle=GOLD,
        expected_gold_hash=EXPECTED_GOLD_HASH,
    )
    after = json.loads((first / "retrieval_result_hashes.json").read_text("utf-8"))
    assert before == after
    audit = json.loads((first / "gold_access_audit.json").read_text("utf-8"))
    assert audit["retrieval_completed_before_gold_access"] is True
    assert audit["tuning_performed"] is False
    assert audit["result_hashes_unchanged_after_gold_access"] is True

    run_blind_retrieval(ROOT, second, run_count=2)
    run_gold_evaluation(
        root=ROOT,
        output=second,
        gold_bundle=GOLD,
        expected_gold_hash=EXPECTED_GOLD_HASH,
    )
    stable = {
        "per_query_metrics.jsonl",
        "aggregate_metrics.json",
        "candidate_coverage.json",
        "qualifier_impact.json",
        "rank_shift_analysis.jsonl",
        "zero_candidate_query_audit.json",
    }
    assert {name: (first / name).read_bytes() for name in stable} == {
        name: (second / name).read_bytes() for name in stable
    }
    manifest = json.loads((first / "evaluation_manifest.json").read_text("utf-8"))
    assert manifest["final_clinical_evaluation"] is False
    assert manifest["gold_used_for_retrieval"] is False
    assert manifest["gold_used_for_evaluation"] is True


def _aggregate(paths: list[Path]) -> str:
    files = sorted(
        (item for path in paths for item in path.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(ROOT).as_posix().casefold(),
    )
    payload = "\n".join(
        f"{item.relative_to(ROOT).as_posix()}:{hashlib.sha256(item.read_bytes()).hexdigest()}"
        for item in files
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_frozen_inputs_remain_byte_identical() -> None:
    v3 = ROOT / "benchmarks" / "mtb_evidence" / "v3"
    assert _aggregate(
        [v3 / "priority_curation" / "annotation_packets" / "second_review"]
    ) == "6bb4ee225e4c273a6f24378dc5c982490cdbf3482a1e780e4c173695fe131bb6"
    assert _aggregate([v3 / "qualification_corpus_v2"]) == (
        "bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827"
    )
    assert _aggregate(
        [
            v3 / "author_approval",
            v3 / "author_approval_22235099",
            v3 / "author_approval_23344087",
        ]
    ) == "8bdafc1188d9050898ffdfab69626ad0d8780b2f137de24bb6d0716d2129c278"
    config = ROOT / "backend" / "pipeline" / "evidence" / "qualified_retriever_scoring_config.json"
    assert hashlib.sha256(config.read_bytes()).hexdigest() == (
        "57d76d377029ba5c92cf4785d8143e2d06d02b6dc0e0c1d7ef57ea118e553fd4"
    )
    payload = json.loads(config.read_text("utf-8"))
    assert payload["hash"] == EXPECTED_SCORING_HASH
    assert payload["clinical_gold_used_for_weights"] is False


def test_generated_metrics_preserve_units_and_structural_policy(tmp_path: Path) -> None:
    if not GOLD.exists():
        pytest.skip("bundle gold esterno non disponibile")
    run_blind_retrieval(ROOT, tmp_path, run_count=2)
    run_gold_evaluation(
        root=ROOT,
        output=tmp_path,
        gold_bundle=GOLD,
        expected_gold_hash=EXPECTED_GOLD_HASH,
    )
    per_query = [
        json.loads(line)
        for line in (tmp_path / "per_query_metrics.jsonl").read_text("utf-8").splitlines()
    ]
    assert {
        row["modes"]["qualified_soft"]["proposition_ranking"]["relevant_denominator"]
        for row in per_query
    } == {0, 2, 3}
    assert all(
        row["modes"]["qualified_soft"]["statement_ranking"]
        == "not_computed_no_statement_level_gold"
        for row in per_query
    )
    aggregate = json.loads((tmp_path / "aggregate_metrics.json").read_text("utf-8"))
    assert aggregate["zero_candidate_query_included"] is True
    assert aggregate["p_values_computed"] is False
    assert aggregate["nDCG"] == "not_computed_no_graded_relevance"
    structural = json.loads((tmp_path / "structural_metrics.json").read_text("utf-8"))
    assert structural["pmid_checks"]["31358542"]["checks"]["candidate_invalid_is_audit_only"] is True
    assert structural["pmid_checks"]["22235099"]["checks"]["h3122_kras_remains_negative"] is True
    assert structural["pmid_checks"]["23344087"]["checks"]["unresolved_panel_not_separable"] is True
    assert structural["pmid_checks"]["22277784"]["checks"]["ch5424802_alectinib_pending"] is True

def test_evaluator_has_no_network_neo4j_llm_or_tuning_surface() -> None:
    source = (
        ROOT
        / "benchmarks"
        / "mtb_evidence"
        / "evaluation"
        / "scripts"
        / "v2_v3a_exploratory.py"
    ).read_text("utf-8")
    forbidden = ("requests.", "neo4j", "openai", "def tune")
    assert not any(token in source.casefold() for token in forbidden)
