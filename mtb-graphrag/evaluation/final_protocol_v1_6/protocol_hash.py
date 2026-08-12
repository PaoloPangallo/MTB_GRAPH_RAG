from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = [
    "evaluation/final_protocol_v1_6/amendment_contract.json",
    "evaluation/final_protocol_v1_6/corpus_identity.json",
    "evaluation/final_protocol_v1_6/inherited_protocol_contract.json",
    "evaluation/final_protocol_v1_6/lineage.json",
    "evaluation/final_protocol_v1_6/protocol_manifest.json",
    "evaluation/final_protocol_v1_6/scientific_projection.json",
    "evaluation/final_protocol_v1_6/protocol.md",
]

def digest() -> str:
    h = hashlib.sha256()
    for name in FILES:
        h.update(name.encode("utf-8")); h.update(b"\0")
        h.update((ROOT / name).read_bytes()); h.update(b"\0")
    return h.hexdigest()

if __name__ == "__main__":
    value = digest()
    print(json.dumps({"protocol_version":"1.6", "pre_freeze":True, "files":FILES, "protocol_sha256":value, "protocol_sha256_repeat":digest()}, sort_keys=True))
