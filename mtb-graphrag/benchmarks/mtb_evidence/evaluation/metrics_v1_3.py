"""Frozen, deterministic structural scoring contracts for protocol V1.3."""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

BUCKETS = frozenset({'primary', 'warning', 'audit', 'rejected'})


def score_query(gold: list[Mapping[str, Any]], predicted: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Score one query using exact stable claim_id matching only."""
    if not predicted and any(bool(row.get('expected_abstention')) for row in gold) and all(not row.get('claim_id') for row in gold):
        return {'bucket_accuracy': 1.0, 'denominator': 0, 'empty_abstention_count': 1, 'extra_claim_count': 0, 'missing_claim_count': 0, 'wrong_bucket_count': 0, 'exact_bucket_match_count': 0, 'provenance_container_count': 0, 'non_evaluable_count': 0, 'invalid_empty_universe_count': 0}
    seen_gold: set[str] = set()
    seen_pred: set[str] = set()
    gold_map: dict[str, str] = {}
    pred_map: dict[str, str] = {}
    provenance = non_evaluable = 0
    for row in gold:
        if row.get('candidate_kind') == 'provenance_container':
            provenance += 1
            continue
        if row.get('evaluable') is False:
            non_evaluable += 1
            continue
        cid = row.get('claim_id')
        bucket = row.get('bucket')
        if not isinstance(cid, str) or not cid or cid in seen_gold:
            raise ValueError('duplicate or missing gold claim_id')
        if bucket not in BUCKETS:
            raise ValueError('invalid gold bucket')
        seen_gold.add(cid); gold_map[cid] = bucket
    for row in predicted:
        if row.get('candidate_kind') == 'provenance_container':
            continue
        cid = row.get('claim_id'); bucket = row.get('bucket')
        if not isinstance(cid, str) or not cid or cid in seen_pred:
            raise ValueError('duplicate or missing predicted claim_id')
        if bucket not in BUCKETS:
            raise ValueError('invalid predicted bucket')
        seen_pred.add(cid); pred_map[cid] = bucket
    universe = set(gold_map) | set(pred_map)
    if not universe:
        if all(bool(row.get('expected_abstention')) for row in gold) and not predicted:
            return {'bucket_accuracy': 1.0, 'denominator': 0, 'empty_abstention_count': 1,
                    'extra_claim_count': 0, 'missing_claim_count': 0, 'wrong_bucket_count': 0,
                    'exact_bucket_match_count': 0, 'provenance_container_count': provenance,
                    'non_evaluable_count': non_evaluable, 'invalid_empty_universe_count': 0}
        return {'bucket_accuracy': None, 'denominator': 0, 'empty_abstention_count': 0,
                'extra_claim_count': 0, 'missing_claim_count': 0, 'wrong_bucket_count': 0,
                'exact_bucket_match_count': 0, 'provenance_container_count': provenance,
                'non_evaluable_count': non_evaluable, 'invalid_empty_universe_count': 1}
    exact = sum(cid in gold_map and cid in pred_map and gold_map[cid] == pred_map[cid] for cid in universe)
    wrong = sum(cid in gold_map and cid in pred_map and gold_map[cid] != pred_map[cid] for cid in universe)
    missing = sum(cid in gold_map and cid not in pred_map for cid in universe)
    extra = sum(cid in pred_map and cid not in gold_map for cid in universe)
    return {'bucket_accuracy': exact / len(universe), 'denominator': len(universe),
            'empty_abstention_count': 0, 'extra_claim_count': extra, 'missing_claim_count': missing,
            'wrong_bucket_count': wrong, 'exact_bucket_match_count': exact,
            'provenance_container_count': provenance, 'non_evaluable_count': non_evaluable,
            'invalid_empty_universe_count': 0}


def macro_bucket_accuracy(query_scores: list[Mapping[str, Any]]) -> float | None:
    values = [float(row['bucket_accuracy']) for row in query_scores if row.get('bucket_accuracy') is not None]
    return sum(values) / len(values) if values else None
