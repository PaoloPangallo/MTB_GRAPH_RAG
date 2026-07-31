"""`artifact_tree_hash_policy/1.0`: l'impronta di una directory, definita.

`artifact_hash_policy/2.0` dice cosa significa l'impronta di **un file**. Questa
dice cosa significa l'impronta di **un albero**, ed e' una politica separata
perche' aggiunge quattro decisioni che al livello del file non esistono: quali
file entrano, in che ordine, come si separa un path dal suo digest, e cosa si fa
di un binario.

Ognuna delle quattro era implicita, e ognuna era un modo di sbagliare:

**L'ordine.** `sorted(directory.rglob("*"))` ordina oggetti `Path`, e il
confronto fra `Path` passa dai componenti separati dal separatore della
piattaforma. Su Windows `a\\b` e su POSIX `a/b` non ordinano allo stesso modo
quando ci sono sottodirectory, quindi lo stesso albero puo' dare due impronte
diverse su due macchine. Qui l'ordinamento e' sul **path relativo POSIX**, che
non dipende da dove gira.

**Il separatore.** Comporre `f"{path}:{digest}"` e' ambiguo: un path che
contenesse `:` potrebbe produrre la stessa riga di un'altra coppia. Il
separatore e' `NUL`, che in un nome di file non puo' comparire su nessun
filesystem in uso.

**I binari.** Normalizzare le fini riga di un `.png` lo corrompe. La politica
non indovina: i file testuali sono **dichiarati**, e tutto cio' che non e'
dichiarato testuale viene misurato sui byte grezzi. Nessuna euristica sul
contenuto, perche' un'euristica sbaglia in silenzio proprio sui casi che
contano.

**Le esclusioni.** Solo i path che il contratto dichiara. `__pycache__` viene
escluso perche' qualcuno lo dichiara, non perche' la funzione lo sappia.

Il risultato non dipende da: ordine di enumerazione del filesystem, sistema
operativo, presenza di un checkout git, locale, o fini riga native.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.integrity import hash_policy as FILE_POLICY

POLICY_VERSION = "artifact_tree_hash_policy/1.0"

NORMALIZATION = FILE_POLICY.NORMALIZATION

REASON_LEGACY_TREE_HASH = "LEGACY_LINE_ENDING_DEPENDENT_TREE_HASH"

# Fra il path e il digest, e fra una riga e la successiva. `NUL` non puo'
# comparire in un nome di file: e' l'unico separatore per cui «non ambiguo» e'
# una proprieta' e non una speranza.
SEPARATOR = b"\0"
ROW_TERMINATOR = b"\n"


class TreeHashError(RuntimeError):
    """L'albero non e' misurabile cosi' com'e'."""


class UndeclaredFileError(TreeHashError):
    """Un file dell'albero non e' classificato dal contratto.

    Non c'e' un ramo permissivo. Trattarlo come binario darebbe un'impronta
    stabile ma sbagliata su una macchina CRLF; trattarlo come testo
    corromperebbe un binario. Chi aggiunge un file all'albero dichiara cos'e'.
    """


def relative_posix(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def enumerate_files(
    root: Path, *, exclude: Sequence[str] = ()
) -> list[tuple[str, Path]]:
    """I file dell'albero, in ordine lessicografico sul path relativo POSIX.

    L'ordinamento e' sulla stringa POSIX e non sull'oggetto `Path`: e'
    l'unica delle due forme che non cambia fra piattaforme.
    """
    root = Path(root)
    if not root.is_dir():
        raise TreeHashError(f"albero assente: {root}")
    excluded = set(exclude)
    rows = [
        (relative_posix(root, item), item)
        for item in root.rglob("*")
        if item.is_file()
    ]
    return sorted(
        (
            (relative, path)
            for relative, path in rows
            if not any(part in excluded for part in Path(relative).parts)
            and relative not in excluded
        ),
        key=lambda entry: entry[0],
    )


def file_digest(path: Path, *, is_text: bool) -> str:
    """Il digest di un file secondo la sua classificazione dichiarata."""
    data = Path(path).read_bytes()
    if not is_text:
        return hashlib.sha256(data).hexdigest()
    # Solleva `LoneCarriageReturnError` su un CR isolato: un file dichiarato
    # testuale che ne contiene uno non e' il file che il contratto descrive.
    return hashlib.sha256(FILE_POLICY.canonical_lf_bytes(data)).hexdigest()


def canonical_tree_rows(
    root: Path,
    *,
    text_files: Iterable[str],
    exclude: Sequence[str] = (),
) -> list[tuple[str, str]]:
    """Le coppie `(path relativo POSIX, digest)`, gia' ordinate."""
    declared = set(text_files)
    rows: list[tuple[str, str]] = []
    for relative, path in enumerate_files(Path(root), exclude=exclude):
        rows.append((relative, file_digest(path, is_text=relative in declared)))
    return rows


def canonical_tree_sha256(
    root: Path,
    *,
    text_files: Iterable[str],
    exclude: Sequence[str] = (),
    require_declared: bool = True,
) -> str:
    """L'impronta canonica di un albero sotto `artifact_tree_hash_policy/1.0`.

    `require_declared` esiste per il generatore, che la classificazione la sta
    ancora costruendo. Chi verifica non lo tocca: un albero con un file non
    classificato non ha un'impronta definita, e restituirne una comunque
    significherebbe misurare qualcosa di diverso da cio' che si dichiara.
    """
    declared = set(text_files)
    rows = canonical_tree_rows(root, text_files=declared, exclude=exclude)
    if require_declared:
        unknown = sorted(
            relative
            for relative, _ in rows
            if relative not in declared and not _looks_declared_binary(relative, declared)
        )
        if unknown:
            raise UndeclaredFileError(
                f"file non classificati dal contratto in {root}: {unknown}. "
                f"Dichiarali testuali o binari invece di lasciarlo dedurre."
            )
    payload = b"".join(
        relative.encode("utf-8") + SEPARATOR + digest.encode("ascii") + ROW_TERMINATOR
        for relative, digest in rows
    )
    return hashlib.sha256(payload).hexdigest()


def _looks_declared_binary(relative: str, declared: set[str]) -> bool:
    """Un file e' «dichiarato binario» solo se il contratto lo elenca altrove.

    Questa funzione non indovina: e' un punto di estensione esplicito, e oggi
    restituisce sempre `False` perche' negli alberi coperti non ci sono binari.
    Se un binario comparira', il contratto dovra' dichiararlo e questa funzione
    dovra' leggerlo — non dedurlo dai byte.
    """
    return False


@dataclass(frozen=True)
class TreeHashRecord:
    """Le due impronte di un albero, e perche' non coincidono.

    `historical_raw_tree_sha256` e' cio' che un artefatto congelato afferma;
    `canonical_lf_tree_sha256` e' cio' che un checkout pulito produce sotto
    questa politica. Tenerle entrambe evita di dover scegliere fra riscrivere la
    storia e mentire sul presente — la stessa ragione per cui esiste
    `hash_policy.HashRecord`, un livello piu' giu'.
    """

    tree_root: str
    historical_raw_tree_sha256: str
    canonical_lf_tree_sha256: str
    file_count: int
    affected_text_file_count: int
    reason_code: str = REASON_LEGACY_TREE_HASH
    hash_policy_version: str = POLICY_VERSION
    normalization: str = NORMALIZATION
    affected_paths: tuple[str, ...] = field(default_factory=tuple)

    @property
    def diverges(self) -> bool:
        return self.historical_raw_tree_sha256 != self.canonical_lf_tree_sha256

    def as_dict(self) -> dict[str, Any]:
        return {
            "affected_paths": list(self.affected_paths),
            "affected_text_file_count": self.affected_text_file_count,
            "canonical_lf_tree_sha256": self.canonical_lf_tree_sha256,
            "file_count": self.file_count,
            "hash_policy_version": self.hash_policy_version,
            "historical_raw_tree_sha256": self.historical_raw_tree_sha256,
            "normalization": self.normalization,
            "reason_code": self.reason_code,
            "tree_root": self.tree_root,
        }

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> TreeHashRecord:
        required = {
            "affected_text_file_count",
            "canonical_lf_tree_sha256",
            "file_count",
            "hash_policy_version",
            "historical_raw_tree_sha256",
            "normalization",
            "reason_code",
            "tree_root",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"record di albero incompleto, mancano: {missing}")
        return cls(
            tree_root=payload["tree_root"],
            historical_raw_tree_sha256=payload["historical_raw_tree_sha256"],
            canonical_lf_tree_sha256=payload["canonical_lf_tree_sha256"],
            file_count=payload["file_count"],
            affected_text_file_count=payload["affected_text_file_count"],
            reason_code=payload["reason_code"],
            hash_policy_version=payload["hash_policy_version"],
            normalization=payload["normalization"],
            affected_paths=tuple(payload.get("affected_paths", ())),
        )


__all__ = [
    "NORMALIZATION",
    "POLICY_VERSION",
    "REASON_LEGACY_TREE_HASH",
    "ROW_TERMINATOR",
    "SEPARATOR",
    "TreeHashError",
    "TreeHashRecord",
    "UndeclaredFileError",
    "canonical_tree_rows",
    "canonical_tree_sha256",
    "enumerate_files",
    "file_digest",
    "relative_posix",
]
