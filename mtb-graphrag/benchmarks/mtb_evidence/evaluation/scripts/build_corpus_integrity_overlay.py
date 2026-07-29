"""Costruisce l'overlay di integrita' del corpus promosso.

Il corpus promosso e' congelato: `corpus_manifest.json`, `promotion_log.json` e
`disease_relation_registry.json` non vengono riscritti da questa fase, e i loro
byte restano quelli che la promozione ha prodotto. Quei tre artefatti pero'
dichiarano in `source_artifact_sha256` l'impronta di diciotto sorgenti, e quattro
di quelle impronte furono prese nella forma CRLF: nessun checkout pulito le
riproduce.

L'overlay e' il modo di renderle verificabili senza toccarli. Sta **fuori** dalla
directory congelata, dichiara per ogni etichetta il path e l'impronta canonica
LF, e per le quattro divergenti anche quella storica con il codice della ragione.
Il loader legge l'overlay; il manifest resta com'e'.

L'overlay e' l'unica fonte che il runtime consulta: l'erratum completo sotto
`benchmarks/` e' audit-only e nessun modulo operativo lo apre.

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_corpus_integrity_overlay
    python -m ... --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT  # noqa: E402
from backend.pipeline.evidence.integrity import hash_policy as POLICY  # noqa: E402

REPO_ROOT = CONTRACT.REPO_ROOT

SCHEMA_VERSION = "corpus_integrity_overlay/1.0"

# Gli artefatti congelati che dichiarano `source_artifact_sha256`. Tutti e tre
# portano lo stesso blocco, e l'overlay ne copre uno solo se coprisse solo il
# manifest: sono elencati perche' la copertura sia una constatazione verificabile.
COVERED = (
    "corpus_manifest.json",
    "disease_relation_registry.json",
    "promotion_log.json",
)


def _source_files() -> dict[str, Path]:
    """La mappa etichetta -> file, presa dallo script che l'ha scritta.

    Non viene ricopiata qui: due copie della stessa mappa divergono, e l'overlay
    finirebbe per descrivere una promozione diversa da quella avvenuta.
    """
    from benchmarks.mtb_evidence.evaluation.scripts import (
        promote_qualified_claim_corpus_1_4 as PROMOTION,
    )

    return dict(PROMOTION.SOURCE_FILES)


def build() -> dict[str, Any]:
    corpus = CONTRACT.PROMOTED_CORPUS
    manifest = json.loads(
        (corpus / CONTRACT.MANIFEST_FILE).read_text(encoding="utf-8")
    )
    declared = dict(manifest["source_artifact_sha256"])
    sources = _source_files()

    unknown = sorted(set(declared) - set(sources))
    if unknown:
        raise RuntimeError(
            f"il manifest dichiara etichette che la promozione non conosce: "
            f"{unknown}"
        )

    entries: dict[str, Any] = {}
    for label in sorted(declared):
        path = sources[label]
        canonical = POLICY.canonical_lf_sha256(path)
        entry: dict[str, Any] = {
            "canonical_lf_sha256": canonical,
            "declared_sha256": declared[label],
            "hash_policy_version": POLICY.POLICY_VERSION,
            "normalization": POLICY.NORMALIZATION,
            "path": path.relative_to(REPO_ROOT).as_posix(),
        }
        if declared[label] != canonical:
            # La divergenza e' registrata, non sanata: il manifest continua a
            # dichiarare cio' che misuro' allora.
            entry["historical_raw_sha256"] = declared[label]
            entry["reason_code"] = POLICY.REASON_LEGACY_LINE_ENDING
        entries[label] = entry

    from backend.pipeline.evidence.corpus import loader as LOADER
    from backend.pipeline.evidence.retrieval import v3_backend as BACKEND

    loaded = LOADER.load(verify_sources=False)
    return {
        "applies_to": CONTRACT.PROMOTED_CORPUS_RELPATH,
        "covers": list(COVERED),
        "hash_policy_version": POLICY.POLICY_VERSION,
        # Cio' che l'overlay non cambia, scritto per poterlo verificare invece
        # che per poterlo affermare.
        "invariants": {
            "active_claims_total": loaded.counts()["active_claims_total"],
            "artifact_sha256_unchanged": True,
            "corpus_sha256": loaded.registry_entry["corpus_sha256"],
            "logical_corpus_hash": BACKEND.corpus_hash(loaded),
        },
        "normalization": POLICY.NORMALIZATION,
        "schema_version": SCHEMA_VERSION,
        "source_artifact_sha256": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    overlay = build()
    rendered = json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True)
    target = CONTRACT.OVERLAY_PATH

    diverging = sum(
        1
        for entry in overlay["source_artifact_sha256"].values()
        if "reason_code" in entry
    )
    summary = {
        "divergenti": diverging,
        "etichette": len(overlay["source_artifact_sha256"]),
    }

    if args.check:
        if not target.exists():
            print(f"overlay assente: {target}", file=sys.stderr)
            return 1
        if target.read_text(encoding="utf-8").rstrip("\n") != rendered:
            print("l'overlay non corrisponde al corpus promosso", file=sys.stderr)
            return 1
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(f"scritto {target.relative_to(REPO_ROOT)}")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
