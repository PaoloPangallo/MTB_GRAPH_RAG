"""LIVE-only routing from parsed document units to the frozen selector.

This module deliberately has no replay path.  REPLAY continues to use the
recorded selection adapter in :mod:`backend.research_pipeline.replay`.
"""

from __future__ import annotations

from typing import Any, Mapping

from backend.research_pipeline.experimental import SourceUnitSelectionInput, select

LIVE_SELECTOR_VERSION = "live-sourceunit-selector/1.0"
LIVE_SELECTOR_TOP_K = 5
MAX_PAPERS_PER_ASSOCIATION = 2


def select_live_papers_for_association(
    association: Mapping[str, Any],
    source_units_by_id: Mapping[str, dict[str, Any]],
    *,
    resolution: Any,
    top_k: int = LIVE_SELECTOR_TOP_K,
) -> dict[str, Any]:
    """Select top-k units from every resolved document, without bundle IDs.

    ``resolution`` is the only source of document-to-unit provenance in LIVE.
    In particular, this function never reads ``available_bundles[*].source_unit_ids``.
    """
    candidate = association["candidate"]
    records = [
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
    seen_documents: set[str] = set()
    for record in records:
        if record.document_id in seen_documents:
            excluded.append({
                "bundle_id": record.bundle_id,
                "document_id": record.document_id,
                "reason_codes": ["DUPLICATE_DOCUMENT_ID"],
            })
            continue
        seen_documents.add(record.document_id)
        units = [
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

        selection = select(
            SourceUnitSelectionInput.from_candidate(
                candidate, record.document_id, units,
            ),
            top_k=top_k,
        )
        if not selection.selected_source_unit_ids:
            excluded.append({
                "bundle_id": record.bundle_id,
                "document_id": record.document_id,
                "reason_codes": ["SOURCEUNIT_SELECTION_FAILED"],
                "selector_status": selection.status,
            })
            continue

        selected.append({
            "bundle_id": record.bundle_id,
            "document_id": record.document_id,
            "requested_document_id": record.lineage.get("requested_document_id"),
            "bundle_type": "FULLTEXT_LOCAL_CONTEXT_BUNDLE" if record.full_text_available else "ABSTRACT_BUNDLE",
            "source_unit_ids": [],
            "resolved_source_unit_ids": list(selection.selected_source_unit_ids),
            "paper_role": "primary" if not selected else "secondary",
            "replayed": False,
            "selector": selection.to_dict(ranking_limit=20),
            "selector_version": LIVE_SELECTOR_VERSION,
        })

    selected_all = selected
    selected = selected_all[:MAX_PAPERS_PER_ASSOCIATION]
    for item in selected_all[MAX_PAPERS_PER_ASSOCIATION:]:
        excluded.append({
            "bundle_id": item["bundle_id"],
            "document_id": item["document_id"],
            "reason_codes": ["MAX_PAPERS_PER_ASSOCIATION_EXCEEDED"],
        })
    return {
        "candidate_id": association["candidate_id"],
        "selected_papers": selected,
        "excluded_papers": excluded,
        "criteria_order": [
            "GCA_PROVENANCE", "DOCUMENT_RESOLVED", "SOURCE_UNITS_PARSED",
            "DETERMINISTIC_SOURCEUNIT_SELECTOR", "TOP_K_5",
        ],
        "selector_version": LIVE_SELECTOR_VERSION,
        "bundle_source_unit_ids_used": False,
        "replayed": False,
    }
