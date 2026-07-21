"""Registry dei modelli per ruolo, con revisione tracciabile.

Il codice non deve contenere nomi di modello sparsi: ogni consumatore chiede un
*ruolo*, e il registry risolve quale modello serve quel ruolo secondo l'ambiente.
Cambiare modello diventa una modifica di configurazione, non una modifica di codice.

La `model_revision` e' `provider:model_name:digest`. Il digest identifica i pesi:
due tag possono puntare agli stessi pesi, e lo stesso tag puo' cambiare pesi nel
tempo. Senza digest un esperimento non e' riproducibile.

La temperatura non entra mai nella revision: e' un parametro di campionamento, non
un'identita' del modello. Trattarla come tale renderebbe due run dello stesso
modello indistinguibili da run di modelli diversi.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .model_capabilities import ModelCapabilities, from_show_response
from .ollama_adapter import (
    JSON_SCHEMA,
    PROMPT_VALIDATED,
    OllamaClient,
    OllamaEndpoint,
    OllamaUnavailable,
    configured_endpoint,
    local_endpoint,
)

PROVIDER = "ollama"

# I cinque ruoli del protocollo. Restano separati perche' un modello puo' essere
# adatto a pianificare e inadatto a estrarre qualificatori.
ROLE_PLANNER = "planner"
ROLE_SOURCE_VERIFIER = "source_verifier"
ROLE_FREE_REPORT = "free_report"
ROLE_QUALIFIER_EXTRACTOR = "qualifier_extractor"
ROLE_OPTIONAL_NARRATOR = "optional_narrator"

ROLES = (
    ROLE_PLANNER,
    ROLE_SOURCE_VERIFIER,
    ROLE_FREE_REPORT,
    ROLE_QUALIFIER_EXTRACTOR,
    ROLE_OPTIONAL_NARRATOR,
)

_ROLE_ENV_VARS = {
    ROLE_PLANNER: "OLLAMA_PLANNER_MODEL",
    ROLE_SOURCE_VERIFIER: "OLLAMA_VERIFIER_MODEL",
    ROLE_FREE_REPORT: "OLLAMA_REPORT_MODEL",
    ROLE_QUALIFIER_EXTRACTOR: "OLLAMA_QUALIFIER_MODEL",
    ROLE_OPTIONAL_NARRATOR: "OLLAMA_NARRATOR_MODEL",
}

# Usato quando nessuna variabile di ruolo e' definita. Allineato a llm/__init__.py.
FALLBACK_MODEL_ENV = "LLM_PIPELINE"
FALLBACK_MODEL = "gemma4:31b-cloud"

DEFAULT_NUM_CTX = 16384
DEFAULT_TEMPERATURE = 0.0
DEFAULT_TIMEOUT = 120.0

# Il tag `latest` e' mobile: due run a distanza di giorni possono usare pesi diversi
# sotto lo stesso nome. Negli esperimenti congelati non e' ammesso.
FORBIDDEN_TAGS_IN_EXPERIMENTS = ("latest",)


class ModelConfigurationError(RuntimeError):
    """La configurazione del registry e' incoerente o incompleta."""


@dataclass(frozen=True)
class RunConfig:
    """Parametri di campionamento di una run. Tutti registrati negli artefatti."""

    temperature: float = DEFAULT_TEMPERATURE
    num_ctx: int = DEFAULT_NUM_CTX
    seed: int | None = None
    timeout: float = DEFAULT_TIMEOUT
    prompt_version: str = "v1"
    schema_version: str = "v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "num_ctx": self.num_ctx,
            "seed": self.seed,
            "timeout": self.timeout,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ModelSpec:
    """Un modello risolto per un ruolo, con tutto il necessario a riprodurre la run."""

    role: str
    model_name: str
    endpoint: OllamaEndpoint
    capabilities: ModelCapabilities | None = None
    config: RunConfig = field(default_factory=RunConfig)
    explicit_revision: str = ""

    @property
    def digest(self) -> str:
        return (self.capabilities.digest if self.capabilities else "") or ""

    @property
    def structured_output_mode(self) -> str:
        if self.capabilities:
            return self.capabilities.structured_output_mode
        return PROMPT_VALIDATED if self.endpoint.is_cloud else JSON_SCHEMA

    @property
    def model_revision(self) -> str:
        """`provider:modello:digest`, oppure la revisione esplicita se il digest manca.

        `SOURCE_VERIFIER_MODEL_REVISION` sovrascrive il valore per il ruolo verifier:
        serve quando si vuole invalidare una cache pur restando sullo stesso modello.
        """
        override = os.getenv("SOURCE_VERIFIER_MODEL_REVISION", "").strip()
        if override and self.role == ROLE_SOURCE_VERIFIER:
            return override
        if self.explicit_revision:
            return f"{PROVIDER}:{self.model_name}:{self.explicit_revision}"
        if self.digest:
            return f"{PROVIDER}:{self.model_name}:{self.digest}"
        return f"{PROVIDER}:{self.model_name}:unknown-revision"

    @property
    def uses_forbidden_tag(self) -> bool:
        tag = self.model_name.partition(":")[2]
        return tag in FORBIDDEN_TAGS_IN_EXPERIMENTS

    def as_metadata(self) -> dict[str, Any]:
        """Metadati da registrare in ogni run."""
        capabilities = self.capabilities
        return {
            "role": self.role,
            "model_name": self.model_name,
            "model_digest": self.digest,
            "model_revision": self.model_revision,
            "quantization": capabilities.quantization if capabilities else "",
            "parameter_size": capabilities.parameter_size if capabilities else "",
            "context_length_declared": capabilities.context_length if capabilities else None,
            "tool_calling": capabilities.tool_calling if capabilities else None,
            "structured_output_mode": self.structured_output_mode,
            "endpoint_type": self.endpoint.kind,
            "endpoint": self.endpoint.sanitized,
            "ollama_version": capabilities.ollama_version if capabilities else "unknown",
            **self.config.as_dict(),
        }

    def client(self) -> OllamaClient:
        return OllamaClient(self.endpoint, timeout=self.config.timeout)


def _env_config(seed: int | None = None) -> RunConfig:
    def _float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, "") or default)
        except ValueError:
            return default

    def _int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, "") or default)
        except ValueError:
            return default

    env_seed = os.getenv("OLLAMA_SEED", "").strip()
    resolved_seed = seed if seed is not None else (int(env_seed) if env_seed else None)
    return RunConfig(
        temperature=_float("OLLAMA_TEMPERATURE", DEFAULT_TEMPERATURE),
        num_ctx=_int("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX),
        seed=resolved_seed,
        timeout=_float("OLLAMA_REQUEST_TIMEOUT", DEFAULT_TIMEOUT),
    )


def resolve_model_name(role: str) -> str:
    """Il modello configurato per un ruolo, con ricaduta sul modello di pipeline."""
    if role not in ROLES:
        raise ModelConfigurationError(f"ruolo sconosciuto: {role!r}. Ammessi: {list(ROLES)}")
    explicit = os.getenv(_ROLE_ENV_VARS[role], "").strip()
    if explicit:
        return explicit
    return os.getenv(FALLBACK_MODEL_ENV, "").strip() or FALLBACK_MODEL


def endpoint_for_model(model_name: str) -> OllamaEndpoint:
    """Instrada un modello sull'endpoint giusto.

    Il suffisso `-cloud` e' la convenzione del progetto per i modelli serviti
    dall'endpoint remoto; tutto il resto gira sull'istanza locale. Il routing e'
    deciso dal nome e non dalla configurazione globale, altrimenti un modello locale
    finirebbe sul cloud solo perche' `OLLAMA_BASE_URL` punta la'.
    """
    return configured_endpoint() if model_name.endswith("-cloud") else local_endpoint()


class ModelRegistry:
    """Risolve i ruoli in `ModelSpec`, con rilevazione delle capacita' in cache."""

    def __init__(self, *, probe: bool = True, seed: int | None = None) -> None:
        self._probe = probe
        self._seed = seed
        self._capability_cache: dict[tuple[str, str], ModelCapabilities | None] = {}

    def _capabilities(
        self, model_name: str, endpoint: OllamaEndpoint
    ) -> ModelCapabilities | None:
        if not self._probe:
            return None
        key = (model_name, endpoint.base_url)
        if key in self._capability_cache:
            return self._capability_cache[key]
        # Sull'endpoint cloud i modelli sono elencati senza suffisso.
        remote_name = model_name[: -len("-cloud")] if model_name.endswith("-cloud") else model_name
        client = OllamaClient(endpoint, timeout=30.0)
        result: ModelCapabilities | None = None
        try:
            show = client.show(remote_name)
            listing = next(
                (
                    item
                    for item in client.list_models()
                    if (item.get("name") or "") == remote_name
                ),
                {},
            )
            result = from_show_response(
                remote_name,
                listing,
                show,
                endpoint=endpoint,
                ollama_version=client.version(),
            )
        except OllamaUnavailable:
            result = None
        self._capability_cache[key] = result
        return result

    def spec(
        self,
        role: str,
        *,
        model_name: str | None = None,
        seed: int | None = None,
        explicit_revision: str = "",
    ) -> ModelSpec:
        resolved = model_name or resolve_model_name(role)
        endpoint = endpoint_for_model(resolved)
        return ModelSpec(
            role=role,
            model_name=resolved,
            endpoint=endpoint,
            capabilities=self._capabilities(resolved, endpoint),
            config=_env_config(seed if seed is not None else self._seed),
            explicit_revision=explicit_revision,
        )

    def all_specs(self) -> dict[str, ModelSpec]:
        return {role: self.spec(role) for role in ROLES}


def assert_experiment_safe(specs: dict[str, ModelSpec]) -> list[str]:
    """Problemi che rendono un esperimento non riproducibile.

    Restituisce l'elenco invece di sollevare: chi chiama decide se rifiutare la run
    o registrarli come limite dichiarato.
    """
    problems: list[str] = []
    for role, spec in specs.items():
        if spec.uses_forbidden_tag:
            problems.append(
                f"{role}: il tag `latest` di {spec.model_name} e' mobile e non "
                "identifica pesi stabili"
            )
        if not spec.digest:
            problems.append(
                f"{role}: digest non disponibile per {spec.model_name}; "
                "la revision ricade su un valore esplicito"
            )
    return problems
