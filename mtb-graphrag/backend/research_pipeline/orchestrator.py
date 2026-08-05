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
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import events as ev
from backend.research_pipeline.casecontext import match_verifier as verifier
from backend.research_pipeline.contracts import (
    NOT_IMPLEMENTED_STAGE_IDS,
    STAGE_SEQUENCE,
    PipelineRun,
    PipelineStage,
    StageProducer,
    stage_type_for,
)
from backend.research_pipeline.determinism import gates as detpipe
from backend.research_pipeline.dossier import builder as dossier_mod
from backend.research_pipeline.enrichment import validator as enrichment_validator
from backend.research_pipeline.redaction import redact_candidate, redact_retrieval_result
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod
from backend.research_pipeline.retrieval.paper_selection import select_papers_for_association

CASECONTEXT_VERSION = "end-to-end-pilot-casecontext/1.0"
DOSSIER_VERSION = "end-to-end-pilot-dossier/1.0"
ORCHESTRATOR_VERSION = "research-pipeline-orchestrator/1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deterministic(component: str, version: str = ORCHESTRATOR_VERSION) -> StageProducer:
    return StageProducer(kind="DETERMINISTIC", component=component, version=version)


class RunRecorder:
    """Accumula gli stage e scrive gli eventi sul ledger append-only.

    Il ledger è la fonte di verità; ``PipelineRun`` è una proiezione comoda per
    l'API. Le due non devono divergere, quindi ogni transizione passa di qui.
    """

    def __init__(self, ledger: EventLedger, run_id: str) -> None:
        self._ledger = ledger
        self._run_id = run_id
        self._stages: list[PipelineStage] = []
        self._started: dict[str, float] = {}

    @property
    def stages(self) -> tuple[PipelineStage, ...]:
        return tuple(self._stages)

    def _emit(self, event_type: str, payload: Mapping[str, Any], producer: StageProducer) -> None:
        self._ledger.append(
            self._run_id,
            event_type,
            producer.component,
            dict(payload),
            tool_name=producer.component,
            tool_version=producer.version,
        )

    def run_created(self, case_id: str, clinical_text: str) -> None:
        self._emit(
            ev.RUN_CREATED,
            {"case_id": case_id, "input_chars": len(clinical_text),
             "research_notice": PipelineRun.research_notice()},
            _deterministic("orchestrator"),
        )

    def start(self, stage_id: str, producer: StageProducer, **preview: Any) -> None:
        self._started[stage_id] = time.monotonic()
        self._emit(
            ev.STAGE_STARTED,
            ev.stage_payload(stage_id=stage_id, stage_type=stage_type_for(stage_id),
                             producer=producer, **preview),
            producer,
        )

    def finish(
        self,
        stage_id: str,
        producer: StageProducer,
        *,
        status: str = "SUCCEEDED",
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

        if domain_event is not None:
            self._emit(
                domain_event,
                ev.stage_payload(stage_id=stage_id, stage_type=stage_type_for(stage_id),
                                 producer=producer, **preview),
                producer,
            )

        event_type = {
            "SUCCEEDED": ev.STAGE_COMPLETED, "WARNING": ev.STAGE_WARNING,
            "FAILED": ev.STAGE_FAILED, "SKIPPED": ev.STAGE_SKIPPED,
        }[status]
        self._emit(
            event_type,
            ev.stage_payload(stage_id=stage_id, stage_type=stage_type_for(stage_id),
                             producer=producer, status=status,
                             reason_codes=list(reason_codes), duration_ms=duration_ms),
            producer,
        )

        stage = PipelineStage(
            stage_id=stage_id, stage_type=stage_type_for(stage_id),
            sequence=STAGE_SEQUENCE.index(stage_id) + 1, status=status,
            producer=producer, completed_at=_now(), duration_ms=duration_ms,
            output_preview=preview, reason_codes=reason_codes,
            warnings=warnings, errors=errors,
            metrics=dict(metrics or {}), lineage=dict(lineage or {}),
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
            self.finish(stage_id, producer, status="SKIPPED", reason_codes=(code,))

    def run_completed(self, status: str, stopped_at: str | None) -> None:
        self._emit(
            ev.RUN_COMPLETED,
            {"status": status, "stopped_at": stopped_at, "stage_count": len(self._stages)},
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
) -> PipelineRun:
    """Esegue un caso emettendo un evento per ogni transizione di stage."""
    run_id = run_id or str(uuid4())
    recorder = RunRecorder(ledger, run_id)
    started_at = _now()
    recorder.run_created(case_id, clinical_text)

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
            **extra,
        )

    # STAGE 1 — Case input
    p = _deterministic("case_input")
    recorder.start("stage_1_case_input", p)
    recorder.finish("stage_1_case_input", p,
                    output_preview={"case_id": case_id, "input_chars": len(clinical_text)})

    # STAGE 2 — CaseContext Parser (LLM)
    parser_result = call_parser_fn(budget, case_id, clinical_text)
    parser_producer = StageProducer(
        kind="LLM", component="casecontext_parser", version=CASECONTEXT_VERSION,
        model=parser_result.get("model") or "unknown",
        prompt_version=parser_result.get("prompt_version") or CASECONTEXT_VERSION,
    )
    recorder.start("stage_2_casecontext_parser", parser_producer)
    transport = parser_result.get("transport_result")
    if transport != "FORCED_TOOL_VALID":
        recorder.finish("stage_2_casecontext_parser", parser_producer, status="FAILED",
                        reason_codes=("PARSER_TRANSPORT_FAILED",),
                        errors=(str(transport),),
                        output_preview={"transport_result": transport})
        return _finalize("FAILED", "PARSER_TRANSPORT_FAILED")

    case_context = parser_result["case_context_raw"]
    recorder.finish("stage_2_casecontext_parser", parser_producer,
                    domain_event=ev.CASECONTEXT_PARSED,
                    output_preview={"transport_result": transport,
                                    "query_intent": case_context.get("query_intent"),
                                    "case_context": case_context})

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

    # STAGE 6-7 — Documenti e SourceUnit: artefatti congelati, non risoluzione live
    replayed = {"replayed": True,
                "note": "artefatto congelato: risolto in una run precedente, non recuperato ora"}
    p = _deterministic("document_resolution")
    recorder.start("stage_6_document_resolution", p)
    documents = [
        {"document_id": bundle["document_id"], "bundle_id": bundle["bundle_id"], **replayed}
        for association in retrieval_result["associations"]
        for bundle in association["available_bundles"]
    ]
    recorder.finish("stage_6_document_resolution", p, domain_event=ev.DOCUMENT_RESOLVED,
                    output_preview={"documents": documents, **replayed})

    p = _deterministic("source_units")
    recorder.start("stage_7_source_units", p)
    unit_ids = sorted({
        uid for association in retrieval_result["associations"]
        for bundle in association["available_bundles"]
        for uid in bundle.get("source_unit_ids", [])
    })
    # Solo locatori e hash: il testo non lascia mai l'enricher.
    units_preview = [
        {k: v for k, v in (source_units_by_id.get(uid) or {}).items()
         if k not in {"text", "content", "body"}} or {"source_unit_id": uid}
        for uid in unit_ids
    ]
    recorder.finish("stage_7_source_units", p, domain_event=ev.SOURCE_UNIT_MATERIALIZED,
                    output_preview={"source_units": units_preview, **replayed})

    # STAGE 8-12 — Per associazione: selezione, enrichment, validazione, gate, status
    candidate_therapies: list[dict[str, Any]] = []
    selections, enrichment_calls, validations, evaluations = [], [], [], []

    for association in retrieval_result["associations"]:
        selection = select_papers_for_association(association, dict(source_units_by_id))
        selections.append(selection)
        candidate = association["candidate"]

        enrichment_entries, validation_entries, validated = [], [], []
        for paper in selection["selected_papers"]:
            interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
            requested_drug = (
                (case_context.get("target_intervention") or {}).get("normalized_value")
                or (interventions[0] if interventions else "")
            )
            paper_units = [source_units_by_id[uid] for uid in paper["resolved_source_unit_ids"]
                           if uid in source_units_by_id]

            call = call_enricher_fn(
                budget, case_id, candidate["candidate_id"], paper["bundle_id"], case_context,
                {"candidate_id": candidate["candidate_id"], "disease": candidate.get("disease"),
                 "biomarkers": candidate.get("biomarkers")},
                requested_drug, paper_units,
            )
            enrichment_calls.append(call)

            validation = enrichment_validator.validate_enrichment(
                call["transport_result"], call["enrichment"], candidate=candidate,
                paper_bundle=paper, source_units_by_id=dict(source_units_by_id),
                requested_drug=requested_drug,
            )
            validations.append(validation)
            validation_entries.append({"paper_id": paper["bundle_id"], **validation})
            if call["enrichment"] is not None:
                enrichment_entries.append(call["enrichment"])
            if validation["outcome"] in ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING"):
                validated.append({"validation_outcome": validation["outcome"],
                                  "enrichment": call["enrichment"]})

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
    recorder.finish("stage_8_paper_selection", p, domain_event=ev.PAPER_SELECTED,
                    output_preview={"selections": selections, "max_papers_per_association": 2})

    enricher_producer = StageProducer(
        kind="LLM", component="paper_context_enricher_v2",
        version="paper-context-enricher/2.0",
        model=(enrichment_calls[0].get("model") if enrichment_calls else None) or "unknown",
        prompt_version=(enrichment_calls[0].get("prompt_version") if enrichment_calls else None) or "unknown",
        transport_version=(enrichment_calls[0].get("transport_version") if enrichment_calls else None),
    )
    recorder.start("stage_9_paper_context_enricher", enricher_producer)
    recorder.finish("stage_9_paper_context_enricher", enricher_producer,
                    domain_event=ev.ENRICHMENT_PROPOSED,
                    output_preview={"calls": [
                        {k: v for k, v in call.items() if k != "raw_response"}
                        for call in enrichment_calls]})

    p = _deterministic("enrichment_validator")
    recorder.start("stage_10_enrichment_validation", p)
    recorder.finish("stage_10_enrichment_validation", p, domain_event=ev.ENRICHMENT_VALIDATED,
                    output_preview={"validations": validations})

    p = _deterministic("deterministic_gates")
    recorder.start("stage_11_deterministic_gates", p)
    recorder.finish("stage_11_deterministic_gates", p, domain_event=ev.GATES_COMPUTED,
                    output_preview={
                        "support_masks": [{"candidate_id": e["candidate_id"],
                                           "support_mask": e["support_mask"],
                                           "direction_consistencies": e["direction_consistencies"]}
                                          for e in evaluations],
                        "inherited_axes": {
                            "disease": "ereditata dal match strutturale — stage_5_kg_retrieval",
                            "biomarker": "ereditata dal match strutturale — stage_5_kg_retrieval",
                        },
                        "not_implemented_gates": [
                            "source_gate", "provenance_gate", "completeness",
                            "negation", "contradiction_gate", "score",
                        ],
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
    recorder.finish("stage_13_dossier", p, domain_event=ev.DOSSIER_BUILT,
                    output_preview={"candidate_count": len(candidate_therapies),
                                    "limitations": dossier["limitations"]})

    has_warning = any(stage.status == "WARNING" for stage in recorder.stages)
    return _finalize("PARTIAL" if has_warning else "COMPLETED", None, dossier_id=case_id)
