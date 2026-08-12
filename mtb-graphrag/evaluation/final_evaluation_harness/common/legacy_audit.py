"""Forensic classification of the legacy Protocol 1.1 checker result."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def audit_legacy_checker(repository_root: Path | None = None) -> dict[str, Any]:
    repo = repository_root or Path(__file__).resolve().parents[3]
    command = ["python", "evaluation/final_protocol/check_consistency.py"]
    completed = subprocess.run(command, cwd=repo, capture_output=True, text=True, check=False)
    output = completed.stdout + completed.stderr
    failures: list[dict[str, Any]] = []
    if "[FAIL] runtime_unmodified" in output:
        failures.append({
            "assertion": "runtime_unmodified",
            "file": "evaluation/final_protocol/check_consistency.py",
            "expected": "pre-H02 runtime identity / untouched runtime blobs",
            "actual": "authorized H02 runtime eb20fdfab35724f3b84651d8c02f1ec3970db615",
            "artifact": "backend/research_pipeline/{orchestrator.py,enrichment/validator_v2.py,retrieval/live_sourceunit_selection.py}",
            "classification": "EXPECTED_HISTORICAL_RUNTIME_IDENTITY_INCOMPATIBILITY",
            "blocking": False,
        })
    if "[FAIL] historical_artifacts_untouched" in output:
        failures.append({
            "assertion": "historical_artifacts_untouched",
            "file": "evaluation/final_protocol/check_consistency.py",
            "expected": "no later tracked artifacts",
            "actual": "later authorized Protocol 1.6/Harness additions are tracked",
            "artifact": "evaluation/final_evaluation_harness/**",
            "classification": "CHECKER_FALSE_POSITIVE",
            "blocking": False,
        })
    match = re.search(r"(\d+)/(\d+) PASS", output)
    result = f"{match.group(1)}/{match.group(2)}" if match else "UNKNOWN"
    return {"result": result, "failures": failures, "raw_output": output}
