"""Build the exact-byte package seal for dataset supplement S01."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NORMATIVE_FILES = (
    "README.md",
    "check_supplement.py",
    "hash_supplement.py",
    "provenance.json",
    "sourceunits_1697.jsonl",
    "supplement_manifest.json",
    "validation_report.json",
)


def sha256_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_package_hash(directory: Path = HERE) -> tuple[str, dict[str, str]]:
    files = {name: sha256_bytes(directory / name) for name in NORMATIVE_FILES}
    joined = "\n".join(f"{name}:{files[name]}" for name in sorted(files))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), files


def build_record(directory: Path = HERE) -> dict[str, object]:
    supplement_sha, files = compute_package_hash(directory)
    return {
        "supplement_id": "SOURCEUNIT_SELECTOR_INDEPENDENT_20_TEXT_S01",
        "classification": "PRE_FINAL_DATASET_SUPPLEMENT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "sha256",
        "file_hash_rule": "sha256 over each file's exact bytes; no newline or encoding normalization",
        "supplement_hash_rule": "sha256 of sorted 'relative_name:sha256' lines joined by LF",
        "normative_files": list(NORMATIVE_FILES),
        "files": files,
        "raw_source_sha256": "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99",
        "supplement_sha256": supplement_sha,
        "frozen": False,
        "review_status": "READY_FOR_HUMAN_REVIEW",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write supplement_hash.json")
    args = parser.parse_args()
    record = build_record()
    if args.write:
        (HERE / "supplement_hash.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(f"supplement_sha256 : {record['supplement_sha256']}")
    print(f"normative files   : {len(NORMATIVE_FILES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
