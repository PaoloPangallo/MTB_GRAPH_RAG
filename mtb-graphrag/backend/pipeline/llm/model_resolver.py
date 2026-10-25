"""Risoluzione di un modello richiesto sull'endpoint che lo serve davvero.

Prima di questo modulo il routing era una regola scritta nel codice:
`model_name.endswith("-cloud")` decideva l'endpoint, e il suffisso veniva rimosso a
mano per interrogare il server. E' fragile in entrambe le direzioni. Un modello
locale chiamato `qualcosa-cloud` finirebbe sul cloud; un modello cloud servito con un
altro nome non verrebbe trovato; e se il provider cambia convenzione, il codice mente
senza fallire.

Qui il modello si risolve **interrogando l'inventario del server effettivo**. Si
costruisce un indice di cio' che ogni endpoint dichiara di servire, e la richiesta si
cerca in quell'indice. Il suffisso `-cloud` resta solo come *alias di progetto*
applicato in base al tipo di endpoint osservato, non come regola sul nome.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .model_capabilities import ModelCapabilities, from_show_response
from .ollama_adapter import (
    OllamaClient,
    OllamaEndpoint,
    OllamaUnavailable,
    configured_endpoint,
    local_endpoint,
)

PROVIDER = "ollama"

# Come il modello viene servito. La distinzione conta: cambia chi impone lo schema di
# output e chi applica i rate limit.
MODE_LOCAL = "local"
MODE_LOCAL_PROXY_TO_CLOUD = "local_proxy_to_cloud"
MODE_DIRECT_CLOUD_API = "direct_cloud_api"

# Suffisso con cui il progetto distingue i modelli remoti. Non e' una regola di
# routing: e' un'etichetta applicata a cio' che l'endpoint dichiara.
PROJECT_CLOUD_ALIAS_SUFFIX = "-cloud"


@dataclass(frozen=True)
class ModelResolution:
    """Dove e come un modello richiesto viene effettivamente servito."""

    requested_model_tag: str
    resolved: bool
    effective_api_model: str = ""
    endpoint: OllamaEndpoint | None = None
    endpoint_mode: str = ""
    endpoint_url_sanitized: str = ""
    digest: str = ""
    capabilities: ModelCapabilities | None = None
    reason: str = ""
    explicit_revision: str = ""

    @property
    def model_revision(self) -> str:
        if self.explicit_revision:
            return f"{PROVIDER}:{self.effective_api_model}:{self.explicit_revision}"
        if self.digest:
            return f"{PROVIDER}:{self.effective_api_model}:{self.digest}"
        return f"{PROVIDER}:{self.requested_model_tag}:unknown-revision"

    @property
    def structured_output_mode(self) -> str:
        from .ollama_adapter import JSON_SCHEMA, PROMPT_VALIDATED

        if self.capabilities is not None:
            return self.capabilities.structured_output_mode
        return JSON_SCHEMA if self.endpoint_mode == MODE_LOCAL else PROMPT_VALIDATED

    def as_dict(self) -> dict[str, Any]:
        capabilities = self.capabilities
        return {
            "requested_model_tag": self.requested_model_tag,
            "effective_api_model": self.effective_api_model,
            "endpoint_mode": self.endpoint_mode,
            "endpoint_url_sanitized": self.endpoint_url_sanitized,
            "digest": self.digest,
            "model_revision": self.model_revision,
            "resolved": self.resolved,
            "reason": self.reason,
            "structured_output_mode": self.structured_output_mode,
            "parameter_size": capabilities.parameter_size if capabilities else "",
            "family": capabilities.family if capabilities else "",
            "tool_calling": capabilities.tool_calling if capabilities else None,
            "context_length_declared": capabilities.context_length if capabilities else None,
            # Non esposto dall'API di Ollama per nessun modello: registrato come
            # assente invece che stimato.
            "active_parameters": None,
            "active_parameters_note": "non esposto dall'API del provider",
        }


def _endpoint_mode(endpoint: OllamaEndpoint, server_reported_name: str) -> str:
    """Modalita' dedotta da cio' che il server dichiara, non dal nome richiesto.

    Un endpoint locale che elenca un modello marcato come remoto **dal server stesso**
    sta facendo da proxy verso il cloud: e' un'osservazione, non un'inferenza sul nome
    che abbiamo chiesto noi.
    """
    if endpoint.is_cloud:
        return MODE_DIRECT_CLOUD_API
    if server_reported_name.endswith(PROJECT_CLOUD_ALIAS_SUFFIX):
        return MODE_LOCAL_PROXY_TO_CLOUD
    return MODE_LOCAL


@dataclass
class _EndpointIndex:
    endpoint: OllamaEndpoint
    reachable: bool
    version: str = "unknown"
    listings: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)


class ModelResolver:
    """Indice dei modelli osservati su piu' endpoint, con cache per sessione."""

    def __init__(
        self,
        endpoints: Sequence[OllamaEndpoint] | None = None,
        *,
        timeout: float = 30.0,
        client_factory=None,
    ) -> None:
        if endpoints is None:
            local = local_endpoint()
            configured = configured_endpoint()
            endpoints = [local]
            if configured.base_url.rstrip("/") != local.base_url.rstrip("/"):
                endpoints.append(configured)
        self._endpoints = list(endpoints)
        self._timeout = timeout
        self._client_factory = client_factory or (
            lambda endpoint: OllamaClient(endpoint, timeout=timeout)
        )
        self._indexes: list[_EndpointIndex] | None = None

    def _build_index(self) -> list[_EndpointIndex]:
        if self._indexes is not None:
            return self._indexes
        indexes: list[_EndpointIndex] = []
        for endpoint in self._endpoints:
            client = self._client_factory(endpoint)
            try:
                listings = client.list_models()
            except OllamaUnavailable:
                indexes.append(_EndpointIndex(endpoint=endpoint, reachable=False))
                continue
            index = _EndpointIndex(
                endpoint=endpoint, reachable=True, version=client.version()
            )
            for listing in listings:
                name = str(listing.get("name") or listing.get("model") or "")
                if not name:
                    continue
                index.listings[name] = listing
                index.aliases[name] = name
                # Alias di progetto: applicato in base al tipo di endpoint osservato.
                if endpoint.is_cloud and not name.endswith(PROJECT_CLOUD_ALIAS_SUFFIX):
                    index.aliases.setdefault(f"{name}{PROJECT_CLOUD_ALIAS_SUFFIX}", name)
            indexes.append(index)
        self._indexes = indexes
        return indexes

    def available_tags(self) -> dict[str, str]:
        """Tutti i tag risolvibili, con l'endpoint che li serve."""
        available: dict[str, str] = {}
        for index in self._build_index():
            if not index.reachable:
                continue
            for alias in index.aliases:
                available.setdefault(alias, index.endpoint.sanitized)
        return dict(sorted(available.items()))

    def resolve(
        self, requested_model_tag: str, *, explicit_revision: str = ""
    ) -> ModelResolution:
        """Trova dove il tag richiesto e' effettivamente servito."""
        unreachable: list[str] = []
        for index in self._build_index():
            if not index.reachable:
                unreachable.append(index.endpoint.sanitized)
                continue
            effective = index.aliases.get(requested_model_tag)
            if effective is None:
                continue

            client = self._client_factory(index.endpoint)
            try:
                show = client.show(effective)
            except OllamaUnavailable as error:
                return ModelResolution(
                    requested_model_tag=requested_model_tag,
                    resolved=False,
                    reason=f"modello elencato ma non interrogabile: {error}",
                )
            capabilities = from_show_response(
                effective,
                index.listings.get(effective, {}),
                show,
                endpoint=index.endpoint,
                ollama_version=index.version,
            )
            return ModelResolution(
                requested_model_tag=requested_model_tag,
                resolved=True,
                effective_api_model=effective,
                endpoint=index.endpoint,
                endpoint_mode=_endpoint_mode(index.endpoint, effective),
                endpoint_url_sanitized=index.endpoint.sanitized,
                digest=capabilities.digest,
                capabilities=capabilities,
                explicit_revision=explicit_revision,
                reason="risolto dall'inventario del server",
            )

        detail = (
            f"; endpoint non raggiungibili: {unreachable}" if unreachable else ""
        )
        return ModelResolution(
            requested_model_tag=requested_model_tag,
            resolved=False,
            reason=(
                f"nessun endpoint interrogato dichiara di servire "
                f"{requested_model_tag!r}{detail}"
            ),
        )
