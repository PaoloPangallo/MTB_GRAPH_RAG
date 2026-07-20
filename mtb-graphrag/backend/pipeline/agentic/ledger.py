"""Ledger SQLite append-only e hash-chained per le esecuzioni agentiche."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4


def default_ledger_path() -> Path:
    configured = os.getenv("AGENT_LEDGER_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "data" / "agent_events.sqlite3"


class EventLedger:
    """Archivio che consente INSERT ma impedisce UPDATE e DELETE via trigger."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_ledger_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Apre una connessione, gestisce commit/rollback e la chiude sempre.

        ``sqlite3.Connection`` usata come context manager gestisce solo la
        transazione (commit/rollback), non chiude la connessione: senza una
        chiusura esplicita il file WAL resta aperto (visibile soprattutto su
        Windows, dove impedisce persino la cancellazione della directory
        temporanea nei test)."""
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS agent_events (
                    event_id TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    event_hash TEXT NOT NULL UNIQUE,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_events_run
                    ON agent_events(run_id, sequence);
                CREATE TRIGGER IF NOT EXISTS agent_events_no_update
                BEFORE UPDATE ON agent_events
                BEGIN
                    SELECT RAISE(ABORT, 'agent_events is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS agent_events_no_delete
                BEFORE DELETE ON agent_events
                BEGIN
                    SELECT RAISE(ABORT, 'agent_events is append-only');
                END;
                """
            )

    @staticmethod
    def _hash_event(
        run_id: str,
        sequence: int,
        event_type: str,
        actor: str,
        payload_json: str,
        created_at: str,
        previous_hash: str,
    ) -> str:
        canonical = "|".join((
            run_id,
            str(sequence),
            event_type,
            actor,
            payload_json,
            created_at,
            previous_hash,
        ))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def append(
        self,
        run_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        created_at = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid4())

        with self._session() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                """
                SELECT sequence, event_hash
                FROM agent_events
                WHERE run_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            sequence = int(previous["sequence"]) + 1 if previous else 1
            previous_hash = str(previous["event_hash"]) if previous else "GENESIS"
            event_hash = self._hash_event(
                run_id,
                sequence,
                event_type,
                actor,
                payload_json,
                created_at,
                previous_hash,
            )
            connection.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, sequence, event_type, actor, payload_json,
                    created_at, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    run_id,
                    sequence,
                    event_type,
                    actor,
                    payload_json,
                    created_at,
                    previous_hash,
                    event_hash,
                ),
            )

        return {
            "event_id": event_id,
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "actor": actor,
            "payload": payload,
            "created_at": created_at,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        }

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self._session() as connection:
            rows = connection.execute(
                "SELECT * FROM agent_events WHERE run_id = ? ORDER BY sequence",
                (run_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def verify_chain(self, run_id: str) -> bool:
        previous_hash = "GENESIS"
        for event in self.events(run_id):
            if event["previous_hash"] != previous_hash:
                return False
            expected = self._hash_event(
                event["run_id"],
                event["sequence"],
                event["event_type"],
                event["actor"],
                event["payload_json"],
                event["created_at"],
                event["previous_hash"],
            )
            if expected != event["event_hash"]:
                return False
            previous_hash = event["event_hash"]
        return True
