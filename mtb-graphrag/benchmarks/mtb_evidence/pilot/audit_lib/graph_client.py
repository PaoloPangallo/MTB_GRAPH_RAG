"""Accesso al grafo con import differito e fallimento leggibile.

`backend.pipeline.llm` istanzia il driver Neo4j *e* due client LLM al momento
dell'import. Importarlo a livello di modulo renderebbe questo package inutilizzabile
offline e i test dipendenti da un servizio esterno. Per questo il client reale
risolve `run_cypher` dentro il metodo, alla prima query.

Le credenziali restano quelle gia' configurate dal backend via `.env`: qui non si
legge nessuna password e non si costruisce nessun secondo driver.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .serialize import sanitize_uri


class GraphUnavailable(RuntimeError):
    """Neo4j non e' raggiungibile, o rifiuta le credenziali configurate."""


@runtime_checkable
class GraphClient(Protocol):
    """Superficie minima richiesta dall'audit: eseguire Cypher parametrizzato."""

    def run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        ...


def _readable_failure(error: Exception) -> GraphUnavailable:
    from .connection import describe_connection

    connection = describe_connection()
    return GraphUnavailable(
        "Neo4j non raggiungibile.\n"
        f"  URI       : {connection['uri']}\n"
        f"  database  : {connection['database']}\n"
        f"  causa     : {type(error).__name__}: {error}\n"
        "Avvia l'istanza Neo4j del progetto e verifica NEO4J_URI / NEO4J_USER / "
        "NEO4J_PASSWORD in mtb-graphrag/.env, poi ripeti l'audit."
    )


class Neo4jGraphClient:
    """Client reale, appoggiato a `backend.pipeline.helpers.run_cypher`."""

    def __init__(self) -> None:
        self._run_cypher = None

    def _resolve(self):
        if self._run_cypher is None:
            try:
                from backend.pipeline.helpers import run_cypher
            except Exception as error:  # ImportError, o driver che fallisce all'import
                raise _readable_failure(error) from error
            self._run_cypher = run_cypher
        return self._run_cypher

    def run(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        run_cypher = self._resolve()
        try:
            return list(run_cypher(cypher, params or {}))
        except Exception as error:
            if _is_connectivity_error(error):
                raise _readable_failure(error) from error
            raise


def _is_connectivity_error(error: Exception) -> bool:
    """Distingue i guasti di connessione dagli errori di query, che vanno propagati."""
    name = type(error).__name__
    if name in {
        "ServiceUnavailable",
        "AuthError",
        "SessionExpired",
        "ConfigurationError",
        "ClientError",
    }:
        return name != "ClientError"
    module = type(error).__module__ or ""
    return module.startswith("neo4j") and "Statement" not in name


def sanitized_uri(uri: str) -> str:
    """Riesportato per comodita': un URI privo di credenziali."""
    return sanitize_uri(uri)
