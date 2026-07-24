"""Smoke tecnico V3-A su query pilot congelate, senza usare outcome gold."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Iterable

from backend.pipeline.evidence.qualified_retrieval_query import (
    QualifiedRetrievalQuery,
    QueryBiomarker,
)
from backend.pipeline.evidence.qualified_retriever import QualifiedEvidenceRetriever


MODES = ("v2_compatibility", "native_only", "qualified_soft")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _queries(pilot_path: Path, fingerprint: str) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    for line in pilot_path.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        disease = str(case.get("disease") or "frozen project snapshot")
        gene = str(case.get("gene") or "")
        variant = str(case.get("variant") or "")
        aliases: list[str] = []
        if gene == "ALK":
            aliases = ["Non-Small Cell Lung Cancer", "Lung Non-small Cell Carcinoma"]
        elif gene == "EGFR":
            aliases = ["Non-Small Cell Lung Cancer", "Lung Adenocarcinoma"]
        queries.append(
            {
                "query_id": f"{case['case_id']}:qualified-retrieval",
                "case_id": case["case_id"],
                "disease": disease,
                "disease_aliases": aliases,
                "biomarkers": [
                    {"gene": gene, "alteration": variant, "normalized": ""}
                ],
                "interventions": [],
                "directions": [],
                "assertion_polarities": [],
                "evidence_scopes": [],
                "preferred_evidence_context": "both",
                "clinical_context": {"setting": str(case.get("required_context") or "")},
                "top_k": 20,
                "corpus_fingerprint": fingerprint,
            }
        )
    return queries


def _query(payload: dict[str, Any], mode: str) -> QualifiedRetrievalQuery:
    return QualifiedRetrievalQuery(
        query_id=payload["query_id"],
        case_id=payload["case_id"],
        disease=payload["disease"],
        disease_aliases=tuple(payload["disease_aliases"]),
        biomarkers=tuple(QueryBiomarker(**item) for item in payload["biomarkers"]),
        interventions=tuple(payload["interventions"]),
        directions=tuple(payload["directions"]),
        assertion_polarities=tuple(payload["assertion_polarities"]),
        evidence_scopes=tuple(payload["evidence_scopes"]),
        preferred_evidence_context=payload["preferred_evidence_context"],
        clinical_context=payload["clinical_context"],
        top_k=int(payload["top_k"]),
        mode=mode,
        corpus_fingerprint=payload["corpus_fingerprint"],
    )


def run(root: Path, output: Path) -> dict[str, Any]:
    corpus = root / "benchmarks" / "mtb_evidence" / "v3" / "qualification_corpus_v2"
    config = (
        root
        / "backend"
        / "pipeline"
        / "evidence"
        / "qualified_retriever_scoring_config.json"
    )
    pilot = (
        root
        / "benchmarks"
        / "mtb_evidence"
        / "pilot"
        / "input"
        / "mtb_evidence_gold_pilot_v1.jsonl"
    )
    retriever = QualifiedEvidenceRetriever.from_corpus(
        corpus, scoring_config_path=config
    )
    validation = retriever.validate_corpus()
    fingerprint = validation["qualification_corpus_fingerprint"]
    queries = _queries(pilot, fingerprint)
    output.mkdir(parents=True, exist_ok=True)
    _write_jsonl(output / "queries.jsonl", queries)
    shutil.copyfile(config, output / "scoring_config.json")

    mode_outputs: dict[str, list[dict[str, Any]]] = {}
    traces: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {}
    for mode in MODES:
        rows: list[dict[str, Any]] = []
        mode_metrics = {
            "queries": 0,
            "candidates_generated": 0,
            "results_ranked": 0,
            "retained_with_warning": 0,
            "audit_only_results": 0,
            "native_exclusions": 0,
            "prototype_qualifier_contributions": 0,
            "negative_evidence_surfaced": 0,
            "warning_counts": {},
        }
        mode_deterministic = True
        for payload in queries:
            query = _query(payload, mode)
            result = retriever.retrieve(query)
            serialized = result.as_dict()
            repeated = retriever.retrieve(query).as_dict()
            mode_deterministic = mode_deterministic and serialized == repeated
            rows.append(serialized)
            all_results = result.all_results
            mode_metrics["queries"] += 1
            mode_metrics["candidates_generated"] += result.candidate_count
            mode_metrics["results_ranked"] += len(result.ranked_results)
            mode_metrics["retained_with_warning"] += len(
                result.retained_with_warning
            )
            mode_metrics["audit_only_results"] += len(result.audit_only_results)
            mode_metrics["native_exclusions"] += len(
                result.rejected_by_native_constraints
            )
            mode_metrics["prototype_qualifier_contributions"] += sum(
                any(component["name"] in {"qualified_context_compatible", "qualified_first_review", "qualified_direct_support"} and float(component["contribution"]) != 0 for component in item.score_breakdown)
                for item in all_results
            )
            mode_metrics["negative_evidence_surfaced"] += sum(
                bool(item.negative_evidence_information) for item in all_results
            )
            for item in all_results:
                for warning in item.warnings:
                    mode_metrics["warning_counts"][warning] = (
                        mode_metrics["warning_counts"].get(warning, 0) + 1
                    )
            traces.append(
                {
                    "query_id": payload["query_id"],
                    "mode": mode,
                    "result_statement_ids": [
                        item.statement_id for item in all_results
                    ],
                    "native_exclusions": [
                        item.as_dict() for item in result.rejected_by_native_constraints
                    ],
                    "result_hash": hashlib.sha256(
                        json.dumps(
                            serialized,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ).encode("utf-8")
                    ).hexdigest(),
                }
            )
        target = output / f"results_{mode}.jsonl"
        _write_jsonl(target, rows)
        mode_metrics["result_hash"] = _sha256(target)
        mode_metrics["deterministic_runtime"] = mode_deterministic
        if not mode_deterministic:
            raise RuntimeError(f"output non deterministico in modalita {mode}")
        mode_outputs[mode] = rows
        metrics[mode] = mode_metrics

    _write_jsonl(output / "retrieval_traces.jsonl", traces)
    compatibility: dict[str, Any] = {"cases": []}
    for index, payload in enumerate(queries):
        v2_ids = {
            item["statement_id"]
            for bucket in ("ranked_results", "retained_with_warning", "audit_only_results")
            for item in mode_outputs["v2_compatibility"][index][bucket]
        }
        native_ids = {
            item["statement_id"]
            for bucket in ("ranked_results", "retained_with_warning", "audit_only_results")
            for item in mode_outputs["native_only"][index][bucket]
        }
        compatibility["cases"].append(
            {
                "query_id": payload["query_id"],
                "candidate_set_overlap": len(v2_ids & native_ids),
                "v2_candidate_count": len(v2_ids),
                "native_candidate_count": len(native_ids),
                "missing_candidates": sorted(v2_ids - native_ids),
                "extra_candidates": sorted(native_ids - v2_ids),
                "divergence_cause": (
                    "none: both modes intentionally use the same native offline corpus"
                    if v2_ids == native_ids
                    else None
                ),
                "divergence_classified": v2_ids == native_ids,
            }
        )
    compatibility["all_divergences_explained"] = all(
        bool(item["divergence_classified"]) for item in compatibility["cases"]
    )
    _write_json(output / "prototype_metrics.json", metrics)
    _write_json(output / "compatibility_metrics.json", compatibility)
    _write_json(output / "v2_compatibility_results.json", compatibility)

    result_hashes = {
        mode: _sha256(output / f"results_{mode}.jsonl") for mode in MODES
    }
    manifest = {
        "prototype_version": "qualified_evidence_retriever/1.0",
        "corpus_fingerprint": fingerprint,
        "frozen_kg_snapshot_fingerprint": validation[
            "frozen_kg_snapshot_fingerprint"
        ],
        "scoring_config_hash": retriever.get_scoring_config_hash(),
        "modes": list(MODES),
        "query_count": len(queries),
        "result_hashes": result_hashes,
        "clinical_gold_used_for_weights": False,
        "pilot_fixture_used_for_query_construction": True,
        "gold_outcomes_used_for_retrieval_or_metrics": False,
        "clinical_quality_metrics_computed": False,
        "ready_for_exploratory_v2_v3a_comparison": True,
        "ready_for_final_v2_v3a_evaluation": False,
    }
    _write_json(output / "prototype_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.root.resolve(), args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
