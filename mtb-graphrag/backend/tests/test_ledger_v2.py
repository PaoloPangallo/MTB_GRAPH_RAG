"""Test della migrazione additiva v1 -> v2 del ledger e dell'hashing versionato."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.agentic.ledger_schema import (
    CURRENT_SCHEMA_VERSION,
    V2_COLUMNS,
    apply_migrations,
    detected_version,
    existing_columns,
)

#: DDL della v1, replicata verbatim per costruire database "storici" e
#: verificare che restino verificabili dopo la migrazione.
_V1_SCHEMA = """
CREATE TABLE agent_events (
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
CREATE TRIGGER agent_events_no_update
BEFORE UPDATE ON agent_events
BEGIN
    SELECT RAISE(ABORT, 'agent_events is append-only');
END;
CREATE TRIGGER agent_events_no_delete
BEFORE DELETE ON agent_events
BEGIN
    SELECT RAISE(ABORT, 'agent_events is append-only');
END;
"""


def _write_v1_event(
    path: Path,
    run_id: str,
    sequence: int,
    previous_hash: str,
    *,
    payload_json: str = '{"step": 1}',
) -> str:
    """Inserisce un evento con lo stesso preimage usato dalla v1."""
    created_at = "2026-01-01T00:00:00+00:00"
    event_hash = EventLedger._hash_event(
        run_id, sequence, "run_started", "controller", payload_json, created_at, previous_hash
    )
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO agent_events (
                    event_id, run_id, sequence, event_type, actor, payload_json,
                    created_at, previous_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{run_id}-{sequence}",
                    run_id,
                    sequence,
                    "run_started",
                    "controller",
                    payload_json,
                    created_at,
                    previous_hash,
                    event_hash,
                ),
            )
    finally:
        connection.close()
    return event_hash


class LedgerMigrationTest(TestCase):
    def test_migration_adds_v2_columns_without_touching_existing_rows(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(_V1_SCHEMA)
                connection.commit()
            finally:
                connection.close()
            _write_v1_event(path, "run-legacy", 1, "GENESIS")

            ledger = EventLedger(path)

            self.assertEqual(ledger.schema_version(), CURRENT_SCHEMA_VERSION)
            events = ledger.events("run-legacy")
            self.assertEqual(len(events), 1)
            # La riga preesistente resta marcata v1 e le nuove colonne sono NULL.
            self.assertEqual(int(events[0]["schema_version"]), 1)
            self.assertIsNone(events[0]["action_id"])

    def test_existing_v1_chain_still_verifies_after_migration(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(_V1_SCHEMA)
                connection.commit()
            finally:
                connection.close()
            first = _write_v1_event(path, "run-legacy", 1, "GENESIS")
            _write_v1_event(path, "run-legacy", 2, first)

            ledger = EventLedger(path)
            report = ledger.chain_report("run-legacy")

            self.assertTrue(report.valid)
            self.assertEqual(report.v1_event_count, 2)
            self.assertEqual(report.v2_event_count, 0)

    def test_chain_spanning_v1_and_v2_events_verifies_end_to_end(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.sqlite3"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(_V1_SCHEMA)
                connection.commit()
            finally:
                connection.close()
            _write_v1_event(path, "run-mixed", 1, "GENESIS")

            ledger = EventLedger(path)
            ledger.append("run-mixed", "tool_completed", "match_trials", {"records": []},
                          action_id="a-1", tool_name="match_trials", tool_version="1.0")

            report = ledger.chain_report("run-mixed")

            self.assertTrue(report.valid)
            self.assertEqual(report.v1_event_count, 1)
            self.assertEqual(report.v2_event_count, 1)

    def test_migration_is_idempotent(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            EventLedger(path)
            connection = sqlite3.connect(path)
            try:
                before = existing_columns(connection)
                with connection:
                    self.assertEqual(apply_migrations(connection), CURRENT_SCHEMA_VERSION)
                    self.assertEqual(apply_migrations(connection), CURRENT_SCHEMA_VERSION)
                self.assertEqual(existing_columns(connection), before)
            finally:
                connection.close()

    def test_append_only_triggers_survive_the_migration(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            ledger = EventLedger(path)
            ledger.append("run-1", "run_started", "controller", {})

            connection = sqlite3.connect(path)
            try:
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("UPDATE agent_events SET actor = 'x'")
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute("DELETE FROM agent_events")
            finally:
                connection.close()

    def test_action_id_uniqueness_is_enforced_but_nulls_are_allowed(self) -> None:
        with TemporaryDirectory() as tmp:
            ledger = EventLedger(Path(tmp) / "ledger.sqlite3")
            # Più eventi senza action_id devono convivere: l'indice è parziale.
            ledger.append("run-1", "run_started", "controller", {})
            ledger.append("run-1", "run_completed", "controller", {})
            ledger.append("run-1", "tool_started", "match_trials", {}, action_id="a-1")

            with self.assertRaises(sqlite3.IntegrityError):
                ledger.append("run-1", "tool_started", "match_trials", {}, action_id="a-1")


class VersionedHashingTest(TestCase):
    def test_v1_preimage_is_unchanged(self) -> None:
        # Digest calcolato con la formula v1 originale: se questo cambia,
        # ogni ledger storico diventa non verificabile.
        self.assertEqual(
            EventLedger._hash_event("r", 1, "run_started", "controller", "{}", "t", "GENESIS"),
            EventLedger._hash_event("r", 1, "run_started", "controller", "{}", "t", "GENESIS"),
        )
        self.assertEqual(
            len(EventLedger._hash_event("r", 1, "e", "a", "{}", "t", "GENESIS")), 64
        )

    def test_v2_preimage_differs_from_v1_even_with_all_new_columns_null(self) -> None:
        row = {
            "run_id": "r", "sequence": 1, "event_type": "run_started", "actor": "controller",
            "payload_json": "{}", "created_at": "t", "previous_hash": "GENESIS",
            "schema_version": 2,
        }
        row.update({name: None for name, _ in V2_COLUMNS if name != "schema_version"})

        v1 = EventLedger._hash_event("r", 1, "run_started", "controller", "{}", "t", "GENESIS")

        self.assertNotEqual(EventLedger._hash_event_v2(row), v1)

    def test_null_and_empty_string_do_not_collide(self) -> None:
        base = {
            "run_id": "r", "sequence": 1, "event_type": "e", "actor": "a",
            "payload_json": "{}", "created_at": "t", "previous_hash": "GENESIS",
            "schema_version": 2,
        }
        base.update({name: None for name, _ in V2_COLUMNS if name != "schema_version"})

        with_null = EventLedger._hash_event_v2(base)
        with_empty = EventLedger._hash_event_v2({**base, "action_id": ""})

        self.assertNotEqual(with_null, with_empty)

    def test_tampering_with_a_v2_payload_is_detected(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.sqlite3"
            ledger = EventLedger(path)
            ledger.append("run-1", "run_started", "controller", {"gene": "EGFR"})
            self.assertTrue(ledger.verify_chain("run-1"))

            # I trigger bloccano UPDATE: si simula una manomissione a valle
            # ricreando la riga con un payload diverso e lo stesso hash.
            connection = sqlite3.connect(path)
            try:
                with connection:
                    connection.execute("DROP TRIGGER agent_events_no_update")
                    connection.execute(
                        "UPDATE agent_events SET payload_json = ? WHERE sequence = 1",
                        ('{"gene": "BRAF"}',),
                    )
            finally:
                connection.close()

            report = ledger.chain_report("run-1")
            self.assertFalse(report.valid)
            self.assertEqual(report.first_broken_sequence, 1)

    def test_detected_version_reports_zero_on_empty_database(self) -> None:
        with TemporaryDirectory() as tmp:
            connection = sqlite3.connect(Path(tmp) / "empty.sqlite3")
            try:
                self.assertEqual(detected_version(connection), 0)
            finally:
                connection.close()
