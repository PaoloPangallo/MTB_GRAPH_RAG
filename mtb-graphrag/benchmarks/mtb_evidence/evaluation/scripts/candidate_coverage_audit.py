"""Audit causale, offline e read-only della candidate coverage V2/V3."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence._normalize import normalize_text
from backend.pipeline.evidence.qualified_retrieval_query import build_query
from backend.pipeline.evidence.qualified_retrieval_result import (
    X_BIOMARKER_MISMATCH,
    X_DISEASE_MISMATCH,
    X_DIRECTION_MISMATCH,
    X_INTERVENTION_MISMATCH,
    X_POLARITY_MISMATCH,
    X_SCOPE_MISMATCH,
)
from backend.pipeline.evidence.qualified_retriever import (
    _contains_marker,
    _label,
    _native_match,
)
from backend.pipeline.evidence.v2_adapter import SIGNIFICANCE_TO_DIRECTION
from benchmarks.mtb_evidence.evaluation.scripts.v2_v3a_exploratory import (
    EXPECTED_CORPUS_FINGERPRINT,
    EXPECTED_FROZEN_KG_FINGERPRINT,
    EXPECTED_GOLD_FILES,
    EXPECTED_SCORING_HASH,
)


AUDIT_VERSION = "candidate-coverage-audit/1.0"
SOURCE_SHA = "ec2293baed1202edc9027fdb173a0aa25c1961f4"
EXPECTED_GOLD_HASH = (
    "05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133"
)
EXPECTED_CORPUS_DIRECTORY_HASH = (
    "bf23a06ac8c122d2257487c0109eb8e0226f2b16d2d733740a6cd008ed34e827"
)
EXPECTED_SCORING_FILE_HASH = (
    "57d76d377029ba5c92cf4785d8143e2d06d02b6dc0e0c1d7ef57ea118e553fd4"
)
EXPECTED_PRIOR_EXPLORATION_HASH = (
    "f0ca36d81024170a5fe51b32763333468091a1d3b3a15f822bf57694c7f711cd"
)
EXPECTED_SECOND_REVIEW_HASH = (
    "6bb4ee225e4c273a6f24378dc5c982490cdbf3482a1e780e4c173695fe131bb6"
)
EXPECTED_AUTHOR_APPROVAL_HASH = (
    "8bdafc1188d9050898ffdfab69626ad0d8780b2f137de24bb6d0716d2129c278"
)
EXPECTED_RETRIEVER_HASH = (
    "c1842b444775b06f4328e39f0760c6346540c9da93eeb00d677ec75bde842bc7"
)
EXPECTED_FROZEN_V2_SERIALIZATION_HASH = (
    "2a22b04abbfcff831b7123165e806cdb49d80fd557b2517d8743f72b010087de"
)
EXPECTED_FROZEN_V2_RESULT_HASH = (
    "900a2c6afb61be728cfbebfa5784aeeb87b6478a1bd4153cd044c7f89775f981"
)
GOLD_EVIDENCE_IDS = (
    "evidence:11219",
    "evidence:11598",
    "evidence:11599",
    "evidence:1867",
    "evidence:8173",
)
MODES = ("v2_compatibility", "native_only", "qualified_soft")
FILTERS = (
    ("biomarker", X_BIOMARKER_MISMATCH),
    ("disease", X_DISEASE_MISMATCH),
    ("direction", X_DIRECTION_MISMATCH),
    ("assertion_polarity", X_POLARITY_MISMATCH),
    ("evidence_scope", X_SCOPE_MISMATCH),
    ("intervention", X_INTERVENTION_MISMATCH),
)
FINAL_CATEGORIES = {
    "ranked_results": "ranked",
    "retained_with_warning": "retained_with_warning",
    "audit_only_results": "audit_only",
}
PRIMARY_CAUSES = {
    "statement_not_materialized",
    "adapter_conversion_loss",
    "graph_evidence_id_mapping_gap",
    "source_identity_mapping_gap",
    "disease_normalization_gap",
    "biomarker_gene_normalization_gap",
    "alteration_normalization_gap",
    "intervention_normalization_gap",
    "direction_mapping_gap",
    "assertion_polarity_mapping_gap",
    "evidence_scope_mapping_gap",
    "native_filter_mismatch",
    "duplicate_canonicalization",
    "historical_v2_record_not_evidence_statement",
    "V2_traversal_semantics_not_represented",
    "baseline_serialization_difference",
    "expected_non_equivalence",
    "unresolved_other",
}


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.write_bytes(_json_bytes(payload))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_bytes(_jsonl_bytes(rows))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _aggregate(root: Path, paths: Sequence[Path]) -> dict[str, Any]:
    files = sorted(
        (
            item
            for path in paths
            for item in ([path] if path.is_file() else path.rglob("*"))
            if item.is_file()
        ),
        key=lambda item: item.relative_to(root).as_posix().casefold(),
    )
    payload = "\n".join(
        f"{item.relative_to(root).as_posix()}:{_sha(item)}" for item in files
    )
    return {
        "file_count": len(files),
        "aggregate_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "contract": (
            "sha256 of sorted repository-relative POSIX path:sha256 lines "
            "without trailing newline"
        ),
    }


def _source_ids(statement: Mapping[str, Any]) -> list[str]:
    refs = list(statement.get("source_references") or []) + list(
        statement.get("trial_references") or []
    )
    return sorted(
        {
            str(ref.get("source_id") or ref.get("external_identifier") or "")
            for ref in refs
            if ref.get("source_id") or ref.get("external_identifier")
        }
    )


def _graph_ids(statement: Mapping[str, Any]) -> list[str]:
    return sorted(
        str(item)
        for item in (statement.get("provenance") or {}).get("graph_record_ids")
        or []
    )


def _statement_projection(statement: Mapping[str, Any]) -> dict[str, Any]:
    biomarker = statement.get("biomarker") or {}
    return {
        "statement_id": str(statement.get("evidence_statement_id") or ""),
        "graph_evidence_ids": _graph_ids(statement),
        "source_ids": _source_ids(statement),
        "disease": _label(statement.get("disease")),
        "gene": str(biomarker.get("gene") or ""),
        "alteration": str(statement.get("alteration_type") or ""),
        "biomarker": _label(biomarker),
        "intervention": _label(statement.get("intervention")),
        "direction": str(statement.get("direction") or ""),
        "evidence_scope": str(statement.get("evidence_scope") or ""),
        "assertion_polarity": str(statement.get("assertion_polarity") or ""),
    }


def _raw_origins(root: Path, case_ids: Sequence[str]) -> dict[str, list[str]]:
    origins: dict[str, set[str]] = defaultdict(set)
    audit = root / "benchmarks" / "mtb_evidence" / "pilot" / "audit"
    for case_id in sorted(case_ids):
        for row in _read_jsonl(audit / case_id / "raw_records.jsonl"):
            record = row.get("record") or {}
            evidence_id = record.get("evidence_id")
            if evidence_id is None:
                continue
            graph_id = f"evidence:{evidence_id}"
            origins[graph_id].add(f"{case_id}:{row.get('query')}")
    return {key: sorted(value) for key, value in sorted(origins.items())}


def _filter_audit(
    query_payload: Mapping[str, Any],
    statement: Mapping[str, Any],
    link_polarities: Sequence[str],
) -> dict[str, Any]:
    query = build_query({**query_payload, "mode": "native_only"})
    disease_keys = tuple(sorted(query.disease_keys()))
    intervention_keys = tuple(sorted(query.intervention_keys()))
    direction_keys = tuple(
        sorted({normalize_text(item) for item in query.directions})
    )
    polarity_keys = {
        normalize_text(item) for item in query.assertion_polarities
    }
    scope_keys = tuple(
        sorted({normalize_text(item) for item in query.evidence_scopes})
    )
    normalized_link_polarities = {
        normalize_text(item) for item in link_polarities if item
    }
    stages = [
        {
            "stage": "biomarker",
            "passed": _contains_marker(statement, query.biomarker_keys()),
            "query_value": list(query.biomarker_keys()),
            "statement_value": _label(statement.get("biomarker")),
            "reason_code": X_BIOMARKER_MISMATCH,
        },
        {
            "stage": "disease",
            "passed": _native_match(
                disease_keys, _label(statement.get("disease"))
            ),
            "query_value": list(disease_keys),
            "statement_value": _label(statement.get("disease")),
            "reason_code": X_DISEASE_MISMATCH,
        },
        {
            "stage": "direction",
            "passed": _native_match(direction_keys, statement.get("direction")),
            "query_value": list(direction_keys),
            "statement_value": str(statement.get("direction") or ""),
            "reason_code": X_DIRECTION_MISMATCH,
        },
        {
            "stage": "assertion_polarity",
            "passed": (
                not polarity_keys
                or normalize_text(statement.get("assertion_polarity"))
                in polarity_keys
                or bool(polarity_keys & normalized_link_polarities)
            ),
            "query_value": sorted(polarity_keys),
            "statement_value": sorted(
                {
                    normalize_text(statement.get("assertion_polarity")),
                    *normalized_link_polarities,
                }
            ),
            "reason_code": X_POLARITY_MISMATCH,
        },
        {
            "stage": "evidence_scope",
            "passed": _native_match(
                scope_keys, statement.get("evidence_scope")
            ),
            "query_value": list(scope_keys),
            "statement_value": str(statement.get("evidence_scope") or ""),
            "reason_code": X_SCOPE_MISMATCH,
        },
        {
            "stage": "intervention",
            "passed": _native_match(
                intervention_keys, _label(statement.get("intervention"))
            ),
            "query_value": list(intervention_keys),
            "statement_value": _label(statement.get("intervention")),
            "reason_code": X_INTERVENTION_MISMATCH,
        },
    ]
    first_failure = next(
        (stage["stage"] for stage in stages if not stage["passed"]), None
    )
    return {
        "query_id": str(query_payload["query_id"]),
        "case_id": str(query_payload["case_id"]),
        "statement_id": str(statement["evidence_statement_id"]),
        "graph_evidence_ids": _graph_ids(statement),
        "stages": stages,
        "first_failing_stage": first_failure,
        "accepted": first_failure is None,
    }


def _biomarker_diagnostics(
    query_payload: Mapping[str, Any],
    statement: Mapping[str, Any],
    combined_match: bool,
    mappings: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    marker = (query_payload.get("biomarkers") or [{}])[0]
    gene = normalize_text(marker.get("gene") or "")
    alteration = normalize_text(
        marker.get("normalized") or marker.get("alteration") or ""
    )
    biomarker = statement.get("biomarker") or {}
    haystack = normalize_text(
        " ".join(
            [
                str(biomarker.get("gene") or ""),
                str(biomarker.get("label") or ""),
                " ".join(
                    str(item)
                    for item in biomarker.get("component_biomarkers") or []
                ),
                str(statement.get("alteration_type") or ""),
            ]
        )
    )
    relevant_mappings = [
        dict(item)
        for item in mappings
        if str(item.get("statement_id") or "")
        == str(statement["evidence_statement_id"])
        or str(item.get("canonical_source_id") or "")
        in _source_ids(statement)
    ]
    pending = [
        item
        for item in relevant_mappings
        if str(item.get("mapping_status") or "").startswith("requires_")
    ]
    return {
        "query_id": str(query_payload["query_id"]),
        "case_id": str(query_payload["case_id"]),
        "statement_id": str(statement["evidence_statement_id"]),
        "graph_evidence_id": (_graph_ids(statement) or [""])[0],
        "query_gene_normalized": gene,
        "query_alteration_normalized": alteration,
        "statement_biomarker_normalized": haystack,
        "gene_match": bool(gene and gene in haystack),
        "alteration_match": bool(alteration and alteration in haystack)
        if alteration
        else True,
        "combined_native_biomarker_match": combined_match,
        "pending_mapping_count": len(pending),
        "pending_mapping_statuses": sorted(
            {str(item.get("mapping_status") or "") for item in pending}
        ),
        "pending_mapping_promoted": False,
    }


def _nsclc_lexical_gap(query_id: str, statement_disease: str) -> bool:
    return query_id.startswith("PILOT-C1") and normalize_text(
        statement_disease
    ) == "lung non-small cell carcinoma"


def _cause(
    lineage: Mapping[str, Any],
    filter_record: Mapping[str, Any] | None,
) -> tuple[str, list[str], str, str, str, str]:
    if not lineage["statement_present_in_repository"]:
        return (
            "statement_not_materialized",
            [],
            "statement_repository_lookup",
            "adapter_regeneration_required",
            "yes",
            "high",
        )
    if filter_record is None:
        return (
            "graph_evidence_id_mapping_gap",
            [],
            "v3_result_mapping",
            "implementation_bug_fix",
            "yes",
            "low",
        )
    first = filter_record["first_failing_stage"]
    if first == "disease":
        if _nsclc_lexical_gap(
            str(lineage["query_id"]), str(lineage["statement_disease"])
        ):
            return (
                "disease_normalization_gap",
                ["V2_traversal_semantics_not_represented"],
                "native_filter:disease",
                "requires_domain_review",
                "conditional",
                "medium",
            )
        return (
            "V2_traversal_semantics_not_represented",
            ["native_filter_mismatch", "expected_non_equivalence"],
            "native_filter:disease",
            "expected_architectural_difference",
            "no",
            "high",
        )
    mapped = {
        "biomarker": (
            "V2_traversal_semantics_not_represented",
            ["native_filter_mismatch", "expected_non_equivalence"],
        ),
        "direction": ("direction_mapping_gap", []),
        "assertion_polarity": ("assertion_polarity_mapping_gap", []),
        "evidence_scope": ("evidence_scope_mapping_gap", []),
        "intervention": ("intervention_normalization_gap", []),
    }
    primary, secondary = mapped.get(first, ("unresolved_other", []))
    correction = (
        "expected_architectural_difference"
        if primary == "V2_traversal_semantics_not_represented"
        else "requires_domain_review"
    )
    return (
        primary,
        secondary,
        f"native_filter:{first}",
        correction,
        "conditional",
        "medium",
    )


def _identity_sets(
    historical: Sequence[Mapping[str, Any]],
    v3_results: Sequence[Mapping[str, Any]],
    statement_by_graph: Mapping[str, Mapping[str, Any]],
) -> dict[str, tuple[set[str], set[str]]]:
    def historical_statement(row: Mapping[str, Any]) -> Mapping[str, Any]:
        return statement_by_graph.get(str(row["graph_evidence_id"])) or {}

    historical_graph = {
        str(row["graph_evidence_id"]) for row in historical
    }
    v3_graph = {
        graph_id
        for row in v3_results
        for graph_id in row.get("graph_evidence_ids") or []
    }
    historical_statement_ids = {
        str(historical_statement(row).get("evidence_statement_id") or "")
        for row in historical
        if historical_statement(row)
    }
    v3_statement_ids = {str(row["statement_id"]) for row in v3_results}
    historical_sources = {
        str(source)
        for row in historical
        for source in row.get("source_ids") or []
    }
    v3_sources = {
        str(source)
        for row in v3_results
        for source in row.get("source_ids") or []
    }
    historical_therapy = {
        normalize_text(row.get("drug") or "")
        for row in historical
        if normalize_text(row.get("drug") or "")
    }
    v3_therapy = {
        normalize_text(
            (row.get("evaluation_projection") or {}).get("intervention") or ""
        )
        for row in v3_results
        if normalize_text(
            (row.get("evaluation_projection") or {}).get("intervention") or ""
        )
    }
    historical_claims = {
        "|".join(
            [
                normalize_text(row.get("subject") or ""),
                normalize_text(row.get("drug") or ""),
                normalize_text(
                    SIGNIFICANCE_TO_DIRECTION.get(
                        normalize_text(row.get("relation") or ""),
                        normalize_text(row.get("relation") or ""),
                    )
                ),
            ]
        )
        for row in historical
    }
    v3_claims = {
        "|".join(
            [
                normalize_text(
                    (row.get("evaluation_projection") or {}).get("biomarker")
                    or ""
                ),
                normalize_text(
                    (row.get("evaluation_projection") or {}).get("intervention")
                    or ""
                ),
                normalize_text(
                    (row.get("evaluation_projection") or {}).get("direction")
                    or ""
                ),
            ]
        )
        for row in v3_results
    }
    return {
        "graph_evidence_id": (historical_graph, v3_graph),
        "statement": (historical_statement_ids, v3_statement_ids),
        "source": (historical_sources, v3_sources),
        "therapy": (historical_therapy, v3_therapy),
        "biomarker_intervention_direction": (
            historical_claims,
            v3_claims,
        ),
    }


def _coverage_row(
    baseline: set[str], comparison: set[str]
) -> dict[str, Any]:
    overlap = baseline & comparison
    union = baseline | comparison
    return {
        "historical_v2_count": len(baseline),
        "v3_count": len(comparison),
        "overlap_count": len(overlap),
        "missing_count": len(baseline - comparison),
        "extra_count": len(comparison - baseline),
        "historical_coverage": (
            len(overlap) / len(baseline) if baseline else None
        ),
        "jaccard": len(overlap) / len(union) if union else 1.0,
        "denominator": len(baseline),
    }


def _verify_frozen(root: Path) -> dict[str, Any]:
    v3 = root / "benchmarks" / "mtb_evidence" / "v3"
    corpus = _aggregate(root, [v3 / "qualification_corpus_v2"])
    packets = _aggregate(
        root,
        [v3 / "priority_curation" / "annotation_packets" / "second_review"],
    )
    approvals = _aggregate(
        root,
        [
            v3 / "author_approval",
            v3 / "author_approval_22235099",
            v3 / "author_approval_23344087",
        ],
    )
    prior = _aggregate(root, [v3 / "v2_v3a_exploratory_pilot"])
    retriever_files = sorted(
        (root / "backend" / "pipeline" / "evidence").glob(
            "qualified_retriev*"
        ),
        key=lambda path: path.name.casefold(),
    )
    retriever = _aggregate(root, retriever_files)
    frozen_v2_files = sorted(
        (
            root / "benchmarks" / "mtb_evidence" / "pilot" / "audit"
        ).glob("*/normalized_records.jsonl"),
        key=lambda path: path.as_posix().casefold(),
    )
    frozen_v2 = _aggregate(root, frozen_v2_files)
    config = (
        root
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    expected = {
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
        "prior_exploration": (
            prior["aggregate_sha256"],
            EXPECTED_PRIOR_EXPLORATION_HASH,
        ),
        "retriever": (
            retriever["aggregate_sha256"],
            EXPECTED_RETRIEVER_HASH,
        ),
        "frozen_v2_serializations": (
            frozen_v2["aggregate_sha256"],
            EXPECTED_FROZEN_V2_SERIALIZATION_HASH,
        ),
        "scoring_config_file": (_sha(config), EXPECTED_SCORING_FILE_HASH),
    }
    mismatches = {
        name: {"actual": actual, "expected": frozen}
        for name, (actual, frozen) in expected.items()
        if actual != frozen
    }
    if mismatches:
        raise RuntimeError(f"frozen input mismatch: {mismatches}")
    scoring = json.loads(config.read_text(encoding="utf-8"))
    manifest = json.loads(
        (
            v3
            / "qualification_corpus_v2"
            / "qualification_corpus_manifest.json"
        ).read_text(encoding="utf-8")
    )
    if scoring["hash"] != EXPECTED_SCORING_HASH:
        raise RuntimeError("scoring config canonical hash mismatch")
    if (
        manifest["qualification_corpus_fingerprint"]
        != EXPECTED_CORPUS_FINGERPRINT
        or manifest["frozen_kg_snapshot_fingerprint"]
        != EXPECTED_FROZEN_KG_FINGERPRINT
    ):
        raise RuntimeError("corpus or snapshot fingerprint mismatch")
    return {
        "qualification_corpus": corpus,
        "second_review_packets": packets,
        "author_approval": approvals,
        "prior_exploration": prior,
        "retriever": retriever,
        "frozen_v2_serializations": frozen_v2,
        "frozen_v2_results_file": {
            "sha256": _sha(
                v3
                / "v2_v3a_exploratory_pilot"
                / "frozen_v2_results.jsonl"
            ),
            "declared_result_hash": EXPECTED_FROZEN_V2_RESULT_HASH,
        },
        "scoring_config": {
            "file_sha256": _sha(config),
            "canonical_hash": scoring["hash"],
        },
        "corpus_fingerprint": manifest[
            "qualification_corpus_fingerprint"
        ],
        "frozen_kg_fingerprint": manifest[
            "frozen_kg_snapshot_fingerprint"
        ],
    }


def run_no_gold_audit(
    root: Path, output: Path, *, reverse_input_order: bool = False
) -> dict[str, Any]:
    """Genera diagnosi e cause senza accettare o aprire un percorso gold."""
    integrity = _verify_frozen(root)
    frozen = (
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "v2_v3a_exploratory_pilot"
    )
    corpus = (
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "qualification_corpus_v2"
    )
    queries = _read_jsonl(frozen / "evaluation_queries.jsonl")
    historical_rows = _read_jsonl(frozen / "frozen_v2_results.jsonl")
    mode_rows = {
        mode: _read_jsonl(frozen / f"{mode}_results.jsonl") for mode in MODES
    }
    statements = _read_jsonl(corpus / "evidence_statements.jsonl")
    views = _read_jsonl(corpus / "qualified_evidence_views.jsonl")
    links = _read_jsonl(corpus / "qualification_links.jsonl")
    active_units = _read_jsonl(corpus / "active_source_profile_units.jsonl")
    mappings = _read_jsonl(corpus / "terminology_mappings.jsonl")
    if reverse_input_order:
        queries.reverse()
        historical_rows.reverse()
        statements.reverse()
        views.reverse()
        links.reverse()
        active_units.reverse()
        mappings.reverse()
        for rows in mode_rows.values():
            rows.reverse()

    queries_by_id = {str(row["query_id"]): row for row in queries}
    historical_by_id = {
        str(row["query_id"]): row for row in historical_rows
    }
    modes_by_id = {
        mode: {str(row["query_id"]): row for row in rows}
        for mode, rows in mode_rows.items()
    }
    statements_by_id = {
        str(row["evidence_statement_id"]): row for row in statements
    }
    statements_by_graph = {
        graph_id: statement
        for statement in statements
        for graph_id in _graph_ids(statement)
    }
    views_by_id = {str(row["statement_id"]): row for row in views}
    active_ids = {str(row["profile_unit_id"]) for row in active_units}
    links_by_statement: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for link in links:
        links_by_statement[str(link.get("statement_id") or "")].append(link)
    origins = _raw_origins(
        root, [str(row["case_id"]) for row in queries]
    )

    filter_records: list[dict[str, Any]] = []
    normalization_records: list[dict[str, Any]] = []
    filter_by_query_statement: dict[tuple[str, str], dict[str, Any]] = {}
    for query_id in sorted(queries_by_id):
        query = queries_by_id[query_id]
        for statement_id in sorted(statements_by_id):
            statement = statements_by_id[statement_id]
            polarities = [
                str(link.get("assertion_polarity") or "")
                for link in links_by_statement.get(statement_id, [])
            ]
            record = _filter_audit(query, statement, polarities)
            filter_records.append(record)
            filter_by_query_statement[(query_id, statement_id)] = record
            biomarker_stage = record["stages"][0]
            normalization_records.append(
                _biomarker_diagnostics(
                    query,
                    statement,
                    bool(biomarker_stage["passed"]),
                    mappings,
                )
            )

    v2_inventory: list[dict[str, Any]] = []
    lineage: list[dict[str, Any]] = []
    duplicate_counts: dict[tuple[str, str], int] = {}
    first_rank_by_query_graph: dict[tuple[str, str], int] = {}
    for query_id, historical in historical_by_id.items():
        duplicate_counts.update(
            {
                (query_id, graph_id): count
                for graph_id, count in Counter(
                    str(row["graph_evidence_id"])
                    for row in historical["ranked_results"]
                ).items()
            }
        )
        for row in historical["ranked_results"]:
            key = (query_id, str(row["graph_evidence_id"]))
            first_rank_by_query_graph[key] = min(
                first_rank_by_query_graph.get(key, int(row["rank"])),
                int(row["rank"]),
            )

    result_by_mode_query_graph: dict[
        tuple[str, str, str], dict[str, Any]
    ] = {}
    result_by_mode_query_statement: dict[
        tuple[str, str, str], dict[str, Any]
    ] = {}
    v3_inventory: list[dict[str, Any]] = []
    for mode in MODES:
        for query_id in sorted(modes_by_id[mode]):
            row = modes_by_id[mode][query_id]
            for result in row["complete_candidate_results"]:
                statement_id = str(result["statement_id"])
                for graph_id in result.get("graph_evidence_ids") or []:
                    result_by_mode_query_graph[
                        (mode, query_id, str(graph_id))
                    ] = result
                result_by_mode_query_statement[
                    (mode, query_id, statement_id)
                ] = result
                projection = result.get("evaluation_projection") or {}
                v3_inventory.append(
                    {
                        "mode": mode,
                        "query_id": query_id,
                        "case_id": str(
                            queries_by_id[query_id]["case_id"]
                        ),
                        "rank": int(result["rank"]),
                        "statement_id": statement_id,
                        "graph_evidence_ids": sorted(
                            result.get("graph_evidence_ids") or []
                        ),
                        "source_ids": sorted(result.get("source_ids") or []),
                        "disease": str(projection.get("disease") or ""),
                        "biomarker": str(
                            projection.get("biomarker") or ""
                        ),
                        "intervention": str(
                            projection.get("intervention") or ""
                        ),
                        "direction": str(
                            projection.get("direction") or ""
                        ),
                        "evidence_scope": str(
                            projection.get("evidence_scope") or ""
                        ),
                        "assertion_polarity": str(
                            projection.get("assertion_polarity") or ""
                        ),
                        "bucket": str(result.get("bucket") or ""),
                        "warnings": sorted(result.get("warnings") or []),
                    }
                )

    for query_id in sorted(historical_by_id):
        historical = historical_by_id[query_id]
        query = queries_by_id[query_id]
        case_id = str(query["case_id"])
        for record in sorted(
            historical["ranked_results"], key=lambda item: int(item["rank"])
        ):
            graph_id = str(record["graph_evidence_id"])
            statement = statements_by_graph.get(graph_id)
            statement_id = (
                str(statement["evidence_statement_id"]) if statement else ""
            )
            projection = _statement_projection(statement) if statement else {}
            entry = {
                "lineage_id": f"{query_id}::v2-rank-{int(record['rank']):04d}",
                "query_id": query_id,
                "case_id": case_id,
                "v2_rank": int(record["rank"]),
                "v2_traversal_origins": origins.get(graph_id, []),
                "graph_evidence_id": graph_id,
                "source_ids": sorted(record.get("source_ids") or []),
                "disease": str(record.get("disease") or ""),
                "gene": str(
                    (query.get("biomarkers") or [{}])[0].get("gene") or ""
                ),
                "alteration": str(record.get("subject") or ""),
                "intervention": str(record.get("drug") or ""),
                "direction": str(record.get("relation") or ""),
                "evidence_scope": str(record.get("source_kind") or ""),
                "assertion_polarity": str(record.get("direction") or ""),
                "statement_id": statement_id or None,
                "statement_present_in_repository": bool(statement),
                "statement_present_in_corpus": bool(statement_id in views_by_id),
                "statement_present_in_v3_indices": bool(
                    statement_id in views_by_id
                ),
                "active_profile_unit_ids": sorted(
                    {
                        str(link.get("source_profile_unit_id") or "")
                        for link in links_by_statement.get(statement_id, [])
                        if str(link.get("source_profile_unit_id") or "")
                        in active_ids
                    }
                ),
                "duplicate_group_size": duplicate_counts.get(
                    (query_id, graph_id), 1
                ),
                "duplicate_ordinal": (
                    int(record["rank"])
                    - first_rank_by_query_graph[(query_id, graph_id)]
                    + 1
                ),
                "statement_disease": projection.get("disease"),
                "statement_biomarker": projection.get("biomarker"),
                "statement_intervention": projection.get("intervention"),
                "v3_membership": {
                    mode: (
                        (mode, query_id, graph_id)
                        in result_by_mode_query_graph
                    )
                    for mode in MODES
                },
            }
            filter_record = (
                filter_by_query_statement.get((query_id, statement_id))
                if statement_id
                else None
            )
            entry["normalization"] = (
                {
                    "query_disease": sorted(
                        build_query(query).disease_keys()
                    ),
                    "statement_disease": normalize_text(
                        projection.get("disease") or ""
                    ),
                    "query_biomarker": sorted(
                        build_query(query).biomarker_keys()
                    ),
                    "statement_biomarker": normalize_text(
                        projection.get("biomarker") or ""
                    ),
                }
                if statement
                else {}
            )
            entry["native_filter_results"] = (
                filter_record["stages"] if filter_record else []
            )
            qualified = result_by_mode_query_graph.get(
                ("qualified_soft", query_id, graph_id)
            )
            if not statement:
                entry["final_category"] = (
                    "absent_before_candidate_generation"
                )
                entry["lineage_outcome"] = "not_materialized"
            elif not qualified:
                entry["final_category"] = "rejected_by_native_constraints"
                entry["lineage_outcome"] = "excluded"
            else:
                entry["final_category"] = FINAL_CATEGORIES.get(
                    str(qualified.get("bucket") or ""), "ranked"
                )
                intervention_changed = normalize_text(
                    record.get("drug") or ""
                ) != normalize_text(projection.get("intervention") or "")
                if intervention_changed:
                    entry["lineage_outcome"] = "transformed"
                elif entry["duplicate_group_size"] > 1:
                    entry["lineage_outcome"] = "deduplicated"
                else:
                    entry["lineage_outcome"] = "survives"
            lineage.append(entry)
            v2_inventory.append(
                {
                    key: entry[key]
                    for key in (
                        "lineage_id",
                        "query_id",
                        "case_id",
                        "v2_rank",
                        "v2_traversal_origins",
                        "graph_evidence_id",
                        "source_ids",
                        "disease",
                        "gene",
                        "alteration",
                        "intervention",
                        "direction",
                        "evidence_scope",
                        "assertion_polarity",
                        "duplicate_group_size",
                    )
                }
            )

    missing: list[dict[str, Any]] = []
    for row in lineage:
        if row["final_category"] not in {
            "rejected_by_native_constraints",
            "absent_before_candidate_generation",
        }:
            continue
        filter_record = (
            filter_by_query_statement.get(
                (str(row["query_id"]), str(row["statement_id"]))
            )
            if row["statement_id"]
            else None
        )
        (
            primary,
            secondary,
            stage,
            correction,
            correctable,
            risk,
        ) = _cause(row, filter_record)
        if primary not in PRIMARY_CAUSES:
            raise AssertionError(primary)
        secondary = list(secondary)
        if row["duplicate_ordinal"] > 1:
            secondary.append("duplicate_canonicalization")
        if normalize_text(row["intervention"] or "") != normalize_text(
            row["statement_intervention"] or ""
        ):
            secondary.append("adapter_conversion_loss")
        missing.append(
            {
                "lineage_id": row["lineage_id"],
                "query_id": row["query_id"],
                "case_id": row["case_id"],
                "v2_rank": row["v2_rank"],
                "graph_evidence_id": row["graph_evidence_id"],
                "statement_id": row["statement_id"],
                "source_ids": row["source_ids"],
                "primary_cause": primary,
                "secondary_causes": sorted(set(secondary)),
                "first_divergence_stage": stage,
                "correction_class": correction,
                "correction_possible": correctable,
                "false_positive_risk": risk,
                "cause_evidence": {
                    "gold_used": False,
                    "historical_file": (
                        f"benchmarks/mtb_evidence/pilot/audit/"
                        f"{row['case_id']}/normalized_records.jsonl"
                    ),
                    "statement_file": (
                        "benchmarks/mtb_evidence/v3/"
                        "qualification_corpus_v2/evidence_statements.jsonl"
                    ),
                    "filter_record": (
                        {
                            "first_failing_stage": filter_record[
                                "first_failing_stage"
                            ],
                            "stages": filter_record["stages"],
                        }
                        if filter_record
                        else None
                    ),
                },
            }
        )

    extra: list[dict[str, Any]] = []
    normalization_by_query_graph = {
        (row["query_id"], row["graph_evidence_id"]): row
        for row in normalization_records
    }
    for query_id in sorted(queries_by_id):
        historical_graph = {
            str(row["graph_evidence_id"])
            for row in historical_by_id[query_id]["ranked_results"]
        }
        results = modes_by_id["qualified_soft"][query_id][
            "complete_candidate_results"
        ]
        for result in results:
            for graph_id in sorted(result.get("graph_evidence_ids") or []):
                if graph_id in historical_graph:
                    continue
                diagnostic = normalization_by_query_graph[
                    (query_id, graph_id)
                ]
                classification = (
                    "normalization_overreach"
                    if diagnostic["gene_match"]
                    and not diagnostic["alteration_match"]
                    and diagnostic["combined_native_biomarker_match"]
                    else "V2_traversal_coverage_gap"
                )
                extra.append(
                    {
                        "query_id": query_id,
                        "case_id": queries_by_id[query_id]["case_id"],
                        "graph_evidence_id": graph_id,
                        "statement_id": result["statement_id"],
                        "source_ids": sorted(result.get("source_ids") or []),
                        "rank": result["rank"],
                        "classification": classification,
                        "reason": (
                            "il matcher nativo accetta uno qualunque fra "
                            "gene e alterazione; il gene coincide ma "
                            "l'alterazione richiesta no"
                            if classification == "normalization_overreach"
                            else "statement materializzato non serializzato "
                            "dal traversal storico della query"
                        ),
                        "v2_traversal_origins": origins.get(graph_id, []),
                        "evidence_context": result.get("evidence_context"),
                        "duplicate_representation": False,
                        "query_contract_compatible": (
                            classification != "normalization_overreach"
                        ),
                        "gold_used_for_classification": False,
                    }
                )

    per_query: list[dict[str, Any]] = []
    identity_coverage: list[dict[str, Any]] = []
    for query_id in sorted(queries_by_id):
        historical = historical_by_id[query_id]["ranked_results"]
        counts = {
            "historical_v2_records": len(historical),
            "historical_v2_unique_graph_evidence": len(
                {row["graph_evidence_id"] for row in historical}
            ),
            **{
                mode: int(modes_by_id[mode][query_id]["candidate_count"])
                for mode in MODES
            },
        }
        query_lineage = [
            row for row in lineage if row["query_id"] == query_id
        ]
        per_query.append(
            {
                "query_id": query_id,
                "case_id": queries_by_id[query_id]["case_id"],
                "candidate_counts": counts,
                "lineage_outcomes": dict(
                    sorted(
                        Counter(
                            row["lineage_outcome"] for row in query_lineage
                        ).items()
                    )
                ),
                "missing_v2_records": sum(
                    row["final_category"]
                    == "rejected_by_native_constraints"
                    for row in query_lineage
                ),
                "duplicate_record_surplus": sum(
                    max(count - 1, 0)
                    for (item_query, _), count in duplicate_counts.items()
                    if item_query == query_id
                ),
                "adapter_intervention_conversion_losses": sum(
                    normalize_text(row["intervention"] or "")
                    != normalize_text(row["statement_intervention"] or "")
                    for row in query_lineage
                ),
                "v3_extra_graph_evidence": sum(
                    row["query_id"] == query_id for row in extra
                ),
                "zero_case_classification": (
                    "true_no_evidence_in_snapshot"
                    if counts["historical_v2_records"] == 0
                    and counts["qualified_soft"] == 0
                    else None
                ),
            }
        )
        for mode in MODES:
            v3_results = modes_by_id[mode][query_id][
                "complete_candidate_results"
            ]
            for level, (baseline, comparison) in _identity_sets(
                historical, v3_results, statements_by_graph
            ).items():
                identity_coverage.append(
                    {
                        "query_id": query_id,
                        "case_id": queries_by_id[query_id]["case_id"],
                        "mode": mode,
                        "identity_level": level,
                        **_coverage_row(baseline, comparison),
                    }
                )

    primary_counts = Counter(row["primary_cause"] for row in missing)
    secondary_counts = Counter(
        cause for row in missing for cause in row["secondary_causes"]
    )
    unique_primary: dict[str, set[str]] = defaultdict(set)
    for row in missing:
        unique_primary[row["primary_cause"]].add(
            f"{row['query_id']}::{row['graph_evidence_id']}"
        )
    root_causes = {
        "audit_version": AUDIT_VERSION,
        "gold_used": False,
        "missing_record_count": len(missing),
        "missing_unique_query_graph_count": len(
            {
                (row["query_id"], row["graph_evidence_id"])
                for row in missing
            }
        ),
        "primary_cause_record_counts": dict(sorted(primary_counts.items())),
        "primary_cause_unique_query_graph_counts": {
            key: len(value) for key, value in sorted(unique_primary.items())
        },
        "secondary_cause_record_counts": dict(
            sorted(secondary_counts.items())
        ),
        "all_missing_have_one_primary_cause": all(
            bool(row["primary_cause"]) for row in missing
        ),
        "root_causes_identified": not any(
            row["primary_cause"] == "unresolved_other" for row in missing
        ),
    }
    proposals = [
        {
            "proposal_id": "CCR-001",
            "trigger": "gene-only acceptance with requested alteration",
            "classification": "implementation_bug_fix",
            "demonstrable_without_gold": True,
            "implemented": False,
            "recommendation": (
                "require the requested gene and requested alteration as "
                "separate conjunctive native dimensions"
            ),
            "risk_of_false_positives": "decreases",
            "semantic_review_required": False,
        },
        {
            "proposal_id": "CCR-002",
            "trigger": (
                "Lung Non-small Cell Carcinoma versus configured NSCLC aliases"
            ),
            "classification": "requires_domain_review",
            "demonstrable_without_gold": True,
            "implemented": False,
            "recommendation": (
                "review a versioned disease terminology mapping; do not add "
                "a runtime synonym ad hoc"
            ),
            "risk_of_false_positives": "medium",
            "semantic_review_required": True,
        },
        {
            "proposal_id": "CCR-003",
            "trigger": "one graph record serialized once per targeted drug",
            "classification": "adapter_regeneration_required",
            "demonstrable_without_gold": True,
            "implemented": False,
            "recommendation": (
                "represent all interventions losslessly or materialize one "
                "statement per intervention under a versioned adapter"
            ),
            "risk_of_false_positives": "low",
            "semantic_review_required": False,
        },
        {
            "proposal_id": "CCR-004",
            "trigger": (
                "historical drug/source traversals include other genes or "
                "diseases"
            ),
            "classification": "expected_architectural_difference",
            "demonstrable_without_gold": True,
            "implemented": False,
            "recommendation": (
                "preserve as audit semantics; do not weaken native filters to "
                "force row-count parity"
            ),
            "risk_of_false_positives": "high if forced",
            "semantic_review_required": False,
        },
        {
            "proposal_id": "CCR-005",
            "trigger": (
                "intrahepatic cholangiocarcinoma versus broader or distinct "
                "biliary labels"
            ),
            "classification": "should_not_fix",
            "demonstrable_without_gold": True,
            "implemented": False,
            "recommendation": (
                "retain the documented non-equivalence until a reviewed "
                "ontology relation is available"
            ),
            "risk_of_false_positives": "high",
            "semantic_review_required": True,
        },
    ]

    output.mkdir(parents=True, exist_ok=True)
    ordered_v2 = sorted(v2_inventory, key=lambda row: row["lineage_id"])
    ordered_v3 = sorted(
        v3_inventory,
        key=lambda row: (
            row["mode"],
            row["query_id"],
            row["rank"],
            row["statement_id"],
        ),
    )
    ordered_lineage = sorted(lineage, key=lambda row: row["lineage_id"])
    ordered_missing = sorted(missing, key=lambda row: row["lineage_id"])
    ordered_extra = sorted(
        extra,
        key=lambda row: (
            row["query_id"],
            row["rank"],
            row["statement_id"],
        ),
    )
    ordered_filters = sorted(
        filter_records,
        key=lambda row: (row["query_id"], row["statement_id"]),
    )
    ordered_normalization = sorted(
        normalization_records,
        key=lambda row: (row["query_id"], row["statement_id"]),
    )
    _write_jsonl(output / "v2_candidate_inventory.jsonl", ordered_v2)
    _write_jsonl(output / "v3_candidate_inventory.jsonl", ordered_v3)
    _write_jsonl(output / "candidate_lineage.jsonl", ordered_lineage)
    _write_jsonl(output / "missing_v2_candidates.jsonl", ordered_missing)
    _write_jsonl(output / "extra_v3_candidates.jsonl", ordered_extra)
    _write_json(
        output / "per_query_coverage.json",
        {"audit_version": AUDIT_VERSION, "queries": per_query},
    )
    _write_json(
        output / "coverage_by_identity_level.json",
        {
            "audit_version": AUDIT_VERSION,
            "gold_used": False,
            "records": identity_coverage,
        },
    )
    _write_json(output / "root_cause_counts.json", root_causes)
    _write_jsonl(
        output / "normalization_audit.jsonl", ordered_normalization
    )
    _write_jsonl(output / "filter_stage_audit.jsonl", ordered_filters)
    _write_jsonl(output / "proposed_corrections.jsonl", proposals)

    data_names = (
        "v2_candidate_inventory.jsonl",
        "v3_candidate_inventory.jsonl",
        "candidate_lineage.jsonl",
        "missing_v2_candidates.jsonl",
        "extra_v3_candidates.jsonl",
        "per_query_coverage.json",
        "coverage_by_identity_level.json",
        "root_cause_counts.json",
        "normalization_audit.jsonl",
        "filter_stage_audit.jsonl",
        "proposed_corrections.jsonl",
    )
    manifest = {
        "audit_version": AUDIT_VERSION,
        "branch": "eval/v3-candidate-coverage-audit",
        "source_sha": SOURCE_SHA,
        "corpus_version": "qualification_corpus/2.0",
        "corpus_fingerprint": integrity["corpus_fingerprint"],
        "frozen_kg_fingerprint": integrity["frozen_kg_fingerprint"],
        "scoring_config_hash": EXPECTED_SCORING_HASH,
        "gold_accessed_by_root_cause_audit": False,
        "gold_hash_declared_but_not_loaded": EXPECTED_GOLD_HASH,
        "previous_exploration_immutable": True,
        "retriever_modified": False,
        "corpus_modified": False,
        "scoring_modified": False,
        "external_services_used": [],
        "input_integrity": integrity,
        "artifact_hashes": {
            name: _sha(output / name) for name in data_names
        },
    }
    _write_json(output / "audit_manifest.json", manifest)
    return manifest


def annotate_gold_records(
    root: Path,
    output: Path,
    gold_bundle: Path,
    *,
    expected_gold_hash: str,
) -> list[dict[str, Any]]:
    """Annota i cinque ID solo dopo che diagnosi e hash sono già congelati."""
    if expected_gold_hash != EXPECTED_GOLD_HASH:
        raise RuntimeError("unexpected gold aggregate identity")
    member_hashes = {
        name: _sha(gold_bundle / name) for name in sorted(EXPECTED_GOLD_FILES)
    }
    if member_hashes != dict(sorted(EXPECTED_GOLD_FILES.items())):
        raise RuntimeError("gold member hash mismatch")
    if not (output / "audit_manifest.json").exists():
        raise RuntimeError("run_no_gold_audit must complete before gold access")
    causes_before = _sha(output / "root_cause_counts.json")
    missing = _read_jsonl(output / "missing_v2_candidates.jsonl")
    missing_by_graph = {
        str(row["graph_evidence_id"]): row for row in missing
    }
    statements = _read_jsonl(
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "qualification_corpus_v2"
        / "evidence_statements.jsonl"
    )
    statements_by_graph = {
        graph_id: statement
        for statement in statements
        for graph_id in _graph_ids(statement)
    }
    frozen_v2 = _read_jsonl(
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "v2_v3a_exploratory_pilot"
        / "frozen_v2_results.jsonl"
    )
    historical_presence = {
        str(result["graph_evidence_id"]): str(row["query_id"])
        for row in frozen_v2
        for result in row["ranked_results"]
    }
    gold_rows = _read_jsonl(
        gold_bundle / "mtb_evidence_gold_pilot_v1.jsonl"
    )
    claims = [
        claim
        for row in gold_rows
        for claim in row.get("claims") or []
    ]
    output_rows: list[dict[str, Any]] = []
    for graph_id in GOLD_EVIDENCE_IDS:
        statement = statements_by_graph.get(graph_id)
        projection = _statement_projection(statement) if statement else {}
        source_values = {
            source.removeprefix("PUBMED:")
            for source in projection.get("source_ids") or []
        }
        matching_claims = sorted(
            str(claim.get("claim_id") or "")
            for claim in claims
            if str(claim.get("pmid") or "") in source_values
            and (
                not claim.get("object")
                or normalize_text(claim.get("object"))
                == normalize_text(projection.get("intervention"))
            )
        )
        missing_row = missing_by_graph.get(graph_id)
        output_rows.append(
            {
                "graph_evidence_id": graph_id,
                "present_in_frozen_v2": graph_id in historical_presence,
                "historical_query_id": historical_presence.get(graph_id),
                "present_in_serialized_snapshot": bool(statement),
                "serialized_snapshot_evidence": (
                    {
                        "origin": (statement.get("provenance") or {}).get(
                            "origin"
                        ),
                        "snapshot_fingerprint": (
                            statement.get("provenance") or {}
                        ).get("snapshot_fingerprint"),
                    }
                    if statement
                    else None
                ),
                "present_in_statement_repository": bool(statement),
                "statement_id": projection.get("statement_id"),
                "present_in_corpus": bool(statement),
                "present_in_v3_indices": bool(statement),
                "native_filter_applied": (
                    missing_row.get("first_divergence_stage")
                    if missing_row
                    else None
                ),
                "absence_reason": (
                    missing_row.get("primary_cause")
                    if missing_row
                    else "not_missing_for_historical_query"
                ),
                "loss_classification": (
                    "difference_semantica"
                    if missing_row
                    and missing_row.get("primary_cause")
                    == "V2_traversal_semantics_not_represented"
                    else "limite_di_schema"
                    if missing_row
                    and missing_row.get("primary_cause")
                    == "disease_normalization_gap"
                    else "deduplicazione_attesa"
                    if missing_row
                    and missing_row.get("primary_cause")
                    == "duplicate_canonicalization"
                    else "dato_assente"
                    if not statement
                    else "bug"
                    if missing_row
                    and missing_row.get("correction_class")
                    == "implementation_bug_fix"
                    else "differenza_semantica"
                ),
                "matching_gold_claim_ids": matching_claims,
                "cause_assigned_before_gold_access": True,
                "gold_changed_cause": False,
                "gold_bundle_hash": expected_gold_hash,
                "gold_member_hashes": member_hashes,
            }
        )
    _write_jsonl(
        output / "gold_missing_candidate_audit.jsonl", output_rows
    )
    if _sha(output / "root_cause_counts.json") != causes_before:
        raise RuntimeError("gold access changed root causes")
    manifest_path = output / "audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["gold_annotation"] = {
        "accessed_after_root_cause_freeze": True,
        "aggregate_identity": expected_gold_hash,
        "member_hashes": member_hashes,
        "root_cause_hash_before_and_after": causes_before,
        "root_causes_unchanged": True,
        "record_count": len(output_rows),
        "artifact_sha256": _sha(
            output / "gold_missing_candidate_audit.jsonl"
        ),
    }
    _write_json(manifest_path, manifest)
    return output_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gold-bundle", type=Path)
    parser.add_argument("--reverse-input-order", action="store_true")
    args = parser.parse_args()
    run_no_gold_audit(
        args.root,
        args.output,
        reverse_input_order=args.reverse_input_order,
    )
    if args.gold_bundle:
        annotate_gold_records(
            args.root,
            args.output,
            args.gold_bundle,
            expected_gold_hash=EXPECTED_GOLD_HASH,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
