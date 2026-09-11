"""Resumable evaluation-only RQ3 runner over frozen GCA_DOCUMENT artifacts.

This module orchestrates existing canonical PAPER components; it does not
reimplement selector, Reader, validation, or relation-support behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from backend.research_pipeline.experimental.sourceunit_selector import SourceUnitSelectionInput, select
from backend.research_pipeline.enrichment.enricher_v3 import call_enricher_v3
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.enrichment.relation_support import VERIFIER_POLICY_VERSION
from backend.research_pipeline.enrichment.validator_v3 import VALIDATOR_VERSION, validate_enrichment_v3
from backend.research_pipeline.enrichment.prompt_v3 import PROMPT_VERSION, TRANSPORT_VERSION
from backend.research_pipeline.enrichment.canonical_normalizer import ALIAS_TABLE_VERSION, NORMALIZER_VERSION

ROOT = Path(__file__).parent
RESULTS = ROOT / "results_runtime_v4_paired_200"
VALIDATED_FOR_RELATION_SUPPORT = frozenset({"ENRICHMENT_V3_ACCEPTED"})
EVIDENCE_CONTEXT_POLICY_VERSION = "paper-evidence-context/1.0"


def relation_support_allowed(validation: dict[str, Any]) -> bool:
    """Return whether validation permits invoking the relation verifier."""
    return validation.get("outcome") in VALIDATED_FOR_RELATION_SUPPORT


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def target_rows() -> list[dict[str, Any]]:
    rows = [row for row in jsonl_rows(ROOT / "rq3_scoring_unit_manifest.jsonl") if row["sample_partition"] == "MAIN"]
    keys = [(row["candidate_id"], row["document_id"]) for row in rows]
    if len(rows) != 200 or len(set(keys)) != len(keys):
        raise RuntimeError(f"Frozen MAIN target invariant failed: rows={len(rows)}, unique={len(set(keys))}")
    return rows


def output_path(condition: str) -> Path:
    return RESULTS / f"rq3_{condition}_predictions_clean.jsonl"


def runtime_identity() -> dict[str, str]:
    return {
        "prompt_version": PROMPT_VERSION,
        "transport_version": TRANSPORT_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "verifier_policy_version": VERIFIER_POLICY_VERSION,
        "alias_table_version": ALIAS_TABLE_VERSION,
        "evidence_context_policy_version": EVIDENCE_CONTEXT_POLICY_VERSION,
    }


def write_execution_manifest() -> None:
    """Seal deterministic input identity before a paired run; no sample is regenerated."""
    manifest = ROOT / "rq3_scoring_unit_manifest.jsonl"
    units = ROOT / "sourceunits/sourceunits.jsonl"
    payload = {
        "benchmark_role": "FIXED_PAIRED_REGRESSION_DIAGNOSTIC_BENCHMARK",
        "main_rows": len(target_rows()), "top_k": 5,
        "runtime": runtime_identity(),
        "scoring_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "sourceunits_sha256": hashlib.sha256(units.read_bytes()).hexdigest(),
    }
    (RESULTS / "execution_manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def terminal_row(row: dict[str, Any]) -> bool:
    return isinstance(row.get("candidate_id"), str) and isinstance(row.get("document_id"), str) and isinstance(row.get("errors"), list)


def completed_keys(path: Path, authoritative_keys: set[tuple[str, str]]) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    done: set[tuple[str, str]] = set()
    for row in jsonl_rows(path):
        if not terminal_row(row):
            raise RuntimeError(f"Malformed persisted result in {path}")
        key = (row["candidate_id"], row["document_id"])
        if key not in authoritative_keys:
            raise RuntimeError(f"Non-target persisted result in {path}: {key}")
        if key in done:
            raise RuntimeError(f"Duplicate persisted target result in {path}: {key}")
        done.add(key)
    return done


@contextmanager
def condition_lock(condition: str) -> Iterator[None]:
    RESULTS.mkdir(parents=True, exist_ok=True)
    lock = RESULTS / f".rq3_{condition}.lock"
    acquired = False
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write("RQ3 evaluation condition lock\n")
        acquired = True
        yield
    finally:
        if acquired and lock.exists():
            lock.unlink()


def append_terminal(path: Path, row: dict[str, Any]) -> None:
    if not terminal_row(row):
        raise RuntimeError("Refusing to persist a non-terminal RQ3 result")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()


def run_condition(condition: str) -> None:
    if condition not in {"full_pipeline", "gold_context"}:
        raise ValueError(condition)
    RESULTS.mkdir(parents=True, exist_ok=True)
    write_execution_manifest()
    scoring = target_rows()
    authoritative_keys = {(row["candidate_id"], row["document_id"]) for row in scoring}
    refs = {row["candidate_id"]: row for row in jsonl_rows(ROOT / "annotation/main_reference_annotation_draft_v1.jsonl")}
    samples = {row["candidate_id"]: row["gca"] for row in jsonl_rows(ROOT / "rq3_main_sample_manifest.jsonl")}
    units: dict[str, list[dict[str, Any]]] = {}
    for row in jsonl_rows(ROOT / "sourceunits/sourceunits.jsonl"):
        units.setdefault(row["scoring_unit_id"], []).append({**row, "unit_type": row.get("source_unit_type")})
    out = output_path(condition)
    with condition_lock(condition):
        done = completed_keys(out, authoritative_keys)
        for scoring_row in scoring:
            key = (scoring_row["candidate_id"], scoring_row["document_id"])
            if key in done:
                continue
            candidate = samples[scoring_row["candidate_id"]]
            all_units = units.get(scoring_row["scoring_unit_id"], [])
            if condition == "full_pipeline":
                selected_ids = list(select(SourceUnitSelectionInput.from_candidate(candidate, scoring_row["document_id"], all_units), top_k=5).selected_source_unit_ids)
            else:
                selected_ids = refs[scoring_row["candidate_id"]]["gold_sourceunit_ids"]
            chosen = [unit for unit in all_units if unit["source_unit_id"] in selected_ids]
            try:
                call = call_enricher_v3("RQ3_" + condition.upper(), scoring_row["candidate_id"], scoring_row["document_id"], {}, candidate, chosen)
                validation = validate_enrichment_v3(call["transport_result"], call["enrichment"], candidate=candidate, paper_bundle={"document_id": scoring_row["document_id"], "resolved_source_unit_ids": selected_ids}, source_units_by_id={unit["source_unit_id"]: unit for unit in all_units})
                if relation_support_allowed(validation):
                    support = assess_relation_support(candidate, call["enrichment"])
                    result = {"candidate_id": scoring_row["candidate_id"], "document_id": scoring_row["document_id"], "selected_sourceunit_ids": selected_ids, "reader": call, "validator": validation, "field_support_states": support.get("fields", {}), "final_support": support["result"], "errors": []}
                else:
                    result = {"candidate_id": scoring_row["candidate_id"], "document_id": scoring_row["document_id"], "selected_sourceunit_ids": selected_ids, "reader": call, "validator": validation, "field_support_states": {}, "final_support": "UNVERIFIABLE", "errors": ["VALIDATION_NOT_ACCEPTED_FOR_RELATION_SUPPORT"]}
            except Exception as exc:
                result = {"candidate_id": scoring_row["candidate_id"], "document_id": scoring_row["document_id"], "selected_sourceunit_ids": selected_ids, "errors": [f"{type(exc).__name__}: {exc}"]}
            append_terminal(out, result)
            done.add(key)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=("full_pipeline", "gold_context", "both"), default="both")
    condition = parser.parse_args().condition
    if condition == "both":
        run_condition("full_pipeline")
        run_condition("gold_context")
    else:
        run_condition(condition)


if __name__ == "__main__":
    main()
