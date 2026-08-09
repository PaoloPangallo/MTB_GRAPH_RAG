"""Endpoint del research runtime verificabile.

Namespace separato, dietro ``VERIFIABLE_PIPELINE_RESEARCH_ENABLED``, disattivo
di default. Nessun endpoint esistente viene modificato.

Con il flag disattivo le rotte rispondono **404 e non 403**: in un deployment di
prodotto il research runtime non deve nemmeno rivelare la propria esistenza.

Contratto in ``docs/verifiable_pipeline/api_contract.md`` e ``sse_contract.md``.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ``replay`` non compare fra gli import: nessuna rotta di prodotto deve poter
# raggiungere gli adattatori congelati, nemmeno per descriverli.
from backend.research_pipeline import data_access, execution_mode, llm_config
from backend.research_pipeline.documents import cache_runtime
from backend.research_pipeline.contracts import (
    LLM_STAGE_IDS,
    NOT_IMPLEMENTED_STAGE_IDS,
    PRESENTATION_STAGE_IDS,
    PipelineRun,
)
from backend.research_pipeline.run_store import demo_cases, get_store

router = APIRouter()

HEARTBEAT_SECONDS = 15
POLL_SECONDS = 0.2
STREAM_IDLE_TIMEOUT_SECONDS = 300


def research_enabled() -> bool:
    return os.getenv("VERIFIABLE_PIPELINE_RESEARCH_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _guard() -> None:
    if not research_enabled():
        # 404 e non 403: l'esistenza del runtime di ricerca non va rivelata.
        raise HTTPException(status_code=404, detail="Not Found")


def _handle_or_404(run_id: str):
    _guard()
    handle = get_store().get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="run non trovata")
    return handle


def _snapshot_or_404(run_id: str) -> dict[str, Any]:
    """Vista della run, dalla memoria o dal ledger.

    Prima ogni rotta passava da ``_handle_or_404``, che consulta solo il registro
    in memoria: dopo un riavvio del backend anche ``/events`` rispondeva 404, pur
    avendo tutti i suoi eventi su disco e la catena di hash integra.
    """
    _guard()
    snapshot = get_store().snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="run non trovata")
    return snapshot


class CreateRunRequest(BaseModel):
    """Il caso, e nient'altro.

    ``execution_mode`` è stato rimosso: non esiste più una modalità da scegliere.
    C'è un solo runtime operativo, e il client non ha modo di chiederne un altro
    — né per selezione né per omissione.

    ``extra="forbid"`` è deliberato: un client che continuasse a inviare
    ``execution_mode`` riceve un 422 esplicito invece di vedersi ignorare il
    campo in silenzio e credere di aver scelto qualcosa. Un'opzione ignorata è
    peggio di un'opzione rifiutata, perché sopravvive nelle aspettative di chi
    la invia.
    """

    model_config = {"extra": "forbid"}

    clinical_text: str | None = Field(default=None, min_length=1)
    case_id: str | None = None
    demo_case_key: str | None = None


@router.get("/cases")
def list_cases() -> dict[str, Any]:
    """Casi sintetici disponibili. Eseguono la pipeline reale."""
    _guard()
    return {
        "cases": demo_cases(),
        "no_mock_outputs": True,
        "research_notice": PipelineRun.research_notice(),
    }


@router.get("/config")
def config() -> dict[str, Any]:
    """Stato di dati, cache e provider LLM. Non espone mai la chiave."""
    _guard()
    cache = cache_runtime.describe().to_dict()
    return {
        "llm": llm_config.describe(),
        "data": data_access.describe_availability(),
        "document_cache": cache,
        # Un solo runtime, dichiarato come tale. ``frozen_replay`` è sparito da
        # qui: era la sintesi degli artefatti congelati, ed era ciò da cui la UI
        # derivava l'esistenza di una seconda modalità. Gli artefatti restano,
        # come infrastruttura di ricerca; l'API di prodotto non li annuncia.
        "runtime": {
            "canonical_runtime": execution_mode.CANONICAL_MODE,
            "user_selectable_modes": [],
            "artifact_origins": list(execution_mode.ARTIFACT_ORIGINS),
            "document_acquisition": "CACHE_FIRST_API_ON_MISS",
            "available": cache["document_cache_available"],
            "unavailable_reason": cache["reason_codes"] or None,
        },
        "stages_not_implemented": sorted(NOT_IMPLEMENTED_STAGE_IDS),
        # Stage che producono la vista di presentazione: un loro fallimento non
        # invalida il dossier canonico, attiva il fallback strutturato.
        "presentation_stages": sorted(PRESENTATION_STAGE_IDS),
        "llm_stages": sorted(LLM_STAGE_IDS),
        "research_notice": PipelineRun.research_notice(),
    }


@router.post("/runs", status_code=201)
def create_run(request: CreateRunRequest) -> dict[str, Any]:
    _guard()
    case_id = request.demo_case_key or request.case_id
    clinical_text = request.clinical_text

    if request.demo_case_key:
        case = next((c for c in demo_cases() if c["case_id"] == request.demo_case_key), None)
        if case is None:
            raise HTTPException(status_code=404, detail=f"caso demo sconosciuto: {request.demo_case_key}")
        clinical_text = case["clinical_text"]

    if not clinical_text:
        raise HTTPException(status_code=422, detail="clinical_text o demo_case_key sono obbligatori")
    if not case_id:
        raise HTTPException(status_code=422, detail="case_id obbligatorio per un testo libero")

    # Precondizioni del runtime canonico, verificate **prima** di avviare la run:
    # ciò che non può essere eseguito fallisce subito e con il proprio motivo,
    # invece di degradare in un replay travestito. Non c'è più un ramo
    # alternativo da offrire quando queste precondizioni non reggono — l'assenza
    # di quel ramo è il punto di questa architettura.
    try:
        llm_config.resolve_endpoint()
    except llm_config.MissingLLMCredentials as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not cache_runtime.is_available():
        available, reasons = cache_runtime.validate_cache()
        raise HTTPException(
            status_code=503,
            detail=f"cache documentale non disponibile ({reasons}): il runtime "
                   f"canonico non ripiega su artefatti registrati. Configurare "
                   f"{cache_runtime.CACHE_PATH_ENV}.",
        )

    handle = get_store().start(case_id=case_id, clinical_text=clinical_text)
    return {
        "run_id": handle.run_id,
        "case_id": handle.case_id,
        "status": handle.status,
        # Etichetta della run, non una scelta effettuata: il campo resta nella
        # risposta perché la UI e le run storiche lo leggono con lo stesso nome.
        "execution_mode": execution_mode.CANONICAL_MODE,
        "stream_url": f"/api/v1/research/pipeline/runs/{handle.run_id}/stream",
        "research_notice": PipelineRun.research_notice(),
    }


@router.get("/runs")
def list_runs() -> dict[str, Any]:
    _guard()
    return {"runs": get_store().list_all()}


@router.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _snapshot_or_404(run_id)


@router.get("/runs/{run_id}/events")
def get_events(run_id: str, after_sequence: int = 0, limit: int = 200) -> dict[str, Any]:
    _snapshot_or_404(run_id)
    store = get_store()
    limit = max(1, min(limit, 1000))

    rows = [e for e in store.ledger.events(run_id) if int(e["sequence"]) > after_sequence]
    page = rows[:limit]
    return {
        "run_id": run_id,
        "append_only": True,
        "hash_chain_valid": store.ledger.verify_chain(run_id),
        "events": [_public_event(e) for e in page],
        "next_after_sequence": int(page[-1]["sequence"]) if page else after_sequence,
        "has_more": len(rows) > len(page),
    }


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    """Proiezione pubblica di un evento del ledger.

    ``payload_json`` viene omesso: il payload strutturato è già in ``payload``, e
    duplicarlo come stringa grezza aggiungerebbe soltanto superficie.
    """
    payload = event.get("payload") or {}
    return {
        "event_id": event["event_id"],
        "sequence": int(event["sequence"]),
        "event_type": event["event_type"],
        "created_at": event["created_at"],
        "actor": event["actor"],
        "stage_id": payload.get("stage_id"),
        "stage_type": payload.get("stage_type"),
        "producer": payload.get("producer"),
        "payload_hash": event.get("payload_hash"),
        "payload": payload,
    }


@router.get("/runs/{run_id}/stages/{stage_id}")
def get_stage(run_id: str, stage_id: str) -> dict[str, Any]:
    snapshot = _snapshot_or_404(run_id)
    stage = next((s for s in snapshot["stages"] if s["stage_id"] == stage_id), None)
    if stage is None:
        raise HTTPException(status_code=404, detail=f"stage non trovato: {stage_id}")
    events = [
        _public_event(e) for e in get_store().ledger.events(run_id)
        if (e.get("payload") or {}).get("stage_id") == stage_id
    ]
    return {"run_id": run_id, "stage": stage, "events": events}


@router.get("/runs/{run_id}/dossier")
def get_dossier(run_id: str) -> dict[str, Any]:
    snapshot = _snapshot_or_404(run_id)
    stage = next((s for s in snapshot["stages"] if s["stage_id"] == "stage_13_dossier"), None)
    if stage is None or stage["status"] != "SUCCEEDED":
        raise HTTPException(
            status_code=409,
            detail=f"nessun dossier: la run è {snapshot['status']}"
                   + (f" ({snapshot['stopped_at']})" if snapshot.get("stopped_at") else ""),
        )
    preview = stage["output_preview"]
    verification_stage = next(
        (s for s in snapshot["stages"] if s["stage_id"] == "stage_15_narrative_verifier"), None)
    verification = (verification_stage or {}).get("output_preview") or {}

    return {
        "run_id": run_id,
        # Il dossier vero, non la preview che lo contiene: annidarlo
        # costringerebbe ogni client a conoscere la forma dello stage.
        "dossier": preview.get("dossier", preview),
        "candidate_count": preview.get("candidate_count"),
        "status": snapshot["status"],
        # La narrativa e' una vista, e viaggia separata dal dossier canonico.
        # ``narrative`` e' popolata SOLO se il verifier deterministico ha
        # accettato: il client non deve decidere se mostrarla, deve leggere
        # ``presentation_mode``.
        "narrative": verification.get("verified_narrative"),
        "presentation_mode": verification.get("presentation_mode", "STRUCTURED_DOSSIER_FALLBACK"),
        "narrative_verification": {
            "status": (verification.get("verification") or {}).get("status"),
            "reason_codes": (verification.get("verification") or {}).get("reason_codes", []),
            "verifier_version": (verification.get("verification") or {}).get("verifier_version"),
            "narrative_hash": (verification.get("verification") or {}).get("narrative_hash"),
            "input_hash": (verification.get("verification") or {}).get("input_hash"),
        } if verification else None,
        "research_notice": PipelineRun.research_notice(),
    }


#: Esiti di validazione che ancorano una candidate a un documento. Solo questi
#: rendono ``document_grounded`` vero: un'astensione o un rigetto lasciano la
#: candidate al livello del grafo.
_ACCEPTED_OUTCOMES = ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING",
                      "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")


@router.get("/runs/{run_id}/provenance")
def get_provenance(run_id: str) -> dict[str, Any]:
    """Catena CaseContext → candidate → documento → SourceUnit → quote →
    validazione → controlli → voce di dossier.

    Al livello ``SOURCE_UNIT`` il campo ``text`` è **sempre** ``null``: l'indice
    contiene solo locatori e ``content_hash``, e il testo del documento non
    transita mai per l'API.

    ``document_grounded`` distingue una candidate ancorata a una citazione
    verificata da una che resta sostenuta solo dal grafo. Quest'ultima è marcata
    ``PARENT_LEVEL_ONLY``: presentarla come prova documentale è esattamente la
    lettura che la separazione fra candidate e document support esiste per
    impedire.
    """
    snapshot = _snapshot_or_404(run_id)
    by_id = {s["stage_id"]: s for s in snapshot["stages"]}

    def _preview(stage_id: str) -> dict[str, Any]:
        return by_id.get(stage_id, {}).get("output_preview", {}) or {}

    retrieval = _preview("stage_5_kg_retrieval")
    source_units = _preview("stage_7_source_units").get("source_units", [])
    # Esito reale della risoluzione documentale, per ``document_id``. Il livello
    # DOCUMENT dichiarava ``replayed: true`` in modo incondizionato, ereditato dal
    # runtime che non risolveva affatto i documenti: nel runtime canonico è una
    # falsa attribuzione, e faceva comparire una spunta REPLAY su documenti letti
    # dalla cache autorizzata o appena acquisiti da un'API.
    resolved_documents = {
        entry.get("document_id"): entry
        for entry in _preview("stage_6_document_resolution").get("documents", [])
    }
    #: Vero solo se lo stage 6 ha davvero letto un artefatto registrato — cosa
    #: che il runtime canonico non fa mai. È la stessa origine che classifica la
    #: run, non un secondo giudizio calcolato qui.
    documents_replayed = (
        by_id.get("stage_6_document_resolution", {}).get("artifact_origin")
        == execution_mode.RECORDED_REAL_RUN
    )
    case_context = _preview("stage_2_casecontext_parser").get("case_context", {})
    match_records = _preview("stage_3_casecontext_match").get("records", [])
    enricher_calls = _preview("stage_9_paper_context_enricher").get("calls", [])
    validations = _preview("stage_10_enrichment_validation").get("validations", [])
    checks_by_candidate = {
        entry["candidate_id"]: entry
        for entry in _preview("stage_11_deterministic_gates").get("checks_by_candidate", [])
    }
    statuses = {
        entry["candidate_id"]: entry
        for entry in _preview("stage_12_status").get("statuses", [])
    }
    selections = {
        entry.get("candidate_id"): entry
        for entry in _preview("stage_8_paper_selection").get("selections", [])
    }

    items = []
    for association in retrieval.get("associations", []):
        candidate_id = association["candidate_id"]

        calls = [c for c in enricher_calls if c.get("candidate_id") == candidate_id]
        candidate_validations = [v for v in validations if v.get("candidate_id") == candidate_id]
        accepted = [v for v in candidate_validations if v.get("outcome") in _ACCEPTED_OUTCOMES]
        accepted_papers = {v.get("paper_id") for v in accepted}

        # Una quote entra in catena solo se la sua validazione è passata. Le
        # altre restano visibili per audit, in un campo distinto.
        accepted_quotes, rejected_quotes, abstentions = [], [], []
        for call in calls:
            enrichment = call.get("enrichment") or {}
            entry = {
                "paper_id": call.get("paper_id"),
                "source_unit_id": enrichment.get("source_unit_id"),
                "author_claim_quote": enrichment.get("author_claim_quote"),
                "author_context_summary": enrichment.get("author_context_summary"),
                "abstention_reason": enrichment.get("abstention_reason"),
                "model": call.get("model"),
                "prompt_version": call.get("prompt_version"),
                "transport_version": call.get("transport_version"),
                "replayed": call.get("replayed", False),
            }
            if not enrichment.get("author_claim_quote"):
                abstentions.append(entry)
            elif call.get("paper_id") in accepted_papers:
                accepted_quotes.append(entry)
            else:
                rejected_quotes.append(entry)

        document_grounded = bool(accepted_quotes)
        selection = selections.get(candidate_id, {})

        items.append({
            "candidate_id": candidate_id,
            "document_grounded": document_grounded,
            "provenance_level": "DOCUMENT_GROUNDED" if document_grounded else "PARENT_LEVEL_ONLY",
            "chain": [
                {"level": "CASE_CONTEXT", "ref": snapshot["case_id"],
                 "case_context": case_context, "match_records": match_records},
                {"level": "GRAPH_CANDIDATE_ASSERTION", "ref": candidate_id,
                 "graph_derived": True, "documentary_proof": False,
                 "candidate": association.get("candidate"),
                 "match_reason": association.get("match_reason")},
                {"level": "DOCUMENT",
                 "ref": [b["document_id"] for b in association.get("available_bundles", [])],
                 "bundles": association.get("available_bundles", []),
                 # Come il documento è entrato nella run, dichiarato dallo stage
                 # che lo ha risolto e non asserito a priori.
                 "acquisition": [
                     {"document_id": b["document_id"],
                      "cache_hit": resolved_documents.get(b["document_id"], {}).get("cache_hit"),
                      "resolved": resolved_documents.get(b["document_id"], {}).get("resolved"),
                      "source": resolved_documents.get(b["document_id"], {}).get("source"),
                      "reason_codes": resolved_documents.get(b["document_id"], {}).get("reason_codes", [])}
                     for b in association.get("available_bundles", [])
                 ],
                 "replayed": documents_replayed},
                {"level": "SOURCE_UNIT",
                 "units": [{**unit, "text": None} for unit in source_units],
                 "text_never_exposed": True},
                {"level": "AUTHOR_QUOTE",
                 "accepted_quotes": accepted_quotes,
                 "rejected_quotes": rejected_quotes,
                 "abstentions": abstentions,
                 "selected_papers": [p.get("bundle_id") for p in selection.get("selected_papers", [])],
                 "produced_by": "LLM",
                 "never_decides_status": True},
                {"level": "ENRICHMENT_VALIDATION",
                 "validations": candidate_validations,
                 "accepted_outcomes": list(_ACCEPTED_OUTCOMES)},
                {"level": "DETERMINISTIC_CHECK",
                 "checks": checks_by_candidate.get(candidate_id, {}).get("checks", []),
                 "support_mask": checks_by_candidate.get(candidate_id, {}).get("support_mask", {}),
                 "produced_by": "DETERMINISTIC"},
                {"level": "DOSSIER_ITEM", "ref": statuses.get(candidate_id),
                 "document_grounded": document_grounded},
            ],
        })
    return {"run_id": run_id, "items": items}


@router.get("/runs/{run_id}/metrics")
def get_metrics(run_id: str) -> dict[str, Any]:
    """Metriche canoniche, calcolate dal backend.

    I campi non misurabili restano ``null``: uno zero al loro posto sarebbe una
    misura falsa e non un dato mancante.
    """
    snapshot = _snapshot_or_404(run_id)
    stages = snapshot["stages"]
    by_id = {s["stage_id"]: s for s in stages}

    calls = by_id.get("stage_9_paper_context_enricher", {}).get("output_preview", {}).get("calls", [])
    validations = by_id.get("stage_10_enrichment_validation", {}).get("output_preview", {}).get("validations", [])
    retrieval = by_id.get("stage_5_kg_retrieval", {}).get("output_preview", {})
    statuses = by_id.get("stage_12_status", {}).get("output_preview", {}).get("statuses", [])

    def _sum(field: str) -> int | None:
        values = [c.get(field) for c in calls if isinstance(c.get(field), int)]
        return sum(values) if values else None

    accepted = [v for v in validations if str(v.get("outcome", "")).endswith("ACCEPTED")]
    return {
        "run_id": run_id,
        "duration_ms_total": sum(s["duration_ms"] or 0 for s in stages) or None,
        "duration_ms_by_stage": {s["stage_id"]: s["duration_ms"] for s in stages},
        "llm_calls": len(calls),
        "tokens_input": _sum("input_tokens"),
        "tokens_output": _sum("output_tokens"),
        "candidates_found": len(retrieval.get("associations", [])),
        "candidates_excluded": len(retrieval.get("excluded_candidates", [])),
        "quotes_accepted": len(accepted),
        "quotes_rejected": len([v for v in validations if str(v.get("outcome", "")).startswith("REJECTED")]),
        "abstentions": len([v for v in validations if "ABSTAINED" in str(v.get("outcome", ""))]),
        "warnings": sum(len(s["warnings"]) for s in stages),
        "errors": sum(len(s["errors"]) for s in stages),
        "status_counts": {s: sum(1 for e in statuses if e["status"] == s)
                          for s in {e["status"] for e in statuses}},
        "computed_by": "backend",
    }


@router.get("/runs/{run_id}/stream")
def stream_run(run_id: str, request: Request) -> StreamingResponse:
    """Stream SSE degli eventi della run.

    ``id`` è la ``sequence`` del ledger, monotona per run: ``Last-Event-ID`` è
    quindi utilizzabile direttamente per il resume, senza mappature.
    """
    _snapshot_or_404(run_id)
    # Assente dopo un riavvio: la run non è più in esecuzione, i suoi eventi
    # sono comunque sul ledger e lo stream li invia una volta e chiude.
    handle = get_store().get(run_id)
    last_event_id = request.headers.get("last-event-id")
    try:
        after = int(last_event_id) if last_event_id else 0
    except ValueError:
        after = 0

    def generate() -> Iterator[str]:
        store = get_store()
        cursor = after
        last_beat = time.monotonic()
        deadline = time.monotonic() + STREAM_IDLE_TIMEOUT_SECONDS

        while True:
            rows = [e for e in store.ledger.events(run_id) if int(e["sequence"]) > cursor]
            for event in rows:
                cursor = int(event["sequence"])
                public = _public_event(event)
                yield f"id: {cursor}\nevent: {public['event_type']}\ndata: {json.dumps(public, default=str)}\n\n"
                last_beat = time.monotonic()

            finished = handle is None or handle.thread is None or not handle.thread.is_alive()
            if finished and not rows:
                # La run e' conclusa e non restano eventi da inviare: lo stream
                # si chiude invece di restare aperto inutilmente. Vale anche per
                # gli esiti STOPPED e FAILED, che sono conclusioni, non guasti
                # del trasporto.
                break
            if time.monotonic() > deadline:
                yield ": stream idle timeout\n\n"
                break
            if time.monotonic() - last_beat >= HEARTBEAT_SECONDS:
                yield ": heartbeat\n\n"
                last_beat = time.monotonic()
            time.sleep(POLL_SECONDS)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
