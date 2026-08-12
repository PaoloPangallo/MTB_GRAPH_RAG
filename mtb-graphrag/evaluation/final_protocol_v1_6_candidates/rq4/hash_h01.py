from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent


def _content(name: str) -> bytes:
    path = ROOT / name
    if name == "review_report.json":
        value = json.loads(path.read_text(encoding="utf-8"))
        value.pop("normative_sha256", None)
        value.pop("support_sha256", None)
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return path.read_bytes()


def _manifest(names: list[str]) -> bytes:
    entries = []
    for name in sorted(names):
        path = ROOT / name
        entries.append({"path": path.as_posix(), "sha256": hashlib.sha256(_content(name)).hexdigest()})
    return json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(names: list[str]) -> str:
    return hashlib.sha256(_manifest(names)).hexdigest()


def main() -> None:
    policy = json.loads((ROOT / "normative_hash_policy.json").read_text(encoding="utf-8"))
    normative = policy["normative_files"]
    support = policy["support_files"]
    print(json.dumps({
        "normative_sha256": digest(normative),
        "normative_sha256_repeat": digest(normative),
        "support_sha256": digest(support),
        "support_sha256_repeat": digest(support),
        "normative_files": sorted(normative),
        "support_files": sorted(support),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
