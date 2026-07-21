"""Schema e migrazioni del ledger degli eventi.

Il ledger è **append-only e tamper-evident nel threat model considerato**: i
trigger SQLite impediscono UPDATE e DELETE riga per riga, e la hash-chain rende
rilevabile qualunque riscrittura del contenuto. Non è immutabile in senso
assoluto — chi controlla il filesystem può sostituire il file per intero.

La migrazione v1 → v2 è **puramente additiva**. ``ALTER TABLE ... ADD COLUMN``
è DDL: non attiva i trigger di riga e non riscrive le righe esistenti, quindi
nessun evento già registrato viene toccato. Un rebuild-and-copy della tabella
sarebbe stato l'alternativa, ma è indistinguibile da una manomissione e va
evitato proprio in un archivio di audit.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

CURRENT_SCHEMA_VERSION = 2

#: Colonne introdotte da v2, nell'ordine in cui entrano nel preimage dell'hash.
V2_COLUMNS: tuple[tuple[str, str], ...] = (
    ("schema_version", "INTEGER NOT NULL DEFAULT 1"),
    ("action_id", "TEXT"),
    ("parent_action_id", "TEXT"),
    ("tool_name", "TEXT"),
    ("tool_version", "TEXT"),
    ("query_or_arguments_json", "TEXT"),
    ("payload_hash", "TEXT"),
    ("pagination_state_json", "TEXT"),
    ("completeness_status", "TEXT"),
    ("generating_action_id", "TEXT"),
)

BASE_SCHEMA = """
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
CREATE TABLE IF NOT EXISTS ledger_schema_meta (
    schema_version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    note TEXT NOT NULL
);
"""

# Indici v2. ``action_id`` deve essere unico, ma SQLite rifiuta
# ``ADD COLUMN ... UNIQUE`` e tutte le righe v1 hanno action_id NULL: serve
# quindi un indice parziale, che ignora i NULL.
V2_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_events_action
    ON agent_events(action_id) WHERE action_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_events_parent
    ON agent_events(run_id, parent_action_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_generating
    ON agent_events(run_id, generating_action_id);
"""


def existing_columns(connection: sqlite3.Connection) -> frozenset[str]:
    """Nomi delle colonne attualmente presenti su ``agent_events``."""
    rows = connection.execute("PRAGMA table_info(agent_events)").fetchall()
    return frozenset(str(row[1]) for row in rows)


def detected_version(connection: sqlite3.Connection) -> int:
    """Versione dello schema dedotta dalle colonne effettivamente presenti.

    Si guarda la tabella, non ``ledger_schema_meta``: un database creato da una
    versione precedente del codice non ha la tabella di bookkeeping, e le
    colonne restano l'unica fonte di verità.
    """
    columns = existing_columns(connection)
    if not columns:
        return 0
    if all(name in columns for name, _ in V2_COLUMNS):
        return 2
    return 1


def apply_migrations(connection: sqlite3.Connection) -> int:
    """Porta lo schema a ``CURRENT_SCHEMA_VERSION``. Idempotente.

    Restituisce la versione applicata. Nessuna riga esistente viene modificata:
    le colonne aggiunte valgono NULL (o 1 per ``schema_version``) sulle righe
    già presenti, che restano quindi marcate come v1 e continuano a verificare
    con il preimage v1.
    """
    connection.executescript(BASE_SCHEMA)

    columns = existing_columns(connection)
    for name, ddl in V2_COLUMNS:
        if name not in columns:
            connection.execute(f"ALTER TABLE agent_events ADD COLUMN {name} {ddl}")

    connection.executescript(V2_INDEXES)

    version = detected_version(connection)
    if version == CURRENT_SCHEMA_VERSION:
        connection.execute(
            """
            INSERT INTO ledger_schema_meta (schema_version, applied_at, note)
            VALUES (?, ?, ?)
            ON CONFLICT(schema_version) DO NOTHING
            """,
            (
                CURRENT_SCHEMA_VERSION,
                datetime.now(timezone.utc).isoformat(),
                "migrazione additiva v1->v2: colonne di azione, provenienza e completezza",
            ),
        )

    return version
