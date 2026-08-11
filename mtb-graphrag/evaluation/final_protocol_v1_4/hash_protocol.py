"""Deterministic pre-freeze hash for Protocol 1.4."""
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NORMATIVE_FILES = ["amendment_contract.json", "inherited_protocol_contract.json", "lineage.json", "protocol_manifest.json"]

def protocol_digest() -> tuple[str, dict[str, str]]:
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in NORMATIVE_FILES}
    material = "\n".join(f"{name}:{hashes[name]}" for name in sorted(hashes))
    return hashlib.sha256(material.encode("utf-8")).hexdigest(), hashes

if __name__ == "__main__":
    digest, _ = protocol_digest()
    print(digest)
