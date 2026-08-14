"""Install the exact frozen v2 candidate corpus after strict verification."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path


EXPECTED_NAME = "graph_candidate_repository_v2_candidates.jsonl"
EXPECTED_SHA256 = "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d"
DESTINATION = Path(
    "mtb-graphrag/benchmarks/mtb_evidence/document_grounded_claims/"
    "graph_candidate_repository/2.0/candidates.jsonl"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, *, require_release_name: bool) -> None:
    if require_release_name and path.name != EXPECTED_NAME:
        raise SystemExit(f"unexpected artifact filename: {path.name!r}")
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SystemExit(f"artifact is not strict UTF-8: {exc}") from exc
    observed = sha256(path)
    if observed != EXPECTED_SHA256:
        raise SystemExit(
            f"artifact SHA-256 mismatch: expected {EXPECTED_SHA256}, observed {observed}"
        )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <{EXPECTED_NAME}>")
    source = Path(sys.argv[1])
    if not source.is_file():
        raise SystemExit(f"artifact not found: {source}")
    verify(source, require_release_name=True)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, DESTINATION)
    verify(DESTINATION, require_release_name=False)
    print(f"installed and verified: {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
