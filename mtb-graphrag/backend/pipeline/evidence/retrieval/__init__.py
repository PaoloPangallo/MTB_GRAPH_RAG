"""Selezione esplicita del backend di retrieval delle evidenze.

Il pacchetto contiene il seam fra il retriever legacy e il retriever V3 sul
corpus promosso 1.4. Non contiene ne' l'uno ne' l'altro: contiene il contratto
che li rende intercambiabili e il punto in cui la scelta viene dichiarata.

L'import di questo pacchetto non carica nessun corpus. Il modulo del retriever
V3 — e con lui il loader del corpus promosso — viene importato dentro la
factory, non a livello di modulo, perche' una esecuzione con
`retrieval_backend="legacy"` non deve nemmeno poter toccare i file della 1.4.
"""

from backend.pipeline.evidence.retrieval.backends import (
    ALLOWED_POLICY_MODES,
    BACKEND_LEGACY,
    BACKEND_QUALIFIED_CLAIM_V3,
    DEFAULT_POLICY_MODE,
    DEFAULT_RETRIEVAL_BACKEND,
    RETRIEVAL_BACKENDS,
    SUPPORTED_REPOSITORY_VERSIONS,
    EvidenceRetrievalBackend,
    RetrievalBackendConfig,
    UnknownPolicyModeError,
    UnknownRepositoryVersionError,
    UnknownRetrievalBackendError,
    backend_selection_contract,
)

__all__ = [
    "ALLOWED_POLICY_MODES",
    "BACKEND_LEGACY",
    "BACKEND_QUALIFIED_CLAIM_V3",
    "DEFAULT_POLICY_MODE",
    "DEFAULT_RETRIEVAL_BACKEND",
    "RETRIEVAL_BACKENDS",
    "SUPPORTED_REPOSITORY_VERSIONS",
    "EvidenceRetrievalBackend",
    "RetrievalBackendConfig",
    "UnknownPolicyModeError",
    "UnknownRepositoryVersionError",
    "UnknownRetrievalBackendError",
    "backend_selection_contract",
]
