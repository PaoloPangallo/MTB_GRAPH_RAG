"""Endpoint del research runtime verificabile.

Namespace separato, dietro ``VERIFIABLE_PIPELINE_RESEARCH_ENABLED``, disattivo
di default. Nessun endpoint esistente viene modificato.

Con il flag disattivo le rotte rispondono **404 e non 403**: in un deployment di
prodotto il research runtime non deve nemmeno rivelare la propria esistenza.

Contratto in ``docs/verifiable_pipeline/api_contract.md`` e ``sse_contract.md``.
"""

from __future__ import annotations

import json
import hashlib
import os
import time
from typing import Any, Iterator

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ``replay`` non compare fra gli import: nessuna rotta di prodotto deve poter
# raggiungere gli adattatori congelati, nemmeno per descriverli.
from backend.research_pipeline import data_access, execution_mode, llm_config, events
from backend.research_pipeline.documents import cache_runtime
from backend.research_pipeline.narrative import input_projection as narrative_projection
from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
from backend.research_pipeline.dossier.accounting import apply_publication_integrity
from backend.research_pipeline.operational_metrics import operational_summary
from backend.research_pipeline.contracts import (
    LLM_STAGE_IDS,
    NOT_IMPLEMENTED_STAGE_IDS,
    PRESENTATION_STAGE_IDS,
    PipelineRun,
    RUN_STATUSES,
)
from backend.research_pipeline.public_schemas import (
    CreatedRunResponse, DossierResponse, EventPage, PublicPipelineRun, StageResponse,
)
from backend.research_pipeline.enrichment.verification_policy import public_artifact
from backend.research_pipeline.run_store import RunStoreOverloaded, demo_cases, get_store, narrator_enabled

router = APIRouter()

HEARTBEAT_SECONDS = 15
POLL_SECONDS = 0.2
STREAM_IDLE_TIMEOUT_SECONDS = 300
STREAM_EVENT_PAGE_SIZE = 200


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
    snapshot = public_artifact(snapshot)
    operations = operational_summary(snapshot)
    snapshot["metrics"] = {**(snapshot.get("metrics") or {}), "operational": operations,
                           "recorded_llm_calls": snapshot.get("llm_calls")}
    snapshot["llm_calls"] = operations["llm_calls"]
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

    clinical_text: str | None = Field(default=None, min_length=1, max_length=100_000)
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
            "narrator_enabled": narrator_enabled(),
            "documentary_profile": os.getenv('RESEARCH_PIPELINE_DOCUMENTARY_PROFILE', '').strip() or 'legacy',
            "hierarchical_source_index_enabled": os.getenv('RESEARCH_PIPELINE_HIERARCHICAL_SOURCE_INDEX', '').strip() == '1',
        },
        "stages_not_implemented": sorted(NOT_IMPLEMENTED_STAGE_IDS),
        # Stage che producono la vista di presentazione: un loro fallimento non
        # invalida il dossier canonico, attiva il fallback strutturato.
        "presentation_stages": sorted(PRESENTATION_STAGE_IDS),
        "llm_stages": sorted(LLM_STAGE_IDS),
        "research_notice": PipelineRun.research_notice(),
    }


@router.post("/runs", status_code=201, response_model=CreatedRunResponse, response_model_exclude_unset=True)
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

    # Il provider del parser è una precondizione globale. La cache documentale
    # viene invece verificata dopo il routing: KG_ONLY non la consuma, mentre
    # PAPER e TRIAL continuano a fallire chiusi senza document runtime.
    try:
        llm_config.resolve_endpoint()
    except llm_config.MissingLLMCredentials as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        handle = get_store().start(case_id=case_id, clinical_text=clinical_text)
    except RunStoreOverloaded as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Retry-After": "5"}) from exc
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
def list_runs(limit: int = Query(default=50, ge=1, le=200),
              offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
    _guard()
    return {"runs": get_store().list_all(limit=limit, offset=offset)}


@router.get("/runs/{run_id}", response_model=PublicPipelineRun, response_model_exclude_unset=True)
def get_run(run_id: str, compact: bool = False) -> dict[str, Any]:
    snapshot = _snapshot_or_404(run_id)
    if not compact:
        return snapshot
    return {
        **snapshot,
        "dossier_available": snapshot.get("relation_aware_report") is not None,
        "relation_aware_report": None,
        "stages": [
            {**stage, "input_preview": {}, "output_preview": {}}
            for stage in snapshot.get("stages", [])
        ],
    }


@router.get("/runs/{run_id}/events", response_model=EventPage, response_model_exclude_unset=True)
def get_events(run_id: str, after_sequence: int = Query(default=0, ge=0),
               limit: int = Query(default=200, ge=1, le=500), compact: bool = False) -> dict[str, Any]:
    _guard()
    store = get_store()
    if not store.has_run(run_id):
        raise HTTPException(status_code=404, detail="run non trovata")
    page = store.events_page(run_id, after_sequence=after_sequence, limit=limit)
    return {
        "run_id": run_id,
        "append_only": True,
        "hash_chain_valid": store.verify_chain(run_id),
        "events": [_public_event(e, compact=compact) for e in page["events"]],
        "next_after_sequence": page["next_sequence"],
        "has_more": page["has_more"],
    }


def _public_event(event: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
    """Proiezione pubblica di un evento del ledger.

    ``payload_json`` viene omesso: il payload strutturato è già in ``payload``, e
    duplicarlo come stringa grezza aggiungerebbe soltanto superficie.
    """
    payload = public_artifact(event.get("payload") or {})
    if compact:
        # The ledger stays complete; progress clients need no repeated artifacts.
        keys = {"stage_id", "stage_type", "producer", "status", "reason_codes", "errors", "warnings", "duration_ms", "execution_mode", "artifact_origin", "stopped_at", "stage_count", "llm_calls"}
        if event.get("event_type") == events.PIPELINE_WORK_PROGRESS:
            keys.update({"phase", "completed_candidates", "total_candidates", "reader_calls",
                         "reader_reuses", "candidate_id", "document_id"})
        payload = {key: value for key, value in payload.items() if key in keys}
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


@router.get("/runs/{run_id}/stages/{stage_id}", response_model=StageResponse, response_model_exclude_unset=True)
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


@router.get("/runs/{run_id}/dossier", response_model=DossierResponse, response_model_exclude_unset=True)
def get_dossier(run_id: str) -> dict[str, Any]:
    snapshot = _snapshot_or_404(run_id)
    stage = next((s for s in snapshot["stages"] if s["stage_id"] == "stage_13_dossier"), None)
    canonical = snapshot.get("relation_aware_report")
    if canonical is None and (stage is None or stage["status"] != "SUCCEEDED"):
        raise HTTPException(
            status_code=409,
            detail=f"nessun dossier: la run è {snapshot['status']}"
                   + (f" ({snapshot['stopped_at']})" if snapshot.get("stopped_at") else ""),
        )
    preview = (stage or {}).get("output_preview") or {}
    verification_stage = next(
        (s for s in snapshot["stages"] if s["stage_id"] == "stage_15_narrative_verifier"), None)
    verification = (verification_stage or {}).get("output_preview") or {}
    narrative_trace = (
        narrative_projection.build_narrative_trace(canonical)
        if canonical is not None else None
    )
    publication_input = dict(canonical or preview.get("relation_aware_report", preview))
    if publication_input.get("technical_run_status", publication_input.get("run_status")) not in RUN_STATUSES:
        publication_input["technical_run_status"] = snapshot["status"]
    canonical_dossier = apply_publication_integrity(publication_input)
    if canonical is not None:
        narrative_trace = narrative_projection.build_narrative_trace(canonical_dossier)
    verified_narrative = verification.get("verified_narrative")
    display_verification = verification.get("verification") or {}
    deterministic = (
        verification.get("presentation_mode") == "DETERMINISTIC_NARRATIVE_FALLBACK"
        and (verification.get("deterministic_verification") or {}).get("status") == "PASS"
    )
    if deterministic:
        verified_narrative = verification.get("deterministic_narrative")
        display_verification = verification["deterministic_verification"]
    presentation_mode = verification.get("presentation_mode", "STRUCTURED_DOSSIER_FALLBACK")
    display_presentation = verification.get("presentation")
    if canonical_dossier.get("documentary_projection_migration"):
        # Historical provider text was verified against the old projection.
        # Re-realize the migrated public facts locally; never reuse that PASS
        # for changed input or pretend a new model call took place.
        from backend.research_pipeline.narrative.controlled import build_catalog, default_plan, render_plan, verify_controlled
        from backend.research_pipeline.narrative.presentation import build_narrative_presentation
        source = narrative_projection.build_narrator_input(canonical_dossier)
        catalog = build_catalog(source)
        verified_narrative = render_plan(catalog, default_plan(catalog))
        verified_narrative["generation_origin"] = "DETERMINISTIC_FALLBACK"
        display_verification = verify_controlled(source, verified_narrative)
        deterministic = True
        presentation_mode = "DETERMINISTIC_NARRATIVE_FALLBACK"
        display_presentation = build_narrative_presentation(canonical_dossier, verified_narrative, display_verification)
        display_presentation["presentation_mode"] = presentation_mode
    narrative_publishable = (
        display_verification.get("status") == "PASS" and bool(verified_narrative)
        and presentation_mode in {"VERIFIED_NARRATIVE", "DETERMINISTIC_NARRATIVE_FALLBACK"}
    )
    if not narrative_publishable:
        verified_narrative = None
        presentation_mode = "STRUCTURED_DOSSIER_FALLBACK"
    verification_summary = {
        "status": display_verification.get("status"),
        "reason_codes": display_verification.get("reason_codes", []),
        "verifier_version": display_verification.get("verifier_version"),
        "narrative_hash": display_verification.get("narrative_hash"),
        "input_hash": display_verification.get("input_hash"),
    } if verification or canonical_dossier.get("documentary_projection_migration") else None

    from backend.research_pipeline.dossier.reading import build_reading_guide
    reading_guide = build_reading_guide(canonical_dossier)
    return {
        "run_id": run_id,
        # Il dossier vero, non la preview che lo contiene: annidarlo
        # costringerebbe ogni client a conoscere la forma dello stage.
        "dossier": canonical_dossier,
        "reading_guide": reading_guide,
        "dossier_markdown": render_dossier_markdown(
            canonical_dossier, verified_narrative,
            presentation_mode,
            verification_summary,
        ),
        "legacy_dossier": preview.get("dossier"),
        "candidate_count": (
            (canonical or {}).get("retrieval_summary", {}).get("selected_total")
            if canonical else preview.get("candidate_count")
        ),
        "status": ("PARTIAL" if canonical_dossier.get("publication_integrity", {}).get("reconciliation_status") == "FAIL"
                   and snapshot["status"] == "COMPLETED" else snapshot["status"]),
        "technical_run_status": canonical_dossier.get("technical_run_status") or snapshot["status"],
        "publication_status": canonical_dossier.get("publication_status"),
        # La narrativa e' una vista, e viaggia separata dal dossier canonico.
        # ``narrative`` e' popolata SOLO se il verifier deterministico ha
        # accettato: il client non deve decidere se mostrarla, deve leggere
        # ``presentation_mode``.
        "narrative": verified_narrative,
        # Trace deterministica per candidate: deriva dal dossier canonico e
        # resta disponibile anche se il Narrator è disabilitato o respinto.
        "narrative_trace": narrative_trace,
        # V2 presentation contract: canonical fields are assembled in the
        # backend and generated prose is attached only after verifier PASS.
        "presentation": display_presentation if narrative_publishable else None,
        "presentation_mode": presentation_mode,
        "narrative_verification": verification_summary,
        "model_narrative_verification": verification.get("verification"),
        "narrative_generation_origin": "DETERMINISTIC_FALLBACK" if deterministic else (verified_narrative or {}).get("generation_origin"),
        "research_notice": PipelineRun.research_notice(),
    }


#: Esiti di validazione che ancorano una candidate a un documento. Solo questi
#: rendono ``document_grounded`` vero: un'astensione o un rigetto lasciano la
#: candidate al livello del grafo.
_ACCEPTED_OUTCOMES = ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING",
                      "ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY",
                      "ENRICHMENT_V3_ACCEPTED")


def _reader_validation_link(call, validations, calls, selected_papers=()):
    """Match observation-level provenance, never borrow a paper's acceptance.

    Older ledgers lack bindings: accept a historical linkage only when there
    is exactly one call and one validation for that candidate/document pair.
    Ambiguity is a presentation limitation, not a new scientific rejection.
    """
    observation = call.get("enrichment") or {}
    quote = observation.get("quote") or observation.get("author_claim_quote") or ""
    quote_hash = hashlib.sha256(str(quote).encode("utf-8")).hexdigest()
    paper = call.get("paper_id")
    unit = observation.get("source_unit_id")
    if not paper:
        return None, "PROVENANCE_LINKAGE_UNRESOLVED"
    aliases = {paper}
    for selected in selected_papers:
        identities = {selected.get(k) for k in ("bundle_id", "document_id", "requested_document_id")}
        if paper and paper in identities:
            aliases.update(identity for identity in identities if identity)
    related = [v for v in validations if (v.get("document_id") or v.get("paper_id")) in aliases]
    related_calls = [c for c in calls if c.get("paper_id") in aliases]
    matched = [v for v in related if v.get("source_unit_id") == unit
               and v.get("quote_hash") == quote_hash]
    if len(matched) == 1:
        return matched[0], "EXACT_SOURCE_UNIT_AND_QUOTE_HASH"
    if len(related) == len(related_calls) == 1:
        legacy = related[0]
        if legacy.get("quote_hash") is None and legacy.get("source_unit_id") in (None, unit):
            return legacy, "LEGACY_UNIQUE_CALL_AND_VALIDATION"
    return None, "PROVENANCE_LINKAGE_UNRESOLVED"


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
        selection = selections.get(candidate_id, {})

        # Una quote entra in catena solo se la sua validazione è passata. Le
        # altre restano visibili per audit, in un campo distinto.
        accepted_quotes, rejected_quotes, abstentions = [], [], []
        for call in calls:
            enrichment = call.get("enrichment") or {}
            proposed_quote = enrichment.get("quote") or enrichment.get("author_claim_quote")
            linked_validation, linkage_basis = _reader_validation_link(
                call, candidate_validations, calls, selection.get("selected_papers") or [])
            entry = {
                "paper_id": call.get("paper_id"),
                "source_unit_id": enrichment.get("source_unit_id"),
                "author_claim_quote": proposed_quote,
                "author_context_summary": enrichment.get("author_context_summary"),
                "abstention_reason": enrichment.get("abstain_reason") or enrichment.get("abstention_reason"),
                "model": call.get("model"),
                "prompt_version": call.get("prompt_version"),
                "transport_version": call.get("transport_version"),
                "replayed": call.get("replayed", False),
                "provenance_linkage_basis": linkage_basis,
                "validation_outcome": (linked_validation or {}).get("outcome"),
            }
            if enrichment.get("decision") == "ABSTAIN" or not proposed_quote:
                abstentions.append(entry)
            elif linked_validation and linked_validation.get("outcome") in _ACCEPTED_OUTCOMES:
                accepted_quotes.append(entry)
            else:
                rejected_quotes.append(entry)

        document_grounded = bool(accepted_quotes)

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

    accepted = [v for v in validations if str(v.get("outcome", "")).endswith("ACCEPTED")]
    return {
        "run_id": run_id,
        **operational_summary(snapshot),
        "reused_reader_responses": sum(bool(c.get("reader_response_reused")) for c in calls),
        "candidates_found": len(retrieval.get("associations", [])),
        "candidates_excluded": len(retrieval.get("excluded_candidates", [])),
        "quotes_accepted": len(accepted),
        "quotes_rejected": len([v for v in validations if v.get("outcome") == "QUOTE_INVALID"
                                or str(v.get("outcome", "")).startswith("REJECTED")]),
        "abstentions": len([v for v in validations if "ABSTAINED" in str(v.get("outcome", ""))]),
        "warnings": sum(len(s["warnings"]) for s in stages),
        "errors": sum(len(s["errors"]) for s in stages),
        "status_counts": {s: sum(1 for e in statuses if e["status"] == s)
                          for s in {e["status"] for e in statuses}},
        "computed_by": "backend",
    }


@router.get("/runs/{run_id}/stream")
def stream_run(run_id: str, request: Request, compact: bool = False) -> StreamingResponse:
    """Stream SSE degli eventi della run.

    ``id`` è la ``sequence`` del ledger, monotona per run: ``Last-Event-ID`` è
    quindi utilizzabile direttamente per il resume, senza mappature.
    """
    _guard()
    store = get_store()
    if not store.has_run(run_id):
        raise HTTPException(status_code=404, detail="run non trovata")
    last_event_id = request.headers.get("last-event-id")
    try:
        after = max(0, int(last_event_id)) if last_event_id else 0
    except ValueError:
        after = 0

    def generate() -> Iterator[str]:
        cursor = after
        last_beat = time.monotonic()
        deadline = time.monotonic() + STREAM_IDLE_TIMEOUT_SECONDS

        while True:
            finished_before_read = not store.is_running(run_id)
            page = store.events_page(run_id, after_sequence=cursor, limit=STREAM_EVENT_PAGE_SIZE)
            rows = page["events"]
            for event in rows:
                cursor = int(event["sequence"])
                public = _public_event(event, compact=compact)
                yield f"id: {cursor}\nevent: {public['event_type']}\ndata: {json.dumps(public, default=str)}\n\n"
                last_beat = time.monotonic()
                deadline = last_beat + STREAM_IDLE_TIMEOUT_SECONDS

            # Drain persisted pages without poll delays, including historical
            # runs that have no active worker after a backend restart.
            if page["has_more"]:
                continue
            finished = not store.is_running(run_id)
            if finished and not rows:
                if not finished_before_read:
                    # A worker may append its terminal event between the SQL
                    # read and completion check. Read once after completion.
                    continue
                # La run e' conclusa e non restano eventi da inviare: lo stream
                # si chiude invece di restare aperto inutilmente. Vale anche per
                # gli esiti STOPPED e FAILED, che sono conclusioni, non guasti
                # del trasporto.
                break
            if finished and rows:
                continue
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
