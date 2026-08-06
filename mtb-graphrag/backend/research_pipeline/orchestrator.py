"""Orchestratore osservabile del research runtime.

Rapporto con ``pipeline.run_case``: quella funzione resta l'**implementazione di
riferimento** della pipeline e non viene modificata. Qui si ricostruisce la sola
*sequenza*, emettendo un evento per ogni transizione, ma ogni **decisione** è
delegata agli stessi moduli promossi — ``match_verifier``, ``kg_retrieval``,
``paper_selection``, ``enricher_v2``, ``validator``, ``gates``, ``builder``.

La distinzione è ciò che rende la promozione verificabile: se l'orchestratore
contenesse logica decisionale propria, un suo difetto sarebbe indistinguibile da
un cambiamento di comportamento della pipeline. Un test confronta i due percorsi
sugli stessi input.

Nessun calcolo di status, gate, bucket o score avviene in questo modulo.

**Modalità di esecuzione.** Ogni stage dichiara la propria ``artifact_origin``, e
la modalità della run è derivata da quelle: vedi ``execution_mode.py``. Gli stage
6 e 7 marcavano ``replayed: true`` in modo incondizionato, anche quando la cache
era disponibile e la risoluzione sarebbe stata possibile; ora la risoluzione
avviene davvero, oppure la run fallisce dicendo perché. In nessun punto un
fallimento LIVE viene sostituito da un artefatto registrato.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import events as ev
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline.casecontext import match_verifier as verifier
from backend.research_pipeline.contracts import (
    NOT_IMPLEMENTED_STAGE_IDS,
    STAGE_SEQUENCE,
    PipelineRun,
    PipelineStage,
    StageProducer,
    stage_type_for,
)
from backend.research_pipeline.determinism import check_origin
from backend.research_pipeline.determinism import gates as detpipe
from backend.research_pipeline.documents.live_resolution import DocumentRuntime
from backend.research_pipeline.dossier import builder as dossier_mod
from backend.research_pipeline.enrichment import validator as enrichment_validator
from backend.research_pipeline.live_providers import LiveStageFailed
from backend.research_pipeline.redaction import redact_retrieval_result
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod
from backend.research_pipeline.retrieval.paper_selection import select_papers_for_association

#: Esiti che il validatore v1 considera accettati. ``gates.evaluate_association``
#: filtra su questi nomi.
_V1_ACCEPTED = ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING")

#: Esiti che il validatore v2 considera accettati, secondo la definizione data
#: dal pilot stesso in ``run_pilot_v2.py`` riga 83.
_V2_ACCEPTED = ("ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")


def _accepted_for_gates(outcome: str) -> str | None:
    """Traduce un esito di validazione nel vocabolario atteso dai gate.

    Il pilot non ha mai collegato l'enricher v2 ai gate: ``run_pilot_v2.py`` usa
    i suoi esiti solo per i controlli di sicurezza, mentre la catena completa fino
    ai gate fu percorsa dalla v1. Collegarli è quindi un'integrazione nuova, e
    l'adattamento vive **qui**, al confine, non dentro
    ``gates.evaluate_association``: la regola di decisione resta quella del pilot,
    invariata e verificabile.

    Restituisce ``None`` per ogni esito non accettato — astensioni e rigetti
    inclusi — così un enrichment non validato non può in nessun caso influenzare
    status, mask, gate o bucket.
    """
    if outcome in _V1_ACCEPTED:
        return outcome
    if outcome in _V2_ACCEPTED:
        return "ENRICHMENT_ACCEPTED_WITH_WARNING" if outcome.endswith("SUMMARY_EMPTY") else "ENRICHMENT_ACCEPTED"
    return None


CASECONTEXT_VERSION = "end-to-end-pilot-casecontext/1.0"
DOSSIER_VERSION = "end-to-end-pilot-dossier/1.0"
ORCHESTRATOR_VERSION = "research-pipeline-orchestrator/2.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deterministic(component: str, version: str = ORCHESTRATOR_VERSION) -> StageProducer:
    return StageProducer(kind="DETERMINISTIC", component=component, version=version)


class RunRecorder:
    """Accumula gli stage e scrive gli eventi sul ledger append-only.

    Il ledger è la fonte di verità; ``PipelineRun`` è una proiezione comoda per
    l'API. Le due non devono divergere, quindi ogni transizione passa di qui.
    """

    def __init__(self, ledger: EventLedger, run_id: str, execution_mode: str) -> None:
        self._ledger = ledger
        self._run_id = run_id
        self._mode = execution_mode
        self._stages: list[PipelineStage] = []
        self._started: dict[str, float] = {}

    @property
    def stages(self) -> tuple[PipelineStage, ...]:
        return tuple(self._stages)

    @property
    def origins(self) -> tuple[str, ...]:
        return tuple(stage.artifact_origin for stage in self._stages)

    def _stage_mode(self, origin: str) -> str:
        """Modalità dichiarabile da uno stage con questa origine.

        Uno stage che rigioca un artefatto registrato non può dichiararsi LIVE —
        il contratto lo rifiuterebbe. Marcarlo ``REPLAY`` anche dentro una run
        avviata LIVE è ciò che poi rende la run ``HYBRID`` invece che ``LIVE``.
        """
        if origin == em.RECORDED_REAL_RUN:
            return em.REPLAY
        return self._mode

    def _emit(self, event_type: str, payload: Mapping[str, Any], producer: StageProducer) -> None:
        self._ledger.append(
            self._run_id,
            event_type,
            producer.component,
            dict(payload),
            tool_name=producer.component,
            tool_version=producer.version,
        )

    def run_created(self, case_id: str, clinical_text: str, cache: Mapping[str, Any]) -> None:
        # ``input_text`` è il testo sintetico del caso, troncato come nella run:
        # senza di esso una run reidratata dal ledger non potrebbe mostrare da
        # quale domanda è partita.
        self._emit(
            ev.RUN_CREATED,
            {"case_id": case_id, "input_chars": len(clinical_text),
             "input_text": clinical_text[:600],
             "requested_execution_mode": self._mode,
             "document_cache": dict(cache),
             "research_notice": PipelineRun.research_notice()},
            _deterministic("orchestrator"),
        )

    def start(self, stage_id: str, producer: StageProducer, **preview: Any) -> None:
        self._started[stage_id] = time.monotonic()
        self._emit(
            ev.STAGE_STARTED,
            ev.stage_payload(stage_id=stage_id, stage_type=stage_type_for(stage_id),
                             producer=producer, execution_mode=self._mode, **preview),
            producer,
        )

    def finish(
        self,
        stage_id: str,
        producer: StageProducer,
        *,
        status: str = "SUCCEEDED",
        artifact_origin: str = em.GENERATED_NOW,
        domain_event: str | None = None,
        output_preview: Mapping[str, Any] | None = None,
        reason_codes: tuple[str, ...] = (),
        warnings: tuple[str, ...] = (),
        errors: tuple[str, ...] = (),
        metrics: Mapping[str, Any] | None = None,
        lineage: Mapping[str, Any] | None = None,
    ) -> PipelineStage:
        started = self._started.pop(stage_id, None)
        duration_ms = int((time.monotonic() - started) * 1000) if started is not None else None
        preview = dict(output_preview or {})
        em.assert_origin(artifact_origin)
        stage_mode = self._stage_mode(artifact_origin)

        if domain_event is not None:
            self._emit(
                domain_event,
                ev.stage_payload(stage_id=stage_id, stage_type=stage_type_for(stage_id),
                                 producer=producer, execution_mode=stage_mode,
                                 artifact_origin=artifact_origin, **preview),
                producer,
            )

        event_type = {
            "SUCCEEDED": ev.STAGE_COMPLETED, "WARNING": ev.STAGE_WARNING,
            "FAILED": ev.STAGE_FAILED, "SKIPPED": ev.STAGE_SKIPPED,
        }[status]
        # Warning, errori, metriche e lineage viaggiano nell'evento di chiusura:
        # è da questo che ``rehydration`` ricostruisce lo stage dopo un riavvio,
        # e ciò che non è nell'evento non sopravvive al processo.
        self._emit(
            event_type,
            ev.stage_payload(stage_id=stage_id, stage_type=stage_type_for(stage_id),
                             producer=producer, status=status,
                             execution_mode=stage_mode, artifact_origin=artifact_origin,
                             reason_codes=list(reason_codes), duration_ms=duration_ms,
                             warnings=list(warnings), errors=list(errors),
                             metrics=dict(metrics or {}), lineage=dict(lineage or {}),
                             sequence=STAGE_SEQUENCE.index(stage_id) + 1),
            producer,
        )

        stage = PipelineStage(
            stage_id=stage_id, stage_type=stage_type_for(stage_id),
            sequence=STAGE_SEQUENCE.index(stage_id) + 1, status=status,
            producer=producer, completed_at=_now(), duration_ms=duration_ms,
            output_preview=preview, reason_codes=reason_codes,
            warnings=warnings, errors=errors,
            metrics=dict(metrics or {}), lineage=dict(lineage or {}),
            execution_mode=stage_mode, artifact_origin=artifact_origin,
        )
        self._stages.append(stage)
        return stage

    def skip_remaining(self, reason: str) -> None:
        """Marca SKIPPED ogni stage non ancora eseguito, con il motivo a monte.

        Uno stage saltato senza spiegazione sarebbe indistinguibile da un
        difetto dell'orchestratore.
        """
        done = {stage.stage_id for stage in self._stages}
        producer = _deterministic("orchestrator")
        for stage_id in STAGE_SEQUENCE:
            if stage_id in done:
                continue
            code = "NOT_IMPLEMENTED" if stage_id in NOT_IMPLEMENTED_STAGE_IDS else reason
            origin = em.NOT_APPLICABLE if stage_id in NOT_IMPLEMENTED_STAGE_IDS else em.NOT_EXECUTED
            self.finish(stage_id, producer, status="SKIPPED",
                        artifact_origin=origin, reason_codes=(code,))

    def run_completed(self, status: str, stopped_at: str | None) -> None:
        self._emit(
            ev.RUN_COMPLETED,
            {"status": status, "stopped_at": stopped_at, "stage_count": len(self._stages),
             **em.summarize(self._mode, self.origins)},
            _deterministic("orchestrator"),
        )


def run_case(
    *,
    case_id: str,
    clinical_text: str,
    call_parser_fn: Callable[..., dict[str, Any]],
    call_enricher_fn: Callable[..., dict[str, Any]],
    source_units_by_id: Mapping[str, dict[str, Any]],
    budget: Any,
    ledger: EventLedger,
    run_id: str | None = None,
    select_papers_fn: Callable[..., dict[str, Any]] | None = None,
    validate_fn: Callable[..., dict[str, Any]] | None = None,
    execution_mode: str = em.LIVE,
    document_runtime: DocumentRuntime | None = None,
) -> PipelineRun:
    """Esegue un caso emettendo un evento per ogni transizione di stage.

    ``execution_mode`` è un **input obbligatorio nel significato**, non una
    deduzione: il runtime precedente sceglieva replay quando esistevano artefatti
    congelati per il caso, e quella scelta implicita era il fallback silenzioso.

    ``document_runtime`` è la cache aperta in sola lettura. In modalità LIVE è
    obbligatorio: senza, gli stage 6-7 non possono essere eseguiti e la run
    fallisce con ``DOCUMENT_CACHE_UNAVAILABLE`` invece di rigiocare artefatti.

    ``select_papers_fn`` e ``validate_fn`` restano punti di iniezione per il
    replay esplicito. I default eseguono la logica reale.
    """
    select_papers = select_papers_fn or (
        lambda association, units, **_: select_papers_for_association(association, units)
    )
    validate = validate_fn or (
        lambda transport, enrichment, **kw: enrichment_validator.validate_enrichment(
            transport, enrichment,
            candidate=kw["candidate"], paper_bundle=kw["paper_bundle"],
            source_units_by_id=kw["source_units_by_id"], requested_drug=kw["requested_drug"],
        )
    )
    is_live = execution_mode == em.LIVE
    #: Origine degli stage il cui risultato arriva da un artefatto registrato.
    #: In LIVE non esistono: ogni stage o viene eseguito o fallisce.
    replay_origin = em.RECORDED_REAL_RUN if not is_live else em.GENERATED_NOW

    run_id = run_id or str(uuid4())
    cache_descriptor = dict(document_runtime.descriptor) if document_runtime else {
        "document_cache_available": False,
    }
    recorder = RunRecorder(ledger, run_id, execution_mode)
    started_at = _now()
    recorder.run_created(case_id, clinical_text, cache_descriptor)
    llm_calls = 0

    def _finalize(status: str, stopped_at: str | None, **extra: Any) -> PipelineRun:
        if stopped_at is not None:
            recorder.skip_remaining(stopped_at)
        else:
            recorder.skip_remaining("NOT_IMPLEMENTED")
        recorder.run_completed(status, stopped_at)
        return PipelineRun(
            run_id=run_id, case_id=case_id, status=status, started_at=started_at,
            completed_at=_now(), input_text=clinical_text[:600], stopped_at=stopped_at,
            stages=recorder.stages,
            versions={"casecontext_schema": CASECONTEXT_VERSION,
                      "dossier": DOSSIER_VERSION,
                      "orchestrator": ORCHESTRATOR_VERSION},
            requested_mode=execution_mode,
            document_cache=cache_descriptor,
            llm_calls=llm_calls,
            **extra,
        )

    # STAGE 1 — Case input
    p = _deterministic("case_input")
    recorder.start("stage_1_case_input", p)
    recorder.finish("stage_1_case_input", p,
                    output_preview={"case_id": case_id, "input_chars": len(clinical_text)})

    # STAGE 2 — CaseContext Parser (LLM)
    try:
        parser_result = call_parser_fn(budget, case_id, clinical_text)
    except LiveStageFailed as failure:
        p = _deterministic("casecontext_parser", CASECONTEXT_VERSION)
        recorder.start("stage_2_casecontext_parser", p)
        recorder.finish("stage_2_casecontext_parser", p, status="FAILED",
                        artifact_origin=em.NOT_EXECUTED,
                        reason_codes=(failure.reason_code,), errors=(failure.detail,))
        return _finalize("FAILED", "LIVE_STAGE_FAILED")
    if is_live:
        llm_calls += 1

    parser_producer = StageProducer(
        kind="LLM", component="casecontext_parser", version=CASECONTEXT_VERSION,
        model=parser_result.get("model") or "unknown",
        prompt_version=parser_result.get("prompt_version") or CASECONTEXT_VERSION,
    )
    recorder.start("stage_2_casecontext_parser", parser_producer)
    transport = parser_result.get("transport_result")
    if transport != "FORCED_TOOL_VALID":
        recorder.finish("stage_2_casecontext_parser", parser_producer, status="FAILED",
                        artifact_origin=replay_origin,
                        reason_codes=("PARSER_TRANSPORT_FAILED",),
                        errors=(str(transport),),
                        output_preview={"transport_result": transport})
        return _finalize("FAILED", "PARSER_TRANSPORT_FAILED")

    case_context = parser_result["case_context_raw"]
    recorder.finish("stage_2_casecontext_parser", parser_producer,
                    artifact_origin=replay_origin,
                    domain_event=ev.CASECONTEXT_PARSED,
                    output_preview={"transport_result": transport,
                                    "query_intent": case_context.get("query_intent"),
                                    "case_context": case_context},
                    metrics={"latency_ms": parser_result.get("latency_ms"),
                             "input_tokens": parser_result.get("input_tokens"),
                             "output_tokens": parser_result.get("output_tokens"),
                             "retry_count": parser_result.get("retry_count")})

    # STAGE 3 — Match verifier (deterministico)
    p = _deterministic("casecontext_match_verifier", CASECONTEXT_VERSION)
    recorder.start("stage_3_casecontext_match", p)
    records = verifier.verify_case_context(case_context, clinical_text)
    essential_ok, match_warnings = verifier.essential_fields_pass(records)
    preview = {"records": [r.to_dict() for r in records],
               "essential_fields_pass": essential_ok,
               "warnings": list(match_warnings)}
    if not essential_ok:
        recorder.finish("stage_3_casecontext_match", p, status="WARNING",
                        domain_event=ev.CASECONTEXT_VERIFIED,
                        reason_codes=("CASECONTEXT_MISMATCH",),
                        warnings=tuple(match_warnings), output_preview=preview)
        return _finalize("STOPPED", "CASECONTEXT_MISMATCH")
    recorder.finish("stage_3_casecontext_match", p, domain_event=ev.CASECONTEXT_VERIFIED,
                    warnings=tuple(match_warnings), output_preview=preview)

    # STAGE 4-5 — Piano di retrieval e interrogazione del grafo
    p = _deterministic("retrieval_plan")
    recorder.start("stage_4_retrieval_plan", p)
    recorder.finish("stage_4_retrieval_plan", p, domain_event=ev.RETRIEVAL_COMPLETED,
                    output_preview={
                        "query_intent": case_context.get("query_intent"),
                        "disease": (case_context.get("disease") or {}).get("normalized_value"),
                        "biomarkers": [b.get("normalized_value") for b in case_context.get("biomarkers") or []],
                        "target_intervention": (case_context.get("target_intervention") or {}).get("normalized_value"),
                        "repository": "graph_candidate_repository/2.0",
                        "planner": "DETERMINISTIC_NOT_LLM",
                    })

    p = _deterministic("kg_retrieval")
    recorder.start("stage_5_kg_retrieval", p)
    retrieval_result = retrieval_mod.retrieve(case_context)
    redacted = redact_retrieval_result(retrieval_result)
    retrieval_preview = {
        "graph_derived": True,
        "documentary_proof": False,
        "associations": redacted["associations"],
        "excluded_candidates": redacted["excluded_candidates"],
        "no_match": retrieval_result["no_match"],
    }
    if retrieval_result["no_match"]:
        recorder.finish("stage_5_kg_retrieval", p, status="WARNING",
                        domain_event=ev.CANDIDATES_FOUND,
                        reason_codes=("RETRIEVAL_NO_MATCH",), output_preview=retrieval_preview)
        return _finalize("STOPPED", "RETRIEVAL_NO_MATCH")
    recorder.finish("stage_5_kg_retrieval", p, domain_event=ev.CANDIDATES_FOUND,
                    output_preview=retrieval_preview)

    # STAGE 6 — Document Resolution
    #
    # Eseguita davvero: i documenti vengono cercati nella cache autorizzata al
    # momento della run. Nessun fetch di rete — la cache è aperta in sola lettura
    # e i suoi percorsi di rete sollevano. Un documento assente resta
    # DOCUMENT_UNAVAILABLE: il corrispondente artefatto registrato non viene
    # usato al suo posto.
    p = _deterministic("document_resolution")
    recorder.start("stage_6_document_resolution", p)

    if is_live and document_runtime is None:
        recorder.finish("stage_6_document_resolution", p, status="FAILED",
                        artifact_origin=em.NOT_EXECUTED,
                        reason_codes=("DOCUMENT_CACHE_UNAVAILABLE",),
                        errors=("cache documentale non disponibile: la run LIVE non "
                                "ripiega su artefatti registrati",),
                        output_preview=dict(cache_descriptor))
        return _finalize("FAILED", "DOCUMENT_CACHE_UNAVAILABLE")

    if document_runtime is not None:
        resolution = document_runtime.resolve(retrieval_result["associations"])
        resolution_preview = {**resolution.to_preview(), **cache_descriptor}
        resolved_any = any(doc.resolved for doc in resolution.documents)
        if is_live and not resolved_any:
            recorder.finish("stage_6_document_resolution", p, status="FAILED",
                            artifact_origin=em.DETERMINISTIC_CACHE,
                            reason_codes=("NO_DOCUMENT_RESOLVED", "DOCUMENT_UNAVAILABLE"),
                            output_preview=resolution_preview)
            return _finalize("FAILED", "NO_DOCUMENT_RESOLVED")
        unavailable = tuple(
            f"DOCUMENT_UNAVAILABLE:{doc.document_id}"
            for doc in resolution.documents if not doc.resolved
        )
        recorder.finish("stage_6_document_resolution", p,
                        status="WARNING" if unavailable else "SUCCEEDED",
                        artifact_origin=em.DETERMINISTIC_CACHE,
                        domain_event=ev.DOCUMENT_RESOLVED,
                        warnings=unavailable,
                        reason_codes=("DOCUMENT_RESOLVED_FROM_CACHE",) if not unavailable
                                     else ("DOCUMENT_RESOLVED_FROM_CACHE", "DOCUMENT_UNAVAILABLE"),
                        output_preview=resolution_preview,
                        metrics={"cache_hits": resolution.cache_hits,
                                 "cache_misses": resolution.cache_misses},
                        lineage={"manifest_hash": resolution.manifest_hash})
    else:
        # Solo REPLAY: i documenti sono quelli già citati dai bundle congelati.
        documents = [
            {"document_id": bundle["document_id"], "bundle_id": bundle["bundle_id"]}
            for association in retrieval_result["associations"]
            for bundle in association["available_bundles"]
        ]
        resolution = None
        recorder.finish("stage_6_document_resolution", p,
                        artifact_origin=em.RECORDED_REAL_RUN,
                        domain_event=ev.DOCUMENT_RESOLVED,
                        reason_codes=("DOCUMENT_FROM_RECORDED_RUN",),
                        output_preview={"documents": documents,
                                        "note": "artefatto registrato: nessuna cache consultata"})

    # STAGE 7 — SourceUnit
    #
    # Le unità con testo restano nel backend: il preview porta locatore, hash,
    # tipo e un estratto troncato. È la stessa distinzione che ``live_resolution``
    # tiene nella struttura dati, non al momento della serializzazione.
    p = _deterministic("source_units")
    recorder.start("stage_7_source_units", p)
    requested_unit_ids = sorted({
        uid for association in retrieval_result["associations"]
        for bundle in association["available_bundles"]
        for uid in bundle.get("source_unit_ids", [])
    })

    if document_runtime is not None and resolution is not None:
        bundle_units = document_runtime.load_units(resolution)
        units_for_decisions: Mapping[str, dict[str, Any]] = bundle_units.units_by_id
        units_preview = bundle_units.to_preview(requested_unit_ids)
        with_text = sum(
            1 for uid in requested_unit_ids
            if (bundle_units.units_by_id.get(uid, {}).get("text") or "").strip()
        )
        recorder.finish("stage_7_source_units", p,
                        status="SUCCEEDED" if with_text else "WARNING",
                        artifact_origin=em.DETERMINISTIC_CACHE,
                        domain_event=ev.SOURCE_UNIT_MATERIALIZED,
                        reason_codes=("SOURCE_UNITS_MATERIALIZED_FROM_CACHE",) if with_text
                                     else ("SOURCE_UNIT_TEXT_UNAVAILABLE",),
                        output_preview=units_preview,
                        metrics={"requested": len(requested_unit_ids),
                                 "with_exact_text": with_text,
                                 "parsed_documents": bundle_units.documents_parsed})
    else:
        units_for_decisions = dict(source_units_by_id)
        # Solo locatori e hash: il testo non lascia mai l'enricher.
        recorded_preview = [
            {k: v for k, v in (source_units_by_id.get(uid) or {}).items()
             if k not in {"text", "content", "body"}} or {"source_unit_id": uid}
            for uid in requested_unit_ids
        ]
        recorder.finish("stage_7_source_units", p,
                        artifact_origin=em.RECORDED_REAL_RUN,
                        domain_event=ev.SOURCE_UNIT_MATERIALIZED,
                        reason_codes=("SOURCE_UNITS_FROM_RECORDED_INDEX",),
                        output_preview={"source_units": recorded_preview,
                                        "note": "indice congelato: nessun testo ricostruito"})

    # STAGE 8-12 — Per associazione: selezione, enrichment, validazione, gate, status
    candidate_therapies: list[dict[str, Any]] = []
    selections, enrichment_calls, validations, evaluations = [], [], [], []

    for association in retrieval_result["associations"]:
        selection = select_papers(association, dict(units_for_decisions), case_id=case_id)
        selections.append(selection)
        candidate = association["candidate"]

        enrichment_entries, validation_entries, validated = [], [], []
        for paper in selection["selected_papers"]:
            interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
            requested_drug = (
                (case_context.get("target_intervention") or {}).get("normalized_value")
                or (interventions[0] if interventions else "")
            )
            paper_units = [units_for_decisions[uid] for uid in paper["resolved_source_unit_ids"]
                           if uid in units_for_decisions]

            try:
                call = call_enricher_fn(
                    budget, case_id, candidate["candidate_id"], paper["bundle_id"], case_context,
                    {"candidate_id": candidate["candidate_id"], "disease": candidate.get("disease"),
                     "biomarkers": candidate.get("biomarkers")},
                    requested_drug, paper_units,
                )
            except LiveStageFailed as failure:
                enricher_producer = StageProducer(
                    kind="LLM", component="paper_context_enricher_v2",
                    version="paper-context-enricher/2.0",
                    model="gemma4:cloud", prompt_version="paper-context-enricher-prompt/2.0",
                )
                recorder.start("stage_8_paper_selection", _deterministic("paper_selection"))
                recorder.finish("stage_8_paper_selection", _deterministic("paper_selection"),
                                domain_event=ev.PAPER_SELECTED,
                                output_preview={"selections": selections,
                                                "max_papers_per_association": 2})
                recorder.start("stage_9_paper_context_enricher", enricher_producer)
                recorder.finish("stage_9_paper_context_enricher", enricher_producer,
                                status="FAILED", artifact_origin=em.NOT_EXECUTED,
                                reason_codes=(failure.reason_code,), errors=(failure.detail,),
                                output_preview={"calls": enrichment_calls,
                                                "failed_paper_id": paper["bundle_id"]})
                return _finalize("FAILED", "LIVE_STAGE_FAILED")
            if is_live:
                llm_calls += 1
            enrichment_calls.append(call)

            validation = validate(
                call["transport_result"], call["enrichment"], candidate=candidate,
                paper_bundle=paper, source_units_by_id=dict(units_for_decisions),
                requested_drug=requested_drug, case_id=case_id,
                paper_id=paper["bundle_id"],
            )
            validations.append({"candidate_id": candidate["candidate_id"],
                                "paper_id": paper["bundle_id"], **validation})
            validation_entries.append({"paper_id": paper["bundle_id"], **validation})
            if call["enrichment"] is not None:
                enrichment_entries.append(call["enrichment"])
            gate_outcome = _accepted_for_gates(validation["outcome"])
            if gate_outcome is not None:
                validated.append({"validation_outcome": gate_outcome,
                                  "enrichment": call["enrichment"],
                                  "original_outcome": validation["outcome"]})

        evaluation = detpipe.evaluate_association(
            case_context.get("query_intent"), candidate, validated)
        evaluations.append({"candidate_id": candidate["candidate_id"], **evaluation})
        candidate_therapies.append(dossier_mod.build_candidate_therapy_entry(
            candidate, graph_relation=candidate.get("predicate", ""),
            document_support={"selected_papers": [pp["bundle_id"] for pp in selection["selected_papers"]],
                              "excluded_papers": selection["excluded_papers"]},
            enrichments=enrichment_entries, validation_results=validation_entries,
            evaluation=evaluation,
        ))

    p = _deterministic("paper_selection")
    recorder.start("stage_8_paper_selection", p)
    recorder.finish("stage_8_paper_selection", p,
                    artifact_origin=em.GENERATED_NOW if select_papers_fn is None else replay_origin,
                    domain_event=ev.PAPER_SELECTED,
                    output_preview={"selections": selections,
                                    "max_papers_per_association": 2,
                                    "max_source_units_per_paper": 4,
                                    "recomputed_during_run": select_papers_fn is None})

    enricher_producer = StageProducer(
        kind="LLM", component="paper_context_enricher_v2",
        version="paper-context-enricher/2.0",
        model=(enrichment_calls[0].get("model") if enrichment_calls else None) or "unknown",
        prompt_version=(enrichment_calls[0].get("prompt_version") if enrichment_calls else None) or "unknown",
        transport_version=(enrichment_calls[0].get("transport_version") if enrichment_calls else None),
    )
    recorder.start("stage_9_paper_context_enricher", enricher_producer)
    recorder.finish("stage_9_paper_context_enricher", enricher_producer,
                    artifact_origin=(em.NOT_APPLICABLE if not enrichment_calls else replay_origin),
                    domain_event=ev.ENRICHMENT_PROPOSED,
                    reason_codes=() if enrichment_calls else ("NO_PAPER_SELECTED_FOR_ENRICHMENT",),
                    output_preview={"calls": [
                        {k: v for k, v in call.items() if k != "raw_response"}
                        for call in enrichment_calls]},
                    metrics={"llm_calls": len(enrichment_calls),
                             "retries": sum(int(c.get("retry_count") or 0) for c in enrichment_calls)})

    p = _deterministic("enrichment_validator")
    recorder.start("stage_10_enrichment_validation", p)
    recorder.finish("stage_10_enrichment_validation", p,
                    artifact_origin=(em.NOT_APPLICABLE if not validations else
                                     em.GENERATED_NOW if validate_fn is None else replay_origin),
                    domain_event=ev.ENRICHMENT_VALIDATED,
                    output_preview={
                        "validations": validations,
                        "accepted_outcomes": list(_V1_ACCEPTED + _V2_ACCEPTED),
                        "revalidated_during_run": validate_fn is None,
                        "gate_admission_note": (
                            "solo gli esiti accettati raggiungono i gate; astensioni e "
                            "rigetti non influenzano status, mask, bucket o score"
                        ),
                    })

    p = _deterministic("deterministic_gates")
    recorder.start("stage_11_deterministic_gates", p)
    # Ogni asse porta la propria origine. Una support mask nuda mostrerebbe
    # quattro esiti indistinguibili, mentre solo due sono decisi qui: vedi
    # ``determinism/check_origin.py``.
    recorder.finish("stage_11_deterministic_gates", p, domain_event=ev.GATES_COMPUTED,
                    output_preview={
                        "checks_by_candidate": [
                            {"candidate_id": e["candidate_id"],
                             "support_mask": e["support_mask"],
                             "direction_consistencies": e["direction_consistencies"],
                             "checks": check_origin.checks_payload(e["support_mask"])}
                            for e in evaluations
                        ],
                        "check_sources": list(check_origin.CHECK_SOURCES),
                        "checks_version": check_origin.CHECK_VERSION,
                    })

    p = _deterministic("status_classification")
    recorder.start("stage_12_status", p)
    recorder.finish("stage_12_status", p, domain_event=ev.STATUS_ASSIGNED,
                    output_preview={"statuses": [
                        {"candidate_id": e["candidate_id"], "status": e["status"],
                         "gate_bucket": e["gate_bucket"], "warnings": e["warnings"]}
                        for e in evaluations]})

    # STAGE 13 — Dossier
    p = _deterministic("dossier_builder", DOSSIER_VERSION)
    recorder.start("stage_13_dossier", p)
    dossier = dossier_mod.build_dossier_preview(
        case_id, case_context,
        {"records": [r.to_dict() for r in records], "essential_fields_pass": essential_ok,
         "warnings": list(match_warnings)},
        candidate_therapies,
        limitations=["research_only_pilot", "no_new_document_fetched",
                     "gemma_used_only_as_enricher"],
    )
    # Il dossier completo, non solo i conteggi: ``GET /runs/{id}/dossier`` legge
    # questa preview, e senza il contenuto potrebbe soltanto dichiarare quante
    # candidate esistono — non mostrarle. Le tre sezioni che la UI deve tenere
    # separate (evidenza deterministica, author context, limitazioni) sono già
    # distinte nella struttura prodotta da ``build_dossier_preview``.
    recorder.finish("stage_13_dossier", p, domain_event=ev.DOSSIER_BUILT,
                    output_preview={"candidate_count": len(candidate_therapies),
                                    "dossier": dossier,
                                    "limitations": dossier["limitations"]})

    has_warning = any(stage.status == "WARNING" for stage in recorder.stages)
    return _finalize("PARTIAL" if has_warning else "COMPLETED", None, dossier_id=case_id)
