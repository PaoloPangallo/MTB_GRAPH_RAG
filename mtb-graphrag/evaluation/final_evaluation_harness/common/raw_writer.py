"""Immutable raw attempt writer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DuplicateAttempt(RuntimeError):
    """Attempt output already exists and may not be overwritten."""


def write_raw_once(root: Path, attempt_id: str, payload: dict[str, Any]) -> tuple[Path, str]:
    safe = attempt_id.replace("/", "__")
    path = root / f"{safe}.json"
    if path.exists():
        raise DuplicateAttempt(attempt_id)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(encoded)
    return path, hashlib.sha256(encoded).hexdigest()
