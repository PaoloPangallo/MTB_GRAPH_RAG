"""Registro delle run del research runtime.

Una run viene eseguita in un thread separato e i suoi eventi finiscono sul
ledger append-only mentre procede. Il ledger resta la fonte di veritÃ : questo
registro conserva soltanto ciÃ² che il ledger non esprime â€” se il thread Ã¨ ancora
vivo e con quale errore si Ã¨ eventualmente interrotto.

Il ledger del research runtime Ã¨ un file distinto da quello agentico
(``RESEARCH_LEDGER_PATH``), cosÃ¬ una run di ricerca non entra nella catena di
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
from backend.research_pipeline import orchestrator, rehydration, replay
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.contracts import PipelineRun
from backend.research_pipeline.documents import cache_runtime
from backend.research_pipeline.documents.live_resolution import DocumentRuntime
from backend.research_pipeline.pipeline import CallBudget

#: Tetto di chiamate reali al modello per una singola run. Il pilot autorizzava
#: 20 chiamate complessive; questo lavoro ne autorizza 10 in totale, quindi il
#: tetto per run Ã¨ piÃ¹ stretto di quello del budget storico.
MAX_LLM_CALLS_PER_RUN = 6


def research_ledger_path() -> Path:
    """Percorso del ledger di ricerca.

    ``data_root()`` Ã¨ giÃ  ``mtb-graphrag``: aggiungere di nuovo quel segmento
    produrrebbe ``mtb-graphrag/mtb-graphrag/data`` e un percorso inesistente.
    Il default Ã¨ coperto da un test perchÃ© i test che impostano
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
    ma i loro eventi sÃ¬: il ledger Ã¨ su disco e la trace resta ispezionabile."""

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

    def snapshot(self, run_id: str) -> dict[str, Any] | None:
        """Vista della run, dalla memoria o â€” dopo un riavvio â€” dal ledger.

        L'ordine conta: una run ancora in corso Ã¨ in memoria e il ledger non ne
        ha ancora l'evento finale, quindi la memoria Ã¨ la vista piÃ¹ aggiornata.
        Una run che la memoria non conosce non Ã¨ per questo inesistente.
        """
        handle = self.get(run_id)
        if handle is not None:
            return handle.snapshot()
        return rehydration.rehydrate(self._ledger, run_id)

    def list_runs(self) -> list[RunHandle]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda h: h.started_at, reverse=True)

    def list_all(self) -> list[dict[str, Any]]:
        """Run in memoria piÃ¹ quelle persistite, senza duplicati."""
        in_memory = {
            h.run_id: {
                "run_id": h.run_id, "case_id": h.case_id, "status": h.status,
                "started_at": h.started_at, "requested_mode": h.requested_mode,
                "execution_mode": (h.run.execution_mode if h.run else h.requested_mode),
                "replay_artifacts_used": (
                    h.run.mode_summary()["replay_artifacts_used"] if h.run else 0),
                "fully_live": (h.run.mode_summary()["fully_live"] if h.run else False),
                "recovery_status": "COMPLETE",
                "rehydrated": False,
            }
            for h in self.list_runs()
        }
        rows = list(in_memory.values())
        for run_id in rehydration.list_run_ids(self._ledger):
            if run_id in in_memory:
                continue
            summary = rehydration.summarize_run(self._ledger, run_id)
            if summary is not None:
                rows.append(summary)
        return rows

    def start(self, *, case_id: str, clinical_text: str, execution_mode: str) -> RunHandle:
        """Avvia una run nella modalitÃ  **richiesta esplicitamente**.

        Non esiste piÃ¹ un ``use_replay`` dedotto dalla presenza di artefatti
        congelati per il caso: era il fallback silenzioso. Una modalitÃ 
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
            document_runtime = DocumentRuntime.open_live() if mode == em.LIVE else None
            # In REPLAY l'indice delle SourceUnit fornisce locatori, sezione,
            # offset e ``content_hash`` â€” mai il testo. In LIVE le unitÃ  con
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
        except Exception as exc:  # noqa: BLE001 â€” l'errore deve restare visibile
            # Un errore non diventa mai un risultato: la run resta FAILED e il
            # messaggio Ã¨ esposto, invece di essere confuso con un'astensione.
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
                "call_narrator_fn": live_providers.narrator_fn,
            }
        return {
            "call_parser_fn": replay.parser_fn,
            "call_enricher_fn": replay.enricher_fn,
            "select_papers_fn": lambda a, u, **kw: replay.selection_fn(a, u, case_id=kw["case_id"]),
            "validate_fn": lambda t, e, **kw: replay.validation_fn(
                t, e, case_id=kw["case_id"], paper_id=kw["paper_id"]),
            "call_narrator_fn": replay.narrator_fn,
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
