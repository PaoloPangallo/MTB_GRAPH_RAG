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


#: Host che serve il percorso OpenAI-compatible.
#:
#: ``backend/pipeline/llm`` ha come default ``https://api.ollama.com``, che
#: risponde **HTTP 405 Method Not Allowed** su ``/v1/chat/completions``: con
#: quel default *tutte* le chiamate del research runtime falliscono a livello di
#: trasporto (verificato: 35/35 nello smoke RQ4). ``https://ollama.com`` serve
#: lo stesso percorso e accetta il ``tool_choice`` forzato.
#:
#: Il default di ``backend/pipeline/llm`` **non** viene corretto: quel modulo è
#: sigillato dal manifest dell'esperimento finale
#: (``benchmarks/mtb_evidence/final_experiment/systems_v1.json``) e modificarlo
#: invaliderebbe un esperimento concluso. Il default corretto vive qui, che è
#: l'unico punto in cui il research runtime costruisce l'endpoint.
RESEARCH_BASE_URL = "https://ollama.com"

#: Host noti per non servire il percorso OpenAI-compatible.
KNOWN_BAD_HOSTS = ("api.ollama.com",)


class LLMEndpointMisconfigured(RuntimeError):
    """L'endpoint risolto non può servire una tool call.

    Fallire qui è deliberato: un fallback silenzioso su un host diverso da
    quello configurato renderebbe irriproducibile la run, e proseguire verso un
    host che risponde 405 produrrebbe 35 fallimenti di trasporto indistinguibili
    da un'astensione del modello.
    """


def base_url() -> str:
    """Unico punto di costruzione dell'host. Precedenza esplicita.

    1. ``RESEARCH_PIPELINE_LLM_BASE_URL`` — override di run;
    2. ``OLLAMA_BASE_URL`` **solo se impostata esplicitamente** nell'ambiente;
    3. ``RESEARCH_BASE_URL`` — default corretto del research runtime.

    Il punto 2 è deliberato: se l'utente imposta ``OLLAMA_BASE_URL`` la sua
    scelta vale, ma il *default* del modulo sigillato non viene ereditato.
    """
    override = os.getenv("RESEARCH_PIPELINE_LLM_BASE_URL")
    if override:
        return override.rstrip("/")
    configured = os.getenv("OLLAMA_BASE_URL")
    if configured:
        return configured.rstrip("/")
    return RESEARCH_BASE_URL


#: Modello del pilot, riprodotto alla lettera. ``LLM_PIPELINE`` vale
#: ``gemma4:31b-cloud``: denota lo stesso modello, ma il tag registrato negli
#: artefatti del commit ``6ee64c5`` è ``gemma4:cloud``, e una run LIVE che si
#: confronta con quegli artefatti deve dichiarare lo stesso tag. Un confronto fra
#: due tag diversi dello stesso modello sarebbe indistinguibile da un confronto
#: fra due modelli.
RESEARCH_MODEL = "gemma4:cloud"


def model_name() -> str:
    """Modello usato dagli stage 2 e 9.

    ``LLM_PIPELINE`` resta il default della pipeline di prodotto; qui il default
    è il tag del pilot, sovrascrivibile con ``RESEARCH_PIPELINE_MODEL``.
    """
    return os.getenv("RESEARCH_PIPELINE_MODEL") or RESEARCH_MODEL


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
    host = url.split("//", 1)[-1].split("/", 1)[0].lower()
    if host in KNOWN_BAD_HOSTS:
        raise LLMEndpointMisconfigured(
            f"{url}{CHAT_COMPLETIONS_PATH} non è servito da {host}: quell'host "
            "risponde HTTP 405 sul percorso OpenAI-compatible. Impostare "
            "RESEARCH_PIPELINE_LLM_BASE_URL o OLLAMA_BASE_URL su un host che lo "
            f"serve (default del research runtime: {RESEARCH_BASE_URL}). "
            "Nessun fallback automatico: cambiare host in silenzio renderebbe "
            "la run irriproducibile."
        )
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
