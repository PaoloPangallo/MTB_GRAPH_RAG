"""Audit offline before/after del matching congiuntivo gene-alterazione."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence.qualified_retrieval_query import (
    MODE_NATIVE_ONLY,
    build_query,
)
from backend.pipeline.evidence.qualified_retriever import (
    QualifiedEvidenceRetriever,
    match_biomarker,
)
from benchmarks.mtb_evidence.evaluation.scripts.candidate_coverage_audit import (
    EXPECTED_AUTHOR_APPROVAL_HASH,
    EXPECTED_CORPUS_DIRECTORY_HASH,
    EXPECTED_GOLD_HASH,
    EXPECTED_PRIOR_EXPLORATION_HASH,
    EXPECTED_SCORING_FILE_HASH,
    EXPECTED_SECOND_REVIEW_HASH,
    _aggregate,
)
from benchmarks.mtb_evidence.evaluation.scripts.v2_v3a_exploratory import (
    EXPECTED_CORPUS_FINGERPRINT,
    EXPECTED_FROZEN_KG_FINGERPRINT,
    EXPECTED_GOLD_FILES,
    EXPECTED_SCORING_HASH,
    _bundle_guard,
)


FIX_VERSION = "conjunctive-biomarker-fix/1.0"
SOURCE_SHA = "7d4c623709c01ee69467c8ec615841de745f279e"
FIX_COMMIT = "acba844"
EXPECTED_PREVIOUS_AUDIT_HASH = (
    "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273"
)
EXPECTED_RETRIEVER_AFTER_HASH = (
    "8a810fad76f569964723810bc0ec42a3eba6b32469dc3e5bc040e92fe056dd24"
)
EXPECTED_BEFORE_COUNTS = {
    "PILOT-A2-ALK-G1202R": 32,
    "PILOT-C1-EGFR-L858R-CONTEXT": 17,
    "PILOT-K1-FGFR2-iCCA": 1,
    "PILOT-N1-RMI2-SNAPSHOT": 0,
}
EXPECTED_AFTER_COUNTS = {
    "PILOT-A2-ALK-G1202R": 9,
    "PILOT-C1-EGFR-L858R-CONTEXT": 10,
    "PILOT-K1-FGFR2-iCCA": 1,
    "PILOT-N1-RMI2-SNAPSHOT": 0,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_source_sha(path: Path) -> str:
    source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_bytes(_jsonl_bytes(rows))


def _source_ids(statement: Mapping[str, Any]) -> list[str]:
    references = list(statement.get("source_references") or []) + list(
        statement.get("trial_references") or []
    )
    return sorted(
        {
            str(item.get("source_id") or item.get("external_identifier") or "")
            for item in references
            if item.get("source_id") or item.get("external_identifier")
        }
    )


def _integrity(root: Path, gold_bundle: Path) -> dict[str, Any]:
    v3 = root / "benchmarks" / "mtb_evidence" / "v3"
    corpus = _aggregate(root, [v3 / "qualification_corpus_v2"])
    packets = _aggregate(
        root, [v3 / "priority_curation" / "annotation_packets" / "second_review"]
    )
    approvals = _aggregate(
        root,
        [
            v3 / "author_approval",
            v3 / "author_approval_22235099",
            v3 / "author_approval_23344087",
        ],
    )
    previous = _aggregate(root, [v3 / "v2_v3a_exploratory_pilot"])
    previous_audit = _aggregate(root, [v3 / "candidate_coverage_audit"])
    retriever_files = sorted(
        (root / "backend" / "pipeline" / "evidence").glob("qualified_retriev*"),
        key=lambda path: path.name.casefold(),
    )
    retriever = _aggregate(root, retriever_files)
    config_path = (
        root
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    scoring = json.loads(config_path.read_text(encoding="utf-8"))
    manifest = json.loads(
        (
            v3
            / "qualification_corpus_v2"
            / "qualification_corpus_manifest.json"
        ).read_text(encoding="utf-8")
    )
    actual_expected = {
        "qualification_corpus": (
            corpus["aggregate_sha256"],
            EXPECTED_CORPUS_DIRECTORY_HASH,
        ),
        "second_review_packets": (
            packets["aggregate_sha256"],
            EXPECTED_SECOND_REVIEW_HASH,
        ),
        "author_approval": (
            approvals["aggregate_sha256"],
            EXPECTED_AUTHOR_APPROVAL_HASH,
        ),
        "previous_exploration": (
            previous["aggregate_sha256"],
            EXPECTED_PRIOR_EXPLORATION_HASH,
        ),
        "previous_candidate_audit": (
            previous_audit["aggregate_sha256"],
            EXPECTED_PREVIOUS_AUDIT_HASH,
        ),
        "scoring_file": (_sha(config_path), EXPECTED_SCORING_FILE_HASH),
        "retriever_after_fix": (
            retriever["aggregate_sha256"],
            EXPECTED_RETRIEVER_AFTER_HASH,
        ),
    }
    mismatches = {
        key: {"actual": actual, "expected": expected}
        for key, (actual, expected) in actual_expected.items()
        if actual != expected
    }
    if scoring.get("hash") != EXPECTED_SCORING_HASH:
        mismatches["scoring_hash"] = {
            "actual": scoring.get("hash"),
            "expected": EXPECTED_SCORING_HASH,
        }
    if (
        manifest.get("qualification_corpus_fingerprint")
        != EXPECTED_CORPUS_FINGERPRINT
    ):
        mismatches["corpus_fingerprint"] = {
            "actual": manifest.get("qualification_corpus_fingerprint"),
            "expected": EXPECTED_CORPUS_FINGERPRINT,
        }
    if (
        manifest.get("frozen_kg_snapshot_fingerprint")
        != EXPECTED_FROZEN_KG_FINGERPRINT
    ):
        mismatches["frozen_kg_fingerprint"] = {
            "actual": manifest.get("frozen_kg_snapshot_fingerprint"),
            "expected": EXPECTED_FROZEN_KG_FINGERPRINT,
        }
    if mismatches:
        raise RuntimeError(f"frozen input mismatch: {mismatches}")
    gold = _bundle_guard(gold_bundle, EXPECTED_GOLD_HASH)
    if set(gold["file_sha256"]) != set(EXPECTED_GOLD_FILES):
        raise RuntimeError("gold member inventory mismatch")
    return {
        "qualification_corpus": corpus,
        "second_review_packets": packets,
        "author_approval": approvals,
        "previous_exploration": previous,
        "previous_candidate_audit": previous_audit,
        "scoring_config": {
            "file_sha256": _sha(config_path),
            "canonical_hash": scoring["hash"],
        },
        "retriever_after_fix": retriever,
        "gold_bundle": gold,
        "corpus_fingerprint": manifest["qualification_corpus_fingerprint"],
        "frozen_kg_fingerprint": manifest["frozen_kg_snapshot_fingerprint"],
    }


def _candidate_row(
    *,
    query: Mapping[str, Any],
    result: Mapping[str, Any],
    statement: Mapping[str, Any],
    phase: str,
) -> dict[str, Any]:
    marker_match = match_biomarker(build_query(query).biomarkers, statement)
    return {
        "phase": phase,
        "query_id": query["query_id"],
        "case_id": query["case_id"],
        "statement_id": result["statement_id"],
        "graph_evidence_ids": sorted(result.get("graph_evidence_ids") or []),
        "source_ids": _source_ids(statement),
        "biomarker_label": str((statement.get("biomarker") or {}).get("label") or ""),
        "statement_gene": list(marker_match.statement_genes),
        "statement_alteration": list(marker_match.statement_alterations),
        "query_gene": list(marker_match.query_genes),
        "query_alteration": list(marker_match.query_alterations),
        "biomarker_match_mode": marker_match.mode,
        "gene_match": marker_match.gene_match,
        "alteration_match": marker_match.alteration_match,
        "candidate_bucket": result.get("bucket"),
        "rank": result.get("rank"),
    }


def generate_audit(
    root: Path,
    output: Path,
    gold_bundle: Path,
    *,
    reverse_query_order: bool = False,
) -> dict[str, Any]:
    """Genera l'audit senza leggere record clinici dal bundle gold."""
    integrity = _integrity(root, gold_bundle)
    output.mkdir(parents=True, exist_ok=True)
    v3 = root / "benchmarks" / "mtb_evidence" / "v3"
    query_rows = _read_jsonl(v3 / "qualified_retriever_prototype" / "queries.jsonl")
    if reverse_query_order:
        query_rows.reverse()
    query_rows = sorted(query_rows, key=lambda row: str(row["query_id"]))
    frozen_rows = {
        str(row["query_id"]): row
        for row in _read_jsonl(
            v3 / "v2_v3a_exploratory_pilot" / "native_only_results.jsonl"
        )
    }
    retriever = QualifiedEvidenceRetriever.from_corpus(
        v3 / "qualification_corpus_v2",
        scoring_config_path=(
            root
            / "backend"
            / "pipeline"
            / "evidence"
            / "qualified_retriever_scoring_config.json"
        ),
    )
    statements = {
        str(row["evidence_statement_id"]): row for row in retriever.repository.all()
    }
    before: list[dict[str, Any]] = []
    after: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    preserved: list[dict[str, Any]] = []
    per_query: list[dict[str, Any]] = []
    for query_row in query_rows:
        query_id = str(query_row["query_id"])
        case_id = str(query_row["case_id"])
        query = build_query({**query_row, "mode": MODE_NATIVE_ONLY, "top_k": 500})
        frozen = frozen_rows[query_id]
        current = retriever.retrieve(query)
        before_results = sorted(
            frozen["complete_candidate_results"],
            key=lambda row: str(row["statement_id"]),
        )
        after_results = sorted(
            (item.as_dict() for item in current.all_results),
            key=lambda row: str(row["statement_id"]),
        )
        before_ids = {str(row["statement_id"]) for row in before_results}
        after_ids = {str(row["statement_id"]) for row in after_results}
        exclusions = {
            item.statement_id: item.as_dict()
            for item in current.rejected_by_native_constraints
        }
        for result in before_results:
            before.append(
                _candidate_row(
                    query=query_row,
                    result=result,
                    statement=statements[str(result["statement_id"])],
                    phase="before_frozen_native_only",
                )
            )
        for result in after_results:
            after.append(
                _candidate_row(
                    query=query_row,
                    result=result,
                    statement=statements[str(result["statement_id"])],
                    phase="after_conjunctive_native_only",
                )
            )
        for statement_id in sorted(before_ids - after_ids):
            exclusion = exclusions[statement_id]
            removed.append(
                {
                    "query_id": query_id,
                    "case_id": case_id,
                    "statement_id": statement_id,
                    "reason_code": exclusion["reason_code"],
                    "biomarker_match_mode": exclusion["biomarker_match_mode"],
                    "query_gene": exclusion["query_gene"],
                    "query_alteration": exclusion["query_alteration"],
                    "statement_gene": exclusion["statement_gene"],
                    "statement_alteration": exclusion["statement_alteration"],
                    "classification": "removed_gene_only_match",
                    "gold_used": False,
                }
            )
        after_by_id = {str(row["statement_id"]): row for row in after_results}
        for statement_id in sorted(before_ids & after_ids):
            result = after_by_id[statement_id]
            preserved.append(
                {
                    **_candidate_row(
                        query=query_row,
                        result=result,
                        statement=statements[statement_id],
                        phase="preserved_after_fix",
                    ),
                    "classification": "preserved_alteration_match",
                    "gold_used": False,
                }
            )
        per_query.append(
            {
                "query_id": query_id,
                "case_id": case_id,
                "before_count": len(before_ids),
                "after_count": len(after_ids),
                "removed_count": len(before_ids - after_ids),
                "preserved_count": len(before_ids & after_ids),
                "added_count": len(after_ids - before_ids),
                "removed_statement_ids": sorted(before_ids - after_ids),
                "preserved_statement_ids": sorted(before_ids & after_ids),
                "added_statement_ids": sorted(after_ids - before_ids),
                "unexpected_change": (
                    case_id in {"PILOT-K1-FGFR2-iCCA", "PILOT-N1-RMI2-SNAPSHOT"}
                    and before_ids != after_ids
                ),
            }
        )
    before.sort(key=lambda row: (row["query_id"], row["statement_id"]))
    after.sort(key=lambda row: (row["query_id"], row["statement_id"]))
    removed.sort(key=lambda row: (row["query_id"], row["statement_id"]))
    preserved.sort(key=lambda row: (row["query_id"], row["statement_id"]))
    per_query.sort(key=lambda row: row["query_id"])
    before_counts = {row["case_id"]: row["before_count"] for row in per_query}
    after_counts = {row["case_id"]: row["after_count"] for row in per_query}
    if before_counts != EXPECTED_BEFORE_COUNTS or after_counts != EXPECTED_AFTER_COUNTS:
        raise RuntimeError(
            f"candidate count mismatch: before={before_counts}, after={after_counts}"
        )
    if (
        sum(
            row["removed_count"]
            for row in per_query
            if row["case_id"] == "PILOT-A2-ALK-G1202R"
        )
        != 23
    ):
        raise RuntimeError("ALK overreach count mismatch")
    _write_jsonl(output / "candidate_set_before.jsonl", before)
    _write_jsonl(output / "candidate_set_after.jsonl", after)
    _write_jsonl(output / "removed_gene_only_matches.jsonl", removed)
    _write_jsonl(output / "preserved_alteration_matches.jsonl", preserved)
    _write_json(
        output / "per_query_diff.json",
        {
            "fix_version": FIX_VERSION,
            "queries": per_query,
            "totals": {
                "before": len(before),
                "after": len(after),
                "removed": len(removed),
                "preserved": len(preserved),
                "added": sum(row["added_count"] for row in per_query),
            },
        },
    )
    artifact_names = (
        "candidate_set_before.jsonl",
        "candidate_set_after.jsonl",
        "removed_gene_only_matches.jsonl",
        "preserved_alteration_matches.jsonl",
        "per_query_diff.json",
    )
    artifact_hashes = {name: _sha(output / name) for name in artifact_names}
    manifest = {
        "fix_version": FIX_VERSION,
        "branch": "fix/v3-conjunctive-biomarker-matching",
        "source_sha": SOURCE_SHA,
        "fix_commit": FIX_COMMIT,
        "generator_source_sha256": _canonical_source_sha(Path(__file__)),
        "corpus_fingerprint": integrity["corpus_fingerprint"],
        "frozen_kg_fingerprint": integrity["frozen_kg_fingerprint"],
        "scoring_config_hash": integrity["scoring_config"]["canonical_hash"],
        "gold_bundle_hash": integrity["gold_bundle"]["aggregate_sha256"],
        "gold_content_loaded": False,
        "gold_used_for_fix": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
        "synonyms_added": False,
        "scoring_changed": False,
        "corpus_changed": False,
        "input_integrity": integrity,
        "artifact_hashes": artifact_hashes,
        "candidate_counts_before": before_counts,
        "candidate_counts_after": after_counts,
        "alk_removed_count": 23,
        "unexpected_changes": [
            row["case_id"] for row in per_query if row["unexpected_change"]
        ],
        "deterministic_order": ["query_id", "statement_id"],
    }
    _write_json(output / "fix_manifest.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gold-bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    generate_audit(args.root, args.output, args.gold_bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
