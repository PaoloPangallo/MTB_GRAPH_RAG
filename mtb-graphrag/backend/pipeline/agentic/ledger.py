"""Ledger SQLite append-only e hash-chained, comune alle due architetture.

Append-only e tamper-evident nel threat model considerato (trigger di riga
contro UPDATE/DELETE + hash-chain SHA-256), non immutabile in senso assoluto.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from backend.pipeline.agentic.ledger_schema import (
    CURRENT_SCHEMA_VERSION,
    V2_COLUMNS,
    apply_migrations,
    detected_version,
)

#: Sostituisce ``None`` nel preimage v2. Un byte che non può comparire né in
#: JSON né in un timestamp ISO, così ``("a", None)`` e ``(None, "a")`` non
#: collidono mai.
_NULL_SENTINEL = "\x00"


@dataclass(frozen=True)
class ChainReport:
    """Esito della verifica d'integrità di una catena di eventi."""

    valid: bool
    event_count: int
    first_broken_sequence: int | None
    v1_event_count: int
    v2_event_count: int


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
            apply_migrations(connection)

    def schema_version(self) -> int:
        with self._session() as connection:
            return detected_version(connection)

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
        """Preimage v1 — deve restare byte-identico per sempre.

        Gli eventi già registrati sono stati hashati con esattamente questi
        byte: qualunque modifica qui invaliderebbe retroattivamente ledger
        storici, che è precisamente ciò che un archivio tamper-evident non
        deve poter fare.
        """
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

    @staticmethod
    def _hash_event_v2(row: dict[str, Any]) -> str:
        """Preimage v2: campi v1 + colonne di azione, con separazione di dominio.

        Il prefisso ``v2|`` non è decorativo: senza, un evento v2 con tutte le
        colonne nuove a NULL produrrebbe lo stesso digest di un evento v1,
        annullando il tag di versione.
        """
        parts = [
            "v2",
            str(row["run_id"]),
            str(row["sequence"]),
            str(row["event_type"]),
            str(row["actor"]),
            str(row["payload_json"]),
            str(row["created_at"]),
            str(row["previous_hash"]),
        ]
        for name, _ in V2_COLUMNS:
            value = row.get(name)
            parts.append(_NULL_SENTINEL if value is None else str(value))
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

    @classmethod
    def _hash_for_row(cls, row: dict[str, Any]) -> str:
        """Sceglie il preimage in base alla versione dichiarata dalla riga."""
        if int(row.get("schema_version") or 1) < 2:
            return cls._hash_event(
                str(row["run_id"]),
                int(row["sequence"]),
                str(row["event_type"]),
                str(row["actor"]),
                str(row["payload_json"]),
                str(row["created_at"]),
                str(row["previous_hash"]),
            )
        return cls._hash_event_v2(row)

    def append(
        self,
        run_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        *,
        action_id: str | None = None,
        parent_action_id: str | None = None,
        tool_name: str | None = None,
        tool_version: str | None = None,
        query_or_arguments: dict[str, Any] | None = None,
        pagination_state: dict[str, Any] | None = None,
        completeness_status: str | None = None,
        generating_action_id: str | None = None,
    ) -> dict[str, Any]:
        """Registra un evento in coda alla catena del run.

        I parametri v2 sono keyword-only e opzionali: i chiamatori esistenti
        continuano a funzionare invariati e producono eventi v2 con le colonne
        di azione a NULL.
        """
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        created_at = datetime.now(timezone.utc).isoformat()
        event_id = str(uuid4())
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        arguments_json = (
            json.dumps(query_or_arguments, ensure_ascii=False, sort_keys=True, default=str)
            if query_or_arguments is not None
            else None
        )
        pagination_json = (
            json.dumps(pagination_state, ensure_ascii=False, sort_keys=True, default=str)
            if pagination_state is not None
            else None
        )

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

            row: dict[str, Any] = {
                "event_id": event_id,
                "run_id": run_id,
                "sequence": sequence,
                "event_type": event_type,
                "actor": actor,
                "payload_json": payload_json,
                "created_at": created_at,
                "previous_hash": previous_hash,
                "schema_version": CURRENT_SCHEMA_VERSION,
                "action_id": action_id,
                "parent_action_id": parent_action_id,
                "tool_name": tool_name,
                "tool_version": tool_version,
                "query_or_arguments_json": arguments_json,
                "payload_hash": payload_hash,
                "pagination_state_json": pagination_json,
                "completeness_status": completeness_status,
                "generating_action_id": generating_action_id,
            }
            row["event_hash"] = self._hash_event_v2(row)

            connection.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, sequence, event_type, actor, payload_json,
                    created_at, previous_hash, event_hash,
                    schema_version, action_id, parent_action_id, tool_name,
                    tool_version, query_or_arguments_json, payload_hash,
                    pagination_state_json, completeness_status, generating_action_id
                ) VALUES (
                    :event_id, :run_id, :sequence, :event_type, :actor, :payload_json,
                    :created_at, :previous_hash, :event_hash,
                    :schema_version, :action_id, :parent_action_id, :tool_name,
                    :tool_version, :query_or_arguments_json, :payload_hash,
                    :pagination_state_json, :completeness_status, :generating_action_id
                )
                """,
                row,
            )

        return {**row, "payload": payload}

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
        return self.chain_report(run_id).valid

    def chain_report(self, run_id: str) -> ChainReport:
        """Verifica linkage e digest evento per evento.

        La versione è letta **per riga**: una catena che attraversa il confine
        v1→v2 a metà run resta verificabile end-to-end, perché ogni evento è
        ricontrollato con esattamente il preimage con cui è stato prodotto.
        """
        previous_hash = "GENESIS"
        first_broken: int | None = None
        v1_count = 0
        v2_count = 0
        events = self.events(run_id)

        for event in events:
            if int(event.get("schema_version") or 1) < 2:
                v1_count += 1
            else:
                v2_count += 1

            broken = event["previous_hash"] != previous_hash or (
                self._hash_for_row(event) != event["event_hash"]
            )
            if broken and first_broken is None:
                first_broken = int(event["sequence"])
            previous_hash = event["event_hash"]

        return ChainReport(
            valid=first_broken is None,
            event_count=len(events),
            first_broken_sequence=first_broken,
            v1_event_count=v1_count,
            v2_event_count=v2_count,
        )
