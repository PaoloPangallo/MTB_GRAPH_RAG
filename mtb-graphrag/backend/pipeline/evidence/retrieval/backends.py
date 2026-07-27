"""Contratto dei backend di retrieval e configurazione che li seleziona.

Un backend si sceglie dichiarandolo. Non c'e' una regola che deduca quale usare
dalla forma della query, e non c'e' una che scelga il corpus piu' recente fra
quelli presenti sul disco: entrambe farebbero dipendere il comportamento della
pipeline da cio' che e' stato promosso, e la promozione della 1.4 e' avvenuta
proprio con la promessa di non cambiare nulla.

Le tre dimensioni della configurazione sono indipendenti e vengono validate
separatamente:

    retrieval_backend                  quale implementazione risponde
    qualified_claim_repository_version quale corpus il backend V3 carica
    qualified_claim_policy_mode        con quale politica di malattia decide

Un valore sconosciuto su una qualsiasi delle tre e' un errore. Un valore assente
si risolve nella default dichiarata. Le due cose non condividono un ramo: un
fallback silenzioso su un valore sbagliato trasformerebbe un errore di
configurazione in una risposta piu' permissiva di quella chiesta, che e' la
forma di errore piu' difficile da vedere in un risultato clinico.

Il default e' `legacy` e resta `legacy` per tutta questa fase. Il V3 e'
selezionabile, non attivo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from backend.pipeline.evidence.corpus import promotion_contract as CONTRACT

CONTRACT_VERSION = "evidence_retrieval_backend_contract/1.0"

# --- backend ------------------------------------------------------------------

BACKEND_LEGACY = "legacy"
BACKEND_QUALIFIED_CLAIM_V3 = "qualified_claim_v3"

RETRIEVAL_BACKENDS = (BACKEND_LEGACY, BACKEND_QUALIFIED_CLAIM_V3)

# Il default di fase. Cambiarlo e' un atto separato da questa fase, e il test
# `legacy_default_preserved` esiste per renderlo visibile se avvenisse.
DEFAULT_RETRIEVAL_BACKEND = BACKEND_LEGACY

UNKNOWN_BACKEND_BEHAVIOR = "reject"

# --- repository ----------------------------------------------------------------

# L'unica versione che il backend V3 sa caricare. La costante viene dal
# contratto di promozione invece di essere ricopiata: due dichiarazioni della
# stessa versione possono divergere, una sola no.
QUALIFIED_CLAIM_REPOSITORY_VERSION = CONTRACT.REPOSITORY_VERSION
SUPPORTED_REPOSITORY_VERSIONS = (QUALIFIED_CLAIM_REPOSITORY_VERSION,)

# --- policy --------------------------------------------------------------------

DEFAULT_POLICY_MODE = CONTRACT.DEFAULT_POLICY_MODE
ALLOWED_POLICY_MODES = CONTRACT.ALLOWED_POLICY_MODES
UNKNOWN_POLICY_MODE_BEHAVIOR = CONTRACT.UNKNOWN_POLICY_MODE_BEHAVIOR


class RetrievalBackendError(RuntimeError):
    """La configurazione del backend non e' utilizzabile cosi' com'e'."""


class UnknownRetrievalBackendError(RetrievalBackendError):
    """Il backend richiesto non esiste. Non viene risolto nella default."""


class UnknownRepositoryVersionError(RetrievalBackendError):
    """La versione di repository richiesta non e' fra quelle caricabili."""


class UnknownPolicyModeError(RetrievalBackendError):
    """La modalita' di policy richiesta non e' fra quelle ammesse."""


def validate_backend(name: str | None) -> str:
    """Il backend dichiarato, oppure la default. Mai un allargamento."""
    if name is None:
        return DEFAULT_RETRIEVAL_BACKEND
    if name not in RETRIEVAL_BACKENDS:
        raise UnknownRetrievalBackendError(
            f"UNKNOWN_RETRIEVAL_BACKEND — {name!r} non e' fra "
            f"{list(RETRIEVAL_BACKENDS)}; il comportamento dichiarato e' "
            f"{UNKNOWN_BACKEND_BEHAVIOR!r}"
        )
    return name


def validate_repository_version(version: str | None) -> str:
    """La versione dichiarata, oppure quella promossa. Nessuna selezione automatica.

    In particolare non esiste un ramo che scelga "la piu' recente": il corpus
    che il retriever carica e' quello che la configurazione nomina, e un nome
    che non corrisponde a nulla e' un errore invece che un invito a cercare.
    """
    if version is None:
        return QUALIFIED_CLAIM_REPOSITORY_VERSION
    if version not in SUPPORTED_REPOSITORY_VERSIONS:
        raise UnknownRepositoryVersionError(
            f"UNKNOWN_REPOSITORY_VERSION — {version!r} non e' fra "
            f"{list(SUPPORTED_REPOSITORY_VERSIONS)}; nessuna selezione automatica "
            "del corpus piu' recente e' prevista"
        )
    return version


def validate_policy_mode(mode: str | None) -> str:
    """La modalita' dichiarata, oppure `strict_verified`. Mai un allargamento."""
    try:
        return CONTRACT.validate_policy_mode(mode)
    except CONTRACT.PromotionContractError as error:
        raise UnknownPolicyModeError(str(error)) from error


@dataclass(frozen=True)
class RetrievalBackendConfig:
    """Le tre scelte, gia' validate. Costruirla e' l'atto di configurazione."""

    retrieval_backend: str = DEFAULT_RETRIEVAL_BACKEND
    qualified_claim_repository_version: str = QUALIFIED_CLAIM_REPOSITORY_VERSION
    qualified_claim_policy_mode: str = DEFAULT_POLICY_MODE

    def __post_init__(self) -> None:
        # La validazione avviene nella costruzione e non al primo utilizzo: una
        # configurazione sbagliata deve fallire quando viene scritta, non quando
        # una query la incontra.
        object.__setattr__(
            self, "retrieval_backend", validate_backend(self.retrieval_backend)
        )
        object.__setattr__(
            self,
            "qualified_claim_repository_version",
            validate_repository_version(self.qualified_claim_repository_version),
        )
        object.__setattr__(
            self,
            "qualified_claim_policy_mode",
            validate_policy_mode(self.qualified_claim_policy_mode),
        )

    @property
    def is_legacy(self) -> bool:
        return self.retrieval_backend == BACKEND_LEGACY

    @property
    def is_qualified_claim_v3(self) -> bool:
        return self.retrieval_backend == BACKEND_QUALIFIED_CLAIM_V3

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "qualified_claim_policy_mode": self.qualified_claim_policy_mode,
            "qualified_claim_repository_version": self.qualified_claim_repository_version,
            "retrieval_backend": self.retrieval_backend,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any] | None) -> "RetrievalBackendConfig":
        """Configurazione da un dizionario, senza inventare valori.

        Le chiavi assenti si risolvono nelle default; le chiavi presenti con un
        valore sconosciuto sollevano. Una chiave sconosciuta solleva anch'essa:
        una configurazione con un refuso nel nome del campo si comporterebbe
        altrimenti come una configurazione vuota.
        """
        values = dict(payload or {})
        known = {
            "retrieval_backend",
            "qualified_claim_repository_version",
            "qualified_claim_policy_mode",
        }
        unknown = sorted(set(values) - known)
        if unknown:
            raise RetrievalBackendError(
                f"campi di configurazione sconosciuti: {unknown}; ammessi {sorted(known)}"
            )
        return cls(
            retrieval_backend=values.get("retrieval_backend", DEFAULT_RETRIEVAL_BACKEND),
            qualified_claim_repository_version=values.get(
                "qualified_claim_repository_version", QUALIFIED_CLAIM_REPOSITORY_VERSION
            ),
            qualified_claim_policy_mode=values.get(
                "qualified_claim_policy_mode", DEFAULT_POLICY_MODE
            ),
        )


@runtime_checkable
class EvidenceRetrievalBackend(Protocol):
    """Cio' che la pipeline puo' chiedere a un backend, quale che sia.

    Il protocollo non dice nulla sul *tipo* del risultato, e non e' una
    dimenticanza. Un `EvidenceStatement` legacy e un `QualifiedClaimRetrievalResult`
    V3 non sono la stessa cosa vista da due angoli: sono due oggetti con
    granularita' diverse, e costringerli in un tipo comune significherebbe
    appiattire l'uno sull'altro. La pipeline li tiene distinti in una union
    tipizzata e li confronta soltanto sugli assi in cui il confronto ha senso.
    """

    @property
    def backend_name(self) -> str: ...

    @property
    def repository_version(self) -> str: ...

    @property
    def policy_mode(self) -> str: ...

    def retrieve(self, query: Mapping[str, Any]) -> Any: ...

    def health_check(self) -> dict[str, Any]: ...

    def provenance_summary(self) -> dict[str, Any]: ...


def backend_selection_contract() -> dict[str, Any]:
    """Descrizione serializzabile della selezione, per gli artefatti della fase."""
    return {
        "allowed_policy_modes": list(ALLOWED_POLICY_MODES),
        "automatic_latest_corpus_selection": False,
        "available_backends": list(RETRIEVAL_BACKENDS),
        "contract_version": CONTRACT_VERSION,
        "default_policy_mode": DEFAULT_POLICY_MODE,
        "default_retrieval_backend": DEFAULT_RETRIEVAL_BACKEND,
        "silent_fallback_permitted": False,
        "supported_repository_versions": list(SUPPORTED_REPOSITORY_VERSIONS),
        "unknown_backend_behavior": UNKNOWN_BACKEND_BEHAVIOR,
        "unknown_policy_mode_behavior": UNKNOWN_POLICY_MODE_BEHAVIOR,
        "unknown_repository_version_behavior": "reject",
        "v3_is_selectable_not_default": True,
    }


__all__ = [
    "ALLOWED_POLICY_MODES",
    "BACKEND_LEGACY",
    "BACKEND_QUALIFIED_CLAIM_V3",
    "CONTRACT_VERSION",
    "DEFAULT_POLICY_MODE",
    "DEFAULT_RETRIEVAL_BACKEND",
    "QUALIFIED_CLAIM_REPOSITORY_VERSION",
    "RETRIEVAL_BACKENDS",
    "SUPPORTED_REPOSITORY_VERSIONS",
    "UNKNOWN_BACKEND_BEHAVIOR",
    "UNKNOWN_POLICY_MODE_BEHAVIOR",
    "EvidenceRetrievalBackend",
    "RetrievalBackendConfig",
    "RetrievalBackendError",
    "UnknownPolicyModeError",
    "UnknownRepositoryVersionError",
    "UnknownRetrievalBackendError",
    "backend_selection_contract",
    "validate_backend",
    "validate_policy_mode",
    "validate_repository_version",
]
