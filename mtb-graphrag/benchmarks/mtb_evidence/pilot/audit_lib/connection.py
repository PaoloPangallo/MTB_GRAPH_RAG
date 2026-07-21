"""Descrizione della connessione Neo4j, senza credenziali.

Legge la stessa configurazione del backend (`backend/pipeline/llm.py`, che carica
`mtb-graphrag/.env`) ma non espone mai la password: solo URI sanitizzato, utente e
nome del database finiscono negli artefatti.
"""

from __future__ import annotations

import os
from pathlib import Path

from .serialize import sanitize_uri

# Il backend non passa mai `database=` a `driver.session()`, quindi tutte le query
# colpiscono il database di default dell'istanza.
DEFAULT_DATABASE = "neo4j"


def _load_backend_env() -> None:
    """Carica lo stesso .env del backend, se python-dotenv e' disponibile."""
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=False)


def describe_connection() -> dict[str, str]:
    """Coordinate della connessione, sicure da scrivere su disco."""
    _load_backend_env()
    return {
        "uri": sanitize_uri(os.getenv("NEO4J_URI", "bolt://localhost:7687")),
        "user": os.getenv("NEO4J_USER", "neo4j"),
        "database": os.getenv("NEO4J_DATABASE", DEFAULT_DATABASE),
        "credentials_source": "mtb-graphrag/.env via backend.pipeline.llm",
        "password_recorded": "no",
    }
