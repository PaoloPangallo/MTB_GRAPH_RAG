"""Provenance dei generatori, dal lato audit.

Audit-only, come `legacy_hash_erratum`: nessun modulo operativo lo importa.

Il problema che risolve e' un auto-riferimento. Un manifest che dichiara
`generator_sha256` registra l'impronta del file che lo sta scrivendo; modificare
quel file cambia il valore, e **nessuna** versione successiva del generatore puo'
riprodurre il valore che una versione precedente aveva scritto. Non perche'
produca artefatti diversi — perche' *e'* un file diverso.

Un test che confronta un artefatto rigenerato con quello committato e li trova
diversi su quel campo sta osservando questo, e non un difetto. Ma «non e' un
difetto» non e' una buona ragione per farlo passare in silenzio: la differenza
fra «l'unico campo diverso e' l'auto-riferimento dichiarato» e «l'artefatto e'
cambiato» e' esattamente cio' che il test deve saper dire.

Da qui le tre nozioni separate, che questo modulo espone una per una:

    integrita' storica     il manifest conserva ancora l'impronta che il
                           generatore aveva alla revisione congelata
    integrita' corrente    il generatore corrente ha la propria impronta, e la
                           scrive negli artefatti che produce adesso
    compatibilita'         quali campi il generatore corrente deve ancora
                           riprodurre dell'artefatto storico. E' dichiarata,
                           non dedotta: `non_reproducible_fields` elenca le
                           deroghe, e tutto cio' che non e' elencato deve
                           tornare byte per byte.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "generator_provenance_erratum.json"
)

SCHEMA_VERSION = "generator_provenance_erratum/1.0"
REASON_GENERATOR_EVOLVED = "GENERATOR_SOURCE_EVOLVED_AFTER_FROZEN_ARTIFACT"


class GeneratorProvenanceError(RuntimeError):
    """L'erratum non descrive piu' i generatori che dice di descrivere."""


def _sha_raw(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_canonical_text(data: bytes) -> str:
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


HASH_ALGORITHMS = {
    "raw_bytes": _sha_raw,
    "canonical_text_lf": _sha_canonical_text,
}


@lru_cache(maxsize=1)
def erratum() -> dict[str, Any]:
    payload = json.loads(ERRATUM_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise GeneratorProvenanceError(
            f"erratum in schema {payload.get('schema_version')!r}, "
            f"atteso {SCHEMA_VERSION!r}"
        )
    return payload


def entry_for_artifact(relative: str) -> dict[str, Any] | None:
    """La voce che descrive questo artefatto, se ce n'e' una."""
    for candidate in erratum()["entries"]:
        if candidate["historical_artifact_path"] == relative:
            return candidate
    return None


def entry_for(relative: str) -> dict[str, Any]:
    found = entry_for_artifact(relative)
    if found is None:
        raise GeneratorProvenanceError(
            f"{relative} non e' registrato nell'erratum di provenance"
        )
    return found


def current_generator_sha256(entry: dict[str, Any]) -> str:
    """L'impronta del generatore com'e' adesso, con la sua convenzione."""
    digest = HASH_ALGORITHMS[entry["hash_algorithm"]]
    return digest((REPO_ROOT / entry["historical_generator_path"]).read_bytes())


def non_reproducible_fields(relative: str) -> tuple[str, ...]:
    """I campi per cui la divergenza e' dichiarata. Tutti gli altri devono tornare."""
    found = entry_for_artifact(relative)
    return tuple(found["non_reproducible_fields"]) if found else ()


def check_historical_integrity(relative: str) -> dict[str, Any]:
    """Il manifest conserva ancora l'impronta del generatore originale.

    E' il controllo che impedisce di «chiudere» il caso riscrivendo l'artefatto
    storico: se qualcuno aggiornasse il manifest all'impronta corrente, qui
    fallirebbe, ed e' precisamente cio' che la fase si e' impegnata a non fare.

    Solleva `AssertionError` invece di usare un metodo di `TestCase`: la suite
    esterna e' meta' a funzione e meta' a classe, e un helper che ne servisse
    una sola verrebbe duplicato.
    """
    entry = entry_for(relative)
    manifest = json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))
    declared = manifest[entry["declared_field"]]
    if declared != entry["historical_generator_sha256"]:
        raise AssertionError(
            f"{relative} non dichiara piu' l'impronta storica del proprio "
            f"generatore: registrata {declared}, attesa "
            f"{entry['historical_generator_sha256']}. L'artefatto congelato e' "
            f"stato riscritto."
        )
    return entry


def check_current_integrity(relative: str, regenerated: dict[str, Any]) -> None:
    """Il generatore corrente ha la propria impronta, e la scrive negli artefatti.

    Non basta constatare che l'impronta storica e quella corrente differiscono:
    va verificato che il generatore dichiari *la propria*, altrimenti un campo
    lasciato indietro passerebbe per una divergenza legittima.
    """
    entry = entry_for(relative)
    expected = current_generator_sha256(entry)
    if entry["current_generator_sha256"] != expected:
        raise AssertionError(
            f"l'erratum non descrive il generatore corrente di {relative}: "
            f"registrato {entry['current_generator_sha256']}, misurato "
            f"{expected}. Rigeneralo con build_generator_provenance_erratum."
        )
    written = regenerated[entry["declared_field"]]
    if written != expected:
        raise AssertionError(
            f"il generatore corrente non dichiara la propria impronta in "
            f"{entry['declared_field']}: ha scritto {written}, la sua e' "
            f"{expected}"
        )
    if expected == entry["historical_generator_sha256"]:
        raise AssertionError(
            f"{relative}: impronta corrente e storica coincidono, la voce non "
            f"appartiene piu' all'erratum e va tolta"
        )
    if entry["reason_code"] != REASON_GENERATOR_EVOLVED:
        raise AssertionError(
            f"{relative}: reason_code {entry['reason_code']!r}, atteso "
            f"{REASON_GENERATOR_EVOLVED!r}"
        )


def check_compatible(
    relative: str, committed: dict[str, Any], regenerated: dict[str, Any]
) -> None:
    """Tutto cio' che non e' dichiarato non riproducibile deve tornare.

    La deroga e' puntuale e nominata. Non e' una whitelist di comodo: i campi
    esclusi qui sono verificati uno per uno dagli altri due controlli, sul lato
    storico e su quello corrente. E una deroga che coprisse un campo identico
    verrebbe segnalata come riga morta, perche' nasconderebbe la prossima
    divergenza vera.
    """
    excused = set(non_reproducible_fields(relative))
    differing = sorted(
        key
        for key in set(committed) | set(regenerated)
        if committed.get(key) != regenerated.get(key)
    )
    undeclared = [key for key in differing if key not in excused]
    if undeclared:
        raise AssertionError(
            f"{relative}: campi non riproducibili e non dichiarati: {undeclared}"
        )
    dead = sorted(excused - set(differing))
    if dead:
        raise AssertionError(
            f"{relative}: deroghe che non coprono nessuna divergenza: {dead}. "
            f"Toglile, oppure nasconderanno la prossima."
        )


__all__ = [
    "ERRATUM_PATH",
    "REASON_GENERATOR_EVOLVED",
    "SCHEMA_VERSION",
    "GeneratorProvenanceError",
    "check_compatible",
    "check_current_integrity",
    "check_historical_integrity",
    "current_generator_sha256",
    "entry_for",
    "entry_for_artifact",
    "erratum",
    "non_reproducible_fields",
]
