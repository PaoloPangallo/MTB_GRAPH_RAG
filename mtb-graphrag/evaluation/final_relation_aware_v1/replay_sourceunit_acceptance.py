"""Offline acceptance harness for the frozen Phase 1B.3 source documents.

It reads JSONL records as row dictionaries at the boundary, then re-parses the
evaluation-local canonical cache with the runtime parser.  The harness never
contacts a resolver endpoint and never mutates the frozen pre-fix JSONL.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Any

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache


ROOT = Path(__file__).parent
DOCUMENTS = ROOT / "documents"
SOURCEUNITS = ROOT / "sourceunits"
AVAILABLE_CLASSES = {"FULLTEXT", "ABSTRACT_ONLY"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TypeError(f"{path}:{line_number}: expected JSON object row, got {type(value).__name__}")
        rows.append(value)
    return rows


def target_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row["candidate_id"]), str(row["document_id"])


def canonical_non_id(unit: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in unit.items() if key not in {"source_unit_id", "ordinal"}}


def replay() -> dict[str, Any]:
    old_rows = read_jsonl(SOURCEUNITS / "sourceunits.jsonl")
    document_rows = read_jsonl(DOCUMENTS / "document_manifest.jsonl")
    scoring_rows = read_jsonl(ROOT / "rq3_scoring_unit_manifest.jsonl")
    scoring_by_key = {target_key(row): row for row in scoring_rows}
    old_by_key: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in old_rows:
        old_by_key[target_key(row)].append(row)
    for rows in old_by_key.values():
        rows.sort(key=lambda row: int(row["ordinal"]))

    # The explicit loop avoids treating JSONL strings as dictionaries: this was
    # the original TypeError source in the ad-hoc replay command.
    old_id_groups: dict[tuple[str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for row in old_rows:
        old_id_groups[(str(row["scoring_unit_id"]), str(row["source_unit_id"]))].append(row)
    collision_groups = {key: rows for key, rows in old_id_groups.items() if len(rows) > 1}

    cache = AuthorizedDocumentCache(root=DOCUMENTS / "canonical_cache", network=False)
    comparisons: list[dict[str, Any]] = []
    new_total = 0
    duplicate_groups = 0
    documents_with_duplicate_ids: list[dict[str, Any]] = []
    first_mismatch: dict[str, Any] | None = None
    replayed_collision_groups = 0
    new_collision_groups = 0

    for document_row in document_rows:
        if document_row["resolution_class"] not in AVAILABLE_CLASSES:
            continue
        key = target_key(document_row)
        old_units = old_by_key.get(key)
        scoring = scoring_by_key.get(key)
        if old_units is None or scoring is None:
            raise KeyError(f"no frozen source/scoring row for {key}")
        record = cache._cached_manifest(str(document_row["document_id"]))
        if not isinstance(record, dict):
            raise FileNotFoundError(f"missing cache manifest for {document_row['document_id']}")
        new_units = cache.source_units_for_record(dict(record))
        new_total += len(new_units)
        ids = [str(unit["source_unit_id"]) for unit in new_units]
        duplicate_id_count = len(ids) - len(set(ids))
        if duplicate_id_count:
            duplicate_groups += 1
            documents_with_duplicate_ids.append({"candidate_id": key[0], "document_id": key[1], "duplicate_excess_rows": duplicate_id_count})
        mismatch: dict[str, Any] | None = None
        if len(old_units) != len(new_units):
            mismatch = {"field": "count", "old": len(old_units), "new": len(new_units)}
        else:
            for ordinal, (old, new) in enumerate(zip(old_units, new_units)):
                expected = {
                    "text": old.get("text"),
                    "source_unit_type": old.get("source_unit_type"),
                    "section": old.get("section"),
                    "ordinal": old.get("ordinal"),
                }
                actual = {
                    "text": new.get("text"),
                    "source_unit_type": new.get("unit_type"),
                    "section": new.get("section"),
                    "ordinal": ordinal,
                }
                if expected != actual:
                    mismatch = {"field": "ordered_non_id", "ordinal": ordinal, "old": expected, "new": actual}
                    break
        comparisons.append({"candidate_id": key[0], "document_id": key[1], "scoring_unit_id": scoring["scoring_unit_id"], "old_count": len(old_units), "new_count": len(new_units), "duplicate_source_unit_id_excess": duplicate_id_count, "mismatch": mismatch})
        if mismatch is not None and first_mismatch is None:
            first_mismatch = {"candidate_id": key[0], "document_id": key[1], **mismatch}

    collision_scoring_ids = {scoring_unit_id for scoring_unit_id, _ in collision_groups}
    for comparison in comparisons:
        if comparison["scoring_unit_id"] in collision_scoring_ids:
            replayed_collision_groups += sum(1 for scoring_unit_id, _ in collision_groups if scoring_unit_id == comparison["scoring_unit_id"])
            if comparison["duplicate_source_unit_id_excess"]:
                new_collision_groups += 1

    return {
        "available_documents_replayed": len(comparisons),
        "old_total_sourceunits": len(old_rows),
        "new_total_sourceunits": new_total,
        "old_collision_groups": len(collision_groups),
        "replayed_collision_groups": replayed_collision_groups,
        "new_collision_groups": new_collision_groups,
        "new_duplicate_source_unit_ids_within_document": sum(item["duplicate_source_unit_id_excess"] for item in documents_with_duplicate_ids),
        "documents_with_duplicate_sourceunit_ids": documents_with_duplicate_ids,
        "sourceunit_counts_identical": all(item["old_count"] == item["new_count"] for item in comparisons),
        "sourceunit_text_sequence_identical": first_mismatch is None,
        "sourceunit_order_identical": first_mismatch is None,
        "sourceunit_type_section_identical": first_mismatch is None,
        "non_id_metadata_identical": first_mismatch is None,
        "first_mismatch": first_mismatch,
        "comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    outcome = replay()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in outcome.items() if key != "comparisons"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
