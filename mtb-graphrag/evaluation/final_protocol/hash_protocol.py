"""Hash del protocollo di final evaluation.

Sigilla i documenti e le specifiche che definiscono la valutazione. Va rieseguito
dopo ogni modifica al protocollo: un `protocol_sha256` diverso da quello citato
in un report significa che quel report è stato prodotto sotto un'altra versione
del protocollo.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = Path(__file__).resolve().parent / "protocol_hash.json"

PROTOCOL_VERSION = "mtb-graphrag-final-evaluation/1.0"
RUNTIME_COMMIT = "f52bbf5920c14324953be849e666bc84571957e9"

#: I file che *definiscono* il protocollo. `protocol_hash.json` è escluso per
#: costruzione: non può contenere il proprio hash.
PROTOCOL_FILES = (
    "docs/final_evaluation/final_evaluation_protocol.md",
    "docs/final_evaluation/claim_evidence_matrix.md",
    "docs/final_evaluation/limitations.md",
    "evaluation/final_protocol/build_manifests.py",
    "evaluation/final_protocol/dataset_manifest.json",
    "evaluation/final_protocol/dataset_hashes.json",
    "evaluation/final_protocol/split_manifest.json",
    "evaluation/final_protocol/failure_taxonomy.json",
    "evaluation/final_protocol/metrics_registry.json",
    "evaluation/final_protocol/success_criteria.json",
)


def _sha256_file(path: Path) -> str:
    """SHA-256 con fine riga normalizzati a LF, come in ``build_manifests``.

    Senza normalizzazione il ``protocol_sha256`` dipenderebbe dalla piattaforma
    del clone e non sarebbe verificabile da un revisore.
    """
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build() -> dict[str, object]:
    files: dict[str, str] = {}
    for relative in sorted(PROTOCOL_FILES):
        path = REPO_ROOT / relative
        if not path.exists():
            raise FileNotFoundError(f"file di protocollo mancante: {relative}")
        files[relative] = _sha256_file(path)

    joined = "\n".join(f"{name}:{digest}" for name, digest in sorted(files.items()))
    protocol_sha = hashlib.sha256(joined.encode("utf-8")).hexdigest()

    dataset_hashes = json.loads(
        (REPO_ROOT / "evaluation/final_protocol/dataset_hashes.json").read_text(encoding="utf-8"))

    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "sha256",
        "file_hash_rule": "sha256 of the file bytes with CRLF normalized to LF (platform-independent)",
        "protocol_hash_rule": "sha256 of the sorted 'relative_path:file_sha256' lines joined by \\n",
        "files": files,
        "protocol_sha256": protocol_sha,
        "dataset_bundle_sha256": dataset_hashes["dataset_bundle_sha256"],
        "frozen": False,
        "freeze_note": "frozen=false finché il protocollo non è approvato. Il freeze si registra impostando frozen=true e rieseguendo questo script.",
    }
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


if __name__ == "__main__":
    result = build()
    print(f"protocol_sha256      : {result['protocol_sha256']}")
    print(f"dataset_bundle_sha256: {result['dataset_bundle_sha256']}")
    print(f"files sealed         : {len(result['files'])}")
