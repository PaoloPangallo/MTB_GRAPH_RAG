"""Offline RQ2 protocol utilities.  This module never calls a provider."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Mapping

from backend.research_pipeline.experimental.sourceunit_selector import (
    BM25_B, BM25_K1, SELECTOR_VERSION, SourceUnitSelectionInput, select,
    select_bm25, select_first_k,
)

RQ2_VERSION = "sourceunit-retrieval-benchmark/2.0"
TOP_K = 5
ARMS = ("FIRST_K", "BM25", "DETERMINISTIC_SELECTOR")
LABELS = ("DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT", "CONTEXT_ONLY", "NOT_RELEVANT")
ROOT = Path(__file__).resolve().parents[2]
INDEPENDENT = ROOT / "evaluation" / "sourceunit_selector_independent"
S01 = ROOT / "evaluation" / "final_protocol" / "supplements" / "S01" / "sourceunits_1697.jsonl"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dataset() -> tuple[dict[tuple[str, str], dict[str, str]], dict[tuple[str, str], list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """Loads labels and source units; no ranking is performed."""
    import csv
    labels: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    with (INDEPENDENT / "gold_annotations.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            labels[(row["candidate_id"], row["document_id"])][row["source_unit_id"]] = row["relevance_label"]
    units: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(S01):
        units[(row["candidate_id"], row["document_id"])].append(row)
    candidates = {row["candidate_id"]: row for row in _read_jsonl(INDEPENDENT / "candidate_inventory.jsonl")}
    return dict(labels), dict(units), candidates


def validate_inputs() -> dict[str, int]:
    labels, units, candidates = load_dataset()
    counts = Counter(label for per_pair in labels.values() for label in per_pair.values())
    strict = sum(any(v == "DIRECTLY_RELEVANT" for v in pair.values()) for pair in labels.values())
    broad = sum(any(v in {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"} for v in pair.values()) for pair in labels.values())
    assert len(labels) == len(units) == 20, "RQ2 pair invariant failed"
    assert sum(len(v) for v in units.values()) == 1697, "RQ2 SourceUnit invariant failed"
    assert counts == Counter({"DIRECTLY_RELEVANT": 29, "PARTIALLY_RELEVANT": 49, "CONTEXT_ONLY": 355, "NOT_RELEVANT": 1264})
    assert strict == 9 and broad == 10 and len(labels) - broad == 10
    assert all(candidate_id in candidates for candidate_id, _ in labels)
    return {"pair_count": len(labels), "sourceunit_count": 1697, "strict_positive_pairs": strict,
            "broad_positive_pairs": broad, "broad_negative_pairs": len(labels) - broad}


def build_plan(pair_ids: Iterable[str]) -> list[dict[str, Any]]:
    return [{"unit_id": f"RQ2::{pair_id}::{method}", "rq2_version": RQ2_VERSION,
             "pair_id": pair_id, "retrieval_method": method, "top_k": TOP_K,
             "execution_class": "OFFLINE_RANKING_ONLY", "provider_requirement": "PROHIBITED",
             "reader_requirement": "PROHIBITED", "gold_role": "GROUND_TRUTH_ONLY"}
            for pair_id in sorted(pair_ids) for method in ARMS]


def _grade(label: str) -> int:
    return {"DIRECTLY_RELEVANT": 2, "PARTIALLY_RELEVANT": 1}.get(label, 0)


def _ndcg(labels: list[str], gold_labels: Mapping[str, str]) -> float | None:
    gains = [_grade(label) for label in labels[:TOP_K]]
    ideal = sorted((_grade(label) for label in gold_labels.values()), reverse=True)[:TOP_K]
    if not any(ideal):
        return None
    dcg = sum((2 ** gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, 1))
    idcg = sum((2 ** gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, 1))
    return dcg / idcg


def evaluate_ranked_ids(selected_ids: list[str] | tuple[str, ...], gold_labels: Mapping[str, str]) -> dict[str, Any]:
    """Score a supplied ranking only; retrieval is deliberately outside this pure function."""
    selected = list(selected_ids)[:TOP_K]
    selected_labels = [gold_labels.get(unit_id, "NOT_RELEVANT") for unit_id in selected]
    strict_count = sum(label == "DIRECTLY_RELEVANT" for label in gold_labels.values())
    broad_count = sum(label in {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"} for label in gold_labels.values())
    def metric(relevant: set[str], count: int) -> tuple[float | None, float | None, float | None, float | None]:
        if not count:
            return None, None, None, None
        ranks = [rank for rank, unit_id in enumerate(selected, 1) if unit_id in relevant]
        hit = float(bool(ranks)); precision = sum(unit_id in relevant for unit_id in selected) / TOP_K
        return hit, precision, len(ranks) / count, (1 / ranks[0] if ranks else 0.0)
    strict_ids = {unit_id for unit_id, label in gold_labels.items() if label == "DIRECTLY_RELEVANT"}
    broad_ids = {unit_id for unit_id, label in gold_labels.items() if label in {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"}}
    sh, sp, sr, sm = metric(strict_ids, strict_count); bh, bp, br, bm = metric(broad_ids, broad_count)
    result = {"strict_gold_count": strict_count, "broad_gold_count": broad_count,
              "strict_positive_pair": bool(strict_count), "broad_positive_pair": bool(broad_count),
              "strict_hit_at_5": sh, "strict_precision_at_5": sp, "strict_recall_at_5": sr, "strict_mrr_at_5": sm,
              "broad_hit_at_5": bh, "broad_precision_at_5": bp, "broad_recall_at_5": br, "broad_mrr_at_5": bm,
              "broad_ndcg_at_5": _ndcg(selected_labels, gold_labels), "negative_pair_metrics": None}
    if not broad_count:
        denominator = len(selected_labels) or 1
        result["negative_pair_metrics"] = {"fraction_top5_context_only": selected_labels.count("CONTEXT_ONLY") / denominator,
                                           "fraction_top5_not_relevant": selected_labels.count("NOT_RELEVANT") / denominator,
                                           "max_relevance_grade_top5": max((_grade(label) for label in selected_labels), default=0)}
    return result


def build_unit_output(unit: Mapping[str, Any], *, candidate_id: str, document_id: str, document_type: str,
                      n_sourceunits_document: int, selected_ids: Iterable[str], gold_labels: Mapping[str, str]) -> dict[str, Any]:
    """Canonical future result schema; accepts a completed ranking and never performs one."""
    ids = list(selected_ids)[:TOP_K]
    ranked = [{"rank": rank, "source_unit_id": source_unit_id,
               "relevance_label": gold_labels.get(source_unit_id, "NOT_RELEVANT"),
               "strict_relevant": gold_labels.get(source_unit_id) == "DIRECTLY_RELEVANT",
               "broad_relevant": gold_labels.get(source_unit_id) in {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"}}
              for rank, source_unit_id in enumerate(ids, 1)]
    return {"rq2_version": RQ2_VERSION, "pair_id": unit["pair_id"], "candidate_id": candidate_id,
            "document_id": document_id, "document_type": document_type, "retrieval_method": unit["retrieval_method"],
            "n_sourceunits_document": n_sourceunits_document, "selected_source_unit_ids": ids, "ranked_top5": ranked,
            **evaluate_ranked_ids(ids, gold_labels)}


def select_ids(method: str, selection: SourceUnitSelectionInput) -> tuple[str, ...]:
    """The only ranking dispatch; labels are absent from this signature by design."""
    if method == "FIRST_K": return select_first_k(selection, top_k=TOP_K)
    if method == "BM25": return select_bm25(selection, top_k=TOP_K)
    if method == "DETERMINISTIC_SELECTOR": return select(selection, top_k=TOP_K).selected_source_unit_ids
    raise ValueError(f"Unknown sealed RQ2 method: {method}")


def selector_identity() -> dict[str, Any]:
    selector_path = ROOT / "backend" / "research_pipeline" / "experimental" / "sourceunit_selector.py"
    return {"module": "backend.research_pipeline.experimental.sourceunit_selector", "version": SELECTOR_VERSION,
            "file_sha256": sha256(selector_path), "bm25_k1": BM25_K1, "bm25_b": BM25_B,
            "functions": {"FIRST_K": "select_first_k", "BM25": "select_bm25", "DETERMINISTIC_SELECTOR": "select"}}


def aggregate(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate already-scored future results, preserving pair-level rows for paired analysis."""
    out: dict[str, Any] = {}
    for method in ARMS:
        subset = [row for row in rows if row["retrieval_method"] == method]
        broad = [row for row in subset if row["broad_positive_pair"]]
        strict = [row for row in subset if row["strict_positive_pair"]]
        negative = [row for row in subset if not row["broad_positive_pair"]]
        avg = lambda coll, key: mean(row[key] for row in coll) if coll else None
        out[method] = {"BROAD_POSITIVE_N": len(broad), "STRICT_POSITIVE_N": len(strict), "NEGATIVE_N": len(negative),
                       "BROAD_HIT5_COUNT": sum(row["broad_hit_at_5"] for row in broad), "BROAD_HIT5_RATE": avg(broad, "broad_hit_at_5"),
                       "STRICT_HIT5_COUNT": sum(row["strict_hit_at_5"] for row in strict), "STRICT_HIT5_RATE": avg(strict, "strict_hit_at_5"),
                       "BROAD_PRECISION5_MEAN": avg(broad, "broad_precision_at_5"), "BROAD_RECALL5_MEAN": avg(broad, "broad_recall_at_5"),
                       "BROAD_MRR5_MEAN": avg(broad, "broad_mrr_at_5"), "BROAD_NDCG5_MEAN": avg(broad, "broad_ndcg_at_5"),
                       "STRICT_PRECISION5_MEAN": avg(strict, "strict_precision_at_5"), "STRICT_RECALL5_MEAN": avg(strict, "strict_recall_at_5"), "STRICT_MRR5_MEAN": avg(strict, "strict_mrr_at_5"),
                       "NEGATIVE_CONTEXT_ONLY_FRACTION_MEAN": avg([r["negative_pair_metrics"] for r in negative], "fraction_top5_context_only"),
                       "NEGATIVE_NOT_RELEVANT_FRACTION_MEAN": avg([r["negative_pair_metrics"] for r in negative], "fraction_top5_not_relevant")}
    return out


def paired_hit_table(first: Iterable[int | float], second: Iterable[int | float]) -> dict[str, int | float]:
    """Paired 2×2 table and two-sided exact McNemar p-value for future Broad Hit@5."""
    pairs = list(zip(first, second, strict=True))
    first_only = sum(bool(a) and not bool(b) for a, b in pairs)
    second_only = sum(not bool(a) and bool(b) for a, b in pairs)
    discordant = first_only + second_only
    pvalue = 1.0 if not discordant else min(1.0, 2 * sum(math.comb(discordant, k) for k in range(min(first_only, second_only) + 1)) / 2 ** discordant)
    return {"both_hit": sum(bool(a) and bool(b) for a, b in pairs), "first_only": first_only,
            "second_only": second_only, "both_miss": sum(not bool(a) and not bool(b) for a, b in pairs),
            "mcnemar_exact_pvalue": pvalue}


def paired_continuous_summary(first: Iterable[float], second: Iterable[float], *, bootstrap_samples: int = 10_000,
                              seed: int = 0) -> dict[str, Any]:
    """Pre-specified paired bootstrap; this receives scores, never rankings or labels."""
    deltas = [a - b for a, b in zip(first, second, strict=True)]
    if not deltas:
        raise ValueError("Paired summary requires at least one pair")
    rng = random.Random(seed)
    boot = sorted(mean(rng.choice(deltas) for _ in deltas) for _ in range(bootstrap_samples))
    lower, upper = boot[int(0.025 * (bootstrap_samples - 1))], boot[int(0.975 * (bootstrap_samples - 1))]
    return {"paired_n": len(deltas), "deltas": deltas, "mean_delta": mean(deltas), "median_delta": median(deltas),
            "bootstrap_95_ci": [lower, upper], "bootstrap_samples": bootstrap_samples, "bootstrap_seed": seed}
