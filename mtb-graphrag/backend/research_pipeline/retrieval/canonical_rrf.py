"""Canonical local hybrid retrieval; selector compatibility and overlap stay intact."""
from __future__ import annotations

import math
import os
from dataclasses import replace
from typing import Callable

from backend.research_pipeline.experimental import sourceunit_selector as selector
from .document_plan import focused_enabled
from ..documents.unit_structure import build_unit_structure

STRATEGY = "RRF_STRUCTURE_MEDCPT"
BASELINE = "BM25_STRUCTURE"
CONFIG = {"rrf_constant": 60, "parent_depth": 25, "weights": [1, 1],
          "top_k": 5, "document_cap": 2, "hard_filters": "BEFORE_FUSION",
          "tie_break": "SOURCE_UNIT_ID", "overlap": "CANONICAL"}


def rrf_scores(rankings: list[list[str]]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        if len(ranking) != len(set(ranking)):
            raise ValueError("Duplicate parent ranking ID")
        for position, uid in enumerate(ranking[:25], 1):
            scores[uid] = scores.get(uid, 0.0) + 1 / (60 + position)
    return scores


def dense_scores(selection):
    """Stable injection point; lazy import and no models loaded during import."""
    from .local_medcpt import get_backend
    return get_backend().score(selection)


def select_rrf(selection, *, top_k: int = 5, strategy: str = STRATEGY,
               dense_scorer: Callable | None = None):
    if strategy not in (STRATEGY, BASELINE):
        raise ValueError("Unsupported canonical retrieval strategy")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    invocation_hash = selection.input_hash()
    retrieval = {"requested_strategy": strategy, "actual_strategy": BASELINE,
                 "fallback_reason": None, "configuration": {**CONFIG, "top_k": top_k}}
    if focused_enabled():
        structure = build_unit_structure(list(selection.source_units))
        indexable = tuple(u for u in selection.source_units if structure[u['source_unit_id']]['indexable'])
        retrieval['unit_structure_version'] = 'sourceunit-structure/1.0'
        retrieval['inventory_units'] = len(selection.source_units)
        hierarchical = os.getenv('RESEARCH_PIPELINE_HIERARCHICAL_SOURCE_INDEX', '').strip() == '1'
        retrieval['hierarchical_index_enabled'] = hierarchical
        retrieval['indexed_units'] = len(indexable) if hierarchical and indexable else len(selection.source_units)
        # Hierarchy changes retrieval coverage: opt in separately from focused intent/budget.
        # Default keeps sentences, tables and parent units reachable in both branches.
        if hierarchical:
            selection = replace(selection, source_units=indexable or selection.source_units)
    if strategy == BASELINE:
        result = selector.select(selection, top_k=top_k, ranking_strategy=BASELINE)
    else:
        try:
            templates = {r.source_unit_id: r for r in selector.rank(selection, ranking_strategy="BM25")}
            structure = {uid: r.score_lexical * r.section_prior * r.section_factor
                         for uid, r in templates.items() if not r.exclusion_reason and r.score_lexical > 0}
            dense, telemetry = (dense_scorer or dense_scores)(selection)
            if set(dense) != set(templates) or any(not math.isfinite(v) for v in dense.values()):
                raise ValueError("Dense scores must cover exact document IDs and be finite")
            eligible_dense = {uid: score for uid, score in dense.items() if not templates[uid].exclusion_reason}
            ordered = lambda scores: sorted(scores, key=lambda uid: (-scores[uid], uid))
            fusion = rrf_scores([ordered(structure), ordered(eligible_dense)])
            records = [replace(templates[uid], rank=position, score_total=fusion[uid], selected=False)
                       for position, uid in enumerate(ordered(fusion), 1)]
            result = selector.select(selection, top_k=top_k, ranking_strategy=BASELINE,
                                     ranked_source_units=records)
            structure_rank = {uid: i for i, uid in enumerate(ordered(structure), 1)}
            dense_rank = {uid: i for i, uid in enumerate(ordered(eligible_dense), 1)}
            retrieval.update(actual_strategy=STRATEGY, dense=telemetry,
                             parent_eligible_counts={BASELINE: len(structure), "MEDCPT": len(eligible_dense)},
                             component_ranks={uid: {
                                 "structure": structure_rank.get(uid),
                                 "medcpt": dense_rank.get(uid),
                             } for uid in result.selected_source_unit_ids})
        except Exception as exc:
            retrieval["fallback_reason"] = f"{type(exc).__name__}: {exc}"
            if isinstance(getattr(exc, "progress", None), dict):
                retrieval["dense_cache_progress"] = exc.progress
            result = selector.select(selection, top_k=top_k, ranking_strategy=BASELINE)
    if strategy == BASELINE:
        ranked_positions = {record.source_unit_id: record.rank for record in result.ranked_source_units}
        retrieval["component_ranks"] = {
            uid: {"structure": ranked_positions.get(uid), "medcpt": None}
            for uid in result.selected_source_unit_ids
        }
    return replace(result, input_hash=invocation_hash, matched_features={**result.matched_features,
                                            "ranking_strategy": retrieval["actual_strategy"],
                                            "retrieval": retrieval})
