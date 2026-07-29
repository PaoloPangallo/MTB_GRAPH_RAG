"""Registra separatamente cio' che la chiusura ermetica ha misurato.

I conteggi non vanno sommati fra loro. Un numero che mescola «test saltati
perche' manca il gold» e «test saltati perche' manca la cache degli abstract»
non dice niente su nessuno dei due, ed e' esattamente il modo in cui
ottantaquattro test della cache sono stati contati per anni fra gli skip del
gold.

Il report tiene percio' cinque registri distinti:

    core        eseguiti, passati e saltati — con la ragione di ogni skip
    gold        test non eseguiti dalla suite core, e da quale albero
    cache       gli stessi, per l'altro ingresso, contati a parte
    policy      sotto quale politica di hash le impronte sono state misurate
    erratum     quanti file sono verificati tramite quale erratum

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_hermetic_closure_report
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.pipeline.evidence.integrity import hash_policy as POLICY  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
CLOSURE_DIR = (
    REPO_ROOT / "benchmarks" / "mtb_evidence" / "v3" / "hermetic_reproducibility_closure"
)
REPORT_PATH = CLOSURE_DIR / "closure_report.json"

SCHEMA_VERSION = "hermetic_closure_report/1.0"
PHASE = "hermetic-reproducibility-closure/1.0"


def _count_tests(suite: str) -> int:
    """Quanti test raccoglie pytest in questo albero. Nessuno viene eseguito."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", suite, "-q", "--collect-only"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PYTHONPATH": ".", **_environ_without_external_inputs()},
    )
    for line in reversed(result.stdout.splitlines()):
        if "test" in line and "collected" in line:
            return int(line.split()[0])
    return -1


def _environ_without_external_inputs() -> dict[str, str]:
    import os

    return {
        key: value
        for key, value in os.environ.items()
        if key not in ("MTB_GOLD_BUNDLE", "MTB_SOURCE_ABSTRACT_CACHE")
    }


def _modules(suite: str) -> list[str]:
    return sorted(
        path.name for path in (REPO_ROOT / suite).glob("test_*.py")
    )


def build(matrix: dict[str, Any] | None = None) -> dict[str, Any]:
    artifact_erratum = json.loads(
        (CLOSURE_DIR / "artifact_hash_erratum.json").read_text(encoding="utf-8")
    )
    provenance_erratum = json.loads(
        (CLOSURE_DIR / "generator_provenance_erratum.json").read_text(encoding="utf-8")
    )

    return {
        "core_suite": {
            "collected": _count_tests("backend/tests"),
            "discovery_root": "backend/tests",
            "environments": matrix or {},
            "opens_external_input": False,
        },
        "external_suites": {
            "gold": {
                "collected": _count_tests("backend/tests_external/gold"),
                "command": (
                    "python -m benchmarks.mtb_evidence.evaluation."
                    "run_gold_evaluation --gold-bundle <PATH>"
                ),
                "modules": _modules("backend/tests_external/gold"),
                "not_run_by_core_suite": True,
                "tree": "backend/tests_external/gold",
            },
            "source_cache": {
                "collected": _count_tests("backend/tests_external/source_cache"),
                "command": (
                    "python -m benchmarks.mtb_evidence.evaluation."
                    "run_source_cache_validation --source-abstract-cache <PATH>"
                ),
                "modules": _modules("backend/tests_external/source_cache"),
                "not_run_by_core_suite": True,
                "tree": "backend/tests_external/source_cache",
            },
        },
        "hash_policy": {
            "computed_from": "read_bytes",
            "lone_carriage_return": "rejected",
            "normalization": POLICY.NORMALIZATION,
            "version": POLICY.POLICY_VERSION,
        },
        "phase": PHASE,
        "schema_version": SCHEMA_VERSION,
        "verified_through_erratum": {
            "artifact_hash_erratum": {
                "artifacts": artifact_erratum["counts"]["artifacts"],
                "reason_code": POLICY.REASON_LEGACY_LINE_ENDING,
                "references": artifact_erratum["counts"]["references"],
                "schema_version": artifact_erratum["schema_version"],
                "sources": artifact_erratum["counts"]["sources"],
            },
            "generator_provenance_erratum": {
                "declared": provenance_erratum["counts"]["declared"],
                "diverging": provenance_erratum["counts"]["diverging"],
                "reason_code": "GENERATOR_SOURCE_EVOLVED_AFTER_FROZEN_ARTIFACT",
                "schema_version": provenance_erratum["schema_version"],
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--matrix",
        type=Path,
        default=None,
        help="JSON con i conteggi per ambiente, misurati e non dedotti",
    )
    args = parser.parse_args(argv)

    matrix = (
        json.loads(args.matrix.read_text(encoding="utf-8")) if args.matrix else None
    )
    report = build(matrix)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"scritto {REPORT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
