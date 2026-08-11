"""Schema-only table builders; values must come from raw observations."""

from __future__ import annotations

from typing import Any


TABLES = [f"Table {i}" for i in range(1, 13)] + ["Appendix A1"]


def build_table(table_name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if table_name not in TABLES:
        raise ValueError(f"unknown frozen table: {table_name}")
    if not rows:
        raise ValueError(f"{table_name}: required raw observations are absent")
    return {"table": table_name, "rows": rows}
