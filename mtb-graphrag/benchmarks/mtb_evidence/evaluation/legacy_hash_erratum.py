"""L'erratum delle impronte legacy, dal lato audit.

Questo modulo e' **audit-only**. Nessun modulo operativo lo importa: il runtime
verifica il corpus attraverso l'overlay sotto `backend/`, e l'erratum completo
resta un artefatto di benchmark. La separazione e' voluta — un loader che
consultasse un erratum per decidere se un hash va bene avrebbe una scorciatoia
per accettare qualunque cosa.

## Perche' serve

Dodici artefatti congelati di otto fasi chiuse registrano l'impronta di otto
sorgenti misurati nella forma CRLF di una macchina Windows. Un checkout pulito
consegna LF, quindi rigenerare uno di quegli artefatti oggi produce un digest
diverso da quello committato — e la fase che lo produsse non e' piu' riproducibile.

Ci sono tre modi di uscirne, e due sono peggiori del problema:

1. rigenerare i dodici artefatti — cancella cio' che quelle fasi misurarono
   davvero, e tre di essi stanno nel corpus promosso, che ogni fase dichiara
   congelato;
2. far consegnare al checkout la forma CRLF — piega il repository all'artefatto,
   ed e' il verso sbagliato (era la soluzione precedente, revertita in 33b92ec);
3. dichiarare la discrepanza e farla consultare **solo a chi rigenera un
   artefatto storico**.

Questo modulo e' il terzo. Quando un builder di audit chiede l'impronta di uno
degli otto sorgenti registrati, riceve quella storica, perche' e' cio' che
l'artefatto di quella fase dichiara. Chiunque altro riceve quella canonica.

## Cosa non fa

Non e' un permesso generico. La sostituzione avviene **solo** per gli otto path
registrati, e solo dopo aver verificato che il file abbia ancora la forma
canonica che l'erratum gli attribuisce: se il contenuto cambia, l'impronta
storica smette di descriverlo e la richiesta fallisce invece di restituire un
valore obsoleto. Un erratum che continuasse a dire la sua su un file cambiato
sarebbe una licenza, non una registrazione.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.integrity import hash_policy as POLICY

REPO_ROOT = Path(__file__).resolve().parents[3]

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "artifact_hash_erratum.json"
)


class LegacyErratumError(RuntimeError):
    """L'erratum non descrive piu' il repository che sta descrivendo."""


@lru_cache(maxsize=1)
def erratum() -> dict[str, Any]:
    payload = json.loads(ERRATUM_PATH.read_text(encoding="utf-8"))
    if payload.get("hash_policy_version") != POLICY.POLICY_VERSION:
        raise LegacyErratumError(
            f"erratum scritto sotto {payload.get('hash_policy_version')!r}, "
            f"atteso {POLICY.POLICY_VERSION!r}"
        )
    return payload


@lru_cache(maxsize=1)
def _sources() -> dict[str, dict[str, Any]]:
    return dict(erratum()["sources"])


def _relative(path: Path | str) -> str | None:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return None


def is_registered(path: Path | str) -> bool:
    return _relative(path) in _sources()


def registered_paths() -> tuple[str, ...]:
    return tuple(sorted(_sources()))


def recorded_sha256(path: Path | str) -> str:
    """L'impronta che un artefatto congelato dichiara per questo file.

    Per un file non registrato e' semplicemente quella dei suoi byte. Per uno
    registrato e' quella storica — ma solo se il contenuto e' ancora quello che
    l'erratum descrive.
    """
    relative = _relative(path)
    entry = _sources().get(relative or "")
    if entry is None:
        return POLICY.raw_sha256(path)

    canonical = POLICY.canonical_lf_sha256(path)
    if canonical != entry["canonical_lf_sha256"]:
        raise LegacyErratumError(
            f"{relative} non ha piu' la forma canonica che l'erratum gli "
            f"attribuisce ({canonical} invece di {entry['canonical_lf_sha256']}): "
            f"l'impronta storica non lo descrive piu'. Aggiorna l'erratum con "
            f"build_artifact_hash_erratum invece di ignorare la differenza."
        )
    return entry["historical_raw_sha256"]


def canonical_to_historical() -> dict[str, str]:
    """Le sostituzioni che portano un artefatto rigenerato alla forma committata."""
    return {
        entry["canonical_lf_sha256"]: entry["historical_raw_sha256"]
        for entry in _sources().values()
    }


__all__ = [
    "ERRATUM_PATH",
    "LegacyErratumError",
    "canonical_to_historical",
    "erratum",
    "is_registered",
    "recorded_sha256",
    "registered_paths",
]
