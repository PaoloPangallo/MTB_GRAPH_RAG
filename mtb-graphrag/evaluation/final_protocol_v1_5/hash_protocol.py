"""Canonical pre-freeze Protocol 1.5 artifact hash."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = [
    "evaluation/final_protocol_v1_5/amendment_contract.json",
    "evaluation/final_protocol_v1_5/corpus_identity.json",
    "evaluation/final_protocol_v1_5/inherited_protocol_contract.json",
    "evaluation/final_protocol_v1_5/lineage.json",
    "evaluation/final_protocol_v1_5/protocol_manifest.json",
    "evaluation/final_protocol_v1_5/scientific_projection.json",
    "docs/final_evaluation/v1_5/final_evaluation_protocol_1_5.md",
]

def main() -> int:
    h = hashlib.sha256()
    for name in FILES:
        data = (ROOT / name).read_bytes()
        h.update(name.encode("utf-8")); h.update(b"\0"); h.update(data); h.update(b"\0")
    result = {"protocol_version":"1.5", "pre_freeze":True, "files":FILES, "protocol_sha256":h.hexdigest()}
    (HERE / "protocol_hash.json").write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(result["protocol_sha256"])
    return 0
if __name__ == "__main__": raise SystemExit(main())
