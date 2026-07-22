"""Adapter Ollama: trasporto HTTP e output strutturati.

Questo modulo e' la sede canonica del client. Non importa nulla dal package
genitore a livello di modulo, quindi puo' essere importato dai test e dagli script
di benchmark senza aprire connessioni.

Due regimi di output strutturato, tenuti distinti perche' danno garanzie diverse:

- `json_schema` (locale, Ollama >= 0.5): lo schema vincola il decoding lato server.
  Se il modello produce JSON, quel JSON e' conforme.
- `prompt_validated` (cloud): lo schema viene chiesto a parole e verificato qui. Il
  modello puo' rispondere qualunque cosa, quindi serve validazione e retry.

Confonderli nei risultati significherebbe attribuire a un modello una robustezza che
viene invece dal server.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .credentials import (
    NoCredentialsAvailable,
    classify_http_failure,
    parse_retry_after,
    sleep_for,
)

DEFAULT_LOCAL_URL = "http://localhost:11434"
DEFAULT_CLOUD_URL = "https://api.ollama.com"
CLOUD_HOST_MARKERS = ("api.ollama.com", "ollama.com")
USER_AGENT = "mtb-graphrag/1.0"

JSON_SCHEMA = "json_schema"
PROMPT_VALIDATED = "prompt_validated"

# Oltre due tentativi si smette: un modello che sbaglia lo schema due volte di
# seguito non lo azzecca al terzo, e continuare nasconde il problema.
MAX_STRUCTURED_RETRIES = 2


class OllamaUnavailable(RuntimeError):
    """L'istanza Ollama non risponde, o rifiuta le credenziali."""


class StructuredOutputError(RuntimeError):
    """Il modello non ha prodotto un JSON conforme entro i tentativi ammessi."""


def is_cloud_endpoint(base_url: str) -> bool:
    return any(marker in (base_url or "") for marker in CLOUD_HOST_MARKERS)


def sanitize_endpoint(base_url: str) -> str:
    """Rimuove eventuali credenziali incorporate nell'URL."""
    if "@" not in (base_url or ""):
        return base_url or ""
    scheme, _, rest = base_url.partition("://")
    _, _, host = rest.partition("@")
    return f"{scheme}://[REDACTED]@{host}"


@dataclass(frozen=True)
class OllamaEndpoint:
    base_url: str
    api_key: str = ""

    @property
    def is_cloud(self) -> bool:
        return is_cloud_endpoint(self.base_url)

    @property
    def kind(self) -> str:
        return "cloud" if self.is_cloud else "local"

    @property
    def sanitized(self) -> str:
        return sanitize_endpoint(self.base_url)


def local_endpoint() -> OllamaEndpoint:
    return OllamaEndpoint(base_url=os.getenv("OLLAMA_LOCAL_URL", DEFAULT_LOCAL_URL))


def configured_endpoint() -> OllamaEndpoint:
    """L'endpoint dichiarato dal progetto in `.env`.

    Il default deve restare allineato a `backend/pipeline/llm/__init__.py`, che usa
    l'endpoint cloud quando `OLLAMA_BASE_URL` non e' definita. Con un default
    diverso, un modello `-cloud` finirebbe instradato su localhost e verrebbe
    classificato come locale, attribuendogli garanzie di structured output che non ha.
    """
    return OllamaEndpoint(
        base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_CLOUD_URL),
        api_key=os.getenv("OLLAMA_API_KEY", ""),
    )


class StreamingResponseError(RuntimeError):
    """Risposta parziale seguita da un errore: la run e' fallita, non degradata."""


def _parse_response_body(
    body: str, endpoint: str, path: str, previous_error: str = ""
) -> dict[str, Any]:
    """Interpreta il corpo della risposta, rifiutando quelle parziali.

    Ollama puo' rispondere NDJSON: una sequenza di oggetti seguita, in caso di guasto,
    da un oggetto con `error`. Una risposta parziale **non va analizzata**: il testo
    generato fino a quel punto e' incompleto, e usarlo produrrebbe una metrica
    calcolata su un output che il modello non ha finito di scrivere.
    """
    stripped = (body or "").strip()
    if not stripped:
        return {}

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        # NDJSON, oppure corpo troncato.
        objects: list[dict[str, Any]] = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                objects.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise StreamingResponseError(
                    f"risposta troncata da {endpoint}{path}: corpo non decodificabile "
                    f"({error.msg}). Il testo parziale non viene analizzato."
                ) from error
        errored = next((item for item in objects if item.get("error")), None)
        if errored is not None:
            raise StreamingResponseError(
                f"errore NDJSON da {endpoint}{path}: {errored.get('error')}. "
                "La risposta parziale non viene analizzata."
            )
        if not objects:
            return {}
        payload = objects[-1]

    if isinstance(payload, dict) and payload.get("error"):
        raise StreamingResponseError(
            f"errore da {endpoint}{path}: {payload.get('error')}"
            + (f" (dopo {previous_error})" if previous_error else "")
        )
    if isinstance(payload, dict) and payload.get("done") is False:
        raise StreamingResponseError(
            f"risposta incompleta da {endpoint}{path}: done=false"
        )
    return payload if isinstance(payload, dict) else {"data": payload}


class OllamaClient:
    """Chiamate REST verso una singola istanza Ollama."""

    def __init__(
        self,
        endpoint: OllamaEndpoint,
        *,
        timeout: float = 60.0,
        credential_pool: Any = None,
        sleeper: Any = None,
    ) -> None:
        self.endpoint = endpoint
        self.timeout = timeout
        self._pool = credential_pool
        self._sleeper = sleeper
        self.last_credential_slot: int | None = None
        self.retry_log: list[dict[str, Any]] = []

    def _authorization(self) -> tuple[str, int | None]:
        """Chiave da usare e il suo slot. Il valore non lascia mai questo metodo."""
        if self._pool is not None and len(self._pool):
            credential = self._pool.current()
            if credential is None:
                raise NoCredentialsAvailable(
                    "tutte le credenziali autorizzate sono state invalidate"
                )
            return credential.value, credential.slot
        return self.endpoint.api_key, None

    def _attempt(self, path: str, payload: dict[str, Any] | None) -> tuple[str, int | None]:
        url = f"{self.endpoint.base_url.rstrip('/')}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method="POST" if data else "GET")
        request.add_header("Content-Type", "application/json")
        # Senza User-Agent esplicito l'endpoint cloud risponde 403: urllib si
        # presenta come "Python-urllib/x.y", che viene rifiutato.
        request.add_header("User-Agent", USER_AGENT)
        api_key, slot = self._authorization()
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read().decode("utf-8"), slot

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Esegue una richiesta applicando la politica di ritentativo.

        401 invalida la credenziale e passa alla successiva; 429 rispetta
        `Retry-After` e attende; 5xx ritenta con backoff. Il valore della chiave non
        compare in nessun messaggio d'errore: solo il `credential_slot`.
        """
        attempt = 0
        last_error = ""
        while True:
            attempt += 1
            try:
                body, slot = self._attempt(path, payload)
                self.last_credential_slot = slot
            except urllib.error.HTTPError as error:
                retry_after = parse_retry_after(error.headers.get("Retry-After"))
                outcome = classify_http_failure(
                    error.code,
                    attempt,
                    retry_after=retry_after,
                    pool_size=len(self._pool) if self._pool else 1,
                )
                self.retry_log.append(
                    {
                        "attempt": attempt,
                        "status": error.code,
                        "credential_slot": self.last_credential_slot,
                        "action": outcome.reason,
                    }
                )
                last_error = f"HTTP {error.code}"
                if not outcome.should_retry:
                    raise OllamaUnavailable(
                        f"Ollama ha risposto {error.code} su {self.endpoint.sanitized}"
                        f"{path}: {outcome.reason}."
                    ) from error
                if outcome.invalidate and self._pool is not None:
                    self._pool.invalidate_current(f"HTTP {error.code}")
                if outcome.rotate and self._pool is not None:
                    self._pool.advance()
                if outcome.wait_seconds:
                    sleep_for(outcome.wait_seconds, self._sleeper)
                continue
            except (urllib.error.URLError, OSError, TimeoutError) as error:
                raise OllamaUnavailable(
                    f"Ollama non raggiungibile su {self.endpoint.sanitized}: {error}. "
                    "Avvia il servizio locale oppure configura OLLAMA_BASE_URL."
                ) from error

            return _parse_response_body(body, self.endpoint.sanitized, path, last_error)

    def version(self) -> str:
        try:
            return str(self._request("/api/version").get("version", "unknown"))
        except OllamaUnavailable:
            return "unknown"

    def list_models(self) -> list[dict[str, Any]]:
        return list(self._request("/api/tags").get("models", []))

    def show(self, model: str) -> dict[str, Any]:
        return self._request("/api/show", {"model": model})

    def reachable(self) -> bool:
        try:
            self._request("/api/tags")
            return True
        except OllamaUnavailable:
            return False

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.0,
        num_ctx: int | None = None,
        seed: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Una chiamata di chat. `json_schema` e' onorato solo dagli endpoint locali."""
        options: dict[str, Any] = {"temperature": temperature}
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        if seed is not None:
            options["seed"] = seed
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        if json_schema is not None:
            payload["format"] = json_schema
        return self._request("/api/chat", payload)


@dataclass
class StructuredResult:
    """Esito di una richiesta di output strutturato, con la traccia dei tentativi."""

    parsed: Any
    raw_outputs: list[str] = field(default_factory=list)
    mode: str = JSON_SCHEMA
    attempts: int = 1
    retries: int = 0
    validation_errors: list[str] = field(default_factory=list)
    latency_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "parsed": self.parsed,
            "raw_outputs": list(self.raw_outputs),
            "structured_output_mode": self.mode,
            "attempts": self.attempts,
            "retries": self.retries,
            "validation_errors": list(self.validation_errors),
            "latency_ms": round(self.latency_ms, 2),
        }


def _message_content(response: dict[str, Any]) -> str:
    return str((response.get("message") or {}).get("content") or "")


# Estrae un oggetto JSON solo se occupa il testo per intero, a parte spazi o un
# blocco markdown. Una regex permissiva su testo libero raccoglierebbe frammenti
# arbitrari e trasformerebbe un output invalido in uno apparentemente valido.
_FENCED = re.compile(r"^\s*```(?:json)?\s*(?P<body>\{.*\}|\[.*\])\s*```\s*$", re.DOTALL)


def parse_strict_json(text: str) -> Any:
    """Parsa JSON, tollerando solo un blocco markdown che avvolge l'intero testo."""
    stripped = (text or "").strip()
    if not stripped:
        raise ValueError("output vuoto")
    fenced = _FENCED.match(stripped)
    if fenced:
        stripped = fenced.group("body")
    return json.loads(stripped)


_REPAIR_TEMPLATE = (
    "Il tuo output precedente non e' JSON valido per lo schema richiesto.\n\n"
    "Output non valido:\n{invalid}\n\n"
    "Errore di validazione:\n{error}\n\n"
    "Schema richiesto:\n{schema}\n\n"
    "Rispondi solo con il JSON corretto, senza testo aggiuntivo."
)


def request_structured(
    client: OllamaClient,
    model: str,
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    mode: str,
    validate: Callable[[Any], Any] | None = None,
    temperature: float = 0.0,
    num_ctx: int | None = None,
    seed: int | None = None,
) -> StructuredResult:
    """Ottiene un output strutturato, validato dal modello dati interno.

    In modalita' `json_schema` lo schema viaggia nel campo `format` e vincola il
    decoding. In `prompt_validated` lo schema e' descritto nel prompt e verificato
    qui, con al massimo due retry e un prompt di riparazione minimale che riceve
    soltanto output invalido, errore e schema — nessun contesto aggiuntivo, che
    altrimenti diventerebbe un canale per suggerire la risposta.

    Dopo l'ultimo tentativo fallito si fallisce chiuso: nessuna correzione
    silenziosa dell'output.
    """
    raw_outputs: list[str] = []
    errors: list[str] = []
    conversation = list(messages)
    schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
    started = time.perf_counter()

    if mode == PROMPT_VALIDATED:
        conversation = conversation + [
            {
                "role": "system",
                "content": (
                    "Rispondi esclusivamente con un oggetto JSON conforme a questo "
                    f"schema, senza testo prima o dopo:\n{schema_text}"
                ),
            }
        ]

    for attempt in range(1, MAX_STRUCTURED_RETRIES + 2):
        response = client.chat(
            model,
            conversation,
            temperature=temperature,
            num_ctx=num_ctx,
            seed=seed,
            json_schema=schema if mode == JSON_SCHEMA else None,
        )
        raw = _message_content(response)
        raw_outputs.append(raw)
        try:
            parsed = parse_strict_json(raw)
            if validate is not None:
                parsed = validate(parsed)
        except Exception as error:  # JSONDecodeError o errore di validazione
            errors.append(f"tentativo {attempt}: {type(error).__name__}: {error}")
            if attempt > MAX_STRUCTURED_RETRIES:
                break
            conversation = list(messages) + [
                {
                    "role": "user",
                    "content": _REPAIR_TEMPLATE.format(
                        invalid=raw[:2000], error=str(error)[:500], schema=schema_text
                    ),
                }
            ]
            continue
        return StructuredResult(
            parsed=parsed,
            raw_outputs=raw_outputs,
            mode=mode,
            attempts=attempt,
            retries=attempt - 1,
            validation_errors=errors,
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    raise StructuredOutputError(
        f"{model}: nessun JSON conforme dopo {MAX_STRUCTURED_RETRIES + 1} tentativi "
        f"in modalita' {mode}. Errori: {errors}"
    )
