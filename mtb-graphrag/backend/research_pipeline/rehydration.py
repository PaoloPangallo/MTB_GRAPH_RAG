"""Ricostruzione di una run dal ledger append-only.

``RunStore`` è un registro in memoria: un riavvio del backend lo azzera e
``GET /runs/{id}`` risponde 404 anche se gli eventi di quella run sono ancora su
disco, integri e verificabili. Il ledger è già la fonte canonica — lo dichiara
``events.REPLAYABLE_EVENT_TYPES`` — ma nessuno lo proiettava.

Questo modulo aggiunge la proiezione, non una seconda copia. Non esiste un file
di snapshot da tenere allineato: se la vista e gli eventi divergessero, sarebbe
la vista a essere sbagliata, e ricalcolarla a ogni lettura rende la divergenza
impossibile per costruzione.

``EventLedger`` è **sigillato** dal manifest dell'esperimento finale
(``agentic/ledger.py`` compare in ``final_experiment/systems_v1.json``): non
espone un elenco delle run e non può essere esteso. L'enumerazione avviene
quindi con una lettura SQL diretta e in sola lettura sullo stesso file, senza
toccare il modulo sigillato.

Cosa **non** viene persistito, perché non entra mai negli eventi: documenti
integrali, ``exact_text`` completo, risposte grezze del modello, credenziali.
Il preimage dell'hash è il payload, e ``events.assert_payload_is_publishable``
rifiuta testo documentale e ragionamento interno prima della scrittura: la
persistenza eredita quella garanzia invece di ridichiararla.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import events as ev
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline.contracts import (
    NOT_IMPLEMENTED_STAGE_IDS,
    STAGE_SEQUENCE,
    PipelineRun,
    document_acquisition_summary,
    stage_type_for,
)

#: Chiavi di servizio presenti in ogni payload di stage. Tutto il resto è
#: l'``output_preview`` dello stage, ricostruito per differenza.
_STAGE_META_KEYS: frozenset[str] = frozenset({
    "stage_id", "stage_type", "producer", "status", "execution_mode",
    "artifact_origin", "reason_codes", "duration_ms", "warnings", "errors",
    "metrics", "lineage", "sequence",
})

_TERMINAL_EVENTS: frozenset[str] = frozenset({
    ev.STAGE_COMPLETED, ev.STAGE_WARNING, ev.STAGE_FAILED, ev.STAGE_SKIPPED,
})

_STATUS_BY_EVENT: dict[str, str] = {
    ev.STAGE_COMPLETED: "SUCCEEDED", ev.STAGE_WARNING: "WARNING",
    ev.STAGE_FAILED: "FAILED", ev.STAGE_SKIPPED: "SKIPPED",
}

#: Una run i cui eventi si fermano prima di ``RUN_COMPLETED`` è stata interrotta
#: — processo ucciso, riavvio a metà. Non è né riuscita né fallita: dichiararla
#: ``FAILED`` attribuirebbe alla pipeline un esito che non ha prodotto.
RECOVERED_INCOMPLETE = "RECOVERED_INCOMPLETE"


def list_run_ids(ledger: EventLedger) -> list[str]:
    """Run presenti sul ledger, dalla più recente. Lettura diretta e read-only."""
    path = Path(ledger.path)
    if not path.is_file():
        return []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT run_id, MIN(sequence) AS first_seq FROM agent_events "
            "GROUP BY run_id ORDER BY first_seq DESC"
        ).fetchall()
    except sqlite3.DatabaseError:
        return []
    finally:
        connection.close()
    return [row[0] for row in rows]


def _stage_from_events(stage_id: str, events: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Ricompone uno stage dai suoi eventi, nell'ordine in cui sono stati scritti."""
    terminal = next(
        (e for e in reversed(events) if e["event_type"] in _TERMINAL_EVENTS), None
    )
    if terminal is None:
        return None

    payload = terminal["payload"]
    # L'``output_preview`` sta nell'evento di dominio, non in quello di chiusura:
    # il primo porta il risultato, il secondo l'esito.
    domain = next(
        (e for e in reversed(events) if e["event_type"] in ev.REPLAYABLE_EVENT_TYPES), None
    )
    preview = (
        {k: v for k, v in domain["payload"].items() if k not in _STAGE_META_KEYS}
        if domain is not None else {}
    )
    started = next((e for e in events if e["event_type"] == ev.STAGE_STARTED), None)

    return {
        "stage_id": stage_id,
        "stage_type": payload.get("stage_type") or stage_type_for(stage_id),
        "sequence": payload.get("sequence") or (STAGE_SEQUENCE.index(stage_id) + 1),
        "status": _STATUS_BY_EVENT[terminal["event_type"]],
        "started_at": started["created_at"] if started is not None else None,
        "completed_at": terminal["created_at"],
        "duration_ms": payload.get("duration_ms"),
        "input_ref": None,
        "output_ref": None,
        "input_preview": {},
        "output_preview": preview,
        "reason_codes": list(payload.get("reason_codes") or []),
        "warnings": list(payload.get("warnings") or []),
        "errors": list(payload.get("errors") or []),
        "producer": payload.get("producer") or {},
        "metrics": dict(payload.get("metrics") or {}),
        "lineage": dict(payload.get("lineage") or {}),
        # Un payload che non dichiara la modalità viene letto come canonico, non
        # come REPLAY. Il default precedente era prudente quando esistevano due
        # modalità; ora sarebbe una **falsa attribuzione**: etichetterebbe come
        # rigiocata una run che nessun artefatto registrato ha toccato. Ciò che
        # distingue davvero le due cose resta ``artifact_origin``, che ogni stage
        # scrive esplicitamente e che qui non viene mai indovinato.
        "execution_mode": payload.get("execution_mode") or em.CANONICAL_MODE,
        "artifact_origin": payload.get("artifact_origin") or em.NOT_EXECUTED,
    }


def rehydrate(ledger: EventLedger, run_id: str) -> dict[str, Any] | None:
    """Snapshot della run ricostruito dagli eventi, o ``None`` se non esiste.

    La forma è identica a quella di ``PipelineRun.to_dict()``: un client non
    deve poter distinguere una run in memoria da una reidratata, altrimenti la
    persistenza diventerebbe un secondo contratto da mantenere.
    """
    events = ledger.events(run_id)
    if not events:
        return None

    created = next((e for e in events if e["event_type"] == ev.RUN_CREATED), None)
    completed = next(
        (e for e in reversed(events) if e["event_type"] == ev.RUN_COMPLETED), None
    )
    created_payload = created["payload"] if created is not None else {}

    by_stage: dict[str, list[Mapping[str, Any]]] = {}
    for event in events:
        stage_id = (event.get("payload") or {}).get("stage_id")
        if stage_id:
            by_stage.setdefault(stage_id, []).append(event)

    stages = [
        stage for stage in (
            _stage_from_events(stage_id, by_stage[stage_id])
            for stage_id in STAGE_SEQUENCE if stage_id in by_stage
        ) if stage is not None
    ]
    stages.sort(key=lambda s: s["sequence"])

    # Come sopra: l'assenza del campo non è una prova di replay. Le run storiche
    # che *furono* rigiocate lo dichiarano nel proprio ``RUN_CREATED``, e restano
    # decodificate come tali; quelle che non dichiarano nulla sono canoniche.
    requested_mode = created_payload.get("requested_execution_mode") or em.CANONICAL_MODE
    origins = [stage["artifact_origin"] for stage in stages]

    if completed is not None:
        status = completed["payload"].get("status") or "COMPLETED"
        stopped_at = completed["payload"].get("stopped_at")
        completed_at = completed["created_at"]
    else:
        # Interrotta: gli eventi si fermano a metà. Gli stage già scritti restano
        # visibili — sono ciò che la run ha davvero prodotto prima di sparire.
        status = "FAILED"
        stopped_at = None
        completed_at = None

    return {
        "run_id": run_id,
        "case_id": created_payload.get("case_id", ""),
        "status": status,
        "started_at": created["created_at"] if created is not None else events[0]["created_at"],
        "completed_at": completed_at,
        "current_stage": None,
        "stopped_at": stopped_at,
        "input_text": created_payload.get("input_text", ""),
        "stages": stages,
        "dossier_id": created_payload.get("case_id") if any(
            s["stage_id"] == "stage_13_dossier" and s["status"] == "SUCCEEDED" for s in stages
        ) else None,
        "warnings": [],
        "errors": [],
        "versions": {},
        "metrics": {},
        "research_notice": PipelineRun.research_notice(),
        "document_cache": dict(created_payload.get("document_cache") or {}),
        # Stessa funzione della run in memoria, sugli stessi stage: le due
        # proiezioni non devono poter divergere, ed e' l'invariante dichiarato
        # in cima a questo modulo.
        "document_acquisition": document_acquisition_summary(stages),
        # Valore canonico scritto dall'orchestratore, non ricalcolato: sommare le
        # metriche degli stage escludeva il parser e contava come reali le
        # chiamate rigiocate, dando due numeri diversi per la stessa run a
        # seconda che la si leggesse dalla memoria o dal ledger.
        "llm_calls": int((completed["payload"].get("llm_calls") or 0)) if completed is not None else 0,
        **em.summarize(requested_mode, origins),
        # Marcature che esistono **solo** su una run reidratata: chi legge deve
        # poter distinguere una vista ricostruita da una run appena eseguita.
        "rehydrated": True,
        "recovery_status": RECOVERED_INCOMPLETE if completed is None else "COMPLETE",
        "hash_chain_valid": ledger.verify_chain(run_id),
        "stages_recorded": len(stages),
        "stages_expected": len(STAGE_SEQUENCE),
        "stages_missing": [
            stage_id for stage_id in STAGE_SEQUENCE
            if stage_id not in by_stage and stage_id not in NOT_IMPLEMENTED_STAGE_IDS
        ],
    }


def summarize_run(ledger: EventLedger, run_id: str) -> dict[str, Any] | None:
    """Riga di elenco per una run persistita, senza ricostruirla per intero."""
    snapshot = rehydrate(ledger, run_id)
    if snapshot is None:
        return None
    return {
        "run_id": run_id,
        "case_id": snapshot["case_id"],
        "status": snapshot["status"],
        "started_at": snapshot["started_at"],
        "execution_mode": snapshot["execution_mode"],
        "requested_mode": snapshot["requested_mode"],
        "replay_artifacts_used": snapshot["replay_artifacts_used"],
        "fully_live": snapshot["fully_live"],
        "recovery_status": snapshot["recovery_status"],
        "rehydrated": True,
    }
