"""Binding del backend nel livello di orchestrazione.

Il binding sta qui e non nel corpus. Un corpus che sapesse quale retriever lo
usa avrebbe un'opinione sul proprio impiego, e la promozione della 1.4 e'
avvenuta con la promessa opposta: il corpus e' un artefatto versionato, e chi lo
legge e' una decisione di configurazione.

La pipeline espone una firma sola::

    pipeline.run(query, retrieval_backend="legacy")
    pipeline.run(query, retrieval_backend="qualified_claim_v3")

e restituisce un `RetrievalOutcome`, che e' una union tipizzata e non un
denominatore comune. Dentro c'e' l'oggetto che il backend ha prodotto — un
`QualifiedRetrievalOutput` legacy oppure un `QualifiedClaimRetrievalResult` V3 —
non convertito. La conversione sarebbe la cosa piu' comoda e la piu' sbagliata:
appiattire i claim V3 sugli statement legacy perderebbe i bucket, e appiattire
gli statement legacy sui claim V3 affermerebbe una granularita' che il percorso
operativo non ha.

L'isolamento del percorso legacy e' strutturale. Il modulo del retriever V3 —
e con lui il loader del corpus promosso — viene importato **dentro** la factory
del backend V3, mai a livello di modulo. Una `run(..., retrieval_backend="legacy")`
in un processo pulito lascia `backend.pipeline.evidence.corpus.loader` fuori da
`sys.modules`, ed e' un fatto controllabile invece che una convenzione.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from backend.pipeline.evidence.retrieval.backends import (
    BACKEND_LEGACY,
    BACKEND_QUALIFIED_CLAIM_V3,
    DEFAULT_RETRIEVAL_BACKEND,
    RETRIEVAL_BACKENDS,
    RetrievalBackendConfig,
    validate_backend,
)

PIPELINE_VERSION = "evidence_retrieval_pipeline/1.0"


@dataclass(frozen=True)
class RetrievalOutcome:
    """Cosa ha risposto, con quale corpus, e in quanto tempo.

    `payload` e' l'oggetto nativo del backend. Non viene normalizzato: e' la
    union tipizzata di cui parla il docstring del modulo.
    """

    backend_name: str
    repository_version: str
    policy_mode: str
    query_id: str
    payload: Any
    latency_ms: int = 0
    warnings: tuple[str, ...] = ()
    failure_reason: str = ""
    observability: dict[str, Any] = field(default_factory=dict)
    pipeline_version: str = PIPELINE_VERSION

    @property
    def is_v3(self) -> bool:
        return self.backend_name == BACKEND_QUALIFIED_CLAIM_V3

    def to_dict(self) -> dict[str, Any]:
        payload = self.payload
        rendered = payload.as_dict() if hasattr(payload, "as_dict") else None
        if rendered is None and hasattr(payload, "to_dict"):
            rendered = payload.to_dict()
        return {
            "backend_name": self.backend_name,
            "failure_reason": self.failure_reason,
            "latency_ms": self.latency_ms,
            "observability": dict(self.observability),
            "payload": rendered,
            "pipeline_version": self.pipeline_version,
            "policy_mode": self.policy_mode,
            "query_id": self.query_id,
            "repository_version": self.repository_version,
            "warnings": list(self.warnings),
        }


def _build_legacy(config: RetrievalBackendConfig) -> Any:
    from backend.pipeline.evidence.retrieval.legacy_backend import (
        LegacyEvidenceRetrieverAdapter,
    )

    del config  # la configurazione V3 non riguarda il backend legacy
    return LegacyEvidenceRetrieverAdapter.from_corpus()


def _build_v3(config: RetrievalBackendConfig) -> Any:
    # Import locale, e non e' uno stile: e' la ragione per cui una run legacy
    # non tocca il corpus promosso. Vedi il docstring del modulo.
    from backend.pipeline.evidence.retrieval.v3_backend import QualifiedClaimRetrieverV3

    return QualifiedClaimRetrieverV3.from_registry(
        policy_mode=config.qualified_claim_policy_mode,
        repository_version=config.qualified_claim_repository_version,
    )


BACKEND_FACTORIES = {
    BACKEND_LEGACY: _build_legacy,
    BACKEND_QUALIFIED_CLAIM_V3: _build_v3,
}


class EvidenceRetrievalPipeline:
    """Il punto in cui la scelta del backend viene dichiarata e applicata."""

    def __init__(self, config: RetrievalBackendConfig | None = None) -> None:
        self._config = config or RetrievalBackendConfig()
        self._backends: dict[str, Any] = {}

    @classmethod
    def from_config(
        cls, payload: Mapping[str, Any] | None = None
    ) -> "EvidenceRetrievalPipeline":
        """Pipeline da una configurazione di runner, validata alla costruzione."""
        return cls(RetrievalBackendConfig.from_mapping(payload))

    @property
    def config(self) -> RetrievalBackendConfig:
        return self._config

    @property
    def default_backend(self) -> str:
        return self._config.retrieval_backend

    def instantiated_backends(self) -> tuple[str, ...]:
        """Quali backend sono stati davvero costruiti in questa pipeline."""
        return tuple(sorted(self._backends))

    def backend(self, name: str | None = None) -> Any:
        """Il backend richiesto, costruito alla prima richiesta e non prima.

        La costruzione pigra non e' una ottimizzazione: e' cio' che garantisce
        che una pipeline configurata su `legacy` non apra mai il corpus V3,
        nemmeno quando il codice del V3 e' presente nel repository.
        """
        resolved = validate_backend(name if name is not None else self._config.retrieval_backend)
        if resolved not in self._backends:
            self._backends[resolved] = BACKEND_FACTORIES[resolved](self._config)
        return self._backends[resolved]

    def run(
        self,
        query: Mapping[str, Any],
        *,
        retrieval_backend: str | None = None,
    ) -> RetrievalOutcome:
        """Esegue la query sul backend dichiarato. Nessuna selezione automatica."""
        resolved = validate_backend(
            retrieval_backend
            if retrieval_backend is not None
            else self._config.retrieval_backend
        )
        backend = self.backend(resolved)
        started = perf_counter()
        payload = backend.retrieve(query)
        elapsed = int((perf_counter() - started) * 1000)

        warnings = tuple(getattr(payload, "warnings", ()) or ())
        return RetrievalOutcome(
            backend_name=backend.backend_name,
            repository_version=backend.repository_version,
            policy_mode=backend.policy_mode,
            query_id=str(
                getattr(payload, "query_id", "") or query.get("query_id") or ""
            ),
            payload=payload,
            latency_ms=elapsed,
            warnings=warnings,
            observability=self._observability(backend, payload, resolved, elapsed),
        )

    def _observability(
        self, backend: Any, payload: Any, resolved: str, elapsed: int
    ) -> dict[str, Any]:
        """Cio' che va nell'audit log. Nessun dato del gold entra qui."""
        record: dict[str, Any] = {
            "backend_name": backend.backend_name,
            "configured_default_backend": self._config.retrieval_backend,
            "gold_data_recorded": False,
            "latency_ms": {"pipeline_total": elapsed},
            "pipeline_version": PIPELINE_VERSION,
            "policy_mode": backend.policy_mode,
            "repository_version": backend.repository_version,
            "requested_backend": resolved,
            "timestamp": getattr(payload, "timestamp", ""),
        }
        if hasattr(payload, "bucket_counts"):
            record["bucket_counts"] = payload.bucket_counts()
        if hasattr(payload, "gate_decisions"):
            record["gate_decisions"] = dict(payload.gate_decisions)
        if hasattr(payload, "latency_ms"):
            record["latency_ms"] = dict(payload.latency_ms) | {
                "pipeline_total": elapsed
            }
        record["corpus_hash"] = str(
            getattr(payload, "corpus_hash", "")
            or getattr(payload, "corpus_fingerprint", "")
        )
        record["run_id"] = str(getattr(payload, "run_id", ""))
        record["query_id"] = str(getattr(payload, "query_id", ""))
        record["failure_reason"] = str(getattr(payload, "failure_reason", ""))
        return record


def pipeline_binding_manifest() -> dict[str, Any]:
    """Descrizione serializzabile del binding, per gli artefatti della fase."""
    return {
        "available_backends": list(RETRIEVAL_BACKENDS),
        "backend_constructed_lazily": True,
        "binding_layer": "backend.pipeline.evidence.retrieval.pipeline",
        "binding_lives_in_corpus": False,
        "default_backend": DEFAULT_RETRIEVAL_BACKEND,
        "legacy_output_converted_to_v3": False,
        "legacy_path_imports_v3_corpus": False,
        "pipeline_version": PIPELINE_VERSION,
        "result_is_a_typed_union": True,
        "v3_is_default": False,
    }


__all__ = [
    "BACKEND_FACTORIES",
    "PIPELINE_VERSION",
    "EvidenceRetrievalPipeline",
    "RetrievalOutcome",
    "pipeline_binding_manifest",
]
