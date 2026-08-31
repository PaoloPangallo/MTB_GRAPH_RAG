"""Generate only the RQ2 plan and integrity manifest; never run rankings."""
from __future__ import annotations

import json
from pathlib import Path

from .benchmark import INDEPENDENT, ROOT, S01, build_plan, load_dataset, selector_identity, sha256, validate_inputs

HERE = Path(__file__).resolve().parent


def main() -> None:
    invariants = validate_inputs()
    labels, _, _ = load_dataset()
    pair_ids = [f"{candidate_id}|{document_id}" for candidate_id, document_id in labels]
    plan = build_plan(pair_ids)
    assert len(plan) == 60 and len({row["unit_id"] for row in plan}) == 60
    assert {row["retrieval_method"] for row in plan} == {"FIRST_K", "BM25", "DETERMINISTIC_SELECTOR"}
    (HERE / "sealed_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    files = {
        "candidate_inventory": INDEPENDENT / "candidate_inventory.jsonl",
        "gold_annotations": INDEPENDENT / "gold_annotations.csv",
        "gold_annotation_manifest": INDEPENDENT / "gold_annotation_manifest.json",
        "s01_sourceunit_corpus": S01,
        "protocol": HERE / "PROTOCOL.md",
        "sealed_plan": HERE / "sealed_plan.json",
    }
    manifest = {"rq2_protocol_version": "sourceunit-retrieval-benchmark/2.0", "invariants": invariants,
                "input_sha256": {name: sha256(path) for name, path in files.items()},
                "selector_identity": selector_identity(), "ranking_execution": "NOT_EXECUTED"}
    (HERE / "input_hashes.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
