"""Audit deterministico del fix disease alias, senza accesso al gold clinico."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from backend.pipeline.evidence.qualified_disease_matching import (
    DISEASE_MATCHER_VERSION,
    HARD_MATCH_TYPES,
    MATCH_EXPLICIT_CHILD,
    MATCH_EXPLICIT_PARENT,
    MATCH_EXPLICIT_SIBLING,
    MATCH_VERIFIED_ALIAS,
    VERIFIED_ALIAS_SOURCE,
    VERIFIED_ALIAS_VERSION,
    match_disease,
)
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
from benchmarks.mtb_evidence.pilot.audit_lib.disease import (
    _SUBTYPE_OF,
    _SYNONYM_GROUPS,
)


FIX_VERSION = "verified-disease-alias-fix/1.0"
SOURCE_SHA = "ec8aabfb7f8c4d3fe9f0664aa68aa6244be4c964"
FIX_COMMIT = "1133ab72e37e10f54c00398e409f9393c8bf0234"
EXPECTED_CANDIDATE_AUDIT_HASH = "43396526a701ba1ec7f4e1f0bbc498a798ca02fd9600deedf7ef1ed442ca7273"
EXPECTED_CONJUNCTIVE_FIX_HASH = (
    "cf69886100af3f25f06426ad81a3ae811f9c1e76a08c240b5e2c86f41"
    "d88638d"
)
EXPECTED_DISEASE_REVIEW_HASH = (
    "1084763a50e63cfe4c19b72defca5c73788a826f5227a0fd4378c7bc10"
    "20b71c"
)
EXPECTED_DISEASE_NORMALIZER_FILE_HASH = (
    "7e3ab30006ba9c7ccdc80b1d2a4bd544159b3fa0044aee87e3501847986593b7"
)
EXPECTED_DISEASE_SEMANTIC_TABLE_HASH = (
    "6372a0b0f4b24e505266bd061d3997e75aee9cde4a01558ea57e9c3755c9abd4"
)
EXPECTED_BEFORE_COUNTS = {
    "PILOT-A2-ALK-G1202R": 9,
    "PILOT-C1-EGFR-L858R-CONTEXT": 10,
    "PILOT-K1-FGFR2-iCCA": 1,
    "PILOT-N1-RMI2-SNAPSHOT": 0,
}
EXPECTED_AFTER_COUNTS = {
    "PILOT-A2-ALK-G1202R": 9,
    "PILOT-C1-EGFR-L858R-CONTEXT": 32,
    "PILOT-K1-FGFR2-iCCA": 1,
    "PILOT-N1-RMI2-SNAPSHOT": 0,
}
KEY_EVIDENCE_IDS = (
    "evidence:11219",
    "evidence:11598",
    "evidence:11599",
    "evidence:1867",
    "evidence:8173",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_source_sha(path: Path) -> str:
    source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _disease_semantic_table_hash() -> str:
    payload = {
        "synonym_groups": sorted(sorted(group) for group in _SYNONYM_GROUPS),
        "subtype_of": dict(sorted(_SUBTYPE_OF.items())),
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


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


def _integrity(
    root: Path,
    gold_bundle: Path,
) -> dict[str, Any]:
    v3 = root / "benchmarks/mtb_evidence/v3"
    paths = {
        "qualification_corpus": v3 / "qualification_corpus_v2",
        "second_review_packets": (
            v3 / "priority_curation/annotation_packets/second_review"
        ),
        "candidate_coverage_audit": v3 / "candidate_coverage_audit",
        "conjunctive_biomarker_fix": v3 / "conjunctive_biomarker_fix",
        "disease_normalization_review": v3 / "disease_normalization_review",
    }
    actual = {name: _aggregate(root, [path]) for name, path in paths.items()}
    approvals = _aggregate(
        root,
        [
            v3 / "author_approval",
            v3 / "author_approval_22235099",
            v3 / "author_approval_23344087",
        ],
    )
    expected = {
        "qualification_corpus": EXPECTED_CORPUS_DIRECTORY_HASH,
        "second_review_packets": EXPECTED_SECOND_REVIEW_HASH,
        "candidate_coverage_audit": EXPECTED_CANDIDATE_AUDIT_HASH,
        "conjunctive_biomarker_fix": EXPECTED_CONJUNCTIVE_FIX_HASH,
        "disease_normalization_review": EXPECTED_DISEASE_REVIEW_HASH,
    }
    mismatches = {
        name: {
            "actual": actual[name]["aggregate_sha256"],
            "expected": digest,
        }
        for name, digest in expected.items()
        if actual[name]["aggregate_sha256"] != digest
    }
    if approvals["aggregate_sha256"] != EXPECTED_AUTHOR_APPROVAL_HASH:
        mismatches["author_approval"] = {
            "actual": approvals["aggregate_sha256"],
            "expected": EXPECTED_AUTHOR_APPROVAL_HASH,
        }
    config = (
        root
        / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
    )
    scoring = json.loads(config.read_text(encoding="utf-8"))
    disease_normalizer = (
        root / "benchmarks/mtb_evidence/pilot/audit_lib/disease.py"
    )
    disease_normalizer_hash = _sha(disease_normalizer)
    disease_semantic_table_hash = _disease_semantic_table_hash()
    if disease_normalizer_hash != EXPECTED_DISEASE_NORMALIZER_FILE_HASH:
        mismatches["disease_normalizer_file"] = {
            "actual": disease_normalizer_hash,
            "expected": EXPECTED_DISEASE_NORMALIZER_FILE_HASH,
        }
    if disease_semantic_table_hash != EXPECTED_DISEASE_SEMANTIC_TABLE_HASH:
        mismatches["disease_semantic_tables"] = {
            "actual": disease_semantic_table_hash,
            "expected": EXPECTED_DISEASE_SEMANTIC_TABLE_HASH,
        }
    if _sha(config) != EXPECTED_SCORING_FILE_HASH:
        mismatches["scoring_file"] = {
            "actual": _sha(config),
            "expected": EXPECTED_SCORING_FILE_HASH,
        }
    if scoring.get("hash") != EXPECTED_SCORING_HASH:
        mismatches["scoring_hash"] = {
            "actual": scoring.get("hash"),
            "expected": EXPECTED_SCORING_HASH,
        }
    manifest = json.loads(
        (
            v3
            / "qualification_corpus_v2/qualification_corpus_manifest.json"
        ).read_text(encoding="utf-8")
    )
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
        **actual,
        "author_approval": approvals,
        "gold_bundle": gold,
        "scoring_config": {
            "file_sha256": _sha(config),
            "canonical_hash": scoring["hash"],
        },
        "disease_normalizer": {
            "file_sha256": disease_normalizer_hash,
            "semantic_tables_sha256": disease_semantic_table_hash,
            "synonym_group_count": len(_SYNONYM_GROUPS),
            "hierarchy_edge_count": len(_SUBTYPE_OF),
        },
        "corpus_fingerprint": manifest["qualification_corpus_fingerprint"],
        "frozen_kg_fingerprint": manifest["frozen_kg_snapshot_fingerprint"],
    }


def _graph_ids(result: Mapping[str, Any]) -> list[str]:
    return sorted(str(item) for item in result.get("graph_evidence_ids") or [])


def _result_row(
    result: Mapping[str, Any],
    *,
    case_id: str,
    phase: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "query_id": result["query_id"],
        "case_id": case_id,
        "statement_id": result["statement_id"],
        "graph_evidence_ids": _graph_ids(result),
        "rank": result["rank"],
        "bucket": result["bucket"],
        "source_ids": sorted(result.get("source_ids") or []),
        "disease_match": result.get("disease_match") or {},
        "native_matches": result.get("native_matches") or {},
    }


def generate_audit(
    root: Path,
    output: Path,
    gold_bundle: Path,
    *,
    reverse_query_order: bool = False,
) -> dict[str, Any]:
    """Genera il confronto prima/dopo; il gold viene solo autenticato per hash."""
    integrity = _integrity(root, gold_bundle)
    output.mkdir(parents=True, exist_ok=True)
    v3 = root / "benchmarks/mtb_evidence/v3"
    query_rows = _read_jsonl(v3 / "qualified_retriever_prototype/queries.jsonl")
    if reverse_query_order:
        query_rows.reverse()
    query_rows.sort(key=lambda row: str(row["query_id"]))
    before_rows = _read_jsonl(
        v3 / "conjunctive_biomarker_fix/candidate_set_after.jsonl"
    )
    before_by_query: dict[str, list[dict[str, Any]]] = {}
    for row in before_rows:
        before_by_query.setdefault(str(row["query_id"]), []).append(row)

    retriever = QualifiedEvidenceRetriever.from_corpus(
        v3 / "qualification_corpus_v2",
        scoring_config_path=(
            root
            / "backend/pipeline/evidence/qualified_retriever_scoring_config.json"
        ),
    )
    statements = {
        str(row["evidence_statement_id"]): row for row in retriever.repository.all()
    }
    after: list[dict[str, Any]] = []
    newly_matched: list[dict[str, Any]] = []
    biomarker_exclusions: list[dict[str, Any]] = []
    hierarchy: list[dict[str, Any]] = []
    alias_audit: list[dict[str, Any]] = []
    per_query: list[dict[str, Any]] = []

    for query_row in query_rows:
        query = build_query(
            {**query_row, "mode": MODE_NATIVE_ONLY, "top_k": 500}
        )
        current = retriever.retrieve(query)
        current_rows = [
            _result_row(
                item.as_dict(),
                case_id=query.case_id,
                phase="after_verified_alias_fix",
            )
            for item in current.all_results
        ]
        after.extend(current_rows)
        before_query = before_by_query.get(query.query_id, [])
        before_ids = {str(row["statement_id"]) for row in before_query}
        after_ids = {str(row["statement_id"]) for row in current_rows}
        exclusion_by_id = {
            item.statement_id: item for item in current.rejected_by_native_constraints
        }

        for statement_id in sorted(after_ids - before_ids):
            row = next(
                item for item in current_rows if item["statement_id"] == statement_id
            )
            classification = (
                "expected_verified_alias_recovery"
                if row["disease_match"]["match_type"] == MATCH_VERIFIED_ALIAS
                else "unexpected_candidate_addition"
            )
            newly_matched.append({**row, "change_classification": classification})

        for statement in retriever.repository.all():
            statement_id = str(statement["evidence_statement_id"])
            disease_value = str((statement.get("disease") or {}).get("label") or "")
            disease = match_disease(
                query.disease,
                disease_value,
                query_aliases=query.disease_aliases,
            )
            biomarker = match_biomarker(query.biomarkers, statement)
            first_failure = (
                ""
                if biomarker.matched and disease.hard_match_allowed
                else "biomarker"
                if not biomarker.matched
                else "disease"
            )
            graph_ids = sorted(
                str(item)
                for item in (
                    (statement.get("provenance") or {}).get("graph_record_ids")
                    or []
                )
            )
            audit_row = {
                "query_id": query.query_id,
                "case_id": query.case_id,
                "statement_id": statement_id,
                "graph_evidence_ids": graph_ids,
                "biomarker_matched": biomarker.matched,
                "biomarker_reason_code": biomarker.reason_code,
                "disease_match": disease.as_dict(),
                "first_failing_native_constraint": first_failure,
                "in_primary_candidate_set": statement_id in after_ids,
                "gold_used": False,
            }
            alias_audit.append(audit_row)
            if (
                not biomarker.matched
                and disease.match_type == MATCH_VERIFIED_ALIAS
                and statement_id in exclusion_by_id
            ):
                biomarker_exclusions.append(
                    {
                        **audit_row,
                        "change_classification": "expected_biomarker_exclusion",
                        "exclusion": exclusion_by_id[statement_id].as_dict(),
                    }
                )
            if (
                biomarker.matched
                and disease.match_type
                in {
                    MATCH_EXPLICIT_PARENT,
                    MATCH_EXPLICIT_CHILD,
                    MATCH_EXPLICIT_SIBLING,
                }
            ):
                hierarchy.append(
                    {
                        **audit_row,
                        "change_classification": (
                            "expected_hierarchy_not_applied"
                        ),
                    }
                )

        unexpected_additions = [
            row
            for row in newly_matched
            if row["query_id"] == query.query_id
            and row["change_classification"] == "unexpected_candidate_addition"
        ]
        removed_ids = sorted(before_ids - after_ids)
        expected_hierarchy_removals = [
            statement_id
            for statement_id in removed_ids
            if (exclusion_by_id[statement_id].disease_match or {}).get("match_type")
            in {
                MATCH_EXPLICIT_PARENT,
                MATCH_EXPLICIT_CHILD,
                MATCH_EXPLICIT_SIBLING,
            }
        ]
        unexpected_removals = sorted(
            set(removed_ids) - set(expected_hierarchy_removals)
        )
        per_query.append(
            {
                "query_id": query.query_id,
                "case_id": query.case_id,
                "before_count": len(before_ids),
                "after_count": len(after_ids),
                "added_count": len(after_ids - before_ids),
                "removed_count": len(before_ids - after_ids),
                "preserved_count": len(before_ids & after_ids),
                "new_statement_ids": sorted(after_ids - before_ids),
                "removed_statement_ids": removed_ids,
                "expected_hierarchy_not_applied_count": len(
                    expected_hierarchy_removals
                ),
                "expected_hierarchy_not_applied_statement_ids": (
                    expected_hierarchy_removals
                ),
                "unexpected_candidate_addition_count": len(
                    unexpected_additions
                ),
                "unexpected_candidate_removal_count": len(
                    unexpected_removals
                ),
            }
        )

    for rows in (after, newly_matched, biomarker_exclusions, hierarchy, alias_audit):
        rows.sort(
            key=lambda row: (
                str(row["query_id"]),
                str(row["statement_id"]),
            )
        )
    per_query.sort(key=lambda row: str(row["query_id"]))
    before_rows.sort(
        key=lambda row: (str(row["query_id"]), str(row["statement_id"]))
    )

    counts_before = {row["case_id"]: row["before_count"] for row in per_query}
    counts_after = {row["case_id"]: row["after_count"] for row in per_query}
    if counts_before != EXPECTED_BEFORE_COUNTS:
        raise RuntimeError(f"before candidate count mismatch: {counts_before}")
    if counts_after != EXPECTED_AFTER_COUNTS:
        raise RuntimeError(f"after candidate count mismatch: {counts_after}")
    if sum(row["unexpected_candidate_addition_count"] for row in per_query):
        raise RuntimeError("unexpected candidate addition")
    if sum(row["unexpected_candidate_removal_count"] for row in per_query):
        raise RuntimeError("unexpected candidate removal")

    review_rows = _read_jsonl(
        v3 / "disease_normalization_review/disease_pair_classification.jsonl"
    )
    expected_egfr_graph_ids = {
        str(row["graph_evidence_id"])
        for row in review_rows
        if row["case_id"] == "PILOT-C1-EGFR-L858R-CONTEXT"
        and row["biomarker_match_after_fix"]
        and row["disease_relation_classification"]
        in {
            "exact_string_match",
            "normalized_exact_match",
            "verified_alias_match",
        }
    }
    actual_egfr_graph_ids = {
        graph_id
        for row in after
        if row["case_id"] == "PILOT-C1-EGFR-L858R-CONTEXT"
        for graph_id in row["graph_evidence_ids"]
    }
    if expected_egfr_graph_ids != actual_egfr_graph_ids:
        raise RuntimeError("EGFR alias-safe set does not match frozen review")

    output_files = {
        "candidate_sets_before.jsonl": before_rows,
        "candidate_sets_after.jsonl": after,
        "newly_matched_verified_aliases.jsonl": newly_matched,
        "still_excluded_biomarker_mismatches.jsonl": biomarker_exclusions,
        "hierarchical_relations_not_applied.jsonl": hierarchy,
        "alias_match_audit.jsonl": alias_audit,
    }
    for name, rows in output_files.items():
        _write_jsonl(output / name, rows)
    per_query_payload = {
        "fix_version": FIX_VERSION,
        "queries": per_query,
        "totals": {
            "before": sum(row["before_count"] for row in per_query),
            "after": sum(row["after_count"] for row in per_query),
            "added": sum(row["added_count"] for row in per_query),
            "removed": sum(row["removed_count"] for row in per_query),
            "unexpected_candidate_additions": 0,
            "unexpected_candidate_removals": 0,
        },
    }
    _write_json(output / "per_query_diff.json", per_query_payload)
    generated_artifact_names = sorted(
        {*output_files, "per_query_diff.json"}
    )
    artifact_hashes = {
        name: _sha(output / name) for name in generated_artifact_names
    }
    manifest = {
        "fix_version": FIX_VERSION,
        "branch": "fix/v3-verified-disease-alias-matching",
        "source_sha": SOURCE_SHA,
        "fix_commit": FIX_COMMIT,
        "generator_source_sha256": _canonical_source_sha(Path(__file__)),
        "implementation_files_sha256": {
            "qualified_disease_matching.py": _sha(
                root
                / "backend/pipeline/evidence/qualified_disease_matching.py"
            ),
            "qualified_retrieval_result.py": _sha(
                root
                / "backend/pipeline/evidence/qualified_retrieval_result.py"
            ),
            "qualified_retriever.py": _sha(
                root / "backend/pipeline/evidence/qualified_retriever.py"
            ),
        },
        "disease_matcher_version": DISEASE_MATCHER_VERSION,
        "verified_alias_source": VERIFIED_ALIAS_SOURCE,
        "verified_alias_version": VERIFIED_ALIAS_VERSION,
        "hard_match_types": sorted(HARD_MATCH_TYPES),
        "hierarchy_policy_implemented": False,
        "new_aliases_introduced": [],
        "gold_content_loaded": False,
        "gold_used_for_fix": False,
        "network_used": False,
        "neo4j_used": False,
        "llm_used": False,
        "scoring_changed": False,
        "corpus_changed": False,
        "multi_intervention_adapter_changed": False,
        "candidate_counts_before": counts_before,
        "candidate_counts_after": counts_after,
        "expected_verified_alias_recoveries": len(newly_matched),
        "unexpected_candidate_additions": 0,
        "unexpected_candidate_removals": 0,
        "key_evidence_ids": list(KEY_EVIDENCE_IDS),
        "corpus_fingerprint": integrity["corpus_fingerprint"],
        "frozen_kg_fingerprint": integrity["frozen_kg_fingerprint"],
        "scoring_config": integrity["scoring_config"],
        "gold_bundle": integrity["gold_bundle"],
        "input_integrity": {
            name: value
            for name, value in integrity.items()
            if name
            not in {
                "corpus_fingerprint",
                "frozen_kg_fingerprint",
                "scoring_config",
                "gold_bundle",
            }
        },
        "artifact_hashes": artifact_hashes,
        "deterministic_order": ["query_id", "statement_id"],
    }
    _write_json(output / "fix_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gold-bundle", type=Path, required=True)
    parser.add_argument("--reverse-query-order", action="store_true")
    args = parser.parse_args()
    generate_audit(
        args.root.resolve(),
        args.output.resolve(),
        args.gold_bundle.resolve(),
        reverse_query_order=args.reverse_query_order,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
