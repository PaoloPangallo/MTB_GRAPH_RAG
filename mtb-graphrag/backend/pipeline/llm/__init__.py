"""
Configurazione LLM e connessione Neo4j.

Carica le credenziali da mtb-graphrag/.env (root della monorepo).
Espone:
  - driver   : Neo4j GraphDatabase driver
  - llm      : ChatOllama per gli agenti della pipeline
  - llm_judge: ChatOllama per LLM-as-judge (fallback)
  - ONCOKB_TOKEN: token per le API OncoKB

Costruzione differita
---------------------
`driver`, `llm` e `llm_judge` sono risolti al primo accesso tramite `__getattr__`
(PEP 562), non all'import del modulo. Prima erano istanziati subito, e questo rendeva
impossibile importare qualunque sottomodulo — registry, adapter, capability — senza
aprire una connessione Neo4j e due client HTTP. I test dovevano evitare del tutto
questo package.

`from backend.pipeline.llm import driver` continua a funzionare identico: la
costruzione avviene in quel momento invece che all'import del package.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ── Carica .env dalla root della monorepo ──────────────────
# Il file vive in mtb-graphrag/.env: da backend/pipeline/llm/__init__.py sono
# quattro livelli sopra (llm -> pipeline -> backend -> mtb-graphrag).
_env_path = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(_env_path)

# ── Neo4j ──────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# ── Ollama Cloud — modelli gratuiti, no GPU ────────────────
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com")
OLLAMA_API_KEY    = os.getenv("OLLAMA_API_KEY", "")

LLM_PIPELINE  = os.getenv("LLM_PIPELINE", "gemma4:31b-cloud")     # agenti della pipeline
LLM_JUDGE     = os.getenv("LLM_JUDGE", "minimax-m2.5")            # LLM-as-judge (fallback)
TEMPERATURE   = 0.0                      # determinismo per uso clinico

# ── OncoKB ─────────────────────────────────────────────────
ONCOKB_TOKEN = os.getenv("ONCOKB_TOKEN", "")

_LAZY_CACHE: dict[str, Any] = {}


def build_llm(*, timeout: int = 60, model: str | None = None):
    """Costruisce un client con lo stesso modello/credenziali della pipeline,
    ma con un timeout di connessione/lettura configurabile. Il timeout va
    sempre impostato qui, sul client HTTP stesso: è l'unico meccanismo che
    interrompe davvero una richiesta di rete bloccata."""
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=model or LLM_PIPELINE,
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
        temperature=TEMPERATURE,
        timeout=timeout,
    )


def _build_driver():
    from neo4j import GraphDatabase

    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


def _build_judge():
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=LLM_JUDGE,
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
        temperature=TEMPERATURE,
        timeout=60,
    )


_LAZY_BUILDERS = {
    "driver": _build_driver,
    "llm": lambda: build_llm(timeout=60),
    "llm_judge": _build_judge,
}


def __getattr__(name: str) -> Any:
    """Costruisce driver e client LLM al primo accesso, una volta sola."""
    builder = _LAZY_BUILDERS.get(name)
    if builder is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name not in _LAZY_CACHE:
        _LAZY_CACHE[name] = builder()
    return _LAZY_CACHE[name]


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_BUILDERS))


def reset_lazy_clients() -> None:
    """Svuota la cache dei client. Utile ai test che cambiano l'ambiente."""
    _LAZY_CACHE.clear()
