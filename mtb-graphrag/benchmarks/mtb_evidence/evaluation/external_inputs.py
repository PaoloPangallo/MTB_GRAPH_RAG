"""Ingressi esterni privati, e come la suite core ne fa a meno.

Due input non stanno nel repository e non ci staranno mai: il bundle gold, che
e' materiale clinico riservato, e la cache degli abstract, che e' materiale
protetto da copyright. Entrambi sono stati usati da fasi passate, entrambi sono
citati da test che li aprivano direttamente, ed entrambi mancano in qualunque
checkout che non sia la macchina su cui quelle fasi sono state eseguite.

Finche' la suite li apre senza chiedersi se ci siano, la suite non descrive il
codice: descrive una macchina. Un clone pulito falliva 88 test con 106 errori, e
nessuno di quei fallimenti diceva niente sul codice.

Questo modulo separa le due cose. Un ingresso esterno ha un **manifest
tracciato** — versione, schema, hash attesi file per file, hash aggregato — e il
manifest sta nel repository mentre i byte no. Il manifest e' sufficiente a
verificare un bundle quando c'e', e a descriverlo quando non c'e'; non e'
sufficiente a ricostruirlo, ed e' esattamente la proprieta' che serve.

La regola che ne segue e' una sola:

    la suite core non apre un ingresso esterno, e i test che lo aprono si
    dichiarano saltati invece di fallire

`unittest.SkipTest` e' il meccanismo perche' e' l'unico che entrambi i runner
riconoscono: `pytest.mark.skipif` non esiste per `unittest discover`, che dei
test a funzione non sa nulla.
"""

from __future__ import annotations

import hashlib
import json
import os
import unittest
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "external-private-input/1.0"

# Il valore che il manifest dichiara nel campo `availability`. Non e' una nota:
# e' cio' che distingue un artefatto assente per errore da uno assente per
# disegno.
AVAILABILITY_EXTERNAL = "external_private_input"

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = REPO_ROOT / "benchmarks" / "mtb_evidence" / "external_inputs"


class ExternalInputError(RuntimeError):
    """Un ingresso esterno e' stato chiesto e non e' utilizzabile."""


class ExternalInputMissingError(ExternalInputError):
    """L'ingresso esterno non e' stato trovato in nessuna delle posizioni note."""


class ExternalInputMismatchError(ExternalInputError):
    """L'ingresso esterno c'e' ma non e' quello che il manifest descrive."""


@dataclass(frozen=True)
class ExternalInput:
    """Un ingresso privato: dove cercarlo, come chiamarlo, come verificarlo."""

    name: str
    manifest_file: str
    # Posizione convenzionale, relativa alla directory che contiene il package.
    # E' una comodita' per la macchina su cui le fasi sono state eseguite, non
    # un requisito: un path esplicito e una variabile d'ambiente vengono prima.
    default_relative_path: str
    environment_variable: str
    description: str
    kind: str = "directory"
    # Il flag del comando che possiede questo ingresso. Sta nel descrittore e non
    # in un messaggio, perche' un errore che suggerisce il flag di un altro
    # comando manda chi legge nella direzione sbagliata.
    cli_flag: str = "--gold-bundle"

    @property
    def manifest_path(self) -> Path:
        return MANIFEST_DIR / self.manifest_file


GOLD_BUNDLE = ExternalInput(
    name="gold_bundle",
    manifest_file="gold_bundle_manifest.json",
    default_relative_path="MTB_Evidence_gold_pilot_v1_bundle",
    environment_variable="MTB_GOLD_BUNDLE",
    description=(
        "Bundle gold pilota v1. Materiale clinico riservato: non viene copiato "
        "nel repository e non viene tracciato."
    ),
)

SOURCE_ABSTRACT_CACHE = ExternalInput(
    name="source_abstract_cache",
    manifest_file="source_abstract_cache_manifest.json",
    default_relative_path=(
        "mtb-graphrag/benchmarks/mtb_evidence/v3/priority_curation/"
        "source_abstract_cache.jsonl"
    ),
    environment_variable="MTB_SOURCE_ABSTRACT_CACHE",
    description=(
        "Cache degli abstract delle fonti. Testo protetto da copyright: e' "
        "escluso dal versionamento da .gitignore, non per dimenticanza."
    ),
    kind="file",
    cli_flag="--source-abstract-cache",
)

EXTERNAL_INPUTS = (GOLD_BUNDLE, SOURCE_ABSTRACT_CACHE)


# --- hash ---------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_hashes(root: Path) -> dict[str, str]:
    """Hash di ogni file, con chiave il path relativo alla radice dell'ingresso.

    I path sono relativi all'ingresso e non al repository: un bundle montato
    altrove deve verificare lo stesso, altrimenti il manifest descriverebbe una
    posizione invece di un contenuto.
    """
    root = Path(root)
    if root.is_file():
        return {root.name: sha256_file(root)}
    return {
        item.relative_to(root).as_posix(): sha256_file(item)
        for item in sorted(root.rglob("*"))
        if item.is_file() and "__pycache__" not in item.parts
    }


def aggregate_hash(hashes: dict[str, str]) -> str:
    """Hash aggregato: righe `path:hash` ordinate, senza newline finale.

    E' lo stesso contratto che gli audit congelati usano per le directory del
    repository, ripetuto qui perche' un ingresso esterno non possa avere una
    regola sua.
    """
    payload = "\n".join(f"{name}:{digest}" for name, digest in sorted(hashes.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


AGGREGATE_CONTRACT = (
    "sha256 of sorted input-relative POSIX path:sha256 lines without trailing newline"
)


# --- manifest -----------------------------------------------------------------


def manifest(descriptor: ExternalInput) -> dict[str, Any]:
    """Il manifest tracciato dell'ingresso. Non apre l'ingresso."""
    return json.loads(descriptor.manifest_path.read_text(encoding="utf-8"))


def build_manifest(
    descriptor: ExternalInput,
    path: Path,
    *,
    bundle_version: str,
    schema_version: str,
) -> dict[str, Any]:
    """Costruisce il manifest dai byte dell'ingresso.

    Calcolare un digest non e' leggere un contenuto: nessuna riga viene
    deserializzata e niente di cio' che l'ingresso dice entra nel manifest. E' la
    stessa distinzione che gli audit delle fasi precedenti registrano quando
    dichiarano `checksum_only_no_deserialization`.
    """
    hashes = file_hashes(path)
    return {
        "aggregate_contract": AGGREGATE_CONTRACT,
        "availability": AVAILABILITY_EXTERNAL,
        "bundle_version": bundle_version,
        "checksum_only_no_deserialization": True,
        "contract_version": CONTRACT_VERSION,
        "default_relative_path": descriptor.default_relative_path,
        "description": descriptor.description,
        "environment_variable": descriptor.environment_variable,
        "expected_aggregate_hash": aggregate_hash(hashes),
        "expected_file_hashes": dict(sorted(hashes.items())),
        "file_count": len(hashes),
        "kind": descriptor.kind,
        "name": descriptor.name,
        "schema_version": schema_version,
        "tracked_in_repository": False,
    }


# --- risoluzione --------------------------------------------------------------


def candidate_paths(
    descriptor: ExternalInput, explicit: Path | str | None = None
) -> list[Path]:
    """Le posizioni in cui l'ingresso viene cercato, nell'ordine in cui vince.

    Un path esplicito batte la variabile d'ambiente, che batte la posizione
    convenzionale. Nessuno dei tre e' un fallback silenzioso su un altro: se
    quello esplicito manca, l'errore lo nomina.
    """
    if explicit is not None:
        return [Path(explicit)]
    found: list[Path] = []
    from_env = os.environ.get(descriptor.environment_variable)
    if from_env:
        found.append(Path(from_env))
    found.append(REPO_ROOT.parent / descriptor.default_relative_path)
    return found


def resolve(
    descriptor: ExternalInput, explicit: Path | str | None = None
) -> Path | None:
    """Dove sta l'ingresso, oppure `None`. Non solleva e non apre niente."""
    for candidate in candidate_paths(descriptor, explicit):
        if candidate.exists():
            return candidate
    return None


def is_available(
    descriptor: ExternalInput, explicit: Path | str | None = None
) -> bool:
    return resolve(descriptor, explicit) is not None


def _missing_message(
    descriptor: ExternalInput, explicit: Path | str | None
) -> str:
    looked = "\n".join(f"  - {path}" for path in candidate_paths(descriptor, explicit))
    return (
        f"ingresso esterno '{descriptor.name}' non trovato.\n"
        f"{descriptor.description}\n"
        f"Cercato in:\n{looked}\n"
        f"Indicalo con {descriptor.cli_flag} <PATH> oppure con la variabile "
        f"d'ambiente {descriptor.environment_variable}."
    )


def require(
    descriptor: ExternalInput, explicit: Path | str | None = None
) -> Path:
    """L'ingresso, oppure un errore che dice dove e' stato cercato."""
    found = resolve(descriptor, explicit)
    if found is None:
        raise ExternalInputMissingError(_missing_message(descriptor, explicit))
    return found


def require_or_skip(
    descriptor: ExternalInput, explicit: Path | str | None = None
) -> Path:
    """L'ingresso, oppure un test saltato.

    `unittest.SkipTest` e non `pytest.skip`: e' l'unica eccezione che entrambi i
    runner riconoscono, e questa suite viene eseguita da tutti e due.
    """
    found = resolve(descriptor, explicit)
    if found is None:
        raise unittest.SkipTest(
            f"ingresso esterno '{descriptor.name}' non disponibile: "
            f"{descriptor.description}"
        )
    return found


# --- verifica -----------------------------------------------------------------


def verify(
    descriptor: ExternalInput,
    path: Path | str | None = None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Confronta l'ingresso con il proprio manifest, senza deserializzarlo."""
    declared = manifest(descriptor)
    resolved = require(descriptor, path)
    actual = file_hashes(resolved)
    expected = dict(declared["expected_file_hashes"])

    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed = sorted(
        name for name in set(expected) & set(actual) if expected[name] != actual[name]
    )
    computed = aggregate_hash(actual)
    matches = computed == declared["expected_aggregate_hash"]

    report = {
        "aggregate_matches": matches,
        "changed_files": changed,
        "computed_aggregate_hash": computed,
        "expected_aggregate_hash": declared["expected_aggregate_hash"],
        "missing_files": missing,
        "name": descriptor.name,
        "path": str(resolved),
        "unexpected_files": unexpected,
        "verified": matches and not missing and not changed,
    }
    if strict and not report["verified"]:
        raise ExternalInputMismatchError(
            f"'{descriptor.name}' non corrisponde al manifest: "
            f"mancanti={missing} cambiati={changed} inattesi={unexpected} "
            f"aggregato_atteso={declared['expected_aggregate_hash']} "
            f"aggregato_calcolato={computed}"
        )
    return report


def availability_report(
    descriptors: Iterable[ExternalInput] = EXTERNAL_INPUTS,
) -> dict[str, Any]:
    """Che cosa c'e' e che cosa no, senza aprire niente."""
    return {
        "contract_version": CONTRACT_VERSION,
        "inputs": [
            {
                "available": is_available(descriptor),
                "availability": AVAILABILITY_EXTERNAL,
                "environment_variable": descriptor.environment_variable,
                "name": descriptor.name,
                "tracked_in_repository": False,
            }
            for descriptor in descriptors
        ],
    }


__all__ = [
    "AGGREGATE_CONTRACT",
    "AVAILABILITY_EXTERNAL",
    "CONTRACT_VERSION",
    "EXTERNAL_INPUTS",
    "GOLD_BUNDLE",
    "MANIFEST_DIR",
    "REPO_ROOT",
    "SOURCE_ABSTRACT_CACHE",
    "ExternalInput",
    "ExternalInputError",
    "ExternalInputMismatchError",
    "ExternalInputMissingError",
    "aggregate_hash",
    "availability_report",
    "build_manifest",
    "candidate_paths",
    "file_hashes",
    "is_available",
    "manifest",
    "require",
    "require_or_skip",
    "resolve",
    "sha256_file",
    "verify",
]
