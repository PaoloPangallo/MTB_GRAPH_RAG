"""Seal RQ2 v2.1 inputs and plan without executing retrieval."""
from __future__ import annotations

import json

from .benchmark import HERE, RQ2_VERSION, build_plan, input_files, selector_identity, sha256, validate_inputs


def main() -> None:
    invariants = validate_inputs()
    plan = build_plan()
    assert len(plan) == len({row["unit_id"] for row in plan}) == 60
    assert {row["retrieval_method"] for row in plan} == {"FIRST_K", "BM25", "DETERMINISTIC_SELECTOR"}
    (HERE / "sealed_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    second = build_plan()
    assert plan == second
    files = input_files()
    manifest = {
        "rq2_protocol_version": RQ2_VERSION,
        "invariants": invariants,
        "input_sha256": {name: sha256(path) for name, path in files.items()},
        "selector_identity": selector_identity(),
        "plan_deterministic": True,
        "ranking_execution": "NOT_EXECUTED",
    }
    (HERE / "input_hashes.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
