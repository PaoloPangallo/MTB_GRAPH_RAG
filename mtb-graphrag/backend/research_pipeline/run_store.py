"""Registro delle run del research runtime.

Una run viene eseguita in un thread separato e i suoi eventi finiscono sul
ledger append-only mentre procede. Il ledger resta la fonte di verità: questo
registro conserva soltanto ciò che il ledger non esprime — se il thread è ancora
vivo e con quale errore si è eventualmente interrotto.

Il ledger del research runtime è un file distinto da quello agentico
(``RESEARCH_LEDGER_PATH``), così una run di ricerca non entra nella catena di
eventi del percorso di prodotto.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import data_access as da
from backend.research_pipeline import orchestrator, replay
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.contracts import PipelineRun
from backend.research_pipeline.pipeline import CallBudget


def research_ledger_path() -> Path:
    configured = os.getenv("RESEARCH_LEDGER_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return da.data_root() / "mtb-graphrag/data/research_pipeline_events.sqlite3"


@dataclass
class RunHandle:
    run_id: str
    case_id: str
    status: str
    started_at: str
    run: PipelineRun | None = None
    error: str | None = None
    thread: threading.Thread | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        if self.run is not None:
            return self.run.to_dict()
        return {
            "run_id": self.run_id, "case_id": self.case_id, "status": self.status,
            "started_at": self.started_at, "completed_at": None, "current_stage": None,
            "stopped_at": None, "input_text": "", "stages": [], "dossier_id": None,
            "warnings": [], "errors": [self.error] if self.error else [],
            "versions": {}, "metrics": {},
            "research_notice": PipelineRun.research_notice(),
        }


class RunStore:
    """Registro in memoria. Le run non sopravvivono a un riavvio del processo,
    ma i loro eventi sì: il ledger è su disco e la trace resta ispezionabile."""

    def __init__(self) -> None:
        self._runs: dict[str, RunHandle] = {}
        self._lock = threading.Lock()
        self._ledger = EventLedger(research_ledger_path())

    @property
    def ledger(self) -> EventLedger:
        return self._ledger

    def get(self, run_id: str) -> RunHandle | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_runs(self) -> list[RunHandle]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda h: h.started_at, reverse=True)

    def start(self, *, case_id: str, clinical_text: str, use_replay: bool) -> RunHandle:
        run_id = str(uuid4())
        handle = RunHandle(
            run_id=run_id, case_id=case_id, status="CREATED",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._runs[run_id] = handle

        thread = threading.Thread(
            target=self._execute, args=(handle, clinical_text, use_replay),
            name=f"research-run-{run_id[:8]}", daemon=True,
        )
        handle.thread = thread
        handle.status = "RUNNING"
        thread.start()
        return handle

    def _execute(self, handle: RunHandle, clinical_text: str, use_replay: bool) -> None:
        try:
            kwargs = self._providers(handle.case_id, use_replay)
            handle.run = orchestrator.run_case(
                case_id=handle.case_id, clinical_text=clinical_text,
                source_units_by_id={}, budget=CallBudget(),
                ledger=self._ledger, run_id=handle.run_id, **kwargs,
            )
            handle.status = handle.run.status
        except Exception as exc:  # noqa: BLE001 — l'errore deve restare visibile
            # Un errore non diventa mai un risultato: la run resta FAILED e il
            # messaggio è esposto, invece di essere confuso con un'astensione.
            handle.status = "FAILED"
            handle.error = f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _providers(case_id: str, use_replay: bool) -> dict[str, Callable[..., Any]]:
        if not use_replay:
            # Percorso live: parser ed enricher chiamano davvero il modello.
            from backend.research_pipeline.casecontext import parser as cc_parser
            from backend.research_pipeline.enrichment import enricher_v2

            return {
                "call_parser_fn": lambda budget, cid, text: cc_parser.call_parser(cid, text),
                "call_enricher_fn": enricher_v2.call_enricher_v2,
            }
        return {
            "call_parser_fn": replay.parser_fn,
            "call_enricher_fn": replay.enricher_fn,
            "select_papers_fn": lambda a, u, **kw: replay.selection_fn(a, u, case_id=kw["case_id"]),
            "validate_fn": lambda t, e, **kw: replay.validation_fn(
                t, e, case_id=kw["case_id"], paper_id=kw["paper_id"]),
        }


_STORE: RunStore | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> RunStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = RunStore()
        return _STORE


def reset_store() -> None:
    """Solo per i test: scarta il registro e riapre il ledger."""
    global _STORE
    with _STORE_LOCK:
        _STORE = None


def demo_cases() -> list[dict[str, Any]]:
    """Casi sintetici disponibili. Eseguono la pipeline reale, non output finti."""
    return [
        {
            "case_id": case["case_id"],
            "clinical_text": case["clinical_text"],
            "expected_query_intent": case.get("expected_query_intent"),
            "expected_result": case.get("expected_result"),
            "frozen_artifacts_available": replay.has_frozen_case(case["case_id"]),
        }
        for case in CASES
    ]
