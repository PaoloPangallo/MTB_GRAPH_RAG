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

PROTOCOL_VERSION = "mtb-graphrag-final-evaluation/1.1"
RUNTIME_COMMIT = "3d2251f82a586535f79f3d0b3725c16330c365ba"
#: Runtime storico sostituito nel riallineamento pre-freeze del 2026-08-10.
#: Resta nel sigillo come provenance: dice sotto quale architettura il
#: protocollo era stato scritto la prima volta.
PREVIOUS_RUNTIME_COMMIT = "f52bbf5920c14324953be849e666bc84571957e9"

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
    "evaluation/final_protocol/result_schemas.json",
    "evaluation/final_protocol/reliability_subset.json",
    "evaluation/final_protocol/build_reliability_subset.py",
    "evaluation/final_protocol/heldout/build_heldout.py",
    "evaluation/final_protocol/heldout/architectural_challenge_cases.json",
    "evaluation/final_protocol/heldout/architectural_challenge_gold.json",
    "evaluation/final_protocol/heldout/narrative_heldout_cases.json",
    "evaluation/final_protocol/heldout/narrative_heldout_gold.json",
    "evaluation/final_protocol/heldout/narrative_heldout_valid_control.json",
    "evaluation/final_protocol/heldout/overlap_report.json",
    "evaluation/final_protocol/heldout/grounded_review.json",
    "evaluation/final_protocol/heldout/heldout_manifest.json",
    "evaluation/final_protocol/heldout/heldout_hashes.json",
    "docs/final_evaluation/heldout_review.md",
    "docs/final_evaluation/scientific_blueprint_reference.md",
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
        "previous_runtime_commit": PREVIOUS_RUNTIME_COMMIT,
        "reseal_note": (
            "Protocol 1.1 resealed against the final single canonical runtime "
            "before experimental freeze."
        ),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash_algorithm": "sha256",
        "file_hash_rule": "sha256 of the file bytes with CRLF normalized to LF (platform-independent)",
        "protocol_hash_rule": "sha256 of the sorted 'relative_path:file_sha256' lines joined by \\n",
        "files": files,
        "protocol_sha256": protocol_sha,
        "dataset_bundle_sha256": dataset_hashes["dataset_bundle_sha256"],
        "frozen": True,
        "freeze_timestamp": "2026-08-10T10:06:29.933862+00:00",
        "freeze_scope": "FINAL_PROTOCOL_FREEZE",
        "human_review": {
            "status": "ACCEPTED",
            "reviewer": "Paolo Pangallo",
            "reviewer_role": "thesis author / protocol reviewer",
            "date": "2026-08-10",
            "record": "docs/final_evaluation/heldout_review.md",
            "approved": [
                "HELDOUT_ARCHITECTURAL_35",
                "NARRATIVE_HELDOUT_20",
                "NARRATIVE_HELDOUT_VALID_CONTROL_5",
                "final success criteria with stable identifiers",
                "single canonical runtime alignment",
                "removal of the primary LIVE-vs-REPLAY comparison",
                "held-out provenance distinction",
            ],
        },
        "freeze_note": "Protocollo congelato dopo la review umana finale. Da qui in poi ogni modifica a runtime, corpus, gold, criteri, metriche, denominatori, schemi, sottoinsieme di affidabilita' o piano statistico richiede una nuova protocol version: vedi la regola di immutabilita' post-freeze nel protocollo.",
    }
    with OUT_PATH.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return payload


if __name__ == "__main__":
    result = build()
    print(f"protocol_sha256      : {result['protocol_sha256']}")
    print(f"dataset_bundle_sha256: {result['dataset_bundle_sha256']}")
    print(f"files sealed         : {len(result['files'])}")
