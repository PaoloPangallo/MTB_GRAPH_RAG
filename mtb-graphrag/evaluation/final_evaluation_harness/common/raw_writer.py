"""Immutable raw attempt writer."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


class DuplicateAttempt(RuntimeError):
    """Attempt output already exists and may not be overwritten."""


def write_raw_once(root: Path, attempt_id: str, payload: dict[str, Any]) -> tuple[Path, str]:
    if not re.fullmatch(r"run_[0-9a-f]{64}/a[0-9]{4}", attempt_id):
        raise ValueError("invalid attempt_id")
    safe = attempt_id.replace("/", "__")
    path = root / f"{safe}.json"
    if path.exists():
        raise DuplicateAttempt(attempt_id)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(encoded)
    except FileExistsError as exc:
        raise DuplicateAttempt(attempt_id) from exc
    return path, hashlib.sha256(encoded).hexdigest()
