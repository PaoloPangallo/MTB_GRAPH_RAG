"""LIVE-only routing from parsed document units to the frozen selector.

This module deliberately has no replay path.  REPLAY continues to use the
recorded selection adapter in :mod:`backend.research_pipeline.replay`.
"""

from __future__ import annotations

import os
import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping
from .document_plan import focused_enabled, plan_documents
from .selection_intent import build_selection_intent
from .reader_budget import pack_reader_units

from backend.research_pipeline.experimental import SourceUnitSelectionInput, select
from backend.research_pipeline.retrieval.canonical_rrf import (
    BASELINE as BM25_STRUCTURE,
    STRATEGY as HYBRID_RRF,
    select_rrf,
)

LIVE_SELECTOR_VERSION = "live-sourceunit-selector/3.0"
LIVE_SELECTOR_TOP_K = 5
_DOCUMENT_CAP = os.getenv("RESEARCH_PIPELINE_MAX_DOCUMENTS_PER_ASSOCIATION", "2").strip()
MAX_PAPERS_PER_ASSOCIATION = int(_DOCUMENT_CAP) if _DOCUMENT_CAP else None
LIVE_RETRIEVAL_STRATEGY = os.getenv("RESEARCH_PIPELINE_SOURCEUNIT_STRATEGY", HYBRID_RRF).strip()
if LIVE_RETRIEVAL_STRATEGY not in (HYBRID_RRF, BM25_STRUCTURE):
    raise ValueError("RESEARCH_PIPELINE_SOURCEUNIT_STRATEGY must be RRF_STRUCTURE_MEDCPT or BM25_STRUCTURE")


@dataclass(frozen=True)
class SelectionIndex:
    """Run-scoped document lookup; retains unit order and candidate lineage."""

    records_by_candidate_id: Mapping[str, tuple[Any, ...]]
    units_by_document_id: Mapping[str, tuple[dict[str, Any], ...]]
    selection_cache: dict = field(default_factory=dict)

    @classmethod
    def build(cls, resolution: Any, units: Mapping[str, dict[str, Any]]) -> "SelectionIndex":
        records: dict[str, list[Any]] = {}
        documents: dict[str, list[dict[str, Any]]] = {}
        for record in resolution.documents:
            if record.resolved:
                records.setdefault(record.candidate_id, []).append(record)
        for unit in units.values():
            document_id = unit.get("document_id")
            if isinstance(document_id, str) and (unit.get("text") or "").strip():
                documents.setdefault(document_id, []).append(unit)
        return cls({k: tuple(v) for k, v in records.items()},
                   {k: tuple(v) for k, v in documents.items()})


def select_live_papers_for_association(
    association: Mapping[str, Any],
    source_units_by_id: Mapping[str, dict[str, Any]],
    *,
    resolution: Any,
    top_k: int = LIVE_SELECTOR_TOP_K,
    selector_fn: Callable[..., Any] | None = None,
    selection_index: SelectionIndex | None = None,
    case_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select top-k units from every resolved document, without bundle IDs.

    ``resolution`` is the only source of document-to-unit provenance in LIVE.
    In particular, this function never reads ``available_bundles[*].source_unit_ids``.
    """
    candidate = association["candidate"]
    records = list(selection_index.records_by_candidate_id.get(association["candidate_id"], ())) if selection_index else [
        record for record in resolution.documents
        if record.candidate_id == association["candidate_id"] and record.resolved
    ]
    records.sort(key=lambda record: (
        0 if record.full_text_available else 1,
        record.document_id,
        record.bundle_id,
    ))

    selected: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    retrieval_attempts: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    focused = focused_enabled()
    intent = build_selection_intent(dict(candidate), dict(case_context or {}), []) if focused else None
    deferred = []
    if focused:
        documents = selection_index.units_by_document_id if selection_index else {
            r.document_id: tuple(u for u in source_units_by_id.values() if u.get('document_id') == r.document_id)
            for r in records}
        plan = plan_documents(records, documents, intent, MAX_PAPERS_PER_ASSOCIATION)
        excluded.extend({'bundle_id': r.bundle_id, 'document_id': r.document_id,
                         'reason_codes': ['DUPLICATE_DOCUMENT_ID']} for r in plan['duplicates'])
        records = plan['selected']
        deferred = [{'bundle_id': r.bundle_id, 'document_id': r.document_id,
                     'reason_codes': ['DOCUMENT_DEFERRED_BY_PLAN'], 'status': 'NOT_EXECUTED'} for r in plan['deferred']]
        excluded.extend(deferred)
    for record in records:
        if record.document_id in seen_documents:
            excluded.append({
                "bundle_id": record.bundle_id,
                "document_id": record.document_id,
                "reason_codes": ["DUPLICATE_DOCUMENT_ID"],
            })
            continue
        seen_documents.add(record.document_id)
        units = list(selection_index.units_by_document_id.get(record.document_id, ())) if selection_index else [
            unit for unit in source_units_by_id.values()
            if unit.get("document_id") == record.document_id
            and (unit.get("text") or "").strip()
        ]
        if not units:
            excluded.append({
                "bundle_id": record.bundle_id,
                "document_id": record.document_id,
                "reason_codes": ["SOURCE_UNIT_TEXT_UNAVAILABLE"],
            })
            continue

        if focused and record.document_id.startswith('nct:'):
            from ..documents.trial_facts import extract_trial_facts
            digest = getattr(record, 'content_hash', None) or hashlib.sha256(
                json.dumps(units, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            key = ('trial-facts', record.document_id, digest)
            facts = selection_index.selection_cache.get(key) if selection_index else None
            if facts is None:
                facts = extract_trial_facts({'document_id': record.document_id, 'units': units}, digest)
                if selection_index:
                    selection_index.selection_cache[key] = facts
            selected.append({'bundle_id': record.bundle_id, 'document_id': record.document_id,
                             'requested_document_id': record.lineage.get('requested_document_id'),
                             'bundle_type': 'ABSTRACT_BUNDLE', 'source_unit_ids': [],
                             'resolved_source_unit_ids': [u['source_unit_id'] for u in units],
                             'paper_role': 'primary', 'replayed': False, 'selector': {},
                             'retrieval_strategy': 'STRUCTURED_TRIAL_RECORD', 'document_relevance_score': 0,
                             'trial_fact_provenance': {k: v for k, v in facts.items() if k != 'units'}})
            retrieval_attempts.append({'document_id': record.document_id,
                                      'actual_strategy': 'STRUCTURED_TRIAL_RECORD', 'fallback_reason': None})
            continue

        selection_input = SourceUnitSelectionInput.from_candidate(
            candidate, record.document_id, units, selection_intent=intent,
        )
        rank_and_select = selector_fn or (
            lambda value, *, top_k: select_rrf(
                value, top_k=top_k, strategy=LIVE_RETRIEVAL_STRATEGY,
            )
        )
        cache_key = (replace(selection_input, candidate_id='').input_hash(), top_k,
                     LIVE_RETRIEVAL_STRATEGY, focused, id(selector_fn),
                     hashlib.sha256(json.dumps(units, sort_keys=True, ensure_ascii=False).encode()).hexdigest())
        cached = selection_index.selection_cache.get(cache_key) if selection_index else None
        if cached is not None:
            selection = replace(cached, candidate_id=association['candidate_id'], input_hash=selection_input.input_hash())
        else:
            selection = rank_and_select(selection_input, top_k=top_k)
            # Encoding-budget fallback may have retained incremental vectors.
            # Let a subsequent request resume rather than freezing that fallback.
            if selection_index and not (selection.matched_features.get('retrieval') or {}).get('fallback_reason'):
                selection_index.selection_cache[cache_key] = selection
        attempt_retrieval = selection.matched_features.get("retrieval") or {}
        deferred_units = ()
        if focused:
            limit = os.getenv('RESEARCH_PIPELINE_MAX_READER_SOURCE_CHARACTERS', '').strip()
            kept, deferred_units = pack_reader_units(selection.selected_source_unit_ids,
                {u['source_unit_id']: u for u in units}, int(limit) if limit else None)
            if deferred_units:
                selection = replace(selection, selected_source_unit_ids=kept,
                    selected_ids_hash=hashlib.sha256(json.dumps(list(kept), ensure_ascii=False,
                        sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                    status='SELECTED' if kept else 'NO_RELEVANT_SOURCE_UNIT',
                    ranked_source_units=tuple(replace(r, selected=False, exclusion_reason='READER_TEXT_BUDGET_DEFERRED')
                        if r.source_unit_id in deferred_units else r for r in selection.ranked_source_units))
        retrieval_attempts.append({
            "document_id": record.document_id,
            "actual_strategy": attempt_retrieval.get("actual_strategy", LIVE_RETRIEVAL_STRATEGY),
            "fallback_reason": attempt_retrieval.get("fallback_reason"),
        })
        if not selection.selected_source_unit_ids:
            excluded.append({
                "bundle_id": record.bundle_id,
                "document_id": record.document_id,
                "reason_codes": ["READER_TEXT_BUDGET_DEFERRED" if deferred_units else "SOURCEUNIT_SELECTION_FAILED"],
                "selector_status": selection.status,
                "retrieval_strategy": attempt_retrieval.get("actual_strategy", LIVE_RETRIEVAL_STRATEGY),
                "retrieval_fallback_reason": attempt_retrieval.get("fallback_reason"),
            })
            continue

        ranking = selection.to_dict(ranking_limit=None)
        # Per-document ranking must remain on the historical structural-score
        # scale; RRF scores are only comparable within a paper.
        top_score = max((record.score_lexical * record.section_prior * record.section_factor
                         for record in selection.ranked_source_units
                         if not record.exclusion_reason), default=0.0)
        retrieval_meta = selection.matched_features.get("retrieval") or {}
        retrieval_meta = {
            **retrieval_meta,
            "selected_component_ranks": [
                {"source_unit_id": uid,
                 "fusion_rank": next((item["rank"] for item in ranking["ranked_source_units"]
                                      if item["source_unit_id"] == uid), None),
                 "structure_rank": retrieval_meta.get("component_ranks", {}).get(uid, {}).get("structure"),
                 "medcpt_rank": retrieval_meta.get("component_ranks", {}).get(uid, {}).get("medcpt")}
                for uid in selection.selected_source_unit_ids
            ],
        }
        if retrieval_meta:
            ranking["matched_features"]["retrieval"] = retrieval_meta
        selected.append({
            "bundle_id": record.bundle_id,
            "document_id": record.document_id,
            "requested_document_id": record.lineage.get("requested_document_id"),
            "bundle_type": "FULLTEXT_LOCAL_CONTEXT_BUNDLE" if record.full_text_available else "ABSTRACT_BUNDLE",
            "source_unit_ids": [],
            "resolved_source_unit_ids": list(selection.selected_source_unit_ids),
            "paper_role": "primary" if not selected else "secondary",
            "replayed": False,
            "selector": ranking,
            "selector_version": LIVE_SELECTOR_VERSION,
            "retrieval_strategy": retrieval_meta.get("actual_strategy", LIVE_RETRIEVAL_STRATEGY),
            "retrieval_fallback_reason": retrieval_meta.get("fallback_reason"),
            "document_relevance_score": top_score,
            'selection_reused': cached is not None,
            **({'selection_intent': intent} if focused else {}),
            **({'reader_text_deferred_source_unit_ids': list(deferred_units)} if deferred_units else {}),
        })

    selected_all = sorted(
        selected,
        key=lambda item: (
            0 if item["bundle_type"] == "FULLTEXT_LOCAL_CONTEXT_BUNDLE" else 1,
            -float(item.get("document_relevance_score") or 0.0),
            item["document_id"],
            item["bundle_id"],
        ),
    )
    selected = selected_all if MAX_PAPERS_PER_ASSOCIATION is None else selected_all[:MAX_PAPERS_PER_ASSOCIATION]
    excluded_by_cap = () if MAX_PAPERS_PER_ASSOCIATION is None else selected_all[MAX_PAPERS_PER_ASSOCIATION:]
    for item in excluded_by_cap:
        excluded.append({
            "bundle_id": item["bundle_id"],
            "document_id": item["document_id"],
            "reason_codes": ["MAX_PAPERS_PER_ASSOCIATION_EXCEEDED"],
            "retrieval_strategy": item.get("retrieval_strategy"),
            "retrieval_fallback_reason": item.get("retrieval_fallback_reason"),
        })
    return {
        "candidate_id": association["candidate_id"],
        "selected_papers": selected,
        "excluded_papers": excluded,
        "criteria_order": [
            "GCA_PROVENANCE", "DOCUMENT_RESOLVED", "SOURCE_UNITS_PARSED",
            "DETERMINISTIC_SOURCEUNIT_SELECTOR", f"TOP_K_{top_k}",
            "DOCUMENT_RELEVANCE_THEN_SOURCE_DIVERSITY",
        ],
        "selector_version": LIVE_SELECTOR_VERSION,
        "retrieval_strategy": sorted({item["actual_strategy"] for item in retrieval_attempts}),
        "retrieval_attempts": retrieval_attempts,
        "retrieval_fallbacks": [
            {"document_id": item["document_id"], "reason": item["fallback_reason"]}
            for item in retrieval_attempts if item.get("fallback_reason")
        ],
        "max_documents_per_association": MAX_PAPERS_PER_ASSOCIATION,
        "bundle_source_unit_ids_used": False,
        "replayed": False,
        **({'document_plan_version': 'document-plan/1.0', 'deferred_documents': deferred} if focused else {}),
    }
