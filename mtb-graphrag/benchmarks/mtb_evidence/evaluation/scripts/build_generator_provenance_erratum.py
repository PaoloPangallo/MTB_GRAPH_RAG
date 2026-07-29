"""Costruisce l'erratum di provenance dei generatori.

Distinto da `artifact_hash_erratum` perche' registra un fatto diverso.
Quell'erratum dice: *l'impronta di un sorgente fu presa in una forma di byte che
un checkout pulito non riproduce*. Questo dice: *un artefatto congelato registra
l'impronta del generatore che lo produsse, e quel generatore e' cambiato dopo*.

La differenza non e' formale. Nel primo caso il file e' lo stesso e cambia la
forma; qui il file e' proprio un altro, e nessuna normalizzazione lo riporta
indietro. Metterli nello stesso erratum significherebbe dare lo stesso nome a due
cose che si chiudono in modi diversi.

## Il punto fisso che si sposta

Un manifest che dichiara `generator_sha256` registra l'impronta del file che lo
sta scrivendo. E' un auto-riferimento: modificare il generatore cambia quel
valore, e nessuna versione successiva del generatore puo' riprodurre il valore
che una versione precedente aveva scritto — non perche' produca artefatti
diversi, ma perche' *e'* un file diverso.

Questo rende necessario distinguere tre cose che il test unico confondeva:

    integrita' storica     il manifest conserva ancora l'impronta del generatore
                           originale, e quell'impronta e' verificabile contro il
                           blob della revisione che l'ha congelata

    integrita' corrente    il generatore corrente ha la propria impronta e
                           produce gli artefatti della propria versione

    compatibilita'         quanto dell'artefatto storico il generatore corrente
                           deve ancora riprodurre. Non e' automaticamente
                           "tutto": va dichiarato.

    python -m benchmarks.mtb_evidence.evaluation.scripts.build_generator_provenance_erratum
    python -m ... --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.pipeline.evidence.integrity import hash_policy as POLICY  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
GIT_ROOT = REPO_ROOT.parent
PACKAGE_PREFIX = "mtb-graphrag/"

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "generator_provenance_erratum.json"
)

SCHEMA_VERSION = "generator_provenance_erratum/1.0"
PHASE = "hermetic-reproducibility-closure/1.0"

REASON_GENERATOR_EVOLVED = "GENERATOR_SOURCE_EVOLVED_AFTER_FROZEN_ARTIFACT"

# La revisione che chiude la fase precedente: e' li' che i generatori avevano la
# forma che i manifest congelati registrano.
FROZEN_REVISION = "b6694ba23d189b17a9ca87a5a3e86990db4445a8"

_TIMEOUT_SECONDS = 120


def _sha_raw(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_canonical_text(data: bytes) -> str:
    """La convenzione di `_canonical_text_sha`: CRLF e CR isolati diventano LF.

    Piu' permissiva della politica 2.0, che un CR isolato lo rifiuta. E'
    riprodotta qui com'e' perche' l'erratum deve descrivere l'impronta che il
    generatore calcola davvero, non quella che si preferirebbe calcolasse.
    """
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


HASH_ALGORITHMS = {
    "raw_bytes": _sha_raw,
    "canonical_text_lf": _sha_canonical_text,
}

# I manifest che registrano l'impronta del proprio generatore, con il campo che
# usano e la convenzione con cui la calcolano. Le due convenzioni convivono da
# prima di questa fase e non vengono uniformate qui: cambiare il modo in cui un
# artefatto congelato e' stato misurato non lo renderebbe piu' vero.
DECLARED = (
    {
        "artifact": (
            "benchmarks/mtb_evidence/v3/multi_intervention_adapter_review/"
            "review_manifest.json"
        ),
        "generator": (
            "benchmarks/mtb_evidence/evaluation/scripts/"
            "multi_intervention_adapter_review.py"
        ),
        "field": "generator_source_sha256",
        "hash_algorithm": "raw_bytes",
        "version_field": "review_version",
    },
    {
        "artifact": (
            "benchmarks/mtb_evidence/v3/multi_intervention_source_review/"
            "review_manifest.json"
        ),
        "generator": (
            "benchmarks/mtb_evidence/evaluation/scripts/"
            "multi_intervention_source_review.py"
        ),
        "field": "generator_sha256",
        "hash_algorithm": "canonical_text_lf",
        # Questo manifest chiama `manifest_version` cio' che l'altro chiama
        # `review_version`. Il nome del campo si dichiara qui invece di
        # indovinarlo: leggere una chiave assente darebbe `null`, e un erratum
        # che non sa a quale versione di generatore si riferisce non registra
        # niente.
        "version_field": "manifest_version",
    },
)


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args],
        cwd=GIT_ROOT,
        capture_output=True,
        check=True,
        timeout=_TIMEOUT_SECONDS,
    ).stdout


def build() -> dict[str, Any]:
    entries = []
    for spec in DECLARED:
        artifact = REPO_ROOT / spec["artifact"]
        generator = REPO_ROOT / spec["generator"]
        manifest = json.loads(artifact.read_text(encoding="utf-8"))
        digest = HASH_ALGORITHMS[spec["hash_algorithm"]]

        declared = manifest[spec["field"]]
        current = digest(generator.read_bytes())
        frozen = digest(
            _git("show", f"{FROZEN_REVISION}:{PACKAGE_PREFIX}{spec['generator']}")
        )

        # Se il manifest non conserva piu' l'impronta che il generatore aveva
        # alla revisione congelata, l'artefatto e' stato riscritto: non e' un
        # caso da registrare, e' una violazione del perimetro.
        if declared != frozen:
            raise RuntimeError(
                f"{spec['artifact']} non dichiara piu' l'impronta che "
                f"{spec['generator']} aveva a {FROZEN_REVISION[:7]}: "
                f"dichiarata {declared}, misurata {frozen}. L'artefatto storico "
                f"e' stato modificato."
            )

        entries.append(
            {
                "artifact_generation_version": manifest.get(spec["version_field"]),
                "current_generator_compatibility": (
                    "byte_identical_except_declared_provenance_field"
                    if declared != current
                    else "byte_identical"
                ),
                "current_generator_sha256": current,
                "declared_field": spec["field"],
                "hash_algorithm": spec["hash_algorithm"],
                "historical_artifact_path": spec["artifact"],
                "historical_generator_path": spec["generator"],
                "historical_generator_sha256": declared,
                "historical_reproducibility_status": (
                    "reproducible_modulo_generator_self_reference"
                    if declared != current
                    else "reproducible"
                ),
                # Il campo che non torna e' l'auto-riferimento del generatore, e
                # non torna per costruzione: un file non puo' contenere la
                # propria impronta e restare lo stesso file dopo essere
                # cambiato.
                "non_reproducible_fields": (
                    [spec["field"]] if declared != current else []
                ),
                "reason_code": (
                    REASON_GENERATOR_EVOLVED if declared != current else None
                ),
                "frozen_revision": FROZEN_REVISION,
            }
        )

    diverging = [e for e in entries if e["reason_code"]]
    return {
        "counts": {"declared": len(entries), "diverging": len(diverging)},
        "entries": entries,
        "hash_policy_version": POLICY.POLICY_VERSION,
        "phase": PHASE,
        "schema_version": SCHEMA_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    erratum = build()
    rendered = json.dumps(erratum, ensure_ascii=False, indent=2, sort_keys=True)

    if args.check:
        if not ERRATUM_PATH.exists():
            print(f"erratum assente: {ERRATUM_PATH}", file=sys.stderr)
            return 1
        if ERRATUM_PATH.read_text(encoding="utf-8").rstrip("\n") != rendered:
            print("l'erratum non corrisponde ai generatori correnti", file=sys.stderr)
            return 1
        print(json.dumps(erratum["counts"], indent=2, sort_keys=True))
        return 0

    ERRATUM_PATH.parent.mkdir(parents=True, exist_ok=True)
    ERRATUM_PATH.write_text(rendered + "\n", encoding="utf-8", newline="\n")
    print(f"scritto {ERRATUM_PATH.relative_to(REPO_ROOT)}")
    print(json.dumps(erratum["counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
