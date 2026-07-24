"""Confronto esplorativo offline V2/V3-A con separazione fisica dal gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from backend.pipeline.evidence._normalize import normalize_text
from backend.pipeline.evidence.qualified_retrieval_query import (
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import (
    SUPPORTED_CORPUS_VERSION,
    QualifiedEvidenceRetriever,
)
from backend.pipeline.evidence.qualified_retrieval_errors import UnsupportedCorpusVersionError
from backend.pipeline.evidence.qualified_retrieval_scoring import ScoringConfig
from backend.pipeline.evidence.repository import EvidenceStatementRepository


MODES = ("v2_compatibility", "native_only", "qualified_soft")
TOP_KS = (1, 3, 5, 10)
METRIC_CONTRACT_VERSION = "v2-v3a-exploratory/1.0"
EXPECTED_SCORING_HASH = (
    "ddbfe3cec5d79f0f321b6a853938aa074e55f9ab77149fc73f2ce17224908c00"
)
EXPECTED_CORPUS_FINGERPRINT = (
    "99a1a575a813676bb3d2658a3ab103cf396755f4b0cdbd9a8c26f09ea6c77ffd"
)
EXPECTED_FROZEN_KG_FINGERPRINT = (
    "ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae"
)
EXPECTED_GOLD_FILES = {
    "MTB_Evidence_annotation_notes_v1.md": (
        "72ee84c53bfb5d6634f238a771d6b52b1a8f03bfe36b4ab3e577932be7b72520"
    ),
    "mtb_evidence_gold_pilot_v1.jsonl": (
        "30e64dc5f3dffde3d1d43c316f6bc75f1afafab41567fa8657214a10fa16c667"
    ),
    "MTB_Evidence_gold_pilot_v1.xlsx": (
        "128a68c5aa324ef8a4f033d2a2721c251583b9ac0a8d83d6b603ba1aad662124"
    ),
}

# Contratto dichiarato e congelato prima di osservare gli outcome.
IMPACT_THRESHOLDS: dict[str, Any] = {
    "version": "qualifier-impact/1.0",
    "no_measurable": {"maximum_changes": 0},
    "limited": {"maximum_affected_fraction": 0.10},
    "moderate": {"maximum_affected_fraction": 0.30},
    "substantial": {"minimum_affected_fraction_exclusive": 0.30},
    "rule": (
        "affected_fraction=unique_affected_query_candidates/"
        "max(candidate_universe,1)"
    ),
}


class BlindRetrievalComplete(RuntimeError):
    """Il valutatore richiede risultati ciechi già congelati."""


class GoldAccessViolation(RuntimeError):
    """Accesso al gold non conforme al contratto a due passaggi."""


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Iterable[Any]) -> bytes:
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_json(path: Path, payload: Any) -> None:
    path.write_bytes(_json_bytes(payload))


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.write_bytes(_jsonl_bytes(rows))


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha(path: Path) -> str:
    return _sha_bytes(path.read_bytes())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _query(payload: Mapping[str, Any], mode: str) -> QualifiedRetrievalQuery:
    return QualifiedRetrievalQuery(
        query_id=str(payload["query_id"]),
        case_id=str(payload["case_id"]),
        disease=str(payload["disease"]),
        disease_aliases=tuple(payload.get("disease_aliases") or ()),
        biomarkers=tuple(
            QueryBiomarker(**item) for item in payload.get("biomarkers") or ()
        ),
        interventions=tuple(payload.get("interventions") or ()),
        directions=tuple(payload.get("directions") or ()),
        assertion_polarities=tuple(payload.get("assertion_polarities") or ()),
        evidence_scopes=tuple(payload.get("evidence_scopes") or ()),
        preferred_evidence_context=str(
            payload.get("preferred_evidence_context") or "both"
        ),
        clinical_context=dict(payload.get("clinical_context") or {}),
        top_k=int(payload.get("top_k") or 20),
        mode=mode,
        corpus_fingerprint=str(payload.get("corpus_fingerprint") or ""),
    )


def _statement_projection(statement: Mapping[str, Any]) -> dict[str, Any]:
    def label(value: Any) -> str:
        return (
            str(value.get("label") or "")
            if isinstance(value, Mapping)
            else str(value or "")
        )

    refs = list(statement.get("source_references") or []) + list(
        statement.get("trial_references") or []
    )
    return {
        "statement_id": str(statement.get("evidence_statement_id") or ""),
        "graph_evidence_ids": sorted(
            (statement.get("provenance") or {}).get("graph_record_ids") or []
        ),
        "disease": label(statement.get("disease")),
        "biomarker": label(statement.get("biomarker")),
        "intervention": label(statement.get("intervention")),
        "direction": str(statement.get("direction") or ""),
        "assertion_polarity": str(statement.get("assertion_polarity") or ""),
        "evidence_scope": str(statement.get("evidence_scope") or ""),
        "source_ids": sorted(
            {
                str(ref.get("source_id") or ref.get("external_identifier") or "")
                for ref in refs
                if ref.get("source_id") or ref.get("external_identifier")
            }
        ),
    }


def _enrich_v3(
    serialized: dict[str, Any], projections: Mapping[str, dict[str, Any]]
) -> dict[str, Any]:
    enriched = json.loads(json.dumps(serialized))
    for bucket in (
        "ranked_results",
        "retained_with_warning",
        "audit_only_results",
    ):
        for result in enriched[bucket]:
            result["evaluation_projection"] = projections[result["statement_id"]]
    return enriched


def _complete_candidates(
    scored: Sequence[Any], projections: Mapping[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rank, result in enumerate(scored, 1):
        item = result.as_dict()
        item["rank"] = rank
        item["evaluation_projection"] = projections[item["statement_id"]]
        rows.append(item)
    return rows


def _historical_v2(root: Path, queries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for query in queries:
        case_id = str(query["case_id"])
        path = (
            root
            / "benchmarks"
            / "mtb_evidence"
            / "pilot"
            / "audit"
            / case_id
            / "normalized_records.jsonl"
        )
        records = _read_jsonl(path)
        ranked = [
            {
                **record,
                "rank": index,
                "graph_evidence_id": str(record.get("record_id") or ""),
                "source_ids": [
                    *[f"PUBMED:{value}" for value in record.get("pmids") or []],
                    *[str(value) for value in record.get("nct_ids") or []],
                ],
            }
            for index, record in enumerate(records, 1)
        ]
        manifest_path = path.with_name("query_manifest.json")
        rows.append(
            {
                "query_id": query["query_id"],
                "case_id": case_id,
                "baseline_kind": "historical_v2_frozen_serialization",
                "serialized_order_is_rank": True,
                "score_available": False,
                "source_path": (
                    f"benchmarks/mtb_evidence/pilot/audit/{case_id}/"
                    "normalized_records.jsonl"
                ),
                "source_sha256": _sha(path),
                "query_manifest_sha256": _sha(manifest_path),
                "candidate_count": len(ranked),
                "ranked_results": ranked,
            }
        )
    return rows


def _runtime_stats(values: Sequence[float]) -> dict[str, Any]:
    return {
        "unit": "milliseconds",
        "run_count": len(values),
        "minimum": round(min(values), 6),
        "median": round(statistics.median(values), 6),
        "maximum": round(max(values), 6),
    }


def _load_corpus_snapshot(corpus: Path, config: Path) -> dict[str, Any]:
    manifest = json.loads(
        (corpus / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("corpus_version") != SUPPORTED_CORPUS_VERSION:
        raise UnsupportedCorpusVersionError(str(manifest.get("corpus_version")))
    return {
        "manifest": manifest,
        "statements": _read_jsonl(corpus / "evidence_statements.jsonl"),
        "views": _read_jsonl(corpus / "qualified_evidence_views.jsonl"),
        "active_units": _read_jsonl(corpus / "active_source_profile_units.jsonl"),
        "historical_units": _read_jsonl(corpus / "historical_source_profile_units.jsonl"),
        "links": _read_jsonl(corpus / "qualification_links.jsonl"),
        "qualification_gold": _read_jsonl(corpus / "statement_qualification_gold.jsonl"),
        "terminology_mappings": _read_jsonl(corpus / "terminology_mappings.jsonl"),
        "scoring_config": ScoringConfig.load(config),
    }


def _build_retriever_from_snapshot(
    corpus: Path, snapshot: Mapping[str, Any]
) -> QualifiedEvidenceRetriever:
    manifest = snapshot["manifest"]
    return QualifiedEvidenceRetriever(
        corpus_dir=corpus,
        manifest=manifest,
        repository=EvidenceStatementRepository(
            snapshot["statements"],
            created_at=str(manifest.get("generated_at") or ""),
        ),
        views={item["statement_id"]: item for item in snapshot["views"]},
        active_units={item["profile_unit_id"]: item for item in snapshot["active_units"]},
        historical_units={item["profile_unit_id"]: item for item in snapshot["historical_units"]},
        links=snapshot["links"],
        qualification_gold=snapshot["qualification_gold"],
        terminology_mappings=snapshot["terminology_mappings"],
        scoring_config=snapshot["scoring_config"],
    )

def run_blind_retrieval(
    root: Path, output: Path, *, run_count: int = 5
) -> dict[str, Any]:
    """Passaggio A. Non accetta né apre alcun percorso gold."""
    if run_count < 2:
        raise ValueError("run_count deve essere almeno 2")
    corpus = (
        root / "benchmarks" / "mtb_evidence" / "v3" / "qualification_corpus_v2"
    )
    config = (
        root
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    query_fixture = (
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "qualified_retriever_prototype"
        / "queries.jsonl"
    )
    queries = sorted(_read_jsonl(query_fixture), key=lambda row: row["query_id"])
    output.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output / "evaluation_queries.jsonl", queries)

    load_samples: list[float] = []
    index_samples: list[float] = []
    retrieval_samples: dict[str, list[float]] = {mode: [] for mode in MODES}
    retriever: QualifiedEvidenceRetriever | None = None
    for _ in range(run_count):
        started = time.perf_counter_ns()
        snapshot = _load_corpus_snapshot(corpus, config)
        load_samples.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        candidate = _build_retriever_from_snapshot(corpus, snapshot)
        index_samples.append((time.perf_counter_ns() - started) / 1_000_000)
        if retriever is None:
            retriever = candidate
    assert retriever is not None
    validation = retriever.validate_corpus()
    if (
        validation["qualification_corpus_fingerprint"]
        != EXPECTED_CORPUS_FINGERPRINT
        or validation["frozen_kg_snapshot_fingerprint"]
        != EXPECTED_FROZEN_KG_FINGERPRINT
        or retriever.get_scoring_config_hash() != EXPECTED_SCORING_HASH
    ):
        raise GoldAccessViolation("corpus o scoring config non coincidono col freeze")

    projections = {
        row["evidence_statement_id"]: _statement_projection(row)
        for row in retriever.repository.all()
    }
    mode_rows: dict[str, list[dict[str, Any]]] = {}
    phase_samples: dict[str, dict[str, list[float]]] = {
        mode: {
            "candidate_generation": [],
            "scoring": [],
            "ranking": [],
            "explanation": [],
        }
        for mode in MODES
    }
    for mode in MODES:
        frozen: list[dict[str, Any]] | None = None
        for _ in range(run_count):
            current: list[dict[str, Any]] = []
            started_total = time.perf_counter_ns()
            for payload in queries:
                query = _query(payload, mode)
                started = time.perf_counter_ns()
                candidates, _ = retriever._candidates(query)
                phase_samples[mode]["candidate_generation"].append(
                    (time.perf_counter_ns() - started) / 1_000_000
                )
                started = time.perf_counter_ns()
                scored = [retriever._result(query, item) for item in candidates]
                phase_samples[mode]["scoring"].append(
                    (time.perf_counter_ns() - started) / 1_000_000
                )
                started = time.perf_counter_ns()
                scored.sort(key=lambda item: retriever._sort_key(query, item))
                phase_samples[mode]["ranking"].append(
                    (time.perf_counter_ns() - started) / 1_000_000
                )
                started = time.perf_counter_ns()
                for item in scored:
                    retriever.explain(item)
                phase_samples[mode]["explanation"].append(
                    (time.perf_counter_ns() - started) / 1_000_000
                )
                serialized = _enrich_v3(
                    retriever.retrieve(query).as_dict(), projections
                )
                serialized["complete_candidate_results"] = _complete_candidates(
                    scored, projections
                )
                serialized["complete_candidate_count"] = len(scored)
                current.append(serialized)
            retrieval_samples[mode].append(
                (time.perf_counter_ns() - started_total) / 1_000_000
            )
            if frozen is None:
                frozen = current
            elif _jsonl_bytes(frozen) != _jsonl_bytes(current):
                raise RuntimeError(f"risultati non deterministici: {mode}")
        assert frozen is not None
        mode_rows[mode] = frozen
        _write_jsonl(output / f"{mode}_results.jsonl", frozen)

    historical = _historical_v2(root, queries)
    _write_jsonl(output / "frozen_v2_results.jsonl", historical)
    result_paths = {
        "frozen_v2": output / "frozen_v2_results.jsonl",
        **{mode: output / f"{mode}_results.jsonl" for mode in MODES},
    }
    hashes = {
        "phase": "blind_retrieval_complete",
        "gold_loaded": False,
        "scoring_config_hash_before_retrieval": retriever.get_scoring_config_hash(),
        "query_set_hash": _sha(output / "evaluation_queries.jsonl"),
        "results": {name: _sha(path) for name, path in sorted(result_paths.items())},
    }
    _write_json(output / "retrieval_result_hashes.json", hashes)
    _write_json(
        output / "runtime_metrics.json",
        {
            "environment_comparison": "not_equivalent_to_historical_agentic_pipeline",
            "load_corpus": _runtime_stats(load_samples),
            "build_index": _runtime_stats(index_samples),
            "modes": {
                mode: {
                    "candidate_generation": _runtime_stats(
                        phase_samples[mode]["candidate_generation"]
                    ),
                    "scoring": _runtime_stats(phase_samples[mode]["scoring"]),
                    "ranking": _runtime_stats(phase_samples[mode]["ranking"]),
                    "explanation": _runtime_stats(
                        phase_samples[mode]["explanation"]
                    ),
                    "total_retrieval": _runtime_stats(retrieval_samples[mode]),
                }
                for mode in MODES
            },
        },
    )
    return hashes


def compute_binary_ranking_metrics(
    ranked_ids: Sequence[str], relevant_ids: set[str], top_ks: Sequence[int] = TOP_KS
) -> dict[str, Any]:
    first = next(
        (index for index, item in enumerate(ranked_ids, 1) if item in relevant_ids),
        None,
    )
    found_ranks = [
        index for index, item in enumerate(ranked_ids, 1) if item in relevant_ids
    ]
    return {
        "relevant_denominator": len(relevant_ids),
        "retrieved_denominator_at_k": {
            str(k): min(k, len(ranked_ids)) for k in top_ks
        },
        "precision_at_k": {
            str(k): (
                len(set(ranked_ids[:k]) & relevant_ids) / min(k, len(ranked_ids))
                if ranked_ids[:k]
                else 0.0
            )
            for k in top_ks
        },
        "recall_at_k": {
            str(k): (
                len(set(ranked_ids[:k]) & relevant_ids) / len(relevant_ids)
                if relevant_ids
                else None
            )
            for k in top_ks
        },
        "hit_rate_at_k": {
            str(k): int(bool(set(ranked_ids[:k]) & relevant_ids)) for k in top_ks
        },
        "mrr": 1 / first if first else 0.0,
        "mean_rank_of_relevant": (
            sum(found_ranks) / len(found_ranks) if found_ranks else None
        ),
        "best_rank_of_relevant": min(found_ranks) if found_ranks else None,
        "ndcg": "not_computed_no_graded_relevance",
    }


def _v3_results(row: Mapping[str, Any], *, include_audit: bool = False) -> list[dict[str, Any]]:
    if "complete_candidate_results" in row:
        return [
            dict(item)
            for item in row["complete_candidate_results"]
            if include_audit or item.get("bucket") != "audit_only_results"
        ]
    buckets = ["ranked_results", "retained_with_warning"]
    if include_audit:
        buckets.append("audit_only_results")
    return sorted(
        [dict(item) for bucket in buckets for item in row.get(bucket) or []],
        key=lambda item: (int(item.get("rank") or 10**9), item["statement_id"]),
    )


def _result_identity(item: Mapping[str, Any]) -> str:
    return str(item.get("statement_id") or item.get("record_id") or "")


def _graph_ids(item: Mapping[str, Any]) -> set[str]:
    projection = item.get("evaluation_projection") or {}
    values = list(projection.get("graph_evidence_ids") or [])
    values += list(item.get("graph_evidence_ids") or [])
    values += [str(item.get("graph_evidence_id") or item.get("record_id") or "")]
    return {str(value) for value in values if value}


def _therapy(item: Mapping[str, Any]) -> str:
    projection = item.get("evaluation_projection") or {}
    return normalize_text(projection.get("intervention") or item.get("drug") or "")


def _pmids(item: Mapping[str, Any]) -> set[str]:
    source_ids = list((item.get("evaluation_projection") or {}).get("source_ids") or [])
    source_ids += list(item.get("source_ids") or [])
    source_ids += [str(value) for value in item.get("pmids") or []]
    return {
        str(value).upper().replace("PUBMED:", "").replace("PMID:", "")
        for value in source_ids
        if "PUBMED:" in str(value).upper()
        or "PMID:" in str(value).upper()
        or str(value).isdigit()
    }


def _direction_value(value: Any) -> str:
    text = normalize_text(value or "")
    if "resistance" in text:
        return "resistance"
    if any(marker in text for marker in ("sensitivity", "response", "benefit", "clinical activity")):
        return "sensitivity"
    return text


def _claim_direction(claim: Mapping[str, Any]) -> str:
    return _direction_value(claim.get("relation"))


def _biomarker_matches(item_value: Any, claim_value: Any) -> bool:
    item_text = normalize_text(item_value or "")
    claim_raw = str(claim_value or "")
    claim_text = normalize_text(claim_raw)
    if not item_text or not claim_text:
        return False
    gene = claim_text.split()[0]
    if gene not in item_text:
        return False
    variants = [value.casefold() for value in re.findall(r"[A-Z]\d+[A-Z]", claim_raw.upper())]
    exons = re.findall(r"exon\s+\d+", claim_text)
    specific = [*variants, *exons]
    if specific and not any(value in item_text for value in specific):
        return False
    if any(value in claim_text for value in ("fusion", "rearrangement")):
        return any(value in item_text for value in ("fusion", "rearrangement"))
    return True

def _claim_matches(item: Mapping[str, Any], claim: Mapping[str, Any]) -> bool:
    if claim.get("documentary_status") != "supported_as_written":
        return False
    projection = item.get("evaluation_projection") or {}
    item_biomarker = normalize_text(
        projection.get("biomarker") or item.get("subject") or ""
    )
    claim_biomarker = normalize_text(claim.get("subject") or "")
    biomarker_match = _biomarker_matches(item_biomarker, claim_biomarker)
    item_direction = normalize_text(
        projection.get("direction") or item.get("relation") or ""
    )
    item_polarity = normalize_text(
        item.get("assertion_polarity")
        or projection.get("assertion_polarity")
        or item.get("direction")
        or ""
    )
    return all(
        (
            biomarker_match,
            _therapy(item) == normalize_text(claim.get("object") or ""),
            _direction_value(item_direction) == _claim_direction(claim),
            item_polarity == normalize_text(claim.get("direction") or ""),
            not claim.get("pmid") or str(claim["pmid"]) in _pmids(item),
        )
    )


def _relevant_statement_ids(
    results: Sequence[Mapping[str, Any]], gold: Mapping[str, Any]
) -> set[str]:
    return {
        _result_identity(item)
        for item in results
        if any(_claim_matches(item, claim) for claim in gold.get("claims") or [])
    }


def _relevant_evaluation_ids(
    results: Sequence[Mapping[str, Any]], gold: Mapping[str, Any]
) -> set[str]:
    return {
        identity
        for item in results
        if any(_claim_matches(item, claim) for claim in gold.get("claims") or [])
        for identity in (_graph_ids(item) or {_result_identity(item)})
    }


def _matched_claim_ids(
    item: Mapping[str, Any], gold: Mapping[str, Any]
) -> list[str]:
    return sorted(
        str(claim["claim_id"])
        for claim in gold.get("claims") or []
        if _claim_matches(item, claim)
    )

def _claim_ranking_metrics(
    results: Sequence[Mapping[str, Any]],
    gold: Mapping[str, Any],
    top_ks: Sequence[int] = TOP_KS,
) -> dict[str, Any]:
    relevant = {
        str(claim["claim_id"])
        for claim in gold.get("claims") or []
        if claim.get("documentary_status") == "supported_as_written"
    }
    matches = [_matched_claim_ids(item, gold) for item in results]
    first = next((index for index, item in enumerate(matches, 1) if item), None)
    ranks_by_claim = {
        claim_id: next(
            (index for index, matched in enumerate(matches, 1) if claim_id in matched),
            None,
        )
        for claim_id in relevant
    }
    found = [rank for rank in ranks_by_claim.values() if rank is not None]
    covered_at_k = {
        str(k): {claim_id for matched in matches[:k] for claim_id in matched}
        for k in top_ks
    }
    return {
        "unit": "biomarker_intervention_direction_polarity_source_claim_projection",
        "relevant_denominator": len(relevant),
        "retrieved_denominator_at_k": {
            str(k): min(k, len(results)) for k in top_ks
        },
        "precision_at_k": {
            str(k): (
                sum(bool(matched) for matched in matches[:k])
                / min(k, len(results))
                if results[:k]
                else 0.0
            )
            for k in top_ks
        },
        "recall_at_k": {
            str(k): (
                len(covered_at_k[str(k)]) / len(relevant) if relevant else None
            )
            for k in top_ks
        },
        "hit_rate_at_k": {
            str(k): int(bool(covered_at_k[str(k)])) for k in top_ks
        },
        "mrr": 1 / first if first else 0.0,
        "mean_rank_of_relevant": sum(found) / len(found) if found else None,
        "best_rank_of_relevant": min(found) if found else None,
        "missing_claim_ids": sorted(
            claim_id for claim_id, rank in ranks_by_claim.items() if rank is None
        ),
        "ndcg": "not_computed_no_graded_relevance",
    }

def compute_rank_shifts(
    *,
    query_id: str,
    relevant_ids: set[str],
    v2_ids: Sequence[str],
    native_rows: Sequence[Mapping[str, Any]],
    qualified_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    v2_rank = {item: index for index, item in enumerate(v2_ids, 1)}

    def index_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
        output: dict[str, Mapping[str, Any]] = {}
        for item in rows:
            for identifier in _graph_ids(item) or {_result_identity(item)}:
                output[identifier] = item
        return output

    native = index_rows(native_rows)
    qualified = index_rows(qualified_rows)
    rows: list[dict[str, Any]] = []
    for identifier in sorted(relevant_ids):
        n = native.get(identifier)
        q = qualified.get(identifier)
        n_rank = int(n["rank"]) if n else None
        q_rank = int(q["rank"]) if q else None
        q_components = list((q or {}).get("score_breakdown") or [])
        qualified_components = [
            item
            for item in q_components
            if item.get("category") == "qualified"
            and float(item.get("contribution") or 0) != 0
        ]
        warnings = list((q or {}).get("warnings") or [])
        if q is None:
            classification = "absent_from_candidates"
        elif "candidate_invalid" in warnings:
            classification = "demoted_by_invalid_link"
        elif "candidate_partial" in warnings:
            classification = "demoted_by_partial_support"
        elif any("ambiguous" in value for value in warnings):
            classification = "demoted_by_ambiguity"
        elif n_rank is not None and q_rank is not None and q_rank < n_rank:
            classification = (
                "promoted_by_prototype_qualifier"
                if any(float(item["contribution"]) > 0 for item in qualified_components)
                else "promoted_by_native_match"
            )
        else:
            classification = "unchanged"
        rank_v2 = v2_rank.get(identifier)
        rows.append(
            {
                "query_id": query_id,
                "evaluation_identity": identifier,
                "item_id": _result_identity(q or n or {"record_id": identifier}),
                "rank_v2": rank_v2,
                "rank_native_only": n_rank,
                "rank_qualified_soft": q_rank,
                "delta_v2_to_qualified_soft": (
                    rank_v2 - q_rank
                    if rank_v2 is not None and q_rank is not None
                    else None
                ),
                "classification": classification,
                "responsible_score_components": qualified_components,
                "warnings": warnings,
                "active_profile_units": list(
                    (q or {}).get("active_profile_unit_ids") or []
                ),
                "review_status": (q or {}).get("review_status"),
                "propagation_eligibility": (q or {}).get(
                    "propagation_eligibility"
                ),
            }
        )
    return rows


def classify_qualifier_impact(
    affected_candidates: int, candidate_universe: int
) -> str:
    fraction = affected_candidates / max(candidate_universe, 1)
    if affected_candidates == 0:
        return "no measurable ranking impact"
    if fraction <= 0.10:
        return "limited ranking impact"
    if fraction <= 0.30:
        return "moderate ranking impact"
    return "substantial ranking impact"

def _bundle_guard(bundle: Path, expected_aggregate: str) -> dict[str, Any]:
    file_hashes = {
        name: _sha(bundle / name) for name in sorted(EXPECTED_GOLD_FILES)
    }
    if file_hashes != dict(sorted(EXPECTED_GOLD_FILES.items())):
        raise GoldAccessViolation("un file del bundle gold non coincide col freeze")
    if expected_aggregate != (
        "05bc53c2ba0baec1c5264fdce74a4ea247808791877d4675b9ae4e32c8997133"
    ):
        raise GoldAccessViolation("identità aggregata gold inattesa")
    return {
        "aggregate_sha256": expected_aggregate,
        "file_sha256": file_hashes,
        "verification_contract": (
            "aggregate identity frozen by preexisting inventory; every member "
            "is independently SHA-256 verified"
        ),
    }


def _micro_macro(
    per_query: Sequence[Mapping[str, Any]],
    mode: str,
    field: str = "proposition_ranking",
) -> dict[str, Any]:
    values = [row["modes"][mode][field] for row in per_query]
    relevant_total = sum(int(item["relevant_denominator"]) for item in values)
    output: dict[str, Any] = {"query_denominator": len(values)}
    for metric in ("precision_at_k", "recall_at_k", "hit_rate_at_k"):
        output[f"macro_{metric}"] = {
            str(k): (
                sum(
                    float(item[metric][str(k)])
                    for item in values
                    if item[metric][str(k)] is not None
                )
                / max(
                    sum(item[metric][str(k)] is not None for item in values), 1
                )
            )
            for k in TOP_KS
        }
    output["macro_mrr"] = sum(float(item["mrr"]) for item in values) / max(
        len(values), 1
    )
    output["micro_relevant_denominator"] = relevant_total
    output["micro_recall_at_k"] = {
        str(k): (
            sum(
                round(
                    float(item["recall_at_k"][str(k)])
                    * int(item["relevant_denominator"])
                )
                for item in values
                if item["recall_at_k"][str(k)] is not None
            )
            / relevant_total
            if relevant_total
            else None
        )
        for k in TOP_KS
    }
    return output


def _zero_audit(
    query: Mapping[str, Any],
    historical: Mapping[str, Any],
    mode_rows: Mapping[str, Mapping[str, Any]],
    statements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    biomarker = (query.get("biomarkers") or [{}])[0]
    gene = normalize_text(biomarker.get("gene") or "")
    alteration = normalize_text(biomarker.get("alteration") or "")
    corpus_text = [
        normalize_text(json.dumps(row.get("biomarker") or {}, ensure_ascii=False))
        for row in statements
    ]
    gene_present = any(gene and gene in value for value in corpus_text)
    alteration_present = any(
        alteration and alteration in value for value in corpus_text
    )
    disease = normalize_text(query.get("disease") or "")
    disease_present = any(
        disease
        and disease
        in normalize_text(json.dumps(row.get("disease") or {}, ensure_ascii=False))
        for row in statements
    )
    return {
        "query_id": query["query_id"],
        "case_id": query["case_id"],
        "disease": query["disease"],
        "biomarker": biomarker,
        "interventions": query.get("interventions") or [],
        "directions": query.get("directions") or [],
        "candidate_counts": {
            "historical_v2": historical["candidate_count"],
            **{mode: row["candidate_count"] for mode, row in mode_rows.items()},
        },
        "first_zeroing_filter": "biomarker",
        "gene_present_in_corpus": gene_present,
        "alteration_present_in_corpus": alteration_present,
        "disease_present_in_corpus": disease_present,
        "terminology_mapping_present": False,
        "classification": (
            "true_no_evidence_in_snapshot"
            if not gene_present and historical["candidate_count"] == 0
            else "unresolved_other"
        ),
        "query_modified": False,
    }


def run_gold_evaluation(
    *,
    root: Path,
    output: Path,
    gold_bundle: Path,
    expected_gold_hash: str,
) -> dict[str, Any]:
    """Passaggio B. Verifica il freeze prima di leggere il gold."""
    hashes_path = output / "retrieval_result_hashes.json"
    if not hashes_path.exists():
        raise BlindRetrievalComplete("eseguire prima il passaggio A")
    frozen_hashes = json.loads(hashes_path.read_text(encoding="utf-8"))
    if frozen_hashes.get("phase") != "blind_retrieval_complete":
        raise BlindRetrievalComplete("freeze del passaggio A incompleto")
    result_files = {
        "frozen_v2": output / "frozen_v2_results.jsonl",
        **{mode: output / f"{mode}_results.jsonl" for mode in MODES},
    }
    before = {name: _sha(path) for name, path in sorted(result_files.items())}
    if before != frozen_hashes["results"]:
        raise GoldAccessViolation("risultati modificati prima dell'accesso gold")
    if frozen_hashes["scoring_config_hash_before_retrieval"] != EXPECTED_SCORING_HASH:
        raise GoldAccessViolation("scoring config non congelata")

    gold_integrity = _bundle_guard(gold_bundle, expected_gold_hash)
    gold_path = gold_bundle / "mtb_evidence_gold_pilot_v1.jsonl"
    gold_rows = sorted(_read_jsonl(gold_path), key=lambda row: row["case_id"])
    _write_jsonl(output / "evaluation_gold_snapshot.jsonl", gold_rows)
    queries = _read_jsonl(output / "evaluation_queries.jsonl")
    historical_rows = _read_jsonl(output / "frozen_v2_results.jsonl")
    v3 = {
        mode: _read_jsonl(output / f"{mode}_results.jsonl") for mode in MODES
    }
    query_by_case = {row["case_id"]: row for row in queries}
    gold_by_case = {row["case_id"]: row for row in gold_rows}
    historical_by_case = {row["case_id"]: row for row in historical_rows}
    v3_by_case = {
        mode: {
            row["query_id"].removesuffix(":qualified-retrieval"): row
            for row in rows
        }
        for mode, rows in v3.items()
    }

    per_query: list[dict[str, Any]] = []
    shifts: list[dict[str, Any]] = []
    warning_counter: dict[str, Counter[str]] = {
        mode: Counter() for mode in MODES
    }
    warning_gold_positive: dict[str, Counter[str]] = {
        mode: Counter() for mode in MODES
    }
    warning_non_gold: dict[str, Counter[str]] = {
        mode: Counter() for mode in MODES
    }
    policy_retention: dict[str, Counter[str]] = {
        mode: Counter() for mode in MODES
    }
    source_metrics: list[dict[str, Any]] = []
    therapy_metrics: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for case_id in sorted(gold_by_case):
        gold = gold_by_case[case_id]
        historical_results = historical_by_case[case_id]["ranked_results"]
        mode_results: dict[str, list[dict[str, Any]]] = {
            "historical_v2": historical_results,
            **{
                mode: _v3_results(v3_by_case[mode][case_id])
                for mode in MODES
            },
        }
        modes_metrics: dict[str, Any] = {}
        for mode, results in mode_results.items():
            relevant_ids = _relevant_statement_ids(results, gold)
            ranked_ids = [_result_identity(item) for item in results]
            statement_metrics = _claim_ranking_metrics(results, gold)
            expected_pmids = {str(value) for value in gold.get("expected_pmids") or []}
            ranked_pmids: list[str] = []
            for item in results:
                for pmid in sorted(_pmids(item)):
                    if pmid not in ranked_pmids:
                        ranked_pmids.append(pmid)
            expected_therapies = {
                normalize_text(value) for value in gold.get("expected_therapies") or []
            }
            ranked_therapies: list[str] = []
            for item in results:
                therapy = _therapy(item)
                if therapy and therapy not in ranked_therapies:
                    ranked_therapies.append(therapy)
            source = compute_binary_ranking_metrics(ranked_pmids, expected_pmids)
            therapy = compute_binary_ranking_metrics(
                ranked_therapies, expected_therapies
            )
            modes_metrics[mode] = {
                "candidate_count": (
                    historical_by_case[case_id]["candidate_count"]
                    if mode == "historical_v2"
                    else v3_by_case[mode][case_id]["candidate_count"]
                ),
                "proposition_ranking": statement_metrics,
                "statement_ranking": "not_computed_no_statement_level_gold",
                "source_ranking": source,
                "therapy_ranking": therapy,
                "gold_statement_ids_observed": sorted(relevant_ids),
                "ranked_statement_ids": ranked_ids,
                "missing_expected_pmids": sorted(expected_pmids - set(ranked_pmids)),
                "missing_expected_therapies": sorted(
                    expected_therapies - set(ranked_therapies)
                ),
            }
            source_metrics.append(
                {"query_id": query_by_case[case_id]["query_id"], "mode": mode, **source}
            )
            therapy_metrics.append(
                {"query_id": query_by_case[case_id]["query_id"], "mode": mode, **therapy}
            )
            if mode in MODES:
                for item in results:
                    item_warnings = item.get("warnings") or []
                    warning_counter[mode].update(item_warnings)
                    target = (
                        warning_gold_positive
                        if _matched_claim_ids(item, gold)
                        else warning_non_gold
                    )
                    target[mode].update(item_warnings)
                    if item.get("propagation_eligibility") == "prototype_only":
                        policy_retention[mode]["prototype_only_results_retained"] += 1
                    if "qualifier_mismatch_observed_but_not_hard_filtered" in item_warnings:
                        policy_retention[mode]["qualifier_mismatch_not_hard_filtered"] += 1
                policy_retention[mode]["audit_only_results"] += len(
                    v3_by_case[mode][case_id].get("audit_only_results") or []
                )
        complete_mode_results = {
            mode: _v3_results(v3_by_case[mode][case_id], include_audit=True)
            for mode in MODES
        }
        native_ids = {
            value for item in complete_mode_results["native_only"] for value in _graph_ids(item)
        }
        qualified_ids = {
            value for item in complete_mode_results["qualified_soft"] for value in _graph_ids(item)
        }
        compatibility_ids = {
            value
            for item in complete_mode_results["v2_compatibility"]
            for value in _graph_ids(item)
        }
        historical_ids = {
            value for item in mode_results["historical_v2"] for value in _graph_ids(item)
        }
        coverage.append(
            {
                "query_id": query_by_case[case_id]["query_id"],
                "candidate_counts": {
                    mode: data["candidate_count"]
                    for mode, data in modes_metrics.items()
                },
                "gold_claim_coverage": {
                    mode: {
                        "covered": len({
                            claim_id
                            for item in results
                            for claim_id in _matched_claim_ids(item, gold)
                        }),
                        "denominator": sum(
                            claim.get("documentary_status") == "supported_as_written"
                            for claim in gold.get("claims") or []
                        ),
                        "missing_claim_ids": sorted(
                            {
                                str(claim["claim_id"])
                                for claim in gold.get("claims") or []
                                if claim.get("documentary_status") == "supported_as_written"
                            }
                            - {
                                claim_id
                                for item in results
                                for claim_id in _matched_claim_ids(item, gold)
                            }
                        ),
                        "extra_candidate_rows": sum(
                            not bool(_matched_claim_ids(item, gold)) for item in results
                        ),
                    }
                    for mode, results in mode_results.items()
                },
                "overlap": {
                    "historical_v2_vs_qualified_soft": len(
                        historical_ids & qualified_ids
                    ),
                    "v2_compatibility_vs_qualified_soft": len(
                        compatibility_ids & qualified_ids
                    ),
                    "native_only_vs_qualified_soft": len(native_ids & qualified_ids),
                },
                "qualified_soft_missing_from_historical_v2": sorted(
                    historical_ids - qualified_ids
                ),
                "qualified_soft_extra_vs_historical_v2": sorted(
                    qualified_ids - historical_ids
                ),
                "historical_v2_divergence_explanation": {
                    "missing_in_v3_count": len(historical_ids - qualified_ids),
                    "extra_in_v3_count": len(qualified_ids - historical_ids),
                    "cause_codes": sorted({
                        *(
                            ["historical_v2_broader_graph_traversal_vs_v3_native_constraints"]
                            if historical_ids - qualified_ids else []
                        ),
                        *(
                            ["v3_statement_corpus_candidates_not_serialized_by_historical_v2"]
                            if qualified_ids - historical_ids else []
                        ),
                    }),
                    "all_differences_enumerated": True,
                },
            }
        )
        per_query.append(
            {
                "query_id": query_by_case[case_id]["query_id"],
                "case_id": case_id,
                "gold_denominators": {
                    "claims": len(gold.get("claims") or []),
                    "pmids": len(gold.get("expected_pmids") or []),
                    "therapies": len(gold.get("expected_therapies") or []),
                },
                "modes": modes_metrics,
            }
        )
        native_rows = mode_results["native_only"]
        qualified_rows = mode_results["qualified_soft"]
        relevant_union = (
            _relevant_evaluation_ids(mode_results["historical_v2"], gold)
            | _relevant_evaluation_ids(native_rows, gold)
            | _relevant_evaluation_ids(qualified_rows, gold)
        )
        shifts.extend(
            compute_rank_shifts(
                query_id=query_by_case[case_id]["query_id"],
                relevant_ids=relevant_union,
                v2_ids=[
                    next(iter(_graph_ids(item)), _result_identity(item))
                    for item in mode_results["historical_v2"]
                ],
                native_rows=native_rows,
                qualified_rows=qualified_rows,
            )
        )

    _write_jsonl(output / "per_query_metrics.jsonl", per_query)
    _write_jsonl(output / "rank_shift_analysis.jsonl", shifts)
    _write_json(output / "candidate_coverage.json", {"queries": coverage})
    _write_json(
        output / "source_metrics.json",
        {
            "rows": source_metrics,
            "aggregate": {
                mode: _micro_macro(per_query, mode, "source_ranking")
                for mode in ("historical_v2", *MODES)
            },
        },
    )
    _write_json(
        output / "therapy_metrics.json",
        {
            "rows": therapy_metrics,
            "aggregate": {
                mode: _micro_macro(per_query, mode, "therapy_ranking")
                for mode in ("historical_v2", *MODES)
            },
        },
    )

    aggregate = {
        "metric_contract_version": METRIC_CONTRACT_VERSION,
        "top_k": list(TOP_KS),
        "nDCG": "not_computed_no_graded_relevance",
        "p_values_computed": False,
        "modes": {
            mode: _micro_macro(per_query, mode)
            for mode in ("historical_v2", *MODES)
        },
        "zero_candidate_query_included": True,
    }
    _write_json(output / "aggregate_metrics.json", aggregate)

    native_all = {
        case: _v3_results(v3_by_case["native_only"][case])
        for case in v3_by_case["native_only"]
    }
    qualified_all = {
        case: _v3_results(v3_by_case["qualified_soft"][case])
        for case in v3_by_case["qualified_soft"]
    }
    rank_changed_ids: set[str] = set()
    membership_changed_ids: set[str] = set()
    membership_changes_by_k: Counter[str] = Counter()
    candidate_universe_ids: set[str] = set()
    warning_only = 0
    contribution_candidates = 0
    total_contribution = 0.0
    absolute_contribution = 0.0
    used_fields: Counter[str] = Counter()
    qualifier_fields_present: Counter[str] = Counter()
    qualifier_fields_neutral: Counter[str] = Counter()
    gold_positive_with_contribution = 0
    units: set[str] = set()
    for case_id in sorted(native_all):
        n_rank = {
            _result_identity(item): int(item["rank"]) for item in native_all[case_id]
        }
        q_rank = {
            _result_identity(item): int(item["rank"])
            for item in qualified_all[case_id]
        }
        common = set(n_rank) & set(q_rank)
        candidate_universe_ids.update(
            f"{case_id}:{item}" for item in set(n_rank) | set(q_rank)
        )
        rank_changed_ids.update(
            f"{case_id}:{item}"
            for item in common
            if n_rank[item] != q_rank[item]
        )
        for k in TOP_KS:
            changed = (
                {item for item, rank in n_rank.items() if rank <= k}
                ^ {item for item, rank in q_rank.items() if rank <= k}
            )
            membership_changes_by_k[str(k)] += len(changed)
            membership_changed_ids.update(
                f"{case_id}:{item}" for item in changed
            )
        for item in qualified_all[case_id]:
            components = [
                component
                for component in item.get("score_breakdown") or []
                if component.get("category") == "qualified"
                and float(component.get("contribution") or 0) != 0
            ]
            if components:
                contribution_candidates += 1
                if _matched_claim_ids(item, gold_by_case[case_id]):
                    gold_positive_with_contribution += 1
            for dimension, payload in sorted((item.get("qualified_matches") or {}).items()):
                value = payload.get("value") if isinstance(payload, Mapping) else payload
                if value in (None, "", "unknown", "not_applicable", "not_separable"):
                    qualifier_fields_neutral[dimension] += 1
                else:
                    qualifier_fields_present[dimension] += 1
            for component in components:
                value = float(component["contribution"])
                total_contribution += value
                absolute_contribution += abs(value)
                used_fields[str(component["name"])] += 1
            units.update(item.get("active_profile_unit_ids") or [])
            if item.get("warnings") and n_rank.get(_result_identity(item)) == q_rank.get(
                _result_identity(item)
            ):
                warning_only += 1
    affected_ids = rank_changed_ids | membership_changed_ids
    impact = {
        "threshold_contract": IMPACT_THRESHOLDS,
        "candidate_universe": len(candidate_universe_ids),
        "unique_affected_query_candidates": len(affected_ids),
        "affected_fraction": len(affected_ids) / max(len(candidate_universe_ids), 1),
        "candidates_with_qualifier_contribution": contribution_candidates,
        "gold_projected_positive_with_qualifier_contribution": gold_positive_with_contribution,
        "qualifier_contribution_total": total_contribution,
        "qualifier_contribution_absolute_total": absolute_contribution,
        "ranking_swaps": len(rank_changed_ids),
        "top_k_membership_changes_unique": len(membership_changed_ids),
        "top_k_membership_changes_by_k": dict(sorted(membership_changes_by_k.items())),
        "warning_only_changes": warning_only,
        "qualifier_fields_used": dict(sorted(used_fields.items())),
        "qualifier_fields_present": dict(sorted(qualifier_fields_present.items())),
        "qualifier_fields_present_but_neutral": dict(
            sorted(qualifier_fields_neutral.items())
        ),
        "qualifier_fields_absent": [
            field
            for field in (
                "disease_setting", "therapy_line", "population", "prior_therapies",
                "stage", "regimen", "resection_status"
            )
            if field not in qualifier_fields_present
            and field not in qualifier_fields_neutral
        ],
        "prototype_only_units_involved": sorted(units),
        "impact_classification": classify_qualifier_impact(
            len(affected_ids), len(candidate_universe_ids)
        ),
    }
    _write_json(output / "qualifier_impact.json", impact)
    _write_json(
        output / "warning_metrics.json",
        {
            "modes": {
                mode: {
                    "all_results": dict(sorted(warning_counter[mode].items())),
                    "gold_positive_results": dict(
                        sorted(warning_gold_positive[mode].items())
                    ),
                    "non_gold_results": dict(sorted(warning_non_gold[mode].items())),
                    "policy_retention": dict(sorted(policy_retention[mode].items())),
                }
                for mode in MODES
            }
        },
    )

    corpus_path = (
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "qualification_corpus_v2"
        / "evidence_statements.jsonl"
    )
    statements = _read_jsonl(corpus_path)
    active_units = {
        unit["profile_unit_id"]: unit
        for unit in _read_jsonl(corpus_path.with_name("active_source_profile_units.jsonl"))
    }
    terminology_mappings = _read_jsonl(
        corpus_path.with_name("terminology_mappings.jsonl")
    )
    zero_case = next(
        row for row in queries if row["case_id"] == "PILOT-N1-RMI2-SNAPSHOT"
    )
    zero = _zero_audit(
        zero_case,
        historical_by_case[zero_case["case_id"]],
        {
            mode: v3_by_case[mode][zero_case["case_id"]]
            for mode in MODES
        },
        statements,
    )
    _write_json(output / "zero_candidate_query_audit.json", zero)

    all_qualified = [
        item
        for case in v3_by_case["qualified_soft"]
        for item in _v3_results(
            v3_by_case["qualified_soft"][case], include_audit=True
        )
    ]
    pmid_checks: dict[str, Any] = {}
    for pmid in ("31358542", "22235099", "23344087", "22277784"):
        selected = [
            item for item in all_qualified if pmid in _pmids(item)
        ]
        pmid_checks[pmid] = {
            "result_count": len(selected),
            "invalid_primary_results": sum(
                "candidate_invalid" in (item.get("warnings") or [])
                and item.get("bucket") != "audit_only_results"
                for item in selected
            ),
            "negative_preserved": all(
                not item.get("negative_evidence_information")
                or item["negative_evidence_information"].get(
                    "preserved_as_negative"
                )
                for item in selected
            ),
            "case_level_frequency_inferred": sum(
                bool((item.get("case_level_information") or {}).get("frequency_inferred"))
                for item in selected
            ),
            "pending_mapping_treated_as_exact": sum(
                mapping.get("match_grade") == "exact"
                and str(mapping.get("mapping_status") or "").startswith("requires_")
                for item in selected
                for mapping in item.get("terminology_mappings") or []
            ),
        }
    by_statement = {item["statement_id"]: item for item in all_qualified}
    invalid = by_statement.get("ES-V2-evidence-100003", {})
    partial = by_statement.get("ES-V2-evidence-100004", {})
    alk_negative = [
        by_statement.get("ES-V2-evidence-764", {}),
        by_statement.get("ES-V2-evidence-766", {}),
    ]
    unresolved_panel = [
        by_statement.get("ES-V2-evidence-765", {}),
        by_statement.get("ES-V2-evidence-767", {}),
    ]
    alectinib_rows = [
        item
        for item in all_qualified
        if "22277784" in _pmids(item)
        and "alectinib" in _therapy(item)
    ]
    units_313 = [
        unit for unit in active_units.values()
        if "31358542" in (unit.get("pmids") or [])
    ]
    units_233 = [
        unit for unit in active_units.values()
        if "23344087" in (unit.get("pmids") or [])
    ]
    units_22277784 = [
        unit for unit in active_units.values()
        if "22277784" in (unit.get("pmids") or [])
    ]
    cuto_unit = active_units.get("PU-PMID-22235099-cuto1-comparative", {})
    baf3_units = [unit for unit in units_22277784 if unit.get("is_preclinical")]
    clinical_22277784 = [unit for unit in units_22277784 if unit.get("is_clinical")]

    pmid_checks["31358542"]["checks"] = {
        "candidate_invalid_is_audit_only": bool(invalid)
        and invalid.get("bucket") == "audit_only_results",
        "candidate_invalid_intervention": (
            invalid.get("evaluation_projection") or {}
        ).get("intervention"),
        "invalid_not_primary_brigatinib_support": bool(invalid)
        and invalid.get("bucket") == "audit_only_results"
        and normalize_text((invalid.get("evaluation_projection") or {}).get("intervention"))
        == "brigatinib",
        "partial_statement_warned": bool(partial)
        and "candidate_partial" in (partial.get("warnings") or []),
        "false_preclinical_unit_count": sum(
            bool(unit.get("is_preclinical")) for unit in units_313
        ),
    }
    qualification_links = _read_jsonl(
        root
        / "benchmarks"
        / "mtb_evidence"
        / "v3"
        / "qualification_corpus_v2"
        / "qualification_links.jsonl"
    )
    negative_link_statements = {
        str(link.get("statement_id") or "")
        for link in qualification_links
        if link.get("assertion_polarity") == "does_not_support"
        and link.get("experiment_role") == "negative_experiment"
    }
    pmid_checks["22235099"]["checks"] = {
        "clinical_and_preclinical_profile_units_distinct": bool(alk_negative)
        and all(bool(item) for item in alk_negative)
        and any(
            any("clinical-cohort" in unit for unit in item.get("active_profile_unit_ids") or [])
            and any(
                marker in unit
                for unit in item.get("active_profile_unit_ids") or []
                for marker in ("engineered", "h3122", "cuto1")
            )
            for item in alk_negative
        ),
        "h3122_kras_remains_negative": {
            "ES-V2-evidence-764",
            "ES-V2-evidence-766",
        }.issubset(negative_link_statements),
        "cuto1_non_inheritance_verified": bool(cuto_unit)
        and cuto_unit.get("cross_context_biomarker_propagation") == "forbidden"
        and cuto_unit.get("ALK_rearrangement_in_CUTO1_model")
        == "lost_or_not_detected",
        "case_level_frequency_inferred": any(
            bool((item.get("case_level_information") or {}).get("frequency_inferred"))
            for item in alk_negative if item
        ),
        "named_patient_frequency_inferred": any(
            bool((item.get("case_level_information") or {}).get("frequency_inferred"))
            and bool((item.get("case_level_information") or {}).get("named_patient_subset"))
            for item in alk_negative if item
        ),
    }
    mappings_233 = [
        mapping for mapping in terminology_mappings
        if mapping.get("canonical_source_id") == "PMID:23344087"
    ]
    pmid_checks["23344087"]["checks"] = {
        "unresolved_panel_not_separable": bool(units_233)
        and any(unit.get("not_separable_dimensions") for unit in units_233),
        "abstract_only_warning": bool(units_233)
        and all(
            unit.get("source_basis") == "abstract_only"
            or unit.get("availability") == "abstract_only"
            for unit in units_233
        ),
        "less_sensitive_not_complete_resistance": any(
            mapping.get("source_term") == "less sensitive to crizotinib"
            and str(mapping.get("mapping_status") or "").startswith("requires_")
            for mapping in mappings_233
        ),
        "cng_amplification_not_exact": any(
            "copy number gain" in str(mapping.get("source_term") or "").casefold()
            and str(mapping.get("mapping_status") or "").startswith("requires_")
            for mapping in mappings_233
        ),
        "egfr_l858r_confounder_visible": any(
            "egfr l858r" in json.dumps(unit, ensure_ascii=False).casefold()
            for unit in units_233
        ),
    }
    complete_resistance_text = " ".join(
        json.dumps(item, ensure_ascii=False).casefold()
        for item in alectinib_rows
    )
    pmid_checks["22277784"]["checks"] = {
        "clinical_and_baf3_profile_units_distinct": bool(baf3_units)
        and bool(clinical_22277784)
        and not ({unit["profile_unit_id"] for unit in baf3_units}
                 & {unit["profile_unit_id"] for unit in clinical_22277784}),
        "ch5424802_alectinib_pending": any(
            mapping.get("source_term") == "CH5424802"
            and str(mapping.get("mapping_status") or "").startswith("requires_")
            for mapping in terminology_mappings
        ),
        "complete_resistance_claim_present": "complete resistance" in complete_resistance_text,
        "clinical_population_non_propagation_verified": bool(baf3_units)
        and bool(clinical_22277784)
        and all(
            "ba/f3" in str(unit.get("population") or "").casefold()
            for unit in baf3_units
        )
        and all(
            "patient" not in str(unit.get("population") or "").casefold()
            for unit in baf3_units
        ),
    }
    structural = {
        "pmid_checks": pmid_checks,
        "provenance_complete": all(
            bool(item.get("provenance_references")) for item in all_qualified
        ),
        "negative_evidence_preserved": all(
            not item.get("negative_evidence_information")
            or item["negative_evidence_information"].get("preserved_as_negative")
            for item in all_qualified
        ),
        "final_clinical_claim": False,
    }
    _write_json(output / "structural_metrics.json", structural)

    after = {name: _sha(path) for name, path in sorted(result_files.items())}
    config_path = (
        root
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    audit = {
        "event_order": [
            "scoring_config_verified",
            "blind_retrieval_completed",
            "retrieval_results_hashed",
            "gold_bundle_integrity_verified",
            "gold_loaded_read_only",
            "metrics_computed",
            "result_hashes_reverified",
        ],
        "retrieval_completed_before_gold_access": True,
        "scoring_config_hash_before_retrieval": frozen_hashes[
            "scoring_config_hash_before_retrieval"
        ],
        "scoring_config_hash_after_evaluation": config_payload["hash"],
        "result_hashes_before_gold_access": before,
        "result_hashes_after_gold_access": after,
        "result_hashes_unchanged_after_gold_access": before == after,
        "gold_integrity": gold_integrity,
        "gold_open_mode": "read_only",
        "gold_used_for_retrieval": False,
        "gold_used_for_evaluation": True,
        "tuning_performed": False,
        "parameters_derived_from_gold": [],
    }
    _write_json(output / "gold_access_audit.json", audit)

    manifest = {
        "branch": "eval/v3-v2-v3a-exploratory-pilot",
        "source_sha": "ec66746010b70701edf630a41b47109283c07f48",
        "corpus_version": "qualification_corpus/2.0",
        "corpus_fingerprint": EXPECTED_CORPUS_FINGERPRINT,
        "frozen_kg_fingerprint": EXPECTED_FROZEN_KG_FINGERPRINT,
        "scoring_config_version": config_payload["version"],
        "scoring_config_hash": config_payload["hash"],
        "query_set_hash": frozen_hashes["query_set_hash"],
        "frozen_v2_result_hash": before["frozen_v2"],
        "gold_bundle_hash": expected_gold_hash,
        "result_hash_per_mode": frozen_hashes["results"],
        "metric_contract_version": METRIC_CONTRACT_VERSION,
        "top_k": list(TOP_KS),
        "run_count": json.loads(
            (output / "runtime_metrics.json").read_text(encoding="utf-8")
        )["load_corpus"]["run_count"],
        "evaluation_phase": "exploratory",
        "tuning_performed": False,
        "gold_used_for_retrieval": False,
        "gold_used_for_evaluation": True,
        "final_clinical_evaluation": False,
        "ready_for_expanded_exploratory_evaluation": False,
        "qualification_coverage_too_sparse_for_expansion": True,
        "expansion_readiness_reason": (
            "only one gold claim projection has a qualifier contribution and "
            "V3 native candidate coverage does not preserve the historical V2 "
            "gold-source coverage"
        ),
    }
    _write_json(output / "evaluation_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gold-bundle", type=Path)
    parser.add_argument("--expected-gold-hash")
    parser.add_argument("--phase", choices=("blind", "evaluate", "all"), default="all")
    parser.add_argument("--run-count", type=int, default=5)
    args = parser.parse_args()
    if args.phase in {"blind", "all"}:
        run_blind_retrieval(args.root, args.output, run_count=args.run_count)
    if args.phase in {"evaluate", "all"}:
        if not args.gold_bundle or not args.expected_gold_hash:
            parser.error("evaluation richiede --gold-bundle e --expected-gold-hash")
        run_gold_evaluation(
            root=args.root,
            output=args.output,
            gold_bundle=args.gold_bundle,
            expected_gold_hash=args.expected_gold_hash,
        )


if __name__ == "__main__":
    main()
