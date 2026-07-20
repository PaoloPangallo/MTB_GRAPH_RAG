"""
Configurazione LLM e connessione Neo4j.

Carica le credenziali da mtb-graphrag/.env (root della monorepo).
Espone:
  - driver   : Neo4j GraphDatabase driver
  - llm      : ChatOllama per gli agenti della pipeline (Gemma 4 31B)
  - llm_judge: ChatOllama per LLM-as-judge (Gemma 4 31B, fallback)
  - ONCOKB_TOKEN: token per le API OncoKB
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from neo4j import GraphDatabase

# ── Carica .env dalla root della monorepo ──────────────────
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

# ── Neo4j ──────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# ── Ollama Cloud — modelli gratuiti, no GPU ────────────────
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "https://api.ollama.com")
OLLAMA_API_KEY    = os.getenv("OLLAMA_API_KEY", "")

LLM_PIPELINE  = os.getenv("LLM_PIPELINE", "gemma4:31b-cloud")       # agenti della pipeline
LLM_JUDGE     = os.getenv("LLM_JUDGE", "minimax-m2.5")           # LLM-as-judge per valutazione (fallback)
TEMPERATURE   = 0.0                      # determinismo per uso clinico

def build_llm(*, timeout: int = 60) -> ChatOllama:
    """Costruisce un client con lo stesso modello/credenziali della pipeline,
    ma con un timeout di connessione/lettura configurabile. Il timeout va
    sempre impostato qui, sul client HTTP stesso: è l'unico meccanismo che
    interrompe davvero una richiesta di rete bloccata."""
    return ChatOllama(
        model=LLM_PIPELINE,
        base_url=OLLAMA_BASE_URL,
        api_key=OLLAMA_API_KEY,
        temperature=TEMPERATURE,
        timeout=timeout,
    )


llm = build_llm(timeout=60)

llm_judge = ChatOllama(
    model=LLM_JUDGE,
    base_url=OLLAMA_BASE_URL,
    api_key=OLLAMA_API_KEY,
    temperature=TEMPERATURE,
    timeout=60,
)

# ── OncoKB ─────────────────────────────────────────────────
ONCOKB_TOKEN = os.getenv("ONCOKB_TOKEN", "")
