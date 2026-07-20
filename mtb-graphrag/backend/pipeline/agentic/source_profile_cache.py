"""Cache persistente del profilo di una fonte (asse del supporto documentale),
indipendente dal contesto paziente.

Il profilo di una fonte (source_support_status/reason, source_population/
line/setting/prerequisites, source_arms, categorie strutturate,
derived_verified_claim) descrive esclusivamente cosa dice la fonte — non
dipende mai dal caso clinico richiesto (il prompt istruisce esplicitamente
l'LLM a non riscrivere la claim usando i dati del paziente). Cambiare il
contesto paziente non deve quindi mai invalidare né rieseguire l'estrazione
PubMed/CIViC per un PMID già verificato con lo stesso prompt e medesimo
modello.

La chiave di cache è (pmid, hash dell'evidence statement, versione del
prompt, revisione del modello): cambia se il record CIViC sottostante cambia
(hash dello statement), se il prompt del verificatore viene aggiornato, o se
si cambia modello/versione LLM — mai per un cambio di paziente.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def default_cache_path() -> Path:
    configured = os.getenv("SOURCE_PROFILE_CACHE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "data" / "source_profile_cache.sqlite3"


def statement_hash(evidence_statement: str | None, citation_text: str | None) -> str:
    canonical = f"{evidence_statement or ''}|{citation_text or ''}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SourceProfileCache:
    """Archivio chiave→profilo backed da SQLite, con upsert idempotente."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS source_profiles (
                    pmid INTEGER NOT NULL,
                    statement_hash TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    model_revision TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (pmid, statement_hash, prompt_version, model_revision)
                );
                """
            )

    def get(
        self, pmid: int, statement_hash_value: str, prompt_version: str, model_revision: str,
    ) -> dict[str, Any] | None:
        with self._session() as connection:
            row = connection.execute(
                """
                SELECT profile_json FROM source_profiles
                WHERE pmid = ? AND statement_hash = ? AND prompt_version = ? AND model_revision = ?
                """,
                (pmid, statement_hash_value, prompt_version, model_revision),
            ).fetchone()
        return json.loads(row["profile_json"]) if row else None

    def put(
        self,
        pmid: int,
        statement_hash_value: str,
        prompt_version: str,
        model_revision: str,
        profile: dict[str, Any],
    ) -> None:
        with self._session() as connection:
            connection.execute(
                """
                INSERT INTO source_profiles (
                    pmid, statement_hash, prompt_version, model_revision, profile_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (pmid, statement_hash, prompt_version, model_revision)
                DO UPDATE SET profile_json = excluded.profile_json, created_at = excluded.created_at
                """,
                (
                    pmid, statement_hash_value, prompt_version, model_revision,
                    json.dumps(profile, ensure_ascii=False, sort_keys=True),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


class InMemorySourceProfileCache:
    """Cache in-memoria per test: stesso contratto get/put, nessun I/O su
    disco — usata dai test per isolamento e velocità."""

    def __init__(self) -> None:
        self._store: dict[tuple[int, str, str, str], dict[str, Any]] = {}

    def get(
        self, pmid: int, statement_hash_value: str, prompt_version: str, model_revision: str,
    ) -> dict[str, Any] | None:
        return self._store.get((pmid, statement_hash_value, prompt_version, model_revision))

    def put(
        self,
        pmid: int,
        statement_hash_value: str,
        prompt_version: str,
        model_revision: str,
        profile: dict[str, Any],
    ) -> None:
        self._store[(pmid, statement_hash_value, prompt_version, model_revision)] = dict(profile)
