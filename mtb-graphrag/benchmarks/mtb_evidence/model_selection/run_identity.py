"""Identita' atomica delle run e semantica del resume.

Una run e' identificata da una `run_key` deterministica calcolata su tredici
componenti. Il punto non e' evitare duplicati per eleganza: senza un'identita' che
comprenda anche gli *input* (caso e profili delle fonti), due run prodotte da dati
diversi verrebbero confuse, e un cambiamento nei dati passerebbe inosservato dentro
una media.

Il resume opera per `run_key`, mai per coppia modello-ruolo. La completezza di una
coppia si stabilisce solo dopo aver verificato tutte le `run_key` attese: contare le
righe direbbe che dodici run ci sono, non che sono *quelle* dodici.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ..pilot.audit_lib.serialize import canonical_json, fingerprint

# I tredici componenti dell'identita'. L'ordine e' irrilevante — il JSON canonico
# ordina le chiavi — ma l'insieme no: togliere un componente significa dichiarare che
# due run che differiscono per quel campo sono la stessa run.
RUN_KEY_FIELDS: tuple[str, ...] = (
    "requested_model_tag",
    "effective_api_model",
    "model_revision",
    "role",
    "case_id",
    "task_id",
    "seed",
    "prompt_version",
    "schema_version",
    "case_hash",
    "source_profile_hash",
    "temperature",
    "num_ctx",
)

# Esiti del confronto fra una run attesa e quelle gia' su disco.
SKIP = "skip"
EXECUTE = "execute"
REPLACE = "replace"
PRESERVE_NOT_REUSE = "preserve_but_do_not_reuse"
FAIL_DUPLICATE = "fail_duplicate"


class DuplicateRunKeyError(RuntimeError):
    """Due run distinte condividono la stessa run_key: l'identita' non e' affidabile."""


@dataclass(frozen=True)
class RunIdentity:
    """I componenti dell'identita' di una run, piu' la chiave che ne deriva."""

    requested_model_tag: str
    effective_api_model: str
    model_revision: str
    role: str
    case_id: str
    task_id: str
    seed: int | None
    prompt_version: str
    schema_version: str
    case_hash: str
    source_profile_hash: str
    temperature: float
    num_ctx: int

    @property
    def components(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in RUN_KEY_FIELDS}

    @property
    def run_key(self) -> str:
        return fingerprint(self.components)

    def as_dict(self) -> dict[str, Any]:
        return {**self.components, "run_key": self.run_key}


def case_hash(case: Any) -> str:
    """Hash del caso clinico servito al modello.

    Copre domanda, contesto e qualunque campo che entri nel prompt: se il caso cambia,
    le run precedenti non descrivono piu' lo stesso esperimento.
    """
    payload = case.as_dict() if hasattr(case, "as_dict") else dict(case)
    return fingerprint(payload)


def source_profile_hash(profiles: Sequence[Any]) -> str:
    """Hash dell'insieme dei profili clinici usati nei prompt."""
    payload = [
        profile.as_dict() if hasattr(profile, "as_dict") else dict(profile)
        for profile in profiles
    ]
    return fingerprint(sorted(payload, key=lambda item: str(item.get("source_id", ""))))


def build_identity(
    *,
    requested_model_tag: str,
    resolution: Mapping[str, Any],
    role: str,
    case_id: str,
    task_id: str,
    seed: int | None,
    case_digest: str,
    profiles_digest: str,
    temperature: float,
    num_ctx: int,
    prompt_version: str = "v1",
    schema_version: str = "v1",
) -> RunIdentity:
    """Costruisce l'identita' da una risoluzione di modello e da un compito."""
    return RunIdentity(
        requested_model_tag=requested_model_tag,
        effective_api_model=str(resolution.get("effective_api_model", "")),
        model_revision=str(resolution.get("model_revision", "")),
        role=role,
        case_id=case_id,
        task_id=task_id,
        seed=seed,
        prompt_version=prompt_version,
        schema_version=schema_version,
        case_hash=case_digest,
        source_profile_hash=profiles_digest,
        temperature=float(temperature),
        num_ctx=int(num_ctx),
    )


def is_complete(row: Mapping[str, Any]) -> bool:
    """Una run e' completa se ha prodotto un esito definitivo, valido o fallito.

    Una run interrotta non ha `completed`: va rieseguita, non interpretata.
    """
    return bool(row.get("completed")) and "valid_output" in row


@dataclass(frozen=True)
class ResumeDecision:
    run_key: str
    action: str
    reason: str
    existing: Mapping[str, Any] | None = None

    @property
    def should_execute(self) -> bool:
        return self.action in {EXECUTE, REPLACE}


class RunLedger:
    """Le run gia' su disco, indicizzate per `run_key`.

    Rifiuta in costruzione due righe complete con la stessa chiave e componenti
    diversi: significherebbe che la chiave non identifica univocamente una run, e
    qualunque conteggio successivo sarebbe sbagliato.
    """

    def __init__(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self._by_key: dict[str, Mapping[str, Any]] = {}
        self._incompatible: list[Mapping[str, Any]] = []
        for row in rows:
            key = str(row.get("run_key") or "")
            if not key:
                # Riga prodotta prima dell'introduzione di run_key: conservata, mai
                # riusata, perche' la sua compatibilita' non e' verificabile.
                self._incompatible.append(row)
                continue
            previous = self._by_key.get(key)
            if previous is None:
                self._by_key[key] = row
                continue
            if _components(previous) != _components(row):
                raise DuplicateRunKeyError(
                    f"run_key {key[:16]} associata a componenti diversi: "
                    "l'identita' della run non e' affidabile"
                )
            if is_complete(row) or not is_complete(previous):
                self._by_key[key] = row

    @property
    def incompatible(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self._incompatible)

    def decide(self, identity: RunIdentity) -> ResumeDecision:
        key = identity.run_key
        existing = self._by_key.get(key)
        if existing is None:
            return ResumeDecision(key, EXECUTE, "nessuna run con questa identita'")
        if _components(existing) != identity.components:
            return ResumeDecision(
                key, PRESERVE_NOT_REUSE,
                "componenti divergenti: conservata ma non riusata", existing,
            )
        if is_complete(existing):
            return ResumeDecision(key, SKIP, "run completa e compatibile", existing)
        return ResumeDecision(key, REPLACE, "run incompleta: da rieseguire", existing)

    def completed_keys(self) -> set[str]:
        return {key for key, row in self._by_key.items() if is_complete(row)}

    def rows_excluding(self, keys: set[str]) -> list[Mapping[str, Any]]:
        """Le run da conservare quando alcune vengono sostituite."""
        return [row for key, row in self._by_key.items() if key not in keys]


def _components(row: Mapping[str, Any]) -> dict[str, Any]:
    components = {name: row.get(name) for name in RUN_KEY_FIELDS}
    # I numerici vanno confrontati per valore: 0 e 0.0 sono la stessa temperatura.
    if components.get("temperature") is not None:
        components["temperature"] = float(components["temperature"])
    if components.get("num_ctx") is not None:
        components["num_ctx"] = int(components["num_ctx"])
    return components


def pair_is_complete(
    ledger: RunLedger, identities: Sequence[RunIdentity]
) -> tuple[bool, list[RunIdentity]]:
    """Una coppia modello-ruolo e' completa solo se **tutte** le run attese ci sono.

    Restituisce anche quali mancano: contare le righe direbbe quante ce ne sono, non
    quali.
    """
    completed = ledger.completed_keys()
    missing = [item for item in identities if item.run_key not in completed]
    return (not missing, missing)


def identity_manifest(identities: Sequence[RunIdentity]) -> dict[str, Any]:
    """Descrive lo spazio delle run attese, per verifica esterna."""
    return {
        "expected_run_count": len(identities),
        "run_key_fields": list(RUN_KEY_FIELDS),
        "run_keys": sorted(item.run_key for item in identities),
        "canonical_example": canonical_json(identities[0].components) if identities else "",
        "note": (
            "La run_key e' lo SHA-256 del JSON canonico dei tredici componenti. "
            "Include case_hash e source_profile_hash: se cambiano i dati di input, "
            "le run precedenti non sono piu' compatibili."
        ),
    }
