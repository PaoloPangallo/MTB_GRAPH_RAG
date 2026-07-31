"""Safe CLI. In this freeze commit, official mode is intentionally closed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .harness import guard_official_mode, plan_runs, validate_frozen_inputs

SCHEMA_VERSION = "mtb-final-experiment-runner/1.0"
BASE_COMMIT = "84bcecaafdee60206799fd0a245cb78f816b257e"
CORPUS_VERSION = "qualified_claim_repository/1.4"
CORPUS_HASH = "31636f26c44bee03b16ed7d7c5e9b9580292f750e04b80e4effbaf9618ec39fa"
GATE_VERSION = "qualified_claim_structural_gate/1.3"
RETRIEVER_VERSION = "qualified_claim_retriever/1.0"
GENERATOR_VERSION = "final_experiment_generator/1.0"
CONTENT_SHA256 = "98d3875f247971c3e5b8e5cc15aebe92a9346057459bbf30288ccea3077fe7a0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("plan", "smoke", "official"))
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if args.mode == "official":
        guard_official_mode(root / "gold_external_manifest.json")
    validated = validate_frozen_inputs(root)
    if args.mode == "smoke":
        from .smoke import run_smoke
        report = run_smoke()
        print(json.dumps({
            "pilot_only": report["pilot_only"],
            "final_evaluable": report["final_evaluable"],
            "checks": report["checks"],
            "validated_inputs": validated,
        }, sort_keys=True))
        return 0
    systems = json.loads((root / "systems_v1.json").read_text(encoding="utf-8"))
    queries = [
        json.loads(line)
        for line in (root / "queries_v1.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    planned = plan_runs(systems, queries)
    runnable = sum(row["model"] != "ROBUSTNESS_MODEL_BLOCKED" for row in planned)
    print(json.dumps({
        "planned_system_runs": len(planned),
        "runnable_system_runs": runnable,
        "blocked_system_runs": len(planned) - runnable,
        "blocked_reason": "robustness model unavailable",
        "unique_run_keys": len({row["run_key"] for row in planned}),
        "validated_inputs": validated,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())