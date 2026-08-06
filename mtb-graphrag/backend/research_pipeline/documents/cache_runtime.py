"""Collegamento fra il runtime di ricerca e la cache documentale autorizzata.

La cache resta dove è, fuori dal repository e fuori dal frontend: qui non viene
copiata, duplicata né riscritta. Questo modulo fa tre cose e nessun'altra —
risolve il percorso da configurazione, verifica che sia utilizzabile, e legge.

**Sola lettura imposta, non promessa.** ``AuthorizedDocumentCache`` è nata per
popolare la cache: il suo costruttore crea sette directory e i suoi metodi
scrivono sul manifest. Riusarla così com'è significherebbe che una run di sola
lettura può modificare la cache. ``ReadOnlyDocumentCache`` eredita i soli parser
e rende ogni percorso di scrittura un errore immediato, così la proprietà è
verificabile con un test invece che affidata alla disciplina del chiamante.

**Nessun fallback.** Se la cache non è disponibile la lettura fallisce con un
errore esplicito. Non esiste un percorso che, non trovandola, rigiochi un
artefatto registrato: sarebbe la sostituzione silenziosa che il mandato vieta.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .authorized_cache import AuthorizedDocumentCache

#: Variabile canonica. ``RESEARCH_PIPELINE_CACHE_ROOT`` resta accettata perché
#: già documentata; ``DOCUMENT_GROUNDING_CACHE`` era relativa alla directory di
#: lavoro del processo ed è la sola delle tre a non essere affidabile.
CACHE_PATH_ENV = "RESEARCH_DOCUMENT_CACHE_PATH"
LEGACY_CACHE_PATH_ENV = "RESEARCH_PIPELINE_CACHE_ROOT"

CACHE_LAYOUT_VERSION = "authorized-document-cache/1.0"

#: Sottocartelle che devono esistere perché la cache sia riconoscibile come tale.
#: Una directory vuota qualsiasi non è una cache: accettarla produrrebbe zero
#: documenti risolti, indistinguibili da documenti realmente non disponibili.
_REQUIRED_SUBDIRECTORIES = ("pubmed", "pmc", "clinical_trials")


class DocumentCacheUnavailable(RuntimeError):
    """La cache documentale non è utilizzabile.

    Sollevata invece di degradare: senza documenti la pipeline non può risolvere
    nulla, e un risultato vuoto verrebbe letto a valle come "nessun documento
    disponibile per questa candidate", cioè un guasto di configurazione
    travestito da esito della pipeline.
    """


class CacheIsReadOnly(RuntimeError):
    """Tentativo di scrittura su una cache aperta in sola lettura."""


class ReadOnlyDocumentCache(AuthorizedDocumentCache):
    """``AuthorizedDocumentCache`` senza alcun percorso di scrittura né di rete.

    Non chiama ``super().__init__``: quel costruttore crea directory, e creare
    directory è già una scrittura.
    """

    resolver_version = "read-only-document-cache/1.0"

    def __init__(self, root: str | Path) -> None:  # noqa: D107 — vedi docstring di classe
        self.root = Path(root)
        self.network = False
        self.delay_seconds = 0.0
        self.manifest_path = self.root / "manifests" / "documents.jsonl"
        self.user_agent = ""

    def _request(self, url: str) -> tuple[bytes | None, dict[str, Any]]:
        raise CacheIsReadOnly(f"nessun fetch di rete in Document Resolution: {url}")

    def _write_payload(self, relative: str, payload: bytes) -> tuple[str, str]:
        raise CacheIsReadOnly(f"scrittura vietata sulla cache in sola lettura: {relative}")

    def _record(self, record: dict[str, Any]) -> dict[str, Any]:
        raise CacheIsReadOnly("il manifest della cache non viene modificato da una run")


def _configured_path() -> str | None:
    for name in (CACHE_PATH_ENV, LEGACY_CACHE_PATH_ENV):
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def cache_path() -> Path:
    """Percorso della cache. Nessun valore assoluto cablato nel sorgente.

    In assenza di configurazione si usa la posizione convenzionale **relativa
    alla radice dei dati**, non alla directory di lavoro: il runtime può essere
    avviato da qualunque cartella.
    """
    from backend.research_pipeline import data_access as da

    configured = _configured_path()
    if configured:
        return Path(configured).expanduser().resolve()
    return (da.data_root() / "data_cache" / "document_grounding").resolve()


def redact_path(path: Path) -> str:
    """Percorso mostrabile: le ultime due componenti, mai la home dell'utente."""
    parts = path.parts
    tail = parts[-2:] if len(parts) >= 2 else parts
    # ASCII: questo valore finisce in log e console Windows, dove un'ellissi
    # tipografica si rende come byte illeggibili.
    return ".../" + "/".join(tail)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cache(path: Path | None = None) -> tuple[bool, list[str]]:
    """Verifica all'avvio. Restituisce ``(utilizzabile, reason_codes)``."""
    root = path or cache_path()
    reasons: list[str] = []
    if not root.exists():
        return False, ["CACHE_PATH_NOT_FOUND"]
    if not root.is_dir():
        return False, ["CACHE_PATH_NOT_A_DIRECTORY"]
    missing = [name for name in _REQUIRED_SUBDIRECTORIES if not (root / name).is_dir()]
    if missing:
        reasons.append(f"CACHE_LAYOUT_INCOMPLETE:{sorted(missing)}")
    if not os.access(root, os.R_OK):
        return False, ["CACHE_NOT_READABLE"]
    return not reasons, reasons


def is_available(path: Path | None = None) -> bool:
    available, _ = validate_cache(path)
    return available


def require_cache(path: Path | None = None) -> Path:
    """Percorso della cache, o errore. Mai un ritorno degradato."""
    root = path or cache_path()
    available, reasons = validate_cache(root)
    if not available:
        raise DocumentCacheUnavailable(
            f"cache documentale non utilizzabile in {redact_path(root)}: {reasons}. "
            f"Configurare {CACHE_PATH_ENV}. Una run LIVE non ripiega su artefatti "
            "registrati."
        )
    return root


def open_read_only(path: Path | None = None) -> ReadOnlyDocumentCache:
    return ReadOnlyDocumentCache(require_cache(path))


@dataclass(frozen=True)
class CacheDescriptor:
    """Stato della cache per la UI. Nessun percorso locale completo."""

    available: bool
    redacted_path: str
    cache_version: str
    reason_codes: tuple[str, ...]
    manifest_hash: str | None
    manifest_rows: int
    document_count: int
    documents_with_text: int
    documents_unavailable: int
    source_unit_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_cache_available": self.available,
            "cache_path_redacted": self.redacted_path,
            "cache_version": self.cache_version,
            "reason_codes": list(self.reason_codes),
            "manifest_hash": self.manifest_hash,
            "manifest_rows": self.manifest_rows,
            "document_count": self.document_count,
            "documents_with_text": self.documents_with_text,
            "documents_unavailable": self.documents_unavailable,
            "source_unit_count": self.source_unit_count,
        }


#: Availability del manifest che implica testo leggibile dalla cache.
TEXT_BEARING_AVAILABILITY: frozenset[str] = frozenset({
    "ABSTRACT_AVAILABLE", "PMC_XML_AVAILABLE", "LOCAL_PDF_AVAILABLE", "METADATA_ONLY",
})


def describe(path: Path | None = None) -> CacheDescriptor:
    """Descrittore completo. Non solleva: descrivere una cache assente è lecito."""
    from backend.research_pipeline import data_access as da

    root = path or cache_path()
    available, reasons = validate_cache(root)

    manifest_path = da.document_manifest_path()
    manifest_hash = _file_sha256(manifest_path) if manifest_path.is_file() else None
    rows = da.read_jsonl(manifest_path) if manifest_path.is_file() else []

    resolvable = 0
    with_text = 0
    for row in rows:
        relative = row.get("local_cache_path")
        if available and relative and (root / relative).is_file():
            resolvable += 1
            if row.get("availability") in TEXT_BEARING_AVAILABILITY:
                with_text += 1

    index_path = da.source_unit_index_path()
    source_unit_count = sum(1 for _ in da.iter_jsonl(index_path)) if index_path.is_file() else 0

    return CacheDescriptor(
        available=available,
        redacted_path=redact_path(root),
        cache_version=CACHE_LAYOUT_VERSION,
        reason_codes=tuple(reasons),
        manifest_hash=manifest_hash,
        manifest_rows=len(rows),
        document_count=resolvable,
        documents_with_text=with_text,
        documents_unavailable=len(rows) - resolvable,
        source_unit_count=source_unit_count,
    )
