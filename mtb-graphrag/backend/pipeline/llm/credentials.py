"""Pool di credenziali e politica di ritentativo.

Due principi che vincolano tutto il modulo.

**I segreti non escono mai.** Non si registrano chiavi, loro prefissi o suffissi,
header `Authorization`, ne' hash reversibili. L'unica cosa osservabile in un artefatto
e' un `credential_slot`: un intero interno alla sessione, che dice *quale* credenziale
e' stata usata senza dire *quale valore* avesse.

**La rotazione e' resilienza, non elusione.** Serve a sopravvivere a una chiave
revocata o a un guasto, non a superare una quota. Su 429 si rispetta `Retry-After` e
si attende: passare a un'altra chiave per aggirare un limite di account sarebbe un
abuso del provider, e il codice lo consente solo se esplicitamente dichiarato lecito
dalle quote (`OLLAMA_ROTATE_ON_RATE_LIMIT`, di default disattivato).
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Sequence

# Variabile con l'elenco delle chiavi autorizzate, separate da virgola.
KEYS_ENV_VAR = "OLLAMA_API_KEYS"
SINGLE_KEY_ENV_VAR = "OLLAMA_API_KEY"

# La rotazione su 429 e' disattivata per default: usarla per aggirare un rate limit
# di account non e' un comportamento legittimo verso il provider.
ROTATE_ON_RATE_LIMIT_VAR = "OLLAMA_ROTATE_ON_RATE_LIMIT"

MAX_ATTEMPTS_RATE_LIMIT = 4
MAX_ATTEMPTS_SERVER_ERROR = 3
BASE_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 60.0


class NoCredentialsAvailable(RuntimeError):
    """Tutte le credenziali autorizzate sono state invalidate."""


@dataclass
class _Credential:
    slot: int
    value: str
    valid: bool = True
    invalidated_reason: str = ""


@dataclass
class CredentialPool:
    """Le chiavi autorizzate, identificate solo dal loro slot.

    `OLLAMA_API_KEYS` deve contenere **esclusivamente chiavi autorizzate**: il pool
    non verifica la provenienza, si limita a non esporne il valore.
    """

    _credentials: list[_Credential] = field(default_factory=list)
    _index: int = 0

    @classmethod
    def from_env(cls) -> "CredentialPool":
        raw = os.getenv(KEYS_ENV_VAR, "")
        values = [item.strip() for item in raw.split(",") if item.strip()]
        if not values:
            single = os.getenv(SINGLE_KEY_ENV_VAR, "").strip()
            values = [single] if single else []
        return cls(
            _credentials=[
                _Credential(slot=index, value=value) for index, value in enumerate(values)
            ]
        )

    def __len__(self) -> int:
        return len(self._credentials)

    @property
    def slots(self) -> tuple[int, ...]:
        return tuple(item.slot for item in self._credentials)

    @property
    def active_slots(self) -> tuple[int, ...]:
        return tuple(item.slot for item in self._credentials if item.valid)

    def current(self) -> _Credential | None:
        """La credenziale in uso, saltando quelle invalidate."""
        for offset in range(len(self._credentials)):
            candidate = self._credentials[(self._index + offset) % len(self._credentials)]
            if candidate.valid:
                self._index = (self._index + offset) % len(self._credentials)
                return candidate
        return None

    def invalidate_current(self, reason: str) -> None:
        """Marca la credenziale corrente come inutilizzabile per questa sessione."""
        credential = self.current()
        if credential is None:
            return
        credential.valid = False
        credential.invalidated_reason = reason

    def advance(self) -> bool:
        """Passa alla credenziale successiva ancora valida."""
        if not self.active_slots:
            return False
        self._index = (self._index + 1) % len(self._credentials)
        return self.current() is not None

    def report(self) -> dict[str, object]:
        """Stato del pool, senza alcun valore di chiave."""
        return {
            "credential_count": len(self._credentials),
            "active_slots": list(self.active_slots),
            "invalidated": [
                {"credential_slot": item.slot, "reason": item.invalidated_reason}
                for item in self._credentials
                if not item.valid
            ],
            "note": "nessun valore di chiave, prefisso, suffisso o hash e' registrato",
        }


def rotation_on_rate_limit_allowed() -> bool:
    """La rotazione su 429 e' lecita solo se le quote del provider la consentono."""
    return os.getenv(ROTATE_ON_RATE_LIMIT_VAR, "").strip().lower() in {"1", "true", "yes"}


def backoff_seconds(attempt: int, retry_after: float | None = None) -> float:
    """Attesa prima del ritentativo.

    `Retry-After` del provider vince sempre: e' l'unica indicazione autorevole su
    quando sara' accettata una nuova richiesta. In sua assenza, backoff esponenziale
    con jitter, che evita di sincronizzare i ritentativi di piu' processi.
    """
    if retry_after is not None and retry_after >= 0:
        return min(float(retry_after), MAX_BACKOFF_SECONDS)
    exponential = BASE_BACKOFF_SECONDS * (2 ** max(attempt - 1, 0))
    jitter = random.uniform(0, BASE_BACKOFF_SECONDS)
    return min(exponential + jitter, MAX_BACKOFF_SECONDS)


@dataclass
class RetryOutcome:
    should_retry: bool
    wait_seconds: float = 0.0
    rotate: bool = False
    invalidate: bool = False
    reason: str = ""


def classify_http_failure(
    status: int, attempt: int, *, retry_after: float | None = None, pool_size: int = 1
) -> RetryOutcome:
    """Decide che fare di un fallimento HTTP.

    - **401**: la chiave non e' valida. Si invalida e si passa alla successiva; a
      esaurimento si fallisce.
    - **429**: si e' raggiunto un limite. Si rispetta `Retry-After` e si attende. La
      rotazione avviene solo se dichiarata lecita: usarla di default significherebbe
      aggirare la quota del provider.
    - **5xx**: guasto lato server, ritentativo limitato con backoff.
    """
    if status == 401:
        return RetryOutcome(
            should_retry=pool_size > 1,
            rotate=True,
            invalidate=True,
            reason="credenziale rifiutata: invalidata, si prova la successiva",
        )
    if status == 429:
        if attempt >= MAX_ATTEMPTS_RATE_LIMIT:
            return RetryOutcome(False, reason="rate limit persistente dopo i ritentativi")
        return RetryOutcome(
            should_retry=True,
            wait_seconds=backoff_seconds(attempt, retry_after),
            rotate=rotation_on_rate_limit_allowed(),
            reason=(
                "rate limit: attesa e ritentativo"
                + ("; rotazione consentita dalle quote" if rotation_on_rate_limit_allowed()
                   else "; rotazione non usata per non aggirare la quota")
            ),
        )
    if 500 <= status < 600:
        if attempt >= MAX_ATTEMPTS_SERVER_ERROR:
            return RetryOutcome(False, reason="errore server persistente")
        return RetryOutcome(
            should_retry=True,
            wait_seconds=backoff_seconds(attempt),
            reason="errore server: ritentativo con backoff",
        )
    return RetryOutcome(False, reason=f"HTTP {status} non ritentabile")


def sleep_for(seconds: float, sleeper: Callable[[float], None] | None = None) -> None:
    """Attesa iniettabile, così i test non aspettano davvero."""
    (sleeper or time.sleep)(max(seconds, 0.0))


def parse_retry_after(value: str | None) -> float | None:
    """`Retry-After` in secondi. Il formato data HTTP non e' supportato: si ignora."""
    if not value:
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def redact_headers(headers: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    """Header sicuri da registrare: `Authorization` non compare mai."""
    return [
        (name, "[REDACTED]" if name.lower() == "authorization" else value)
        for name, value in headers
    ]
