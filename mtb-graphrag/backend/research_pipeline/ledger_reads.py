"""Bounded read-only projections without modifying the sealed event ledger."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import execution_mode as em

DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 500
DEFAULT_RUN_LIMIT = 50
MAX_RUN_LIMIT = 200


def validate_page(limit: int, offset: int = 0, *, maximum: int = MAX_RUN_LIMIT) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= maximum:
        raise ValueError(f"limit must be an integer between 1 and {maximum}")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("cursor/offset must be a non-negative integer")


@contextmanager
def _connection(ledger: EventLedger) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(Path(ledger.path).resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def has_run(ledger: EventLedger, run_id: str) -> bool:
    with _connection(ledger) as connection:
        return connection.execute(
            "SELECT 1 FROM agent_events WHERE run_id = ? LIMIT 1", (run_id,),
        ).fetchone() is not None


def verify_chain(ledger: EventLedger, run_id: str) -> bool:
    """Verify every raw row with the sealed preimage, retaining one row only.

    This remains an O(n) integrity audit; it never fetches/decodes all payloads
    into memory and does not cache a result that could hide later tampering.
    """
    previous_hash = "GENESIS"
    with _connection(ledger) as connection:
        cursor = connection.execute(
            "SELECT * FROM agent_events WHERE run_id = ? ORDER BY sequence", (run_id,)
        )
        for row in cursor:
            event = dict(row)
            if event["previous_hash"] != previous_hash or ledger._hash_for_row(event) != event["event_hash"]:
                return False
            previous_hash = event["event_hash"]
    return True


def events_page(
    ledger: EventLedger, run_id: str, *, after_sequence: int = 0,
    limit: int = DEFAULT_EVENT_LIMIT,
) -> dict[str, Any]:
    """Read at most limit+1 rows; a cursor is the last returned sequence."""
    validate_page(limit, after_sequence, maximum=MAX_EVENT_LIMIT)
    with _connection(ledger) as connection:
        rows = connection.execute(
            "SELECT * FROM agent_events WHERE run_id = ? AND sequence > ? "
            "ORDER BY sequence LIMIT ?", (run_id, after_sequence, limit + 1),
        ).fetchall()
    events = [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows[:limit]]
    return {"events": events, "has_more": len(rows) > limit,
            "next_sequence": events[-1]["sequence"] if events else after_sequence}


def run_summaries(
    ledger: EventLedger, *, limit: int = DEFAULT_RUN_LIMIT, offset: int = 0,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Project scalar summary fields in SQL; no stage or document payloads leave SQL.

    Ordering uses the run's first creation timestamp. Sequences are local to
    each run and cannot establish chronology between different runs.
    """
    validate_page(limit, offset)
    with _connection(ledger) as connection:
        rows = connection.execute(
            """
            WITH page AS (
                SELECT run_id, MIN(created_at) AS started_at, MIN(sequence) AS first_sequence
                FROM agent_events WHERE (? IS NULL OR run_id = ?)
                GROUP BY run_id ORDER BY started_at DESC, run_id DESC LIMIT ? OFFSET ?
            )
            SELECT page.run_id, page.started_at,
                COALESCE(json_extract(c.payload_json, '$.case_id'), '') AS case_id,
                COALESCE(json_extract(c.payload_json, '$.requested_execution_mode'), 'LIVE') AS requested_mode,
                COALESCE(json_extract(t.payload_json, '$.status'), 'FAILED') AS status,
                json_extract(t.payload_json, '$.execution_mode') AS execution_mode,
                json_extract(t.payload_json, '$.requested_mode') AS terminal_requested_mode,
                json_extract(t.payload_json, '$.fully_live') AS fully_live,
                json_extract(t.payload_json, '$.replay_artifacts_used') AS replay_artifacts_used,
                t.sequence AS terminal_sequence,
                (SELECT COUNT(*) FROM agent_events s WHERE s.run_id = page.run_id
                    AND s.event_type IN ('STAGE_COMPLETED','STAGE_WARNING','STAGE_FAILED','STAGE_SKIPPED')
                    AND json_extract(s.payload_json, '$.artifact_origin') = 'RECORDED_REAL_RUN') AS replay_count
            FROM page
            JOIN agent_events c ON c.run_id = page.run_id AND c.sequence = page.first_sequence
            LEFT JOIN agent_events t ON t.run_id = page.run_id AND t.sequence = (
                SELECT MAX(sequence) FROM agent_events WHERE run_id = page.run_id AND event_type = 'RUN_COMPLETED'
            )
            ORDER BY page.started_at DESC, page.run_id DESC
            """, (run_id, run_id, limit, offset),
        ).fetchall()
    summaries = []
    for row in rows:
        requested = row["terminal_requested_mode"] or row["requested_mode"]
        replay_count = row["replay_artifacts_used"]
        if replay_count is None:
            replay_count = row["replay_count"]
        mode = row["execution_mode"] or (
            em.REPLAY if requested == em.REPLAY else em.HYBRID if replay_count else em.CANONICAL_MODE)
        summaries.append({
            "run_id": row["run_id"], "case_id": row["case_id"], "status": row["status"],
            "started_at": row["started_at"], "requested_mode": requested, "execution_mode": mode,
            "fully_live": bool(row["fully_live"]) if row["fully_live"] is not None else mode == em.LIVE,
            "replay_artifacts_used": int(replay_count),
            "recovery_status": "COMPLETE" if row["terminal_sequence"] is not None else "RECOVERED_INCOMPLETE",
            "rehydrated": True,
        })
    return summaries
