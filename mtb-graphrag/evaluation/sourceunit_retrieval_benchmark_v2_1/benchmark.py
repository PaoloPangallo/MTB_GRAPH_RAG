"""RQ2 v2.1 sealing utilities; this module never ranks or calls providers."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from backend.research_pipeline.experimental.sourceunit_selector import (
    BM25_B,
    BM25_K1,
    SELECTOR_VERSION,
)

RQ2_VERSION = "sourceunit-retrieval-benchmark/2.1"
TOP_K = 5
ARMS = ("FIRST_K", "BM25", "DETERMINISTIC_SELECTOR")
LABELS = ("DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT", "CONTEXT_ONLY", "NOT_RELEVANT")
REMOVED_PAIR = "GCA-002decb1b8be445d9dad8730|pmid:231047"
REPLACEMENT_PAIR = "GCA-00e16c83d9144ac87139b7a3|pmid:15928335"
ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evaluation" / "sourceunit_selector_external_validation_20_v2"
V1_DATASET = ROOT / "evaluation" / "sourceunit_selector_independent"
V1_S01 = ROOT / "evaluation" / "final_protocol" / "supplements" / "S01" / "sourceunits_1697.jsonl"
HERE = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_labels(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    labels: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["candidate_id"], row["document_id"])
            labels[key][row["source_unit_id"]] = row["relevance_label"]
    return dict(labels)


def load_dataset() -> tuple[dict[tuple[str, str], dict[str, str]], dict[tuple[str, str], list[dict[str, Any]]], list[dict[str, Any]]]:
    """Load the frozen v2.1 inputs only; deliberately no ranking dispatch exists."""
    labels = _read_labels(DATASET / "gold_annotations.csv")
    units: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(DATASET / "sourceunits.jsonl"):
        units[(row["candidate_id"], row["document_id"])].append(row)
    return labels, dict(units), _read_jsonl(DATASET / "candidate_inventory.jsonl")


def build_plan(pair_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    if pair_ids is None:
        labels, _, _ = load_dataset()
        pair_ids = (f"{candidate_id}|{document_id}" for candidate_id, document_id in labels)
    return [
        {
            "unit_id": f"RQ2::{pair_id}::{method}",
            "rq2_version": RQ2_VERSION,
            "pair_id": pair_id,
            "retrieval_method": method,
            "top_k": TOP_K,
            "execution_class": "OFFLINE_RANKING_ONLY",
            "provider_requirement": "PROHIBITED",
            "reader_requirement": "PROHIBITED",
            "gold_role": "GROUND_TRUTH_ONLY",
        }
        for pair_id in sorted(pair_ids)
        for method in ARMS
    ]


def selector_identity() -> dict[str, Any]:
    selector_path = ROOT / "backend" / "research_pipeline" / "experimental" / "sourceunit_selector.py"
    return {
        "module": "backend.research_pipeline.experimental.sourceunit_selector",
        "version": SELECTOR_VERSION,
        "file_sha256": sha256(selector_path),
        "bm25_k1": BM25_K1,
        "bm25_b": BM25_B,
        "functions": {"FIRST_K": "select_first_k", "BM25": "select_bm25", "DETERMINISTIC_SELECTOR": "select"},
    }


def validate_inputs() -> dict[str, Any]:
    labels, units, candidates = load_dataset()
    candidate_pairs = {(row["candidate_id"], row["document_id"]) for row in candidates}
    unit_pairs = set(units)
    label_counts = Counter(label for pair in labels.values() for label in pair.values())
    replacement_key = tuple(REPLACEMENT_PAIR.split("|", 1))
    replacement_counts = Counter(labels[replacement_key].values())
    v1 = _read_labels(V1_DATASET / "gold_annotations.csv")
    retained_v1 = {key: value for key, value in v1.items() if "|".join(key) != REMOVED_PAIR}
    retained_v2 = {key: value for key, value in labels.items() if key != replacement_key}
    changes = sum(
        1
        for key, source_labels in retained_v1.items()
        for source_unit_id, label in source_labels.items()
        if retained_v2.get(key, {}).get(source_unit_id) != label
    )
    strict = sum(any(label == "DIRECTLY_RELEVANT" for label in pair.values()) for pair in labels.values())
    broad = sum(any(label in {"DIRECTLY_RELEVANT", "PARTIALLY_RELEVANT"} for label in pair.values()) for pair in labels.values())
    assert len(labels) == len(units) == len(candidate_pairs) == 20
    assert candidate_pairs == set(labels) == unit_pairs
    assert REMOVED_PAIR not in {f"{candidate_id}|{document_id}" for candidate_id, document_id in labels}
    assert REPLACEMENT_PAIR in {f"{candidate_id}|{document_id}" for candidate_id, document_id in labels}
    assert sum(len(rows) for rows in units.values()) == 1706
    assert label_counts == Counter({"DIRECTLY_RELEVANT": 30, "PARTIALLY_RELEVANT": 51, "CONTEXT_ONLY": 364, "NOT_RELEVANT": 1261})
    assert replacement_counts == Counter({"DIRECTLY_RELEVANT": 3, "PARTIALLY_RELEVANT": 2, "CONTEXT_ONLY": 9})
    assert len(units[replacement_key]) == len(labels[replacement_key]) == 14
    assert changes == 0 and set(retained_v1) == set(retained_v2)
    assert strict == 9 and broad == 10 and len(labels) - broad == 10
    return {
        "pair_count": 20,
        "sourceunit_count": 1706,
        "strict_positive_pairs": strict,
        "broad_positive_pairs": broad,
        "broad_negative_pairs": len(labels) - broad,
        "label_counts": {label: label_counts[label] for label in LABELS},
        "replacement_annotation_counts": {label: replacement_counts[label] for label in LABELS},
        "retained_gold_label_changes": changes,
    }


def verify_input_hashes() -> bool:
    manifest = json.loads((HERE / "input_hashes.json").read_text(encoding="utf-8"))
    files = input_files()
    return all(manifest["input_sha256"].get(name) == sha256(path) for name, path in files.items())


def input_files() -> dict[str, Path]:
    remediation = ROOT / "evaluation" / "sourceunit_selector_external_validation_v2_1_remediation"
    return {
        "dataset_manifest": DATASET / "dataset_manifest.json",
        "candidate_inventory": DATASET / "candidate_inventory.jsonl",
        "document_inventory": DATASET / "document_inventory.jsonl",
        "sourceunit_corpus": DATASET / "sourceunits.jsonl",
        "gold_annotations": DATASET / "gold_annotations.csv",
        "annotation_manifest": DATASET / "gold_annotation_manifest.json",
        "remediation_manifest": remediation / "remediation_manifest.json",
        "replacement_selection_manifest": remediation / "replacement_selection_manifest.json",
        "protocol": HERE / "PROTOCOL.md",
        "sealed_plan": HERE / "sealed_plan.json",
        "benchmark_implementation": HERE / "benchmark.py",
        "selector_production_file": ROOT / "backend" / "research_pipeline" / "experimental" / "sourceunit_selector.py",
    }
