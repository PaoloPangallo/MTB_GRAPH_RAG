"""Canonical resolution of sealed-plan case identifiers.

The frozen RQ3 plan uses ``FULL_SYSTEM`` as a testbed-level symbolic alias.
The production runtime, however, consumes the existing canonical demo-case
registry.  Resolution is kept at this transport boundary so ablation arms
remain selected by the executor registry, never by case lookup.
"""

from __future__ import annotations

from copy import deepcopy
import json
from functools import lru_cache
from typing import Any

from backend.research_pipeline.cases.definitions import CASES


_CANONICAL_CASES = {case["case_id"]: case for case in CASES}

# ``FULL_SYSTEM`` is the frozen RQ3 symbolic case used by the plan.  The
# existing CASE-1 fixture is the canonical full-system regression input used
# throughout the runtime/API tests; no new clinical case is introduced here.
_ALIASES = {"FULL_SYSTEM": "CASE-1-therapy-evaluation-strong-match"}


@lru_cache(maxsize=1)
def _frozen_fixture_cases() -> dict[str, dict[str, Any]]:
    """Load runtime-only case text from frozen RQ4 fixture corpora.

    Held-out evaluation metadata is deliberately projected to only ``case_id``
    and ``text`` here.  Gold/challenge fields are loaded later, after raw
    persistence, by the H01 evaluator boundary.
    """
    root = __import__("pathlib").Path(__file__).resolve().parents[3] / "evaluation"
    fixtures: dict[str, dict[str, Any]] = {}
    development = root / "rq4_casecontext_robustness" / "benchmark.jsonl"
    for line in development.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        fixtures[row["case_id"]] = {
            "case_id": row["case_id"],
            "clinical_text": row["text"],
            "source_fixture": "RQ4_DEVELOPMENT",
        }
    heldout = root / "final_protocol" / "heldout" / "architectural_challenge_cases.json"
    rows = json.loads(heldout.read_text(encoding="utf-8"))["cases"]
    for row in rows:
        fixtures[row["case_id"]] = {
            "case_id": row["case_id"],
            "clinical_text": row["text"],
            "source_fixture": "RQ4_HELDOUT",
        }
    return fixtures


def resolve_production_case(case_id: str) -> tuple[str, dict[str, Any]]:
    """Resolve a sealed-plan ID to an existing immutable production case.

    Unknown IDs fail closed; no default or fuzzy fallback is permitted.
    """

    if not isinstance(case_id, str) or not case_id:
        raise RuntimeError(f"REAL_EXECUTION_INPUT_NOT_RESOLVED:{case_id}")
    resolved_id = _ALIASES.get(case_id, case_id)
    case = _CANONICAL_CASES.get(resolved_id)
    if case is None:
        case = _frozen_fixture_cases().get(case_id)
    if case is None:
        raise RuntimeError(f"REAL_EXECUTION_INPUT_NOT_RESOLVED:{case_id}")
    return resolved_id, deepcopy(case)


def production_case_ids() -> tuple[str, ...]:
    """Return all concrete production case IDs available to the resolver."""

    return tuple(sorted(_CANONICAL_CASES))
