"""Scrittura deterministica degli artefatti di audit, con scrubbing delle credenziali.

Due esigenze si incrociano qui. La prima e' la riproducibilita': lo stesso input deve
produrre gli stessi byte, quindi chiavi ordinate, separatori compatti, newline `\\n`
esplicito (altrimenti su Windows arriva `\\r\\n`) e nessun float non deterministico.
La seconda e' che nessun artefatto deve contenere segreti: ogni scrittura passa da
`scrub`, non solo quelle che si sospettano a rischio.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

REDACTED = "[REDACTED]"

# Variabili d'ambiente il cui *valore* non deve mai comparire in un artefatto.
_SECRET_ENV_VARS = (
    "NEO4J_PASSWORD",
    "OLLAMA_API_KEY",
    "ONCOKB_TOKEN",
    "NCBI_API_KEY",
)

# Segreti aggiuntivi da rimuovere, oltre a quelli letti dalle variabili sopra.
# Sono configurabili invece che scritti nel codice: elencare qui una credenziale
# compromessa la manterrebbe versionata, che e' il problema che questo scrubber
# esiste per evitare. Formato: valori separati da virgola.
_EXTRA_SECRETS_VAR = "AUDIT_EXTRA_SECRETS"

# userinfo dentro un URI: bolt://utente:password@host:porta
_URI_USERINFO = re.compile(r"(?P<scheme>[a-zA-Z][\w+.-]*://)(?P<userinfo>[^/@]+)@")


def secret_values() -> tuple[str, ...]:
    """Valori da rimuovere dagli artefatti: segreti d'ambiente piu' quelli noti."""
    values = {
        value
        for name in _SECRET_ENV_VARS
        for value in (os.environ.get(name, "").strip(),)
        if len(value) >= 4
    }
    values.update(
        item.strip()
        for item in os.environ.get(_EXTRA_SECRETS_VAR, "").split(",")
        if len(item.strip()) >= 4
    )
    return tuple(sorted(values, key=len, reverse=True))


def sanitize_uri(uri: str) -> str:
    """Rimuove le credenziali eventualmente incorporate in un URI."""
    return _URI_USERINFO.sub(lambda m: f"{m.group('scheme')}{REDACTED}@", uri or "")


def scrub(value: Any, secrets: Iterable[str] | None = None) -> Any:
    """Copia ricorsiva con i segreti sostituiti. L'originale non viene mutato."""
    active = tuple(secrets) if secrets is not None else secret_values()
    if isinstance(value, str):
        cleaned = sanitize_uri(value)
        for secret in active:
            if secret and secret in cleaned:
                cleaned = cleaned.replace(secret, REDACTED)
        return cleaned
    if isinstance(value, dict):
        return {scrub(k, active): scrub(v, active) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item, active) for item in value]
    return value


def _default(value: Any) -> Any:
    """Rende serializzabili i tipi che il driver Neo4j puo' restituire."""
    if isinstance(value, (set, frozenset)):
        return sorted(str(item) for item in value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def canonical_json(payload: Any) -> str:
    """JSON canonico: chiavi ordinate, separatori compatti, UTF-8 preservato."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_default,
    )


def fingerprint(payload: Any) -> str:
    """SHA-256 del JSON canonico."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _write(path: Path, text: str) -> Path:
    """Scrittura atomica: file temporaneo, fsync, rename.

    `write_text` diretto lascia il file troncato se il processo muore a meta'. Per gli
    artefatti di run e' inaccettabile: una riga JSON parziale rende il resume
    inaffidabile proprio quando serve, cioe' dopo un'interruzione. `os.replace` e'
    atomico su POSIX e su Windows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path


def append_jsonl_atomic(
    path: Path, row: Any, secrets: Iterable[str] | None = None
) -> Path:
    """Aggiunge una riga a un JSONL senza mai lasciarne una parziale.

    Riscrive l'intero file in modo atomico invece di appendere in coda: con file da
    poche centinaia di righe il costo e' trascurabile, e in cambio non esiste alcuna
    finestra in cui il file contenga una riga troncata.
    """
    existing = ""
    if path.is_file():
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
    line = canonical_json(scrub(row, secrets if secrets is not None else secret_values()))
    return _write(path, existing + line + "\n")


def read_jsonl(path: Path) -> list[Any]:
    """Rilegge un JSONL, ignorando una eventuale riga finale troncata.

    Se un file scritto da una versione precedente contiene una riga parziale, va
    scartata e non interpretata: meglio rieseguire quella run che fidarsi di dati
    incompleti.
    """
    target = Path(path)
    if not target.is_file():
        return []
    rows: list[Any] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return rows


def write_json(path: Path, payload: Any, secrets: Iterable[str] | None = None) -> Path:
    """Scrive JSON indentato e deterministico, con i segreti rimossi."""
    body = json.dumps(
        scrub(payload, secrets),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        default=_default,
    )
    return _write(path, body + "\n")


def write_jsonl(path: Path, rows: Iterable[Any], secrets: Iterable[str] | None = None) -> Path:
    """Scrive JSONL: una riga canonica per record, ordine di input preservato."""
    active = tuple(secrets) if secrets is not None else secret_values()
    lines = [canonical_json(scrub(row, active)) for row in rows]
    return _write(path, "".join(line + "\n" for line in lines))


def write_text(path: Path, text: str, secrets: Iterable[str] | None = None) -> Path:
    body = scrub(text, secrets)
    if not body.endswith("\n"):
        body += "\n"
    return _write(path, body)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(Path(path).read_bytes())
    return digest.hexdigest()
