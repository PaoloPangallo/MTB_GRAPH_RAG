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
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline import orchestrator, replay
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.contracts import PipelineRun
from backend.research_pipeline.documents import cache_runtime
from backend.research_pipeline.documents.live_resolution import DocumentRuntime
from backend.research_pipeline.pipeline import CallBudget

#: Tetto di chiamate reali al modello per una singola run. Il pilot autorizzava
#: 20 chiamate complessive; questo lavoro ne autorizza 10 in totale, quindi il
#: tetto per run è più stretto di quello del budget storico.
MAX_LLM_CALLS_PER_RUN = 6


def research_ledger_path() -> Path:
    """Percorso del ledger di ricerca.

    ``data_root()`` è già ``mtb-graphrag``: aggiungere di nuovo quel segmento
    produrrebbe ``mtb-graphrag/mtb-graphrag/data`` e un percorso inesistente.
    Il default è coperto da un test perché i test che impostano
    ``RESEARCH_LEDGER_PATH`` esplicitamente non lo esercitano mai.
    """
    configured = os.getenv("RESEARCH_LEDGER_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return da.data_root() / "data" / "research_pipeline_events.sqlite3"


@dataclass
class RunHandle:
    run_id: str
    case_id: str
    status: str
    started_at: str
    requested_mode: str = em.LIVE
    run: PipelineRun | None = None
    error: str | None = None
    error_reason_code: str | None = None
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
            "document_cache": {}, "llm_calls": 0,
            "reason_codes": [self.error_reason_code] if self.error_reason_code else [],
            **em.summarize(self.requested_mode, ()),
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

    def start(self, *, case_id: str, clinical_text: str, execution_mode: str) -> RunHandle:
        """Avvia una run nella modalità **richiesta esplicitamente**.

        Non esiste più un ``use_replay`` dedotto dalla presenza di artefatti
        congelati per il caso: era il fallback silenzioso. Una modalità
        sconosciuta solleva invece di ripiegare su un default.
        """
        mode = em.normalize_requested_mode(execution_mode)
        run_id = str(uuid4())
        handle = RunHandle(
            run_id=run_id, case_id=case_id, status="CREATED",
            started_at=datetime.now(timezone.utc).isoformat(), requested_mode=mode,
        )
        with self._lock:
            self._runs[run_id] = handle

        thread = threading.Thread(
            target=self._execute, args=(handle, clinical_text, mode),
            name=f"research-run-{run_id[:8]}", daemon=True,
        )
        handle.thread = thread
        handle.status = "RUNNING"
        thread.start()
        return handle

    def _execute(self, handle: RunHandle, clinical_text: str, mode: str) -> None:
        try:
            kwargs = self._providers(mode)
            document_runtime = DocumentRuntime.open() if mode == em.LIVE else None
            # In REPLAY l'indice delle SourceUnit fornisce locatori, sezione,
            # offset e ``content_hash`` — mai il testo. In LIVE le unità con
            # testo arrivano da ``DocumentRuntime`` e questo argomento non viene
            # usato per alcuna decisione.
            handle.run = orchestrator.run_case(
                case_id=handle.case_id, clinical_text=clinical_text,
                source_units_by_id=da.load_source_unit_index(),
                budget=CallBudget(MAX_LLM_CALLS_PER_RUN),
                ledger=self._ledger, run_id=handle.run_id,
                execution_mode=mode, document_runtime=document_runtime, **kwargs,
            )
            handle.status = handle.run.status
        except cache_runtime.DocumentCacheUnavailable as exc:
            # La cache manca: la run LIVE non parte e **non** ripiega sul replay.
            handle.status = "FAILED"
            handle.error = str(exc)
            handle.error_reason_code = "DOCUMENT_CACHE_UNAVAILABLE"
        except Exception as exc:  # noqa: BLE001 — l'errore deve restare visibile
            # Un errore non diventa mai un risultato: la run resta FAILED e il
            # messaggio è esposto, invece di essere confuso con un'astensione.
            handle.status = "FAILED"
            handle.error = f"{type(exc).__name__}: {exc}"
            handle.error_reason_code = "LIVE_STAGE_FAILED" if handle.requested_mode == em.LIVE else "RUN_FAILED"

    @staticmethod
    def _providers(mode: str) -> dict[str, Callable[..., Any]]:
        if mode == em.LIVE:
            # Percorso live: parser ed enricher chiamano davvero il modello,
            # spendono il budget e la validazione passa dal validatore v2.
            from backend.research_pipeline import live_providers

            return {
                "call_parser_fn": live_providers.parser_fn,
                "call_enricher_fn": live_providers.enricher_fn,
                "validate_fn": live_providers.validate_fn,
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
