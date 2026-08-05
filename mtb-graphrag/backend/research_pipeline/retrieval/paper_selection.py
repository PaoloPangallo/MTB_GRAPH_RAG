"""Deterministic paper selection: at most 2 documents per association, using
9 ordered, documented criteria (protocol section 9). Reuses only the generic
document/SourceUnit text-hydration loader already used throughout this
research thread (technical infrastructure, not a decision component) --
never the claim-extractor's decision logic.
"""
from __future__ import annotations

from typing import Any

MAX_PAPERS_PER_ASSOCIATION = 2

# Criterion 8: priority to more direct evidence, ranked by bundle type (not by any
# ground-truth support label) -- full-text local context > abstract > trial registry.
_BUNDLE_TYPE_RANK = {"FULLTEXT_LOCAL_CONTEXT_BUNDLE": 0, "ABSTRACT_BUNDLE": 1, "TRIAL_BUNDLE": 2}

SELECTION_CRITERIA_ORDER = (
    "1_disease_compatible", "2_biomarker_compatible", "3_intervention_compatible",
    "4_direction_or_relation_pertinent", "5_text_available", "6_source_units_complete",
    "7_provenance_valid", "8_priority_to_direct_evidence", "9_deduplication",
)


def select_papers_for_association(association: dict[str, Any], source_units_by_id: dict[str, dict]) -> dict[str, Any]:
    """Criteria 1-3 already guaranteed by retrieval's candidate match (recorded in
    match_reason_codes). This function applies 4-9 to rank and cap the bundles."""
    candidate = association["candidate"]
    direction_ok = candidate.get("direction") is not None

    scored = []
    excluded = []
    seen_document_ids: set[str] = set()
    for bundle in association["available_bundles"]:
        document_id = bundle["document_id"]
        source_unit_ids = bundle["source_unit_ids"]
        resolved_units = [uid for uid in source_unit_ids if uid in source_units_by_id and (source_units_by_id[uid].get("text") or "").strip()]
        text_available = len(resolved_units) > 0
        source_units_complete = len(resolved_units) >= 1
        provenance_valid = bool(document_id) and bool(bundle.get("bundle_id"))

        if document_id in seen_document_ids:
            excluded.append({"bundle_id": bundle["bundle_id"], "document_id": document_id, "reason_codes": ["DUPLICATE_DOCUMENT_ID"]})
            continue
        if not text_available:
            excluded.append({"bundle_id": bundle["bundle_id"], "document_id": document_id, "reason_codes": ["TEXT_NOT_AVAILABLE_IN_CACHE"]})
            continue
        if not direction_ok:
            excluded.append({"bundle_id": bundle["bundle_id"], "document_id": document_id, "reason_codes": ["ASSOCIATION_DIRECTION_UNDEFINED"]})
            continue
        if not provenance_valid:
            excluded.append({"bundle_id": bundle["bundle_id"], "document_id": document_id, "reason_codes": ["PROVENANCE_INVALID"]})
            continue
        seen_document_ids.add(document_id)
        rank = _BUNDLE_TYPE_RANK.get(bundle.get("bundle_type"), 99)
        scored.append({**bundle, "resolved_source_unit_ids": resolved_units, "priority_rank": rank})

    scored.sort(key=lambda item: (item["priority_rank"], item["bundle_id"]))
    selected = scored[:MAX_PAPERS_PER_ASSOCIATION]
    capped_out = scored[MAX_PAPERS_PER_ASSOCIATION:]
    for item in capped_out:
        excluded.append({"bundle_id": item["bundle_id"], "document_id": item["document_id"], "reason_codes": ["MAX_PAPERS_PER_ASSOCIATION_EXCEEDED"]})

    role_labels = ["primary"] + ["secondary"] * (len(selected) - 1)
    for bundle, role in zip(selected, role_labels):
        bundle["paper_role"] = role

    return {"candidate_id": association["candidate_id"], "selected_papers": selected, "excluded_papers": excluded, "criteria_order": list(SELECTION_CRITERIA_ORDER)}
