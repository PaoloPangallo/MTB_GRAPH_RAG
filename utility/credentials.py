"""Lettura delle credenziali dall'ambiente, senza fallback incorporati.

Prima di questo modulo una quindicina di script portava la password Neo4j scritta
nel codice come valore di default di `os.getenv`. Un default del genere e' peggio di
una password mancante: lo script funziona, quindi nessuno si accorge che il segreto
e' versionato, e chiunque legga il repository lo ottiene.

Qui non esiste alcun valore di ripiego. Se una variabile obbligatoria manca, la
lettura fallisce con un messaggio che dice quale variabile serve e dove definirla.
"""

from __future__ import annotations

import os
from pathlib import Path

# Percorsi in cui cercare un .env, in ordine di precedenza.
_ENV_CANDIDATES = (
    Path(__file__).resolve().parents[1] / ".env",
    Path(__file__).resolve().parents[1] / "mtb-graphrag" / ".env",
)


class MissingCredentialError(RuntimeError):
    """Una variabile d'ambiente obbligatoria non e' definita."""


def load_env() -> None:
    """Carica il primo .env disponibile, se python-dotenv e' installato.

    L'assenza di python-dotenv o del file non e' un errore: le variabili possono
    arrivare direttamente dall'ambiente.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in _ENV_CANDIDATES:
        if candidate.is_file():
            load_dotenv(candidate, override=False)
            return


def require_env(name: str, *, hint: str = "") -> str:
    """Restituisce una variabile obbligatoria, oppure fallisce in modo leggibile.

    Non registra mai il valore nel messaggio di errore.
    """
    load_env()
    value = os.environ.get(name, "").strip()
    if value:
        return value
    where = " oppure ".join(str(path) for path in _ENV_CANDIDATES)
    suffix = f"\n  {hint}" if hint else ""
    raise MissingCredentialError(
        f"La variabile d'ambiente {name} non e' definita.\n"
        f"  Definiscila nell'ambiente o in uno di questi file: {where}\n"
        f"  Non esiste alcun valore di default: una credenziale scritta nel codice "
        f"finirebbe nella cronologia Git.{suffix}"
    )


def optional_env(name: str, default: str = "") -> str:
    """Variabile non obbligatoria. Da usare solo per valori non sensibili."""
    load_env()
    return os.environ.get(name, default)


def neo4j_credentials() -> tuple[str, str, str]:
    """URI, utente e password Neo4j. La password e' obbligatoria."""
    uri = optional_env("NEO4J_URI", "bolt://localhost:7687")
    user = optional_env("NEO4J_USER", "neo4j")
    password = require_env(
        "NEO4J_PASSWORD",
        hint="Vedi mtb-graphrag/.env.example per il template delle variabili.",
    )
    return uri, user, password
