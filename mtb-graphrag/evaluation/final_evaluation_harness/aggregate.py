"""Fail-closed aggregation of immutable raw observations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_raw(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def aggregate(path: Path, required_fields: list[str]) -> dict[str, Any]:
    rows = load_raw(path)
    if not rows:
        raise ValueError("no raw observations")
    missing = sorted({field for row in rows for field in required_fields if field not in row})
    if missing:
        raise ValueError(f"missing raw fields: {missing}")
    return {"observation_count": len(rows), "rows": rows}
