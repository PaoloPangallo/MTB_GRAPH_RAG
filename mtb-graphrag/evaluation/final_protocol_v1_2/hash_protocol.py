"""Create the deterministic protocol 1.2 seal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
NORMATIVE_FILES = [
    "ablation_contract.json",
    "dataset_registry.json",
    "execution_contract.json",
    "latency_contract.json",
    "lineage.json",
    "metric_registry.json",
    "protocol_manifest.json",
    "reliability_contract.json",
    "result_schemas.json",
    "statistical_plan.json",
    "success_criteria.json",
]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol_digest() -> tuple[str, dict[str, str]]:
    file_hashes = {name: _digest(ROOT / name) for name in NORMATIVE_FILES}
    material = "\n".join(
        f"{name}:{file_hashes[name]}" for name in sorted(file_hashes)
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), file_hashes


def main() -> None:
    digest, file_hashes = protocol_digest()
    manifest = json.loads((ROOT / "protocol_manifest.json").read_text(encoding="utf-8"))
    freeze_timestamp = manifest["freeze_timestamp"]
    seal = {
        "protocol_id": "mtb-graphrag-final-evaluation/1.2",
        "protocol_version": "1.2",
        "protocol_1_2_sha256": digest,
        "normative_files": NORMATIVE_FILES,
        "files": file_hashes,
        "generated_at": freeze_timestamp,
        "freeze_timestamp": freeze_timestamp,
        "review_status": manifest["review_status"],
        "frozen": manifest["frozen"],
        "runtime_commit": "3d2251f82a586535f79f3d0b3725c16330c365ba",
        "inherited_1_1_sha256": "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889",
        "inherited_A01_sha256": "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf",
        "S01_raw_sha256": "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99",
        "S01_package_sha256": "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15",
        "ancestor_identities": {
            "runtime_commit": "3d2251f82a586535f79f3d0b3725c16330c365ba",
            "protocol_1_1_sha256": "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889",
            "A01_sha256": "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf",
            "S01_raw_sha256": "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99",
            "S01_package_sha256": "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15",
        },
    }
    (ROOT / "protocol_hash.json").write_text(
        json.dumps(seal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(digest)


if __name__ == "__main__":
    main()
