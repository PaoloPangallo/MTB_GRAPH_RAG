"""Evaluation-only summaries for document support levels.

This module deliberately does not aggregate support across papers or
reclassify canonical pipeline statuses. It only exposes the structured
observations already emitted by the runtime.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


CASE1_DOCUMENT_SUPPORT_LEVEL = "PARTIAL_SUPPORT"
SUPPORT_LEVELS = (
    "STRONG_SUPPORT",
    "PARTIAL_SUPPORT",
    "CONTEXT_ONLY",
    "CONTRADICTORY",
    "UNVERIFIABLE",
)
QUOTE_VALIDATED_OUTCOMES = {"QUOTE_VALIDATED", "VALIDATED", "ACCEPTED"}


def compare_unit_ids(before: Iterable[str], after: Iterable[str]) -> dict[str, Any]:
    before_set = set(before)
    after_set = set(after)
    added = sorted(after_set - before_set)
    removed = sorted(before_set - after_set)
    return {"same": not added and not removed, "added": added, "removed": removed}


def _raw_run(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("raw_pipeline_run") if isinstance(item.get("raw_pipeline_run"), dict) else item


def _candidate_entries(raw: dict[str, Any]) -> list[dict[str, Any]]:
    dossier = raw.get("dossier")
    if not isinstance(dossier, dict):
        return []
    entries = dossier.get("candidate_therapies")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def _support_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in _candidate_entries(raw):
        candidate_id = candidate.get("candidate_id")
        validations = candidate.get("validation_results") or []
        if not isinstance(validations, list):
            continue
        for validation in validations:
            if not isinstance(validation, dict):
                continue
            support = validation.get("candidate_support")
            if not isinstance(support, dict) or support.get("result") not in SUPPORT_LEVELS:
                continue
            rows.append({
                "candidate_id": candidate_id,
                "paper_id": validation.get("paper_id") or validation.get("document_id"),
                "document_id": validation.get("document_id") or validation.get("paper_id"),
                "source_unit_id": (validation.get("enrichment") or {}).get("source_unit_id"),
                "quote": (validation.get("enrichment") or {}).get("author_claim_quote"),
                "support_level": support.get("result"),
            })
    return rows


def summarize_support_levels(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    support_counts: Counter[str] = Counter()
    per_paper: list[dict[str, Any]] = []
    quote_validated = 0
    run_abort_from_no_relevant_source_unit = 0

    for item in results:
        raw = _raw_run(item)
        for row in _support_rows(raw):
            support_counts[row["support_level"]] += 1
            per_paper.append({
                "candidate_id": row["candidate_id"],
                "paper_id": row["paper_id"],
                "support_level": row["support_level"],
            })
        for candidate in _candidate_entries(raw):
            for validation in candidate.get("validation_results") or []:
                if isinstance(validation, dict) and validation.get("outcome") in QUOTE_VALIDATED_OUTCOMES:
                    quote_validated += 1
        reason_codes = set(raw.get("reason_codes") or [])
        if raw.get("status") == "FAILED" and reason_codes.intersection(
            {"NO_RELEVANT_SOURCE_UNIT", "SOURCEUNIT_SELECTION_FAILED"}
        ):
            run_abort_from_no_relevant_source_unit += 1

    total_support = sum(support_counts.values())
    return {
        "quote_validated": quote_validated,
        "support_levels": {level: support_counts[level] for level in SUPPORT_LEVELS},
        "support_level_denominator": total_support,
        "per_paper": per_paper,
        "run_abort_from_no_relevant_source_unit": run_abort_from_no_relevant_source_unit,
    }
