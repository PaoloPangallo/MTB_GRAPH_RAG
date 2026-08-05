"""Configurazione delle chiamate LLM del research runtime — endpoint cloud.

Il transport del pilot puntava a ``http://localhost:11434``, cioè a un Ollama
locale. Le chiamate devono avvenire in cloud, e la configurazione canonica
esiste già in ``backend/pipeline/llm/__init__.py``: ``OLLAMA_BASE_URL``
(default ``https://api.ollama.com``), ``OLLAMA_API_KEY`` e ``LLM_PIPELINE``,
caricate da ``mtb-graphrag/.env``.

Quel modulo è **sigillato** dal manifest dell'esperimento finale, quindi viene
importato in sola lettura: leggere non altera i byte e non rompe il sigillo.
L'import è anche sicuro rispetto agli effetti collaterali — ``driver`` e ``llm``
sono risolti pigramente via PEP 562, e a livello di modulo viene eseguito solo
``load_dotenv``.

La chiave non compare mai in log, payload o eventi. Il ledger la redigerebbe
comunque (``sanitize_text`` riconosce ``Bearer <token>``), ma la difesa
primaria è non farcela arrivare.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from backend.pipeline.llm import (
    LLM_PIPELINE,
    OLLAMA_API_KEY,
    OLLAMA_BASE_URL,
)

#: Percorso OpenAI-compatible usato dal transport del pilot. Serve il
#: ``tool_choice`` forzato, che il client LangChain non espone allo stesso modo:
#: per questo il transport resta su ``requests`` e non su ``ChatOllama``.
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

DEFAULT_TIMEOUT_SECONDS = 60


class MissingLLMCredentials(RuntimeError):
    """Sollevata quando manca la chiave e verrebbe tentata una chiamata reale.

    Fallire qui è deliberato: un fallback silenzioso su un risultato vuoto
    verrebbe letto a valle come un'astensione del modello, cioè un guasto
    infrastrutturale travestito da esito legittimo della pipeline.
    """


@dataclass(frozen=True)
class LLMEndpoint:
    """Coordinate di una chiamata LLM, senza la chiave in chiaro nel repr."""

    url: str
    model: str
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def headers(self, api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers


def base_url() -> str:
    return os.getenv("RESEARCH_PIPELINE_LLM_BASE_URL", OLLAMA_BASE_URL).rstrip("/")


def model_name() -> str:
    """Modello usato dagli stage 2 e 9.

    Default alla configurazione canonica: ``gemma4:31b-cloud`` e ``gemma4:cloud``
    denotano lo stesso modello, quindi riusare ``LLM_PIPELINE`` non altera le
    condizioni sperimentali del pilot.
    """
    return os.getenv("RESEARCH_PIPELINE_MODEL", LLM_PIPELINE)


def api_key() -> str:
    return os.getenv("RESEARCH_PIPELINE_LLM_API_KEY", OLLAMA_API_KEY)


def is_local_endpoint(url: str) -> bool:
    return "localhost" in url or "127.0.0.1" in url


def resolve_endpoint(*, require_credentials: bool = True) -> LLMEndpoint:
    """Endpoint per una chiamata reale.

    ``require_credentials`` è ``False`` solo per ispezionare la configurazione
    senza intenzione di chiamare: non è una modalità di esecuzione degradata.
    """
    url = base_url()
    if require_credentials and not api_key() and not is_local_endpoint(url):
        raise MissingLLMCredentials(
            "OLLAMA_API_KEY (o RESEARCH_PIPELINE_LLM_API_KEY) non impostata: "
            f"impossibile chiamare {url}. La pipeline non produce risultati "
            "simulati quando il provider non è raggiungibile."
        )
    return LLMEndpoint(
        url=f"{url}{CHAT_COMPLETIONS_PATH}",
        model=model_name(),
        timeout_seconds=int(os.getenv("RESEARCH_PIPELINE_LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
    )


def describe() -> dict[str, object]:
    """Configurazione per la UI. **Non** espone la chiave, solo la sua presenza."""
    url = base_url()
    return {
        "base_url": url,
        "model": model_name(),
        "credentials_configured": bool(api_key()),
        "is_cloud": not is_local_endpoint(url),
    }
