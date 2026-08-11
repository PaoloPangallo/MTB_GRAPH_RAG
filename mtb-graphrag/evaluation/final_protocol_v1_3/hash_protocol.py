"""Deterministic pre-freeze seal for Protocol 1.3."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NORMATIVE_FILES = [
    "execution_environment_contract.json", "generation_configuration.json",
    "inherited_protocol_contract.json", "lineage.json", "model_identity_contract.json",
    "provider_metadata_contract.json", "protocol_manifest.json", "reproducibility_contract.json",
]

def protocol_digest() -> tuple[str, dict[str, str]]:
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in NORMATIVE_FILES}
    material = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), hashes

def main() -> None:
    digest, hashes = protocol_digest()
    manifest = json.loads((ROOT / "protocol_manifest.json").read_text(encoding="utf-8"))
    seal = {
        "protocol_id": manifest["protocol_id"], "protocol_version": "1.3",
        "protocol_1_3_sha256": digest, "normative_files": NORMATIVE_FILES,
        "files": hashes, "review_status": manifest["review_status"], "frozen": False,
        "runtime_commit": "3d2251f82a586535f79f3d0b3725c16330c365ba",
        "inherited_protocol_1_1_sha256": "83fcf870a3044b7c85de9c70ac3f7e2f4217e3a1e314368703bfefbce5d80889",
        "inherited_A01_sha256": "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf",
        "inherited_S01_raw_sha256": "83babfa59b0cf9cde320fe8fbdffd2d28c31b117d974bd4472c6015ee2a74f99",
        "inherited_S01_package_sha256": "b5979ac2f9ec7ae61fbf6bb929370e902f9f188de702d690ab71167d3d5a7f15",
        "parent_protocol_1_2_sha256": "76800b10ba85836369f47973802b0df65c0221df39ad8e9eac45a5241b70e106",
    }
    (ROOT / "protocol_hash.json").write_text(json.dumps(seal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(digest)

if __name__ == "__main__":
    main()
