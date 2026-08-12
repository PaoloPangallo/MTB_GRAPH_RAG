from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parent


def repository_root(start: Path = ROOT) -> Path:
    result = subprocess.run(
        ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip()).resolve()


def canonical_repository_path(path: Path, repo: Path | None = None) -> str:
    repo = (repo or repository_root()).resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(repo)
    except ValueError as exc:
        raise ValueError(f"artifact outside repository: {path}") from exc
    value = relative.as_posix()
    if value.startswith("../") or value == ".." or Path(value).is_absolute() or ":" in value:
        raise ValueError(f"invalid repository-relative path: {value}")
    return value


def _content(name: str, artifact_root: Path = ROOT) -> bytes:
    path = artifact_root / name
    if name == "review_report.json":
        value = json.loads(path.read_text(encoding="utf-8"))
        value.pop("normative_sha256", None)
        value.pop("support_sha256", None)
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return path.read_bytes()


def _manifest(names: list[str], artifact_root: Path = ROOT, repo_root: Path | None = None) -> bytes:
    return json.dumps(manifest_entries(names, artifact_root=artifact_root, repo_root=repo_root), sort_keys=True, separators=(",", ":")).encode("utf-8")


def manifest_entries(names: list[str], artifact_root: Path = ROOT, repo_root: Path | None = None) -> list[dict[str, str]]:
    entries = []
    for name in sorted(names):
        path = artifact_root / name
        entries.append({"path": canonical_repository_path(path, repo=repo_root), "sha256": hashlib.sha256(_content(name, artifact_root)).hexdigest()})
    return entries


def digest(names: list[str], artifact_root: Path = ROOT, repo_root: Path | None = None) -> str:
    return hashlib.sha256(_manifest(names, artifact_root=artifact_root, repo_root=repo_root)).hexdigest()


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
