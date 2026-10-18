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
import hashlib
import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import data_access as da
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline import events as ev, ledger_reads
# ``replay`` non compare fra gli import di proposito: il ``RunStore`` non deve
# avere alcun modo di raggiungere gli adattatori congelati. Sono infrastruttura
# di ricerca, iniettabile solo da un harness che chiami ``orchestrator.run_case``.
from backend.research_pipeline import orchestrator, rehydration
from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.contracts import PipelineRun
from backend.research_pipeline.documents import cache_runtime
from backend.research_pipeline.documents.live_resolution import DocumentRuntime
from backend.research_pipeline.budget import CallBudget


# Twenty calls are the initial allowance, not a cap on canonical discovery.
# An explicitly configured maximum remains a hard operational limit.
def max_llm_calls_per_run() -> int:
    """Keep the model-call budget independent of the retrieval family cap."""
    configured = os.getenv("RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN", "").strip()
    value = int(configured or "20")
    if value < 1:
        raise ValueError("RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN must be positive")
    return value


MAX_LLM_CALLS_PER_RUN = max_llm_calls_per_run()


def new_run_budget() -> CallBudget:
    """Size the default budget to retrieval; respect an explicit operator cap."""
    configured = os.getenv("RESEARCH_PIPELINE_MAX_LLM_CALLS_PER_RUN", "").strip()
    token_limit = os.getenv('RESEARCH_PIPELINE_MAX_ESTIMATED_TOKENS_PER_RUN', '').strip()
    budget = CallBudget(max_llm_calls_per_run(), workload_sized=not bool(configured),
                        maximum_estimated_tokens=int(token_limit) if token_limit else None)
    windows = os.getenv('RESEARCH_PIPELINE_MAX_NEW_ENCODING_WINDOWS_PER_RUN', '').strip()
    seconds = os.getenv('RESEARCH_PIPELINE_MAX_ENCODING_SECONDS_PER_RUN', '').strip()
    if windows:
        budget.maximum_encoding_windows = int(windows)
        if budget.maximum_encoding_windows < 1:
            raise ValueError('Encoding windows limit must be positive')
    if seconds:
        import math
        budget.maximum_encoding_seconds = float(seconds)
        if not math.isfinite(budget.maximum_encoding_seconds) or budget.maximum_encoding_seconds <= 0:
            raise ValueError('Encoding time limit must be finite and positive')
    return budget


NARRATOR_ENABLED_ENV = "RESEARCH_NARRATOR_ENABLED"


def narrator_enabled() -> bool:
    """Whether the optional presentation LLM is explicitly enabled."""
    return os.getenv(NARRATOR_ENABLED_ENV, "").strip().lower() in {
        "1", "true", "yes", "on",
    }


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
    #: Etichetta della run. Costante: il ``RunStore`` esegue un solo runtime.
    #: Resta un campo, e non una costante inlineata, perché viaggia nello
    #: snapshot letto dalla UI e dalle run storiche reidratate dal ledger.
    requested_mode: str = em.CANONICAL_MODE
    run: PipelineRun | None = None
    error: str | None = None
    error_reason_code: str | None = None
    thread: FutureThread | None = field(default=None, repr=False)
    _terminal_snapshot: dict[str, Any] | None = field(default=None, repr=False)

    def snapshot(self) -> dict[str, Any]:
        if self.run is not None:
            return self.run.to_dict()
        if self._terminal_snapshot is not None:
            return dict(self._terminal_snapshot)
        return {
            "run_id": self.run_id, "case_id": self.case_id, "status": self.status,
            "started_at": self.started_at, "completed_at": None, "current_stage": None,
            "stopped_at": None, "input_text": "", "stages": [], "dossier_id": None,
            "warnings": [], "errors": [self.error] if self.error else [],
            "versions": {}, "metrics": {},
            "research_notice": PipelineRun.research_notice(),
            "document_cache": {}, "llm_calls": 0,
            "reason_codes": [self.error_reason_code] if self.error_reason_code else [],
            "relation_aware_report": None,
            **em.summarize(self.requested_mode, ()),
        }


class FutureThread:
    """Compatibility facade for callers waiting on a queued or executing run."""

    def __init__(self) -> None:
        self.future: Future[None] | None = None

    def is_alive(self) -> bool:
        return self.future is None or not self.future.done()

    def join(self, timeout: float | None = None) -> None:
        if self.future is not None:
            try:
                self.future.result(timeout=timeout)
            except FutureTimeoutError:
                pass


class RunStoreOverloaded(RuntimeError):
    """No bounded worker/queue slot is available; no run was admitted."""


class RunStore:
    """Registro in memoria. Le run non sopravvivono a un riavvio del processo,
    ma i loro eventi sÃ¬: il ledger Ã¨ su disco e la trace resta ispezionabile."""

    def __init__(self, *, max_workers: int | None = None, queue_capacity: int | None = None,
                 max_cached_runs: int | None = None) -> None:
        max_workers = max_workers if max_workers is not None else int(os.getenv("RESEARCH_PIPELINE_MAX_WORKERS", "2"))
        queue_capacity = queue_capacity if queue_capacity is not None else int(os.getenv("RESEARCH_PIPELINE_QUEUE_CAPACITY", "8"))
        max_cached_runs = max_cached_runs if max_cached_runs is not None else int(os.getenv("RESEARCH_PIPELINE_MAX_CACHED_RUNS", "100"))
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if isinstance(queue_capacity, bool) or not isinstance(queue_capacity, int) or queue_capacity < 0:
            raise ValueError("queue_capacity must be a non-negative integer")
        if type(max_cached_runs) is not int or max_cached_runs < 0:
            raise ValueError("max_cached_runs must be a non-negative integer")
        self._max_cached_runs = max_cached_runs
        self._runs: dict[str, RunHandle] = {}
        self._lock = threading.Lock()
        self._ledger = EventLedger(research_ledger_path())
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="research-run")
        self._slots = threading.BoundedSemaphore(max_workers + queue_capacity)
        self._closed = False

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
            if handle.run is None and handle.status in {"RUNNING", "PENDING"}:
                live = rehydration.rehydrate(self._ledger, run_id)
                if live is not None:
                    if live.get("completed_at") is None:
                        live.update(status=handle.status, recovery_status="IN_PROGRESS", rehydrated=False)
                    return live
            return handle.snapshot()
        return rehydration.rehydrate(self._ledger, run_id)

    def list_runs(self) -> list[RunHandle]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda h: h.started_at, reverse=True)

    def list_all(self, limit: int = ledger_reads.DEFAULT_RUN_LIMIT, offset: int = 0) -> list[dict[str, Any]]:
        """Run in memoria piÃ¹ quelle persistite, senza duplicati."""
        rows = ledger_reads.run_summaries(self._ledger, limit=limit, offset=offset)
        page_ids = {row["run_id"] for row in rows}
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
            for h in self.list_runs() if h.run_id in page_ids
        }
        return [in_memory.get(row["run_id"], row) for row in rows]

    def events_page(self, run_id: str, *, after_sequence: int = 0,
                    limit: int = ledger_reads.DEFAULT_EVENT_LIMIT) -> dict[str, Any]:
        return ledger_reads.events_page(self._ledger, run_id, after_sequence=after_sequence, limit=limit)

    def has_run(self, run_id: str) -> bool:
        return self.get(run_id) is not None or ledger_reads.has_run(self._ledger, run_id)

    def verify_chain(self, run_id: str) -> bool:
        return ledger_reads.verify_chain(self._ledger, run_id)

    def _release_completed(self, _future: Future[None]) -> None:
        self._slots.release()
        self._trim_terminal_cache()

    def _trim_terminal_cache(self) -> None:
        with self._lock:
            terminal = sorted(
                (handle for handle in self._runs.values()
                 if handle.status not in {"CREATED", "RUNNING"}
                 and (handle.thread is None or not handle.thread.is_alive())),
                key=lambda handle: (handle.started_at, handle.run_id), reverse=True,
            )
            for handle in terminal[self._max_cached_runs:]:
                self._runs.pop(handle.run_id, None)

    def is_running(self, run_id: str) -> bool:
        handle = self.get(run_id)
        return bool(handle is not None and handle.thread is not None and handle.thread.is_alive())

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop admission and drain accepted work without cancelling queued runs."""
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait)

    def _admit(self, handle: RunHandle, clinical_text: str) -> None:
        payload = {
            "case_id": handle.case_id, "input_chars": len(clinical_text),
            "input_text": clinical_text[:600], "requested_execution_mode": handle.requested_mode,
            "input_sha256": hashlib.sha256(clinical_text.encode("utf-8")).hexdigest(),
            "document_cache": {}, "research_notice": PipelineRun.research_notice(),
        }
        ev.assert_payload_is_publishable(payload)
        event = self._ledger.append(handle.run_id, ev.RUN_CREATED, "run_store", payload,
                                    tool_name="run_store", tool_version="research-run-store/2")
        handle.started_at = event["created_at"]

    def start(self, *, case_id: str, clinical_text: str) -> RunHandle:
        """Avvia una run del runtime canonico. Non esiste altro da avviare.

        Il parametro ``execution_mode`` e' stato rimosso: non c'e' piu' una
        scelta da propagare. Prima di lui c'era un ``use_replay`` dedotto dalla
        presenza di artefatti congelati per il caso -- il fallback silenzioso --
        e sostituirlo con una scelta esplicita del chiamante ne aveva reso
        visibile il costo senza rimuoverlo. Ora il costo non c'e': il
        ``RunStore`` esegue un solo percorso e non ha nulla da dedurre.
        """
        if not self._slots.acquire(blocking=False):
            raise RunStoreOverloaded("Research pipeline execution capacity is full")
        run_id = str(uuid4())
        handle = RunHandle(
            run_id=run_id, case_id=case_id, status="CREATED",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        try:
            with self._lock:
                if self._closed:
                    raise RunStoreOverloaded("Research pipeline store is shutting down")
                # Admission must survive cache/provider failures and process restart.
                self._admit(handle, clinical_text)
                self._runs[run_id] = handle
                handle.thread = FutureThread()
                handle.status = "RUNNING"
                future = self._executor.submit(self._execute, handle, clinical_text)
                handle.thread.future = future
            future.add_done_callback(self._release_completed)
        except Exception:
            self._slots.release()
            handle.thread = None
            if ledger_reads.has_run(self._ledger, run_id):
                self._abort(handle)
                self._trim_terminal_cache()
            raise
        return handle

    def _execute(self, handle: RunHandle, clinical_text: str) -> None:
        try:
            # Preserve the same durable boundary for direct internal execution.
            if not ledger_reads.has_run(self._ledger, handle.run_id):
                self._admit(handle, clinical_text)
            # Cache-first con acquisizione autorizzata sul miss. L'apertura è
            # tentata una volta; solo i rami documentali la richiedono davvero.
            try:
                document_runtime = DocumentRuntime.open()
            except cache_runtime.DocumentCacheUnavailable:
                # Routing precede l'uso dei documenti. KG_ONLY non deve dipendere
                # da una cache che non consumerà; PAPER/TRIAL falliscono chiusi
                # nello stage documentale dell'orchestratore.
                document_runtime = None
            # Canonical SourceUnits come from DocumentRuntime. Historical
            # indexes belong exclusively to explicitly injected research harnesses.
            handle.run = orchestrator.run_case(
                case_id=handle.case_id, clinical_text=clinical_text,
                source_units_by_id={},
                budget=new_run_budget(),
                ledger=self._ledger, run_id=handle.run_id,
                document_runtime=document_runtime, **self._canonical_providers(),
            )
            handle.status = handle.run.status
        except Exception:  # noqa: BLE001 -- sanitize before durable/public output
            self._abort(handle)

    def _abort(self, handle: RunHandle) -> None:
        handle.status = "FAILED"
        handle.error = "Research pipeline aborted because of an unexpected execution error"
        handle.error_reason_code = "LIVE_STAGE_FAILED"
        snapshot = rehydration.rehydrate(self._ledger, handle.run_id) or handle.snapshot()
        snapshot.update({"status": "FAILED", "stopped_at": handle.error_reason_code,
                         "completed_at": datetime.now(timezone.utc).isoformat(),
                         "errors": [handle.error], "reason_codes": [handle.error_reason_code]})
        for key in ("rehydrated", "recovery_status", "hash_chain_valid", "stages_recorded",
                    "stages_expected", "stages_missing"):
            snapshot.pop(key, None)
        # Stage artifacts are already append-only. Persist only the terminal header.
        header = {key: value for key, value in snapshot.items() if key not in {"stages", "relation_aware_report"}}
        payload = {"status": "FAILED", "stopped_at": handle.error_reason_code,
                   "errors": [handle.error], "reason_codes": [handle.error_reason_code],
                   "pipeline_abort": True, "run_snapshot": header,
                   **em.summarize(handle.requested_mode, ())}
        ev.assert_payload_is_publishable(payload)
        self._ledger.append(handle.run_id, ev.RUN_COMPLETED, "run_store", payload,
                            tool_name="run_store", tool_version="research-run-store/2")
        handle.run = None
        handle._terminal_snapshot = snapshot

    @staticmethod
    def _canonical_providers() -> dict[str, Callable[..., Any]]:
        """Gli unici provider del runtime operativo.

        Parser ed enricher chiamano davvero il modello, spendono il budget e la
        validazione passa dal validatore corrente. Il Narrator è aggiunto solo
        con opt-in esplicito e resta post-dossier. Gli adattatori congelati di
        ``replay.py`` non sono raggiungibili da qui: sono infrastruttura di
        ricerca e vanno iniettati esplicitamente in ``orchestrator.run_case``.
        """
        from backend.research_pipeline import live_providers
        from backend.research_pipeline.enrichment.semantic_alignment import call_semantic_alignment

        providers = {
            "call_parser_fn": live_providers.parser_fn,
            "call_enricher_fn": live_providers.enricher_fn,
            "validate_fn": live_providers.validate_fn,
            "call_semantic_alignment_fn": call_semantic_alignment,
        }
        if narrator_enabled():
            providers["call_narrator_fn"] = live_providers.narrator_fn
        return providers


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
        previous = _STORE
        _STORE = None
    if previous is not None:
        previous.shutdown()


def demo_cases() -> list[dict[str, Any]]:
    """Casi sintetici disponibili. Eseguono la pipeline reale, non output finti."""
    return [
        {
            "case_id": case["case_id"],
            "clinical_text": case["clinical_text"],
            "expected_query_intent": case.get("expected_query_intent"),
            "expected_result": case.get("expected_result"),
        }
        for case in CASES
    ]
