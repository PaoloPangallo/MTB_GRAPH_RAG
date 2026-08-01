"""Prepare and validate the blind G1.0 annotation workflow.

This module never assigns gold labels and never reads a gold bundle.  It only
projects the frozen structured outputs into an auditable annotation universe.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[4]
OUTPUT = ROOT / "benchmarks/mtb_evidence/final_experiment/official_runs/structured_v1_6"
CORPUS = ROOT / "backend/pipeline/evidence/corpus/v3/qualified_claim_repository_1_4"
PROTOCOL = ROOT / "benchmarks/mtb_evidence/final_experiment/v1_6"
GOLD_ROOT = ROOT / "benchmarks/mtb_evidence/final_experiment/gold_protocol/g1_0"
PREP_ROOT = ROOT / "benchmarks/mtb_evidence/final_experiment/gold_g1_0"
SEED = 20260801
FORBIDDEN = {
    "predicted_bucket", "bucket_prediction", "score", "rank", "reason_codes",
    "gate_trace", "gate_outcomes", "gate_outcome", "system_id", "run_id",
    "run_key", "output_path", "semantic_hash", "normalized_semantic_sha256",
}


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dump_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_queries() -> dict[str, dict[str, Any]]:
    rows = load_jsonl(PROTOCOL / "all_queries_v1_6.jsonl")
    return {row["query_id"]: row for row in rows}


def load_corpus() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for name in ("therapeutic_claims.jsonl", "diagnostic_claims.jsonl", "prognostic_claims.jsonl"):
        for row in load_jsonl(CORPUS / name):
            records[row["claim_id"]] = row
    return records


def primary_payloads() -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for manifest_path in (OUTPUT / "run_manifests").glob("*.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("replica") != 1 or manifest.get("status") != "complete":
            continue
        raw_name = Path(manifest["raw_output"]).name
        raw = json.loads((OUTPUT / "raw_results" / raw_name).read_text(encoding="utf-8"))
        payloads[manifest["query_id"]] = raw["result"]["payload"]
    return payloads


def candidate_kind(record: dict[str, Any], corpus: dict[str, dict[str, Any]]) -> str:
    claim_id = record.get("claim_id")
    if claim_id in corpus:
        return "claim"
    if claim_id and claim_id.startswith("GEP-"):
        return "provenance_container"
    if claim_id and claim_id.startswith("UNR-"):
        return "unresolved_association"
    if claim_id and claim_id.startswith("UNS-"):
        return "unsupported_association"
    if claim_id and claim_id.startswith("CLM-"):
        return "deprecated_or_out_of_corpus_claim"
    return "unknown"


def all_candidates(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for section in ("primary_ranked_results", "retained_with_warning", "audit_only_results", "rejected_by_native_constraints"):
        result.extend(payload.get(section, []))
    return result


def source_context(record: dict[str, Any], corpus_record: dict[str, Any]) -> dict[str, Any]:
    provenance = corpus_record.get("provenance") or record.get("provenance") or {}
    return {
        "source_unit_ids": corpus_record.get("source_unit_ids", []),
        "locators": corpus_record.get("locators", provenance.get("locators", [])),
        "source_ids": provenance.get("source_ids", []),
        "pmid": provenance.get("pmid"),
        "doi": provenance.get("doi"),
        "nct": provenance.get("nct"),
    }


def annotation_unit(query: dict[str, Any], record: dict[str, Any], corpus_record: dict[str, Any]) -> dict[str, Any]:
    claim_id = record["claim_id"]
    query_id = query["query_id"]
    return {
        "annotation_unit_id": f"G1-{query_id}-{claim_id}",
        "query_id": query_id,
        "benchmark_id": query["benchmark_id"],
        "query": query.get("query", {}),
        "candidate_kind": "claim",
        "claim_id": claim_id,
        "claim_tuple": {
            "subject": corpus_record.get("canonical_subject", corpus_record.get("subject", corpus_record.get("biomarker"))),
            "relation": corpus_record.get("relation", corpus_record.get("claim_type")),
            "object": corpus_record.get("object", corpus_record.get("canonical_intervention", corpus_record.get("intervention"))),
            "domain": corpus_record.get("claim_domain"),
            "biomarker": corpus_record.get("biomarker"),
            "disease": corpus_record.get("disease_scope"),
            "intervention": corpus_record.get("canonical_intervention", corpus_record.get("intervention")),
            "direction": corpus_record.get("direction"),
            "qualifiers": corpus_record.get("warnings", []),
        },
        "source_context": source_context(record, corpus_record),
        "annotation_status": "pending",
        "annotation_protocol_version": "G1.0",
    }


def audit() -> dict[str, Any]:
    queries, corpus, payloads = load_queries(), load_corpus(), primary_payloads()
    active_ids = set(corpus)
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    units: list[dict[str, Any]] = []
    for query_id in sorted(queries):
        query = queries[query_id]
        records = all_candidates(payloads[query_id])
        counts = Counter(candidate_kind(record, corpus) for record in records)
        ids = [record.get("claim_id") for record in records if record.get("claim_id")]
        duplicates = sorted([item for item, count in Counter(ids).items() if count > 1])
        output_claim_ids = {item for item in ids if item in corpus}
        missing = sorted(active_ids - output_claim_ids)
        extra_claims = sorted({item for item in ids if item not in active_ids and item.startswith("CLM-")})
        rows.append({
            "query_id": query_id,
            "benchmark_id": query["benchmark_id"],
            "corpus_claim_count": len(active_ids),
            "corpus_claim_evaluable_metadata_false": sum(not bool(item.get("final_evaluable")) for item in corpus.values()),
            "output_candidate_count": len(records),
            "output_claim_count": len(output_claim_ids),
            "provenance_container_count": counts["provenance_container"],
            "unresolved_association_count": counts["unresolved_association"],
            "unsupported_association_count": counts["unsupported_association"],
            "other_nonclaim_count": len(records) - len(output_claim_ids) - counts["provenance_container"] - counts["unresolved_association"] - counts["unsupported_association"],
            "corpus_claim_missing_in_output": missing,
            "output_claims_outside_corpus": extra_claims,
            "duplicate_claim_ids": duplicates,
            "universe_complete": not missing and not extra_claims and not duplicates,
        })
        for record in records:
            kind = candidate_kind(record, corpus)
            if kind == "claim":
                units.append(annotation_unit(query, record, corpus[record["claim_id"]]))
            else:
                excluded.append({
                    "query_id": query_id,
                    "record_id": record.get("claim_id"),
                    "candidate_kind": kind,
                    "exclusion_reason": "not_a_claim_candidate_for_primary_annotation",
                    "parent_id": record.get("parent_id"),
                    "graph_evidence_id": record.get("graph_evidence_id"),
                })
    report = {
        "schema_version": "candidate-universe-audit/1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "1.6",
        "protocol_commit": "00bb7982fd897e4dfc5856732acaf01ae99aea46",
        "structured_output_commit": "f8c44e5035cff210527fa7491b50781a6d8d1cf2",
        "corpus_version": "qualified_claim_repository/1.4",
        "corpus_claim_count": len(active_ids),
        "query_count": len(rows),
        "candidate_count_per_query": sorted({row["output_candidate_count"] for row in rows}),
        "candidate_universe_complete": all(row["universe_complete"] for row in rows),
        "gold_coverage_mode_eligible": all(row["universe_complete"] for row in rows),
        "annotation_unit_count": len(units),
        "excluded_annotation_unit_count": len(excluded),
        "notes": "The frozen corpus marks final_evaluable=false for its 148 active records; G1.0 does not convert that readiness flag into a gold label. Reviewers decide evaluable in the blind annotation response.",
        "queries": rows,
    }
    dump_json(PREP_ROOT / "candidate_universe_audit_g1_0.json", report)
    with (PREP_ROOT / "candidate_universe_audit_g1_0.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query_id", "benchmark_id", "corpus_claim_count", "corpus_claim_evaluable_metadata_false", "output_candidate_count", "output_claim_count", "provenance_container_count", "unresolved_association_count", "unsupported_association_count", "other_nonclaim_count", "corpus_claim_missing_in_output", "output_claims_outside_corpus", "duplicate_claim_ids", "universe_complete"])
        writer.writeheader()
        for row in rows:
            item = dict(row)
            for key in ("corpus_claim_missing_in_output", "output_claims_outside_corpus", "duplicate_claim_ids"):
                item[key] = json.dumps(item[key], ensure_ascii=False, separators=(",", ":"))
            writer.writerow(item)
    md = ["# Candidate universe audit G1.0", "", f"- corpus active claims: {len(active_ids)}", f"- queries: {len(rows)}", f"- candidate universe complete: {report['candidate_universe_complete']}", f"- annotation units: {len(units)}", "", "| query | candidates | claims | containers | unresolved | unsupported | complete |", "|---|---:|---:|---:|---:|---:|---|"]
    md.extend(f"| {r['query_id']} | {r['output_candidate_count']} | {r['output_claim_count']} | {r['provenance_container_count']} | {r['unresolved_association_count']} | {r['unsupported_association_count']} | {r['universe_complete']} |" for r in rows)
    (PREP_ROOT / "candidate_universe_audit_g1_0.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    dump_jsonl(PREP_ROOT / "excluded_annotation_units_g1_0.jsonl", excluded)
    return {"report": report, "units": units, "excluded": excluded}


def recursive_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(recursive_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(recursive_keys(item) for item in value)) if value else set()
    return set()


def validate_blind(path: Path) -> dict[str, Any]:
    rows = load_jsonl(path)
    leaks: list[str] = []
    for row in rows:
        leaks.extend(sorted(recursive_keys(row) & FORBIDDEN))
        if row.get("annotation_status") != "pending":
            leaks.append("annotation_status")
    return {"schema_version": "blinding-validation/1.0", "packet": path.name, "unit_count": len(rows), "blinding_leak_count": len(leaks), "leaked_fields": sorted(set(leaks)), "passed": not leaks}


def packets(audit_result: dict[str, Any]) -> None:
    units = list(audit_result["units"])
    rng = random.Random(SEED)
    a = list(units); b = list(units)
    rng.shuffle(a); rng.shuffle(b)
    dump_jsonl(PREP_ROOT / "annotation_packet_A_g1_0.jsonl", a)
    dump_jsonl(PREP_ROOT / "annotation_packet_B_g1_0.jsonl", b)
    mapping = {
        "schema_version": "sealed-annotation-mapping/1.0",
        "randomization_seed": SEED,
        "packet_A_order": [row["annotation_unit_id"] for row in a],
        "packet_B_order": [row["annotation_unit_id"] for row in b],
        "unit_to_identity": {row["annotation_unit_id"]: {"query_id": row["query_id"], "claim_id": row["claim_id"]} for row in units},
        "sealed_for_reviewers": True,
    }
    dump_json(PREP_ROOT / "annotation_unit_mapping_g1_0.json", mapping)
    report = {"schema_version": "blinding-report/1.0", "randomization_seed": SEED, "packet_A": validate_blind(PREP_ROOT / "annotation_packet_A_g1_0.jsonl"), "packet_B": validate_blind(PREP_ROOT / "annotation_packet_B_g1_0.jsonl"), "blinding_leak_count": 0}
    report["blinding_leak_count"] = report["packet_A"]["blinding_leak_count"] + report["packet_B"]["blinding_leak_count"]
    report["passed"] = report["blinding_leak_count"] == 0
    dump_json(PREP_ROOT / "blinding_validation_report_g1_0.json", report)
    by_query = Counter(row["query_id"] for row in units)
    by_domain = Counter(row["claim_tuple"].get("domain") for row in units)
    with (PREP_ROOT / "annotation_workload_g1_0.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(["query_id", "benchmark_id", "unit_count"])
        for query_id, count in sorted(by_query.items()): writer.writerow([query_id, next(row["benchmark_id"] for row in units if row["query_id"] == query_id), count])
    dump_json(PREP_ROOT / "annotation_workload_g1_0.json", {"schema_version": "annotation-workload/1.0", "unit_count": len(units), "units_per_query": dict(sorted(by_query.items())), "core_units": sum(row["benchmark_id"] == "v3_core_applicability" for row in units), "advanced_units": sum(row["benchmark_id"] == "v3_advanced_capability" for row in units), "provenance_containers_excluded": len(audit_result["excluded"]), "units_with_source_locator": sum(bool(row["source_context"].get("locators")) for row in units), "units_without_source_locator": sum(not bool(row["source_context"].get("locators")) for row in units), "units_by_domain": dict(sorted(by_domain.items())), "operational_load_estimate": "148 claims x 22 queries, double independent review; duration intentionally not predicted"})


def build() -> None:
    result = audit()
    if not result["report"]["candidate_universe_complete"]:
        return
    packets(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["build", "audit", "validate-packet"])
    parser.add_argument("path", nargs="?")
    args = parser.parse_args(argv)
    if args.command == "audit":
        audit(); return 0
    if args.command == "build":
        build(); return 0
    if not args.path:
        parser.error("validate-packet requires a JSONL path")
    result = validate_blind(Path(args.path)); print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())


