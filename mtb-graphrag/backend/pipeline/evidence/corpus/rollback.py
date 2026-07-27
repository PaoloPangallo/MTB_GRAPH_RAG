"""Rollback della sola promozione prototipale.

Il rollback disfa una cosa sola: il fatto che il registro prototipale punti alla
1.4. Non disfa la 1.4, che non e' stata creata dalla promozione ed esiste nella
shadow indipendentemente da essa; non cancella il lineage ne' il log, che sono
il materiale con cui si ricostruisce cosa e' successo; e non tocca nulla di
operativo, perche' non c'era nulla di operativo da toccare.

Questa asimmetria e' il punto. Una promozione che avesse collegato il retriever
avrebbe un rollback con un lato operativo da verificare; questa non ce l'ha, e
il rollback lo *dimostra* invece di darlo per scontato — `operational_binding_observed`
e' letto dal registro, non asserito qui.

Idempotenza: ogni passo descrive lo stato voluto invece di applicare una
differenza. Eseguire il rollback due volte non puo' quindi ritirare due voci,
e il report della seconda esecuzione e' uguale a quello della prima tranne che
per `changed`.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.corpus import prototype_registry as REGISTRY
from backend.pipeline.evidence.corpus.atomic_write import directory_hashes

RETAIN_IN_PLACE = "retain_for_audit"
MOVE_TO_INACTIVE = "move_to_inactive"
ROLLBACK_MODES = (RETAIN_IN_PLACE, MOVE_TO_INACTIVE)

INACTIVE_SUFFIX = ".inactive"

# I file che il rollback non puo' rimuovere in nessuna modalita'. Sono cio' che
# resta da leggere quando la promozione non c'e' piu'.
PRESERVED_FILES = (
    "claim_replacement_lineage.jsonl",
    "promotion_log.json",
    "rollback_metadata.json",
)


class RollbackError(RuntimeError):
    """Il rollback ha incontrato uno stato che non puo' ripristinare."""


@dataclass(frozen=True)
class RollbackReport:
    changed: bool
    registry_entry_deactivated: bool
    active_prototype_corpus_after: str | None
    previous_pointer_restored: str | None
    corpus_files_retained: bool
    corpus_path_after: str | None
    preserved_files_present: tuple[str, ...]
    operational_binding_observed: bool
    mode: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "active_prototype_corpus_after": self.active_prototype_corpus_after,
            "changed": self.changed,
            "corpus_files_retained": self.corpus_files_retained,
            "corpus_path_after": self.corpus_path_after,
            "mode": self.mode,
            "operational_binding_observed": self.operational_binding_observed,
            "preserved_files_present": list(self.preserved_files_present),
            "previous_pointer_restored": self.previous_pointer_restored,
            "registry_entry_deactivated": self.registry_entry_deactivated,
        }


def rollback(
    *,
    registry_path: Path,
    corpus_path: Path,
    version: str = CONTRACT.REPOSITORY_VERSION,
    mode: str = RETAIN_IN_PLACE,
) -> RollbackReport:
    """Ritira la promozione prototipale di `version` e riporta il puntatore indietro."""
    if mode not in ROLLBACK_MODES:
        raise RollbackError(f"modalita' di rollback sconosciuta: {mode!r}")

    registry_path = Path(registry_path)
    corpus_path = Path(corpus_path)

    before = REGISTRY.load(registry_path)
    entry_before = (before.get("entries") or {}).get(version) or {}
    was_active = before.get("active_prototype_corpus") == version

    after = REGISTRY.deactivate(before, version)
    changed_registry = after != before
    if changed_registry:
        REGISTRY.save(after, registry_path)

    # I file restano. In `move_to_inactive` cambiano nome e smettono di essere
    # il percorso che il registro citava, ma nessun byte viene rimosso: un
    # rollback che cancellasse renderebbe irripetibile l'audit di cio' che era
    # stato promosso.
    retained_path: Path | None = None
    moved = False
    if corpus_path.exists():
        retained_path = corpus_path
    inactive = corpus_path.with_name(corpus_path.name + INACTIVE_SUFFIX)
    if mode == MOVE_TO_INACTIVE:
        if corpus_path.exists():
            if inactive.exists():
                shutil.rmtree(inactive)
            corpus_path.rename(inactive)
            moved = True
        retained_path = inactive if inactive.exists() else None

    present = ()
    if retained_path is not None and retained_path.is_dir():
        names = set(directory_hashes(retained_path))
        present = tuple(name for name in PRESERVED_FILES if name in names)
        lost = [name for name in PRESERVED_FILES if name not in names]
        if lost:
            raise RollbackError(f"il rollback ha perso artefatti da conservare: {lost}")

    return RollbackReport(
        changed=bool(changed_registry or moved),
        registry_entry_deactivated=bool(was_active or entry_before),
        active_prototype_corpus_after=after.get("active_prototype_corpus"),
        previous_pointer_restored=after.get("active_prototype_corpus"),
        corpus_files_retained=retained_path is not None,
        corpus_path_after=retained_path.name if retained_path is not None else None,
        preserved_files_present=present,
        operational_binding_observed=bool(
            before.get("operational_retriever_bound")
            or entry_before.get("operational_retriever_bound")
        ),
        mode=mode,
    )


def rollback_metadata(
    *, corpus_sha256: Mapping[str, str], source_shadow_sha256: str
) -> dict[str, Any]:
    """Cosa il rollback ripristina, scritto dentro il corpus che ripristina.

    Il metadato vive nel corpus promosso e non accanto: se un giorno la
    directory venisse spostata in stato inattivo, le istruzioni per ritirarla si
    sposterebbero con lei.
    """
    return {
        "corpus_file_sha256": dict(sorted(corpus_sha256.items())),
        "idempotent": True,
        "modes": list(ROLLBACK_MODES),
        "operational_artifacts_touched_by_rollback": [],
        "operational_retriever_was_never_bound": True,
        "preserved_files": list(PRESERVED_FILES),
        "procedure": [
            "disattivare la voce di registro della 1.4",
            "riportare il puntatore prototipale al bersaglio di rollback, se presente",
            "conservare i file promossi per audit, oppure spostarli in stato inactive",
            "non rimuovere lineage, promotion log e rollback metadata",
            "verificare che gli hash operativi non siano cambiati",
            "verificare che il retriever operativo non sia mai stato collegato",
        ],
        "registry_relpath": CONTRACT.REGISTRY_RELPATH,
        "repository_version": CONTRACT.REPOSITORY_VERSION,
        "rollback_scope": "prototype_registry_pointer_only",
        "rollback_target": None,
        "rollback_target_note": (
            "Nessun corpus prototipale era stato promosso prima della 1.4: il "
            "rollback riporta il puntatore a nessuno, non a una versione "
            "precedente. Dichiararlo `null` invece di inventare un bersaglio "
            "evita che un ripristino sembri possibile dove non lo e'."
        ),
        "shadow_repository_removed_by_rollback": False,
        "source_shadow_sha256": source_shadow_sha256,
        "source_shadow_version": CONTRACT.SOURCE_SHADOW_VERSION,
    }


__all__ = [
    "INACTIVE_SUFFIX",
    "MOVE_TO_INACTIVE",
    "PRESERVED_FILES",
    "RETAIN_IN_PLACE",
    "ROLLBACK_MODES",
    "RollbackError",
    "RollbackReport",
    "rollback",
    "rollback_metadata",
]
