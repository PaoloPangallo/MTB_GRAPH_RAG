"""L'erratum degli hash di albero, dal lato audit.

Audit-only, come gli altri due: nessun modulo operativo lo importa.

**Non interroga git.** La classificazione testo/binario e' registrata
nell'erratum path per path, quindi l'impronta canonica di un albero si ricalcola
dai file su disco in qualunque ambiente — compreso un archivio estratto che una
storia non ce l'ha. E' la proprieta' per cui la classificazione e' stata
registrata invece di essere ricavata al volo.

Le tre nozioni restano separate, come per gli altri erratum:

    storico       l'artefatto congelato dichiara ancora l'impronta di allora
    canonico      il checkout corrente produce l'impronta canonica registrata,
                  e la produce identica nei quattro ambienti
    collegamento  l'erratum e' cio' che tiene insieme le due, e dice perche'
                  non coincidono
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.integrity import tree_hash_policy as TREE

REPO_ROOT = Path(__file__).resolve().parents[3]

ERRATUM_PATH = (
    REPO_ROOT
    / "benchmarks"
    / "mtb_evidence"
    / "v3"
    / "hermetic_reproducibility_closure"
    / "tree_hash_erratum.json"
)

SCHEMA_VERSION = "tree_hash_erratum/1.0"
REASON_LEGACY_TREE_HASH = TREE.REASON_LEGACY_TREE_HASH


class TreeErratumError(RuntimeError):
    """L'erratum non descrive piu' gli alberi che dice di descrivere."""


@lru_cache(maxsize=1)
def erratum() -> dict[str, Any]:
    payload = json.loads(ERRATUM_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise TreeErratumError(
            f"erratum in schema {payload.get('schema_version')!r}, "
            f"atteso {SCHEMA_VERSION!r}"
        )
    if payload.get("hash_policy_version") != TREE.POLICY_VERSION:
        raise TreeErratumError(
            f"erratum sotto {payload.get('hash_policy_version')!r}, "
            f"questo lettore verifica sotto {TREE.POLICY_VERSION!r}"
        )
    return payload


@lru_cache(maxsize=1)
def _by_root() -> dict[str, dict[str, Any]]:
    return {tree["tree_root"]: tree for tree in erratum()["trees"]}


@lru_cache(maxsize=1)
def _by_role() -> dict[str, dict[str, Any]]:
    return {tree["role"]: tree for tree in erratum()["trees"]}


def entry_for_role(role: str) -> dict[str, Any] | None:
    return _by_role().get(role)


def entry_for_root(relative: str) -> dict[str, Any] | None:
    return _by_root().get(relative)


def diverging_roles() -> tuple[str, ...]:
    return tuple(
        sorted(
            tree["role"]
            for tree in erratum()["trees"]
            if tree["current_reproducibility_status"]
            == "not_reproducible_from_a_clean_checkout"
        )
    )


def canonical_tree_sha256(entry: dict[str, Any]) -> str:
    """L'impronta canonica dell'albero, ricalcolata dai file su disco.

    La classificazione viene dall'erratum, non da `git check-attr`: e' cio' che
    rende questa funzione utilizzabile dove una storia git non c'e'.
    """
    return TREE.canonical_tree_sha256(
        REPO_ROOT / entry["tree_root"],
        text_files=entry["text_files"],
        exclude=erratum().get("exclude", ()),
        require_declared=False,
    )


def check_canonical(relative: str) -> None:
    """L'albero su disco e' ancora quello che l'erratum descrive."""
    entry = entry_for_root(relative)
    if entry is None:
        raise TreeErratumError(f"{relative} non e' registrato nell'erratum di albero")
    measured = canonical_tree_sha256(entry)
    if measured != entry["canonical_lf_tree_sha256"]:
        raise AssertionError(
            f"{relative} non ha piu' l'impronta canonica che l'erratum gli "
            f"attribuisce: misurata {measured}, registrata "
            f"{entry['canonical_lf_tree_sha256']}. Il contenuto dell'albero e' "
            f"cambiato, e l'impronta storica non lo descrive piu'."
        )


def assert_frozen_tree(role: str, root: Path | str, declared: str) -> None:
    """L'albero e' ancora quello che l'impronta congelata descriveva.

    Due modi di esserlo, e il secondo ha tre congiunti perche' non diventi un
    controllo che passa sempre:

    1. l'impronta corrente coincide con quella dichiarata — nessuna mediazione;
    2. l'erratum registra la divergenza per questo ruolo, l'impronta dichiarata
       e' quella storica che l'erratum riporta, **e** l'albero ha ancora
       l'impronta canonica registrata.

    Il terzo congiunto e' quello che conta: se un file dell'albero cambiasse
    davvero, l'impronta canonica non sarebbe piu' quella registrata e
    l'asserzione fallirebbe, erratum o no.
    """
    from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE

    current = SCOPE.sha256_tree(Path(root))
    if current == declared:
        return

    entry = entry_for_role(role)
    if entry is None:
        raise AssertionError(
            f"l'albero {role!r} non coincide con l'impronta congelata "
            f"{declared} e non e' registrato nell'erratum: il contenuto e' "
            f"cambiato, oppure l'erratum e' incompleto"
        )
    if declared != entry["historical_raw_tree_sha256"]:
        raise AssertionError(
            f"{role!r} porta un'impronta congelata che l'erratum non conosce: "
            f"registrata {declared}, storica dichiarata "
            f"{entry['historical_raw_tree_sha256']}"
        )
    if entry["reason_code"] != REASON_LEGACY_TREE_HASH:
        raise AssertionError(
            f"{role!r}: reason_code {entry['reason_code']!r}, atteso "
            f"{REASON_LEGACY_TREE_HASH!r}"
        )
    check_canonical(entry["tree_root"])


__all__ = [
    "ERRATUM_PATH",
    "REASON_LEGACY_TREE_HASH",
    "SCHEMA_VERSION",
    "TreeErratumError",
    "assert_frozen_tree",
    "canonical_tree_sha256",
    "check_canonical",
    "diverging_roles",
    "entry_for_role",
    "entry_for_root",
    "erratum",
]
