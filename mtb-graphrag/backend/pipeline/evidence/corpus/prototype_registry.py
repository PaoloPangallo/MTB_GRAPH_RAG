"""Registro prototipale V3: quale corpus promosso e' attivo, e per chi.

Il registro e' deliberatamente separato dalla configurazione operativa. Il
retriever legge la propria configurazione da `qualified_retriever_scoring_config.json`
e dal corpus V2; questo file non compare in nessuno dei due percorsi, e
`operational_retriever_bound` non e' un commento ma il campo che lo dichiara.

La ragione della separazione e' che "promosso" e "in uso" sono due stati
distinti che un registro unico non saprebbe tenere separati. Un corpus puo'
essere promosso per il prototipo — versionato, hashato, caricabile — e non
essere raggiungibile da nessuna query operativa. Se i due stati vivessero nella
stessa configurazione, l'unico modo di distinguerli sarebbe leggere il codice
che la consuma.

Ogni funzione restituisce un registro nuovo invece di modificare quello
ricevuto. Un rollback che mutasse la struttura in memoria renderebbe impossibile
confrontare il prima e il dopo, che e' esattamente cio' che il rollback deve
dimostrare.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT
from backend.pipeline.evidence.corpus.atomic_write import write_json_atomically

STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"


class RegistryError(RuntimeError):
    """Il registro prototipale e' in uno stato che il contratto non ammette."""


def empty_registry() -> dict[str, Any]:
    """Il registro prima di qualunque promozione."""
    return {
        "active_prototype_corpus": None,
        "entries": {},
        "operational_retriever_bound": False,
        "operational_retriever_binding": (
            "Nessun corpus di questo registro e' collegato al retriever "
            "operativo. Il collegamento e' una fase separata e richiede una "
            "decisione esplicita: la promozione prototipale non lo implica."
        ),
        "previous_prototype_corpus": None,
        "registry_scope": "prototype_only",
        "registry_version": CONTRACT.REGISTRY_VERSION,
    }


def build_entry(
    *,
    source_shadow_sha256: str,
    corpus_sha256: str,
    corpus_path: str = CONTRACT.PROMOTED_CORPUS_RELPATH,
    rollback_target: str | None = None,
) -> dict[str, Any]:
    """La voce di registro della 1.4, con i valori dichiarati dal contratto.

    Nessun valore viene dedotto dal contenuto del corpus. `clinical_readiness` e
    `final_evaluable` restano falsi perche' nessuna revisione indipendente e'
    avvenuta, e un registro che li ricavasse dai claim direbbe soltanto che i
    claim li dichiarano falsi — che e' un'altra affermazione.
    """
    return {
        "allowed_policy_modes": list(CONTRACT.ALLOWED_POLICY_MODES),
        "clinical_readiness": CONTRACT.CLINICAL_READINESS,
        "corpus_path": corpus_path,
        "corpus_sha256": corpus_sha256,
        "default_policy_mode": CONTRACT.DEFAULT_POLICY_MODE,
        "final_evaluable": CONTRACT.FINAL_EVALUABLE,
        "model_version": CONTRACT.MODEL_VERSION,
        "operational_retriever_bound": CONTRACT.OPERATIONAL_RETRIEVER_BOUND,
        "promoted_at": CONTRACT.PROMOTED_AT,
        "promotion_commit": CONTRACT.PROMOTION_COMMIT,
        "promotion_status": CONTRACT.PROMOTION_STATUS,
        "prototype_promoted": CONTRACT.PROTOTYPE_PROMOTED,
        "repository_version": CONTRACT.REPOSITORY_VERSION,
        "rollback_target": rollback_target,
        "schema_version": CONTRACT.SCHEMA_VERSION,
        "source_shadow_sha256": source_shadow_sha256,
        "source_shadow_version": CONTRACT.SOURCE_SHADOW_VERSION,
        "status": STATUS_ACTIVE,
        "unknown_policy_mode_behavior": CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR,
    }


def validate_entry(entry: Mapping[str, Any]) -> None:
    missing = [field for field in CONTRACT.registry_entry_fields() if field not in entry]
    if missing:
        raise RegistryError(f"voce di registro senza {missing}")
    if entry["promotion_status"] != CONTRACT.PROMOTION_STATUS:
        raise RegistryError(
            f"promotion_status {entry['promotion_status']!r} invece di "
            f"{CONTRACT.PROMOTION_STATUS!r}"
        )
    if entry["operational_retriever_bound"]:
        raise RegistryError(
            "operational_retriever_bound e' true: la promozione prototipale non "
            "collega il retriever operativo"
        )
    if entry["default_policy_mode"] != CONTRACT.DEFAULT_POLICY_MODE:
        raise RegistryError(
            f"default_policy_mode {entry['default_policy_mode']!r} invece di "
            f"{CONTRACT.DEFAULT_POLICY_MODE!r}"
        )
    if entry["unknown_policy_mode_behavior"] != CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR:
        raise RegistryError(
            "unknown_policy_mode_behavior deve essere "
            f"{CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR!r}"
        )
    if entry["clinical_readiness"] or entry["final_evaluable"]:
        raise RegistryError(
            "clinical_readiness e final_evaluable restano falsi in una "
            "promozione prototipale"
        )


def validate(registry: Mapping[str, Any]) -> None:
    if registry.get("registry_version") != CONTRACT.REGISTRY_VERSION:
        raise RegistryError(
            f"registry_version {registry.get('registry_version')!r} invece di "
            f"{CONTRACT.REGISTRY_VERSION!r}"
        )
    if registry.get("operational_retriever_bound"):
        raise RegistryError("il registro prototipale non collega il retriever operativo")
    active = registry.get("active_prototype_corpus")
    entries = registry.get("entries") or {}
    if active is not None and active not in entries:
        raise RegistryError(f"il puntatore attivo cita una voce assente: {active}")
    for version, entry in sorted(entries.items()):
        validate_entry(entry)
        if entry["repository_version"] != version:
            raise RegistryError(
                f"chiave {version!r} e repository_version "
                f"{entry['repository_version']!r} non coincidono"
            )
    active_entries = [
        version
        for version, entry in entries.items()
        if entry.get("status") == STATUS_ACTIVE
    ]
    if len(active_entries) > 1:
        raise RegistryError(f"piu' di una voce attiva: {sorted(active_entries)}")
    if active is not None and entries[active].get("status") != STATUS_ACTIVE:
        raise RegistryError(f"il puntatore attivo cita una voce inattiva: {active}")


def register(
    registry: Mapping[str, Any], entry: Mapping[str, Any]
) -> dict[str, Any]:
    """Il registro con la nuova voce attiva, e la precedente conservata inattiva.

    La voce precedente non viene rimossa: e' il bersaglio del rollback, e un
    registro che la cancellasse renderebbe il rollback una ricostruzione invece
    che un ripristino.
    """
    validate_entry(entry)
    version = entry["repository_version"]
    previous = registry.get("active_prototype_corpus")
    entries = {
        key: (dict(value) | {"status": STATUS_INACTIVE})
        for key, value in (registry.get("entries") or {}).items()
    }
    entries[version] = dict(entry) | {"status": STATUS_ACTIVE}
    updated = dict(registry) | {
        "active_prototype_corpus": version,
        "entries": dict(sorted(entries.items())),
        "previous_prototype_corpus": previous if previous != version else registry.get(
            "previous_prototype_corpus"
        ),
    }
    validate(updated)
    return updated


def deactivate(registry: Mapping[str, Any], version: str) -> dict[str, Any]:
    """Ritira una voce e riporta il puntatore al prototipo precedente.

    Idempotente per costruzione: la funzione descrive lo stato voluto — quella
    voce inattiva, il puntatore su cio' che c'era prima — invece di applicare
    una differenza. Chiamarla due volte non puo' quindi togliere due cose.
    """
    entries = {
        key: dict(value) for key, value in (registry.get("entries") or {}).items()
    }
    if version not in entries:
        validate(registry)
        return dict(registry)

    entries[version] = entries[version] | {"status": STATUS_INACTIVE}
    target = entries[version].get("rollback_target")
    if target is not None and target in entries:
        entries[target] = entries[target] | {"status": STATUS_ACTIVE}
        active: str | None = target
    else:
        active = None

    updated = dict(registry) | {
        "active_prototype_corpus": active,
        "entries": dict(sorted(entries.items())),
        "previous_prototype_corpus": None if active is None else version,
    }
    validate(updated)
    return updated


def dumps(registry: Mapping[str, Any]) -> str:
    return json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def load(path: Path = CONTRACT.REGISTRY_PATH) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return empty_registry()
    registry = json.loads(path.read_text(encoding="utf-8"))
    validate(registry)
    return registry


def save(registry: Mapping[str, Any], path: Path = CONTRACT.REGISTRY_PATH) -> None:
    validate(registry)
    write_json_atomically(Path(path), dumps(registry))


__all__ = [
    "STATUS_ACTIVE",
    "STATUS_INACTIVE",
    "RegistryError",
    "build_entry",
    "deactivate",
    "dumps",
    "empty_registry",
    "load",
    "register",
    "save",
    "validate",
    "validate_entry",
]
