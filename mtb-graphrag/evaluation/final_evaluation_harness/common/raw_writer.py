"""Immutable raw attempt writer."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


class DuplicateAttempt(RuntimeError):
    """Attempt output already exists and may not be overwritten."""


def _json_ready(value: Any) -> Any:
    """Convert approved domain representations without lossy fallbacks."""
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("raw payload mapping keys must be strings")
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    serializer = getattr(value, "to_row", None)
    if callable(serializer):
        return _json_ready(serializer())
    serializer = getattr(value, "to_dict", None)
    if callable(serializer):
        return _json_ready(serializer())
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def write_raw_once(root: Path, attempt_id: str, payload: dict[str, Any]) -> tuple[Path, str]:
    if not re.fullmatch(r"run_[0-9a-f]{64}/a[0-9]{4}", attempt_id):
        raise ValueError("invalid attempt_id")
    safe = attempt_id.replace("/", "__")
    path = root / f"{safe}.json"
    if path.exists():
        raise DuplicateAttempt(attempt_id)
    ready_payload = _json_ready(payload)
    encoded = (json.dumps(ready_payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise DuplicateAttempt(attempt_id) from exc
    return path, hashlib.sha256(encoded).hexdigest()
