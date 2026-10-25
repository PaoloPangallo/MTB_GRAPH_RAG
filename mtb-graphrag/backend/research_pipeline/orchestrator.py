"""Canonical observable runtime: coordinate typed retrieval, document verification and dossier stages.

Historical ``pipeline.run_case`` remains an explicit regression entry point. Canonical
providers and document resolution are selected here; historical adapters require
explicit injection. Recording and post-dossier presentation have dedicated modules.
"""

from __future__ import annotations

import time
import hashlib
from datetime import datetime, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline.recording import RunRecorder
from backend.research_pipeline.operational_metrics import operational_summary
from backend.research_pipeline.narrative.stage_runner import narrate_and_verify as _narrate_and_verify
from backend.research_pipeline import events as ev
from backend.research_pipeline import execution_mode as em
from backend.research_pipeline.data_access import GRAPH_CANDIDATE_REPOSITORY_VERSION
from backend.research_pipeline.casecontext import match_verifier as verifier
from backend.research_pipeline.casecontext import pipeline as cc_pipeline
from backend.research_pipeline.contracts import (
    NOT_IMPLEMENTED_STAGE_IDS,
    STAGE_SEQUENCE,
    PipelineRun,
    RUN_STATUSES,
    PipelineStage,
    StageProducer,
    stage_type_for,
)
from backend.research_pipeline.determinism import check_origin
from backend.research_pipeline.determinism import gates as detpipe
from backend.research_pipeline.redaction import compact_excluded_candidates
from backend.research_pipeline.documents.live_resolution import DocumentResolution, DocumentRuntime
from backend.research_pipeline.documents.trial_resolution import resolve_trial_record, read_trial_structure
from backend.research_pipeline.dossier import builder as dossier_mod
from backend.research_pipeline.dossier.accounting import (
    apply_publication_integrity, build_pipeline_accounting,
)
from backend.research_pipeline.enrichment import validator as enrichment_validator
from backend.research_pipeline.enrichment import prompt_v3
from backend.research_pipeline.enrichment.post_quote_support import assess_candidate_support
from backend.research_pipeline.enrichment.relation_support import assess_relation_support
from backend.research_pipeline.enrichment.document_verification import (
    admit as admit_document_relation, structural_verify,
)
from backend.research_pipeline.enrichment.verification_policy import (
    policy_for, public_artifact,
)
from backend.research_pipeline.enrichment.context_reader import ContextPolicy, read_with_context_policy
from backend.research_pipeline.live_providers import LiveStageFailed
from backend.research_pipeline.narrative import input_projection as narrative_projection
from backend.research_pipeline.narrative import prompt as narrative_prompt
from backend.research_pipeline.narrative import verifier as narrative_verifier
from backend.research_pipeline.narrative import presentation as narrative_presentation
from backend.research_pipeline.redaction import redact_retrieval_result
from backend.research_pipeline.retrieval import kg_retrieval as retrieval_mod
from backend.research_pipeline.retrieval.paper_selection import select_papers_for_association
from backend.research_pipeline.budget import CallBudgetExceeded, run_budget_context
from backend.research_pipeline.retrieval.live_sourceunit_selection import (
    MAX_PAPERS_PER_ASSOCIATION,
    LIVE_RETRIEVAL_STRATEGY,
    select_live_papers_for_association,
)
from backend.research_pipeline.retrieval.relation_family import (
    CLINICAL_TRIAL,
    INVALID_PROVENANCE,
    KG_ONLY,
    PAPER_EVIDENCE,
    classify_relation_family,
)

#: Esiti che il validatore v1 considera accettati. ``gates.evaluate_association``
#: filtra su questi nomi.
_V1_ACCEPTED = ("ENRICHMENT_ACCEPTED", "ENRICHMENT_ACCEPTED_WITH_WARNING")

#: Esiti che il validatore v2 considera accettati, secondo la definizione data
#: dal pilot stesso in ``run_pilot_v2.py`` riga 83.
_V2_ACCEPTED = ("ENRICHMENT_V2_ACCEPTED", "ENRICHMENT_V2_ACCEPTED_SUMMARY_EMPTY")
_V3_ACCEPTED = ("ENRICHMENT_V3_ACCEPTED",)


def _accepted_for_gates(
    outcome: str,
    candidate_support: dict[str, Any] | None,
) -> str | None:
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
    # The relation-aware Reader v3 uses a distinct support vocabulary.  Its
    # highest positive state is ``FULL_SUPPORT``; the legacy gate accepts the
    # equivalent legacy state ``STRONG_SUPPORT``.  Adapt a shallow, ephemeral
    # view here rather than mutating ``candidate_support``: that original object
    # is later projected verbatim into the relation-aware dossier.
    legacy_gate_support = dict(candidate_support) if isinstance(candidate_support, dict) else None
    if legacy_gate_support is not None and legacy_gate_support.get("result") == "FULL_SUPPORT":
        legacy_gate_support["result"] = "STRONG_SUPPORT"

    if legacy_gate_support is None or legacy_gate_support.get("result") != "STRONG_SUPPORT":
        return None
    if outcome in _V1_ACCEPTED:
        return outcome
    if outcome in _V2_ACCEPTED + _V3_ACCEPTED:
        return "ENRICHMENT_ACCEPTED_WITH_WARNING" if outcome.endswith("SUMMARY_EMPTY") else "ENRICHMENT_ACCEPTED"
    return None


def _assess_v3_quoted_relation(
    candidate: dict[str, Any], enrichment: dict[str, Any], source_unit_text: str,
) -> dict[str, Any]:
    """Verify only the literal Reader quote, not unrelated text in its SourceUnit."""
    quote = enrichment.get("quote")
    if not isinstance(quote, str) or not quote or quote not in source_unit_text:
        return assess_relation_support(candidate, {"decision": "ABSTAIN"})
    return assess_relation_support(candidate, enrichment, source_unit_text=quote)


def _reader_attempt_record(
    call: dict[str, Any], validation: dict[str, Any], *,
    document_id: str, gate_accepted: bool, public_source_identity: str | None = None,
    source_unit_text: str = "",
) -> dict[str, Any]:
    """Keep one audit record per Reader call, including parse failure and abstention."""
    enrichment = call.get("enrichment")
    outcome = str(validation.get("outcome") or "")
    transport = str(call.get("transport_result") or "")
    if enrichment is None:
        status = "READER_PARSE_FAILED" if transport in {
            "INVALID_TOOL_ARGUMENTS", "INVALID_TOOL_CALL"
        } else "READER_TRANSPORT_FAILED"
    elif enrichment.get("decision") == "ABSTAIN":
        status = "READER_ABSTAINED"
    elif outcome in _V1_ACCEPTED + _V2_ACCEPTED + _V3_ACCEPTED:
        status = "READER_QUOTE_VALIDATED"
    else:
        status = "VALIDATOR_REJECTED"
    record = dossier_mod.annotate_enrichment(
        enrichment or {}, paper_id=validation.get("paper_id"),
        validation=validation, accepted_for_gates=gate_accepted,
        source_unit_text=source_unit_text,
    )
    return {
        **record,
        "candidate_id": validation.get("candidate_id"),
        "relation_family": validation.get("relation_family"),
        "document_id": document_id,
        "public_source_identity": public_source_identity,
        "reader_attempt_status": status,
        "transport_result": transport,
        "transport_reason_codes": list(call.get("transport_reason_codes") or []),
        "reader_request_hash": call.get("reader_request_hash"),
        "reader_context": call.get("reader_context"),
        "reader_response_reused": bool(call.get("reader_response_reused")),
        "model_call_count": call.get("model_call_count"),
        "candidate_support": validation.get("candidate_support"),
        "document_verification": validation.get("document_verification"),
        "quote_valid": outcome in _V1_ACCEPTED + _V2_ACCEPTED + _V3_ACCEPTED,
    }


CASECONTEXT_VERSION = "end-to-end-pilot-casecontext/1.0"
DOSSIER_VERSION = "end-to-end-pilot-dossier/2.0"
from backend.research_pipeline.versions import ORCHESTRATOR_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deterministic(component: str, version: str = ORCHESTRATOR_VERSION) -> StageProducer:
    return StageProducer(kind="DETERMINISTIC", component=component, version=version)



@run_budget_context
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
    source_unit_selector_fn: Callable[..., Any] | None = None,
    validate_fn: Callable[..., dict[str, Any]] | None = None,
    retrieve_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    research_frozen_artifacts: bool = False,
    document_runtime: DocumentRuntime | None = None,
    call_narrator_fn: Callable[..., dict[str, Any]] | None = None,
    verify_narrative_fn: Callable[..., dict[str, Any]] | None = None,
    narrative_verifier_mode: str = "CANONICAL",
    match_verifier_fn: Callable[..., dict[str, Any]] | None = None,
    eligibility_gate_fn: Callable[..., dict[str, Any] | None] | None = None,
    call_semantic_alignment_fn: Callable[..., dict[str, Any]] | None = None,
) -> PipelineRun:
    """Esegue un caso emettendo un evento per ogni transizione di stage.

    **Un solo percorso operativo.** Non esiste più un parametro ``execution_mode``
    che scelga fra due modalità: i default di questa funzione *sono* il runtime
    canonico — retrieval dalle provenance della GCA, risoluzione documentale
    cache-first con API autorizzate sul miss, parsing reale, SourceUnit Selector
    deterministico con K=5. Il runtime precedente sceglieva replay quando
    esistevano artefatti congelati per il caso, e quella scelta implicita era il
    fallback silenzioso rimosso.

    ``document_runtime`` è la cache aperta per la run. Nel percorso canonico è
    obbligatorio solo quando il routing produce PAPER/TRIAL: senza, il ramo
    documentale fallisce con ``DOCUMENT_CACHE_UNAVAILABLE`` invece di rigiocare
    artefatti. Un run KG_ONLY non consuma la cache.

    ``research_frozen_artifacts`` è **infrastruttura di ricerca e regressione**,
    non una modalità utente. Vale ``False`` per definizione in ogni percorso
    raggiungibile dall'API, dal ``RunStore`` e dalla console clinica; solo un
    harness che voglia riprodurre gli esperimenti storici lo alza, insieme agli
    adattatori congelati (``retrieve_fn``, ``select_papers_fn``, ``validate_fn``,
    ``call_parser_fn``, ``call_enricher_fn``, ``call_narrator_fn``). Nessuna
    stringa di modalità governa più nulla: ciò che cambia il comportamento è ciò
    che il chiamante inietta, e l'iniezione è visibile nella chiamata.

    ``retrieve_fn`` è il punto di iniezione dello stage 5. Il default risolve
    ``retrieval_mod.retrieve`` **al momento della chiamata**, così le probe che
    sostituiscono quell'attributo continuano a intercettarlo.
    """
    if narrative_verifier_mode != "CANONICAL" and not research_frozen_artifacts:
        raise ValueError("narrative verifier bypass is restricted to frozen evaluation runs")
    canonical = not research_frozen_artifacts
    context_policy = ContextPolicy.from_environment() if canonical else ContextPolicy()
    selection_index = None
    if canonical:
        from backend.research_pipeline import live_providers
        if call_enricher_fn is live_providers.enricher_fn:
            call_enricher_fn = live_providers.make_run_enricher()
    retrieve = retrieve_fn or retrieval_mod.retrieve
    if select_papers_fn is not None:
        select_papers = select_papers_fn
    elif canonical:
        select_papers = lambda association, units, **kw: select_live_papers_for_association(
            association, units, resolution=kw["resolution"], top_k=context_policy.initial_top_k,
            selector_fn=source_unit_selector_fn,
            selection_index=selection_index,
            case_context=case_context,
        )
    else:
        select_papers = lambda association, units, **_: select_papers_for_association(association, units)
    validate = validate_fn or (
        lambda transport, enrichment, **kw: enrichment_validator.validate_enrichment(
            transport, enrichment,
            candidate=kw["candidate"], paper_bundle=kw["paper_bundle"],
            source_units_by_id=kw["source_units_by_id"], requested_drug=kw["requested_drug"],
        )
    )
    #: Etichetta registrata per questa run. Deriva dal solo fatto che conta —
    #: se il chiamante ha chiesto artefatti congelati — e non da un parametro
    #: separato che potrebbe contraddirlo.
    execution_mode = em.RESEARCH_FROZEN_MODE if research_frozen_artifacts else em.CANONICAL_MODE
    #: Origine degli stage il cui risultato arriva da un artefatto registrato.
    #: Nel runtime canonico non esistono: ogni stage o viene eseguito o fallisce.
    replay_origin = em.GENERATED_NOW if canonical else em.RECORDED_REAL_RUN

    run_id = run_id or str(uuid4())
    cache_descriptor = dict(document_runtime.descriptor) if document_runtime else {
        "document_cache_available": False,
    }
    recorder = RunRecorder(ledger, run_id, execution_mode)
    started_at = recorder.run_created(case_id, clinical_text, cache_descriptor)
    llm_calls = 0
    semantic_attempts: list[dict[str, Any]] = []

    def semantic_attempt_summary() -> dict[str, Any]:
        budget_rejected = sum(
            item.get("status") == "NOT_EXECUTED_BUDGET" for item in semantic_attempts
        )
        return {
            "attempted_calls": len(semantic_attempts) - budget_rejected,
            "budget_rejected_calls": budget_rejected,
            "attempts": list(semantic_attempts),
        }

    def _finalize(status: str, stopped_at: str | None, **extra: Any) -> PipelineRun:
        relation_aware_report = public_artifact(extra.pop("relation_aware_report", None))
        if relation_aware_report and relation_aware_report.get("technical_run_status", relation_aware_report.get("run_status")) not in RUN_STATUSES:
            relation_aware_report["technical_run_status"] = status
            relation_aware_report = apply_publication_integrity(relation_aware_report)
        if stopped_at is not None:
            recorder.skip_remaining(stopped_at)
        else:
            recorder.skip_remaining("NOT_IMPLEMENTED")
        dossier_recorded = any(stage.stage_id == "stage_13_dossier" and stage.status == "SUCCEEDED"
                               for stage in recorder.stages)
        completed_at = _now()
        operations = operational_summary({"started_at": started_at, "completed_at": completed_at,
            "llm_calls": llm_calls, "stages": [stage.to_dict() for stage in recorder.stages]})
        if hasattr(budget, 'transport_snapshot'):
            physical = budget.transport_snapshot()['physical_calls']
            if physical > operations['llm_calls']:
                operations['llm_calls'] = physical
                operations['llm_calls_complete'] = False
        run = PipelineRun(
            run_id=run_id, case_id=case_id, status=status, started_at=started_at,
            completed_at=completed_at, input_text=clinical_text[:600], stopped_at=stopped_at,
            stages=recorder.stages,
            versions={"casecontext_schema": CASECONTEXT_VERSION,
                      "dossier": DOSSIER_VERSION,
                      "orchestrator": ORCHESTRATOR_VERSION},
            requested_mode=execution_mode,
            document_cache=cache_descriptor,
            llm_calls=operations["llm_calls"], metrics={"operational": operations,
                **({'provider_budget': budget.transport_snapshot()} if hasattr(budget, 'transport_snapshot') else {})},
            relation_aware_report=relation_aware_report,
            **extra,
        )
        header = {key: value for key, value in run.to_dict().items()
                  if key not in {"stages", "relation_aware_report", "document_acquisition"}}
        recorder.run_completed(
            status, stopped_at, operations["llm_calls"],
            early_relation_aware_report=relation_aware_report if not dossier_recorded else None,
            run_snapshot=header,
        )
        return run

    # STAGE 1 — Case input
    p = _deterministic("case_input")
    recorder.start("stage_1_case_input", p)
    recorder.finish("stage_1_case_input", p,
                    output_preview={"case_id": case_id, "input_chars": len(clinical_text)})

    # STAGE 2 — CaseContext Parser (LLM)
    recorder.start("stage_2_casecontext_parser", StageProducer(
        kind="LLM", component="casecontext_parser", version=CASECONTEXT_VERSION,
        model="unknown", prompt_version=CASECONTEXT_VERSION))
    try:
        parser_result = call_parser_fn(budget, case_id, clinical_text)
    except LiveStageFailed as failure:
        p = _deterministic("casecontext_parser", CASECONTEXT_VERSION)
        recorder.finish("stage_2_casecontext_parser", p, status="FAILED",
                        artifact_origin=em.NOT_EXECUTED,
                        reason_codes=(failure.reason_code,), errors=(failure.detail,))
        return _finalize("FAILED", failure.reason_code)
    if canonical:
        llm_calls += 1

    parser_producer = StageProducer(
        kind="LLM", component="casecontext_parser", version=CASECONTEXT_VERSION,
        model=parser_result.get("model") or "unknown",
        prompt_version=parser_result.get("prompt_version") or CASECONTEXT_VERSION,
    )
    parser_metrics = {"latency_ms": parser_result.get("latency_ms"),
                      "input_tokens": parser_result.get("input_tokens"),
                      "output_tokens": parser_result.get("output_tokens"),
                      "retry_count": parser_result.get("retry_count"),
                      "real_llm_calls": parser_result.get("model_call_count", 1) if canonical else 0,
                      "token_usage_complete": parser_result.get("token_usage_complete", not parser_result.get("retry_count"))}
    transport = parser_result.get("transport_result")
    if transport != "FORCED_TOOL_VALID":
        parser_failure = ("PROVIDER_RATE_LIMITED" if canonical and (
            parser_result.get("status_code") == 429
            or "HTTP_429" in (parser_result.get("transport_reason_codes") or []))
            else "PARSER_TRANSPORT_FAILED")
        recorder.finish("stage_2_casecontext_parser", parser_producer, status="FAILED",
                        artifact_origin=replay_origin,
                        reason_codes=(parser_failure,),
                        errors=(str(transport),),
                        metrics=parser_metrics,
                        output_preview={
                            "transport_result": transport,
                            "parser_diagnostics": parser_result.get("parser_diagnostics"),
                        })
        return _finalize("FAILED", parser_failure)

    case_context = parser_result["case_context_raw"]
    recorder.finish("stage_2_casecontext_parser", parser_producer,
                    artifact_origin=replay_origin,
                    domain_event=ev.CASECONTEXT_PARSED,
                    output_preview={"transport_result": transport,
                                    "query_intent": case_context.get("query_intent"),
                                    "case_context": case_context},
                    metrics=parser_metrics)

    # STAGE 3 — Match verifier (deterministico)
    p = _deterministic("casecontext_match_verifier", CASECONTEXT_VERSION)
    recorder.start("stage_3_casecontext_match", p)
    if match_verifier_fn is None:
        records = verifier.verify_case_context(case_context, clinical_text)
        essential_ok, match_warnings = verifier.essential_fields_pass(records)
        match_bypassed = False
    else:
        match_result = match_verifier_fn(case_context, clinical_text)
        records = match_result["records"]
        essential_ok = match_result["essential_fields_pass"]
        match_warnings = match_result.get("warnings", [])
        match_bypassed = bool(match_result.get("bypassed", True))
    preview = {"records": [r.to_dict() for r in records],
               "essential_fields_pass": essential_ok,
               "warnings": list(match_warnings)}
    if match_bypassed:
        preview["bypassed"] = True
        recorder.finish("stage_3_casecontext_match", p, status="SKIPPED",
                        reason_codes=("STAGE_BYPASSED",), output_preview=preview)
    elif not essential_ok:
        recorder.finish("stage_3_casecontext_match", p, status="WARNING",
                        domain_event=ev.CASECONTEXT_VERIFIED,
                        reason_codes=("CASECONTEXT_MISMATCH",),
                        warnings=tuple(match_warnings), output_preview=preview)
        return _finalize("STOPPED", "CASECONTEXT_MISMATCH")
    else:
        recorder.finish("stage_3_casecontext_match", p, domain_event=ev.CASECONTEXT_VERIFIED,
                        warnings=tuple(match_warnings), output_preview=preview)

    # STAGE 3b — Pre-Retrieval Eligibility Gate (deterministico)
    #
    # Il verifier testuale non basta: ``MISSING_IN_TEXT`` non è ``MISMATCH``,
    # quindi un CaseContext completamente vuoto superava lo stage 3 ed entrava
    # nel retrieval. Il gate applica verifica semantica, rilevamento delle
    # istruzioni di controllo e rilevamento delle contraddizioni, e decide.
    p = _deterministic("pre_retrieval_eligibility_gate", cc_pipeline.DETERMINISTIC_CHAIN_VERSION)
    recorder.start("stage_3b_pre_retrieval_eligibility_gate", p)
    chain = (cc_pipeline.run(clinical_text, case_context, transport_ok=True)
             if eligibility_gate_fn is None else eligibility_gate_fn(clinical_text, case_context))
    if chain is None:
        recorder.finish("stage_3b_pre_retrieval_eligibility_gate", p, status="SKIPPED",
                        reason_codes=("STAGE_BYPASSED",), output_preview={"bypassed": True})
    else:
        eligibility = chain["eligibility"]
        gate_preview = {
            "eligibility_status": eligibility["eligibility_status"],
            "eligible": eligibility["eligible"],
            "reason_codes": eligibility["reason_codes"],
            "verified_fields": eligibility["verified_fields"],
            "missing_required_fields": eligibility["missing_required_fields"],
            "rejected_mentions": eligibility["rejected_mentions"],
            "mention_accounting": chain.get("mention_accounting") or {},
            "symptom_mentions": (chain["case_context_v2"] or {}).get("symptom_mentions", []),
            "control_instruction_spans": chain["control_instruction_spans"],
            "contradictions": eligibility["contradictions"],
            "scope_evidence": eligibility["scope_evidence"],
            "forbidden_downstream_stages": eligibility["forbidden_downstream_stages"],
            "policy_version": eligibility["policy_version"],
            "producer": eligibility["producer"],
        }
        legacy_input_stop = eligibility["eligibility_status"] in {
            "INVALID_INPUT", "OUT_OF_SCOPE", "NON_ACTIONABLE_MEDICAL_INPUT",
        }
        if legacy_input_stop:
            recorder.finish("stage_3b_pre_retrieval_eligibility_gate", p, status="WARNING",
                            reason_codes=tuple(eligibility["reason_codes"]),
                            warnings=tuple(eligibility["warning_codes"]),
                            output_preview=gate_preview)
            empty_report = dossier_mod.build_relation_aware_report(
                case_context, [], run_status="INSUFFICIENT_CASE_CONTEXT",
                extra_limitations=["INSUFFICIENT_CASE_CONTEXT"],
            )
            return _finalize("STOPPED", eligibility["eligibility_status"],
                             relation_aware_report=empty_report)
        minimal_validation = cc_pipeline.validate_minimal_case_context(case_context)
        if not minimal_validation["valid"]:
            gate_preview.update(minimal_validation)
            gate_preview["eligibility_status"] = "INSUFFICIENT_ONCOLOGY_CONTEXT"
            recorder.finish("stage_3b_pre_retrieval_eligibility_gate", p, status="WARNING",
                            reason_codes=(minimal_validation["run_status"],),
                            output_preview=gate_preview)
            empty_report = dossier_mod.build_relation_aware_report(
                case_context, [], run_status=minimal_validation["run_status"],
                extra_limitations=[minimal_validation["run_status"]],
            )
            return _finalize("STOPPED", "INSUFFICIENT_ONCOLOGY_CONTEXT",
                             relation_aware_report=empty_report)
        # The intent-aware minimum validator can accept an intervention-only
        # anchor. It cannot supply additional qualifiers requested by the gate
        # (for example, an unspecified microsatellite status).
        additional_required_fields = set(eligibility["missing_required_fields"]) - {
            'biomarker_or_alteration', 'target_intervention',
        }
        blocking_ambiguity = eligibility_gate_fn is None and (
            eligibility["eligibility_status"] in {
                "CONTRADICTORY_CASE_CONTEXT", "ADVERSARIAL_OR_CONTROL_INPUT", "AMBIGUOUS_CASE_CONTEXT",
            } or (not eligibility['eligible'] and bool(additional_required_fields))
        )
        if blocking_ambiguity:
            recorder.finish("stage_3b_pre_retrieval_eligibility_gate", p, status="WARNING",
                            reason_codes=("NEEDS_CLARIFICATION",),
                            warnings=tuple(eligibility["warning_codes"]),
                            output_preview=gate_preview)
            empty_report = dossier_mod.build_relation_aware_report(
                case_context, [], run_status="NEEDS_CLARIFICATION",
                extra_limitations=["NEEDS_CLARIFICATION"],
            )
            return _finalize("STOPPED", eligibility["eligibility_status"],
                             relation_aware_report=empty_report)
        if eligibility_gate_fn is not None and not eligibility["eligible"]:
            recorder.finish("stage_3b_pre_retrieval_eligibility_gate", p, status="WARNING",
                            reason_codes=tuple(eligibility["reason_codes"]),
                            warnings=tuple(eligibility["warning_codes"]),
                            output_preview=gate_preview)
            return _finalize("STOPPED", eligibility["eligibility_status"])
        recorder.finish("stage_3b_pre_retrieval_eligibility_gate", p,
                        warnings=tuple(eligibility["warning_codes"]),
                        output_preview=gate_preview)

    # STAGE 4-5 — Piano di retrieval e interrogazione del grafo
    p = _deterministic("retrieval_plan")
    recorder.start("stage_4_retrieval_plan", p)
    retrieval_case_context = (
        cc_pipeline.build_retrieval_case_context(case_context, chain.get("mentions", []))
        if chain is not None else case_context
    )
    if retrieve_fn is None:
        from backend.research_pipeline.terminology.case_resolution import resolve_case
        from backend.research_pipeline.terminology.loader import get_registry
        retrieval_case_context = resolve_case(retrieval_case_context, get_registry())
    recorder.finish("stage_4_retrieval_plan", p, domain_event=ev.RETRIEVAL_COMPLETED,
                    output_preview={
                        "query_intent": case_context.get("query_intent"),
                        "disease": (case_context.get("disease") or {}).get("normalized_value"),
                        "biomarkers": [b.get("normalized_value") for b in case_context.get("biomarkers") or []],
                        "target_intervention": (case_context.get("target_intervention") or {}).get("normalized_value"),
                        "repository": f"graph_candidate_repository/{GRAPH_CANDIDATE_REPOSITORY_VERSION if canonical else '2.0'}",
                        "planner": "DETERMINISTIC_NOT_LLM",
                        "entity_resolution": retrieval_case_context.get("entity_resolution"),
                    })

    p = _deterministic("kg_retrieval")
    recorder.start("stage_5_kg_retrieval", p)
    # Un solo retrieval, senza parametro di modalità: le candidate ammesse sono
    # quelle con provenance documentale, e i descrittori dei documenti nascono da
    # quella provenance. Un harness storico passa il proprio ``retrieve_fn``.
    retrieval_result = retrieve(retrieval_case_context)
    valid_associations: list[dict[str, Any]] = []
    invalid_candidate_ids: list[str] = []
    for association in retrieval_result["associations"]:
        family = classify_relation_family(association["candidate"])
        association["relation_family"] = family
        if family == INVALID_PROVENANCE:
            invalid_candidate_ids.append(association["candidate_id"])
        else:
            valid_associations.append(association)
    retrieval_result["associations"] = valid_associations
    retrieval_result["no_match"] = not valid_associations
    paper_associations = [a for a in valid_associations if a["relation_family"] == PAPER_EVIDENCE]
    trial_associations = [a for a in valid_associations if a["relation_family"] == CLINICAL_TRIAL]
    kg_only_associations = [a for a in valid_associations if a["relation_family"] == KG_ONLY]
    document_bearing_associations = [
        association for association in paper_associations + trial_associations
        if association.get("available_bundles")
    ]
    redacted = redact_retrieval_result(retrieval_result)
    retrieval_preview = {
        "graph_derived": True,
        "documentary_proof": False,
        "associations": redacted["associations"],
        "excluded_candidates_audit": compact_excluded_candidates(redacted["excluded_candidates"]),
        "no_match": retrieval_result["no_match"],
    }
    if canonical:
        # Honor the selector's document cap, including its unbounded setting.
        # Reserve one Reader call per document and an independent semantic call for
        # EVIDENCE_DRUG.  No evidence outcome influences this finite bound.
        reader_bound = sum(
            (len(a.get("available_bundles") or []) if MAX_PAPERS_PER_ASSOCIATION is None
             else min(len(a.get("available_bundles") or []), MAX_PAPERS_PER_ASSOCIATION))
            for a in document_bearing_associations
        )
        semantic_bound = sum(
            (len(a.get("available_bundles") or []) if MAX_PAPERS_PER_ASSOCIATION is None
             else min(len(a.get("available_bundles") or []), MAX_PAPERS_PER_ASSOCIATION))
            for a in document_bearing_associations
            if a["candidate"].get("relation_family") == "EVIDENCE_DRUG"
        )
        expansion_bound = reader_bound if context_policy.enabled else 0
        narrator_reservation = int(call_narrator_fn is not None)
        from .enrichment.transport import maximum_structured_call_attempts
        structured_attempt_bound = maximum_structured_call_attempts()
        documentary_transport_bound = (reader_bound + semantic_bound + expansion_bound) * structured_attempt_bound
        budget.plan_remaining_calls(documentary_transport_bound + narrator_reservation)
        retrieval_preview["call_budget"] = {
            "policy": "WORKLOAD_SIZED" if budget.workload_sized else "FIXED_LIMIT",
            "maximum": budget.maximum,
            "used_before_documents": budget.used,
            "reader_call_upper_bound": reader_bound,
            "semantic_call_upper_bound": semantic_bound,
            "context_expansion_call_upper_bound": expansion_bound,
            "physical_attempts_per_structured_call": structured_attempt_bound,
            "documentary_physical_call_upper_bound": documentary_transport_bound,
            "sourceunit_context_policy": context_policy.to_dict(),
            "narrator_included": bool(narrator_reservation),
            "initial_narrator_call_reservation": narrator_reservation,
        }
    if retrieval_result["no_match"]:
        recorder.finish("stage_5_kg_retrieval", p, status="WARNING",
                        domain_event=ev.CANDIDATES_FOUND,
                        reason_codes=("RETRIEVAL_NO_MATCH",), output_preview=retrieval_preview)
        empty_report = dossier_mod.build_relation_aware_report(
            case_context, [], run_status="NO_RELEVANT_KG_EVIDENCE",
            retrieval_summary=retrieval_result.get("retrieval_summary"),
            extra_limitations=["NO_RELEVANT_KG_EVIDENCE"] + [
                f"INVALID_PROVENANCE:{candidate_id}" for candidate_id in invalid_candidate_ids
            ],
        )
        empty_report["pipeline_accounting"] = build_pipeline_accounting(
            mention_accounting=(chain or {}).get("mention_accounting") or {},
            retrieval_result=retrieval_result,
            selections=[], paper_results={}, trial_results={}, report=empty_report,
        )
        return _finalize("STOPPED", "RETRIEVAL_NO_MATCH", relation_aware_report=empty_report)
    recorder.finish("stage_5_kg_retrieval", p, domain_event=ev.CANDIDATES_FOUND,
                    output_preview=retrieval_preview)

    # STAGE 6 — Document Resolution
    #
    # Eseguita davvero: i documenti vengono cercati nella cache autorizzata al
    # momento della run. Il runtime canonico è cache-first ma può usare le API
    # autorizzate sul miss; un documento assente resta DOCUMENT_UNAVAILABLE e il
    # corrispondente artefatto legacy/research non viene usato al suo posto.
    p = _deterministic("document_resolution")
    recorder.start("stage_6_document_resolution", p)

    if canonical and document_runtime is None and document_bearing_associations:
        recorder.finish("stage_6_document_resolution", p, status="FAILED",
                        artifact_origin=em.NOT_EXECUTED,
                        reason_codes=("DOCUMENT_CACHE_UNAVAILABLE",),
                        errors=("cache documentale non disponibile: la run LIVE non "
                                "ripiega su artefatti registrati",),
                        output_preview=dict(cache_descriptor))
        return _finalize("FAILED", "DOCUMENT_CACHE_UNAVAILABLE")

    if document_runtime is not None:
        resolution = document_runtime.resolve(document_bearing_associations) if document_bearing_associations else DocumentResolution(
            documents=(), cache_path_redacted=str(cache_descriptor.get("cache_path_redacted") or ""),
            manifest_hash=document_runtime.manifest_hash,
        )
        resolution_preview = {**cache_descriptor, **resolution.to_preview()}
        resolved_any = any(doc.resolved for doc in resolution.documents)
        unavailable = tuple(
            f"DOCUMENT_UNAVAILABLE:{doc.document_id}"
            for doc in resolution.documents if not doc.resolved
        )
        recorder.finish("stage_6_document_resolution", p,
                        status="WARNING" if unavailable else "SUCCEEDED",
                        artifact_origin=em.DETERMINISTIC_CACHE,
                        domain_event=ev.DOCUMENT_RESOLVED,
                        warnings=unavailable,
                        reason_codes=(
                            ("DOCUMENT_RESOLVED_FROM_CACHE",) if not resolution.cache_misses
                            else ("DOCUMENT_RESOLVED_FROM_API",)
                        ) + (("DOCUMENT_UNAVAILABLE",) if unavailable else ()),
                        output_preview=resolution_preview,
                        metrics={"cache_hits": resolution.cache_hits,
                                 "cache_misses": resolution.cache_misses},
                        lineage={"manifest_hash": resolution.manifest_hash})
        for document in resolution.documents:
            cache_event = ev.DOCUMENT_CACHE_HIT if document.cache_hit else ev.DOCUMENT_CACHE_MISS
            recorder.emit_domain_event(
                cache_event, "stage_6_document_resolution", _deterministic("document_resolver"),
                candidate_id=document.candidate_id, document_id=document.document_id,
                bundle_id=document.bundle_id, reason_codes=list(document.reason_codes),
                lineage=dict(document.lineage),
            )
            if not document.cache_hit:
                fetch_event = (ev.DOCUMENT_FETCH_SUCCEEDED if document.resolved
                               else ev.DOCUMENT_FETCH_FAILED)
                recorder.emit_domain_event(
                    fetch_event, "stage_6_document_resolution", _deterministic("document_resolver"),
                    candidate_id=document.candidate_id, document_id=document.document_id,
                    bundle_id=document.bundle_id, retrieval_mode=document.lineage.get("retrieval_mode"),
                    resolver_version=document.lineage.get("resolver_version"),
                )
            if "PMC_RESOLUTION_FAILED" in document.reason_codes and document.abstract_available:
                recorder.emit_domain_event(
                    ev.DOCUMENT_DEGRADED_TO_ABSTRACT, "stage_6_document_resolution",
                    _deterministic("document_resolver"), candidate_id=document.candidate_id,
                    document_id=document.document_id, bundle_id=document.bundle_id,
                    degradation_reason="PMC_RESOLUTION_FAILED",
                )
    elif canonical:
        resolution = DocumentResolution(
            documents=(), cache_path_redacted="", manifest_hash=None,
        )
        recorder.finish(
            "stage_6_document_resolution", p, status="SKIPPED",
            artifact_origin=em.NOT_APPLICABLE,
            reason_codes=("NO_DOCUMENT_BEARING_CANDIDATES",),
            output_preview={"documents": [], "document_cache_available": False},
        )
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
    requested_unit_ids = None if canonical else sorted({
        uid for association in retrieval_result["associations"]
        for bundle in association["available_bundles"]
        for uid in bundle.get("source_unit_ids", [])
    })

    if document_runtime is not None and resolution is not None and (paper_associations or trial_associations):
        paper_ids = {
            item["candidate_id"]
            for item in paper_associations + trial_associations
        }
        paper_resolution = DocumentResolution(
            documents=tuple(doc for doc in resolution.documents if doc.candidate_id in paper_ids),
            cache_path_redacted=resolution.cache_path_redacted,
            manifest_hash=resolution.manifest_hash,
        )
        bundle_units = document_runtime.load_units(paper_resolution)
        resolution = paper_resolution
        units_for_decisions: Mapping[str, dict[str, Any]] = bundle_units.units_by_id
        units_preview = bundle_units.to_preview(requested_unit_ids)
        with_text = (
            bundle_units.with_text if requested_unit_ids is None else
            sum(1 for uid in requested_unit_ids
                if (bundle_units.units_by_id.get(uid, {}).get("text") or "").strip())
        )
        recorder.finish("stage_7_source_units", p,
                        status="SUCCEEDED" if with_text else "WARNING",
                        artifact_origin=em.DETERMINISTIC_CACHE,
                        domain_event=ev.SOURCE_UNIT_MATERIALIZED,
                        reason_codes=("SOURCE_UNITS_MATERIALIZED_FROM_CACHE",) if with_text
                                     else ("SOURCE_UNIT_TEXT_UNAVAILABLE",),
                        output_preview=units_preview,
                        metrics={"requested": (len(requested_unit_ids) if requested_unit_ids is not None
                                             else len(bundle_units.units_by_id)),
                                 "with_exact_text": with_text,
                                 "parsed_documents": bundle_units.documents_parsed})
        recorder.emit_domain_event(
            ev.SOURCE_UNITS_PARSED, "stage_7_source_units", _deterministic("document_parser"),
            documents_parsed=bundle_units.documents_parsed, source_unit_count=len(bundle_units.units_by_id),
            with_exact_text=with_text, parser_mode="CANONICAL" if canonical else "CACHE",
        )
    elif document_runtime is not None:
        units_for_decisions = {}
        recorder.finish("stage_7_source_units", p, status="SKIPPED",
                        artifact_origin=em.NOT_APPLICABLE,
                        reason_codes=("NO_PAPER_CANDIDATES",),
                        output_preview={"source_units": [], "source_unit_count": 0,
                                        "text_never_exposed": True})
    elif canonical:
        units_for_decisions = {}
        recorder.finish(
            "stage_7_source_units", p, status="SKIPPED",
            artifact_origin=em.NOT_APPLICABLE,
            reason_codes=("NO_PAPER_CANDIDATES",),
            output_preview={"source_units": [], "source_unit_count": 0,
                            "text_never_exposed": True},
        )
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
    selection_failed_candidates: set[str] = set()
    relation_paper_results: dict[str, dict[str, Any]] = {}
    relation_trial_results: dict[str, dict[str, Any]] = {}
    trial_reader_attempts: dict[str, list[dict[str, Any]]] = {}
    budget_exhausted = False
    pending_reader_requests: list[dict[str, Any]] = []
    if canonical and resolution is not None:
        from backend.research_pipeline.retrieval.live_sourceunit_selection import SelectionIndex
        selection_index = SelectionIndex.build(resolution, units_for_decisions)
    document_associations = paper_associations + trial_associations
    reader_model_calls = reader_reuses = 0

    def record_pending_reader_request(association: dict[str, Any], paper: dict[str, Any]) -> None:
        pending_reader_requests.append({
            "candidate_id": association["candidate_id"],
            "relation_family": classify_relation_family(association["candidate"]),
            "document_id": paper.get("document_id"),
            "paper_id": paper.get("bundle_id"),
            "source_unit_ids": list(paper.get("resolved_source_unit_ids") or []),
            "status": "NOT_EXECUTED",
            "reason": "CALL_BUDGET_EXCEEDED",
        })

    def work_progress(phase: str, stage_id: str, completed: int, association: dict,
                      document_id: str | None = None) -> None:
        if canonical:
            recorder.emit_domain_event(
                ev.PIPELINE_WORK_PROGRESS, stage_id, _deterministic("orchestrator"),
                phase=phase, completed_candidates=completed,
                total_candidates=len(document_associations),
                candidate_id=association["candidate_id"], document_id=document_id,
                reader_calls=reader_model_calls, reader_reuses=reader_reuses,
            )

    # Trial records now use the same document-to-SourceUnit path as papers.
    # Their eligibility semantics remain separate and are not inferred here.
    for candidate_index, association in enumerate(document_associations):
        work_progress("SOURCEUNIT_SELECTION", "stage_8_paper_selection", candidate_index, association)
        recorder.emit_domain_event(
            ev.SOURCEUNIT_SELECTION_STARTED, "stage_8_paper_selection",
            _deterministic("sourceunit_selector"), candidate_id=association["candidate_id"],
            # ``DETERMINISTIC_SELECTOR`` sostituisce ``LIVE_SELECTOR``: il selettore
            # non è più una delle due modalità, è il solo modo in cui il runtime
            # canonico sceglie i passaggi. ``FROZEN_BUNDLE`` resta per gli harness
            # storici, dove descrive ancora esattamente ciò che accade.
            selection_mode="DETERMINISTIC_SELECTOR" if canonical else "FROZEN_BUNDLE",
            top_k=context_policy.initial_top_k if canonical else None, bundle_source_unit_ids_used=not canonical,
        )
        selection_started = time.perf_counter()
        selection_cpu_started = time.process_time()
        selection = select_papers(
            association, (units_for_decisions if canonical and select_papers_fn is None
                          else dict(units_for_decisions)), case_id=case_id,
            resolution=resolution, execution_mode=execution_mode,
        )
        selection["selection_wall_ms"] = (time.perf_counter() - selection_started) * 1000
        selection["selection_cpu_ms"] = (time.process_time() - selection_cpu_started) * 1000
        selections.append(selection)
        recorder.emit_domain_event(
            ev.SOURCEUNIT_SELECTION_COMPLETED, "stage_8_paper_selection",
            _deterministic("sourceunit_selector"), candidate_id=association["candidate_id"],
            selection_mode="DETERMINISTIC_SELECTOR" if canonical else "FROZEN_BUNDLE",
            selected_papers=[{
                "bundle_id": paper.get("bundle_id"),
                "document_id": paper.get("document_id"),
                "selected_source_unit_ids": paper.get("resolved_source_unit_ids", []),
                "selector": paper.get("selector"),
            } for paper in selection.get("selected_papers", [])],
            bundle_source_unit_ids_used=bool(
                any(paper.get("source_unit_ids") for paper in selection.get("selected_papers", []))
            ) if canonical else True,
        )
        candidate = association["candidate"]
        candidate_selection_failed = bool(
            association.get("available_bundles")
            and not selection.get("selected_papers")
        )
        if candidate_selection_failed:
            selection_failed_candidates.add(candidate["candidate_id"])

        enrichment_entries, validation_entries, validated = [], [], []
        for paper_index, paper in enumerate(selection["selected_papers"]):
            if budget_exhausted:
                record_pending_reader_request(association, paper)
                continue
            interventions = [i.get("label") for i in candidate.get("interventions") or [] if i.get("label")]
            requested_drug = (
                (case_context.get("target_intervention") or {}).get("normalized_value")
                or (interventions[0] if interventions else "")
            )
            paper_units = [units_for_decisions[uid] for uid in paper["resolved_source_unit_ids"]
                           if uid in units_for_decisions]

            try:
                work_progress("READER", "stage_9_paper_context_enricher", candidate_index,
                              association, paper["document_id"])
                if canonical and paper.get('trial_fact_provenance'):
                    from backend.research_pipeline.documents.trial_facts import bind_trial_relation
                    call = bind_trial_relation(candidate,
                        {**paper['trial_fact_provenance'], 'units': paper_units}, case_id)
                elif canonical and (context_policy.adjacent_context_enabled or context_policy.enabled):
                    document_units = list(selection_index.units_by_document_id.get(paper["document_id"], ()))
                    reading = read_with_context_policy(
                        call_enricher_fn, budget, case_id, case_context, candidate, requested_drug,
                        paper, paper_units, document_units, context_policy, selector_fn=source_unit_selector_fn)
                    call, paper, paper_units = reading.call, reading.paper, reading.units
                    selection["selected_papers"][paper_index] = paper
                else:
                    call = call_enricher_fn(
                        budget, case_id, candidate["candidate_id"],
                        paper["document_id"] if canonical else paper["bundle_id"], case_context,
                        candidate, requested_drug, paper_units)
            except LiveStageFailed as failure:
                if failure.reason_code == "CALL_BUDGET_EXCEEDED":
                    budget_exhausted = True
                    for pending_paper in selection["selected_papers"][paper_index:]:
                        record_pending_reader_request(association, pending_paper)
                    break
                failed_call = getattr(failure, "call_result", None)
                if canonical and failed_call is not None:
                    failed_calls = failed_call.get("model_call_count", 1)
                    llm_calls += failed_calls
                    reader_model_calls += failed_calls
                enricher_producer = StageProducer(
                    kind="LLM", component="paper_context_enricher_v3",
                    version=prompt_v3.TRANSPORT_VERSION,
                    model=(failed_call or {}).get("model", "gemma4:cloud"),
                    prompt_version=(failed_call or {}).get("prompt_version", prompt_v3.PROMPT_VERSION),
                )
                recorder.start("stage_8_paper_selection", _deterministic("paper_selection"))
                recorder.finish("stage_8_paper_selection", _deterministic("paper_selection"),
                                domain_event=ev.PAPER_SELECTED,
                                output_preview={"selections": selections,
                                                "max_papers_per_association": MAX_PAPERS_PER_ASSOCIATION})
                recorder.start("stage_9_paper_context_enricher", enricher_producer)
                recorder.finish("stage_9_paper_context_enricher", enricher_producer,
                                status="FAILED", artifact_origin=em.GENERATED_NOW if failed_call is not None else em.NOT_EXECUTED,
                                reason_codes=(failure.reason_code,), errors=(failure.detail,),
                                output_preview={"calls": enrichment_calls,
                                                "failed_call": failed_call,
                                                "failed_paper_id": paper["bundle_id"]},
                                metrics={"real_llm_calls": reader_model_calls, "reused_reader_responses": reader_reuses})
                return _finalize("FAILED", failure.reason_code)
            if canonical:
                actual_calls = call.get("model_call_count", 1)
                llm_calls += actual_calls
                reader_model_calls += actual_calls
                reader_reuses += int(bool(call.get("reader_response_reused")))
            enrichment_calls.append(call)
            work_progress("VERIFICATION", "stage_10_enrichment_validation", candidate_index,
                          association, paper["document_id"])

            validation = validate(
                call["transport_result"], call["enrichment"], candidate=candidate,
                paper_bundle=paper, source_units_by_id=dict(units_for_decisions),
                requested_drug=requested_drug, case_id=case_id,
                paper_id=paper["document_id"] if canonical else paper["bundle_id"],
            )
            validation_record = {"candidate_id": candidate["candidate_id"],
                                 "relation_family": candidate.get("relation_family"),
                                 "paper_id": paper["bundle_id"], **validation}
            # Observation-level audit binding; it does not change admission.
            reader_observation = call.get("enrichment") or {}
            literal_quote = reader_observation.get("quote") or reader_observation.get("author_claim_quote") or ""
            validation_record["source_unit_id"] = reader_observation.get("source_unit_id")
            validation_record["quote_hash"] = hashlib.sha256(str(literal_quote).encode("utf-8")).hexdigest()
            validation_record["document_id"] = paper["document_id"]
            validation_record["requested_document_id"] = paper.get("requested_document_id")
            source_unit_text = ""
            structural = None
            if candidate.get("relation_family") == "EVIDENCE_DRUG":
                reader_observation = call.get("enrichment") or {}
                if (not reader_observation.get("source_unit_id")
                        and not reader_observation.get("quote")):
                    # No reader evidence was produced. Do not turn an
                    # abstention or rejected transport into a structural
                    # source-unit provenance failure.
                    reason = ("READER_ABSTAINED"
                              if validation["outcome"] == "ENRICHMENT_V3_ABSTAINED"
                              else "READER_OUTPUT_UNAVAILABLE")
                    validation_record["document_verification"] = {
                        "verification_status": "NOT_RUN",
                        "final_admission": f"NOT_RUN_{reason}",
                        "structural_reason_codes": [reason],
                        "reader_validation_outcome": validation["outcome"],
                        "reader_validation_reason_codes": validation.get("reason_codes", []),
                    }
                else:
                    proposed_unit_id = reader_observation.get("source_unit_id")
                    proposed_unit = next(
                        (unit for unit in paper_units if unit.get("source_unit_id") == proposed_unit_id),
                        None,
                    )
                    structural = structural_verify(candidate, paper, proposed_unit, reader_observation,
                                                   case_context=case_context)
                    validation_record["document_verification"] = admit_document_relation(structural, None)
            if (
                validation["outcome"] in _V1_ACCEPTED + _V2_ACCEPTED + _V3_ACCEPTED
                and call.get("enrichment") is not None
            ):
                source_unit_id = call["enrichment"].get("source_unit_id")
                source_unit_text = next(
                    (unit.get("text") or "" for unit in paper_units
                     if unit.get("source_unit_id") == source_unit_id),
                    "",
                )
                if candidate.get("relation_family") == "EVIDENCE_DRUG":
                    semantic = None
                    if structural["structural_status"] == "PASS":
                        if call_semantic_alignment_fn is None:
                            semantic = {"relation_alignment": "AMBIGUOUS", "assertion_scope": "UNKNOWN",
                                        "reason": "SEMANTIC_PROVIDER_UNAVAILABLE", "decisive_text": ""}
                        else:
                            semantic_budget_before = getattr(budget, "used", None)
                            attempt = {"candidate_id": candidate["candidate_id"],
                                       "document_id": paper["document_id"],
                                       "model": None, "prompt_version": None}
                            semantic_attempts.append(attempt)
                            try:
                                work_progress("SEMANTIC_VERIFICATION", "stage_10_enrichment_validation",
                                              candidate_index, association, paper["document_id"])
                                semantic = call_semantic_alignment_fn(
                                    budget, case_id, structural["target_snapshot"],
                                    structural["GEP_snapshot"],
                                )
                                attempt["status"] = "EXECUTED"
                            except CallBudgetExceeded as error:
                                budget_exhausted = True
                                semantic = None
                                attempt.update(
                                    status="NOT_EXECUTED_BUDGET",
                                    reason_code="CALL_BUDGET_EXCEEDED",
                                    detail=str(error),
                                )
                            except Exception as error:  # noqa: BLE001 -- fail closed at provider boundary
                                attempt["status"] = "FAILED"
                                semantic = {"relation_alignment": "AMBIGUOUS", "assertion_scope": "UNKNOWN",
                                            "reason": f"SEMANTIC_PROVIDER_FAILURE:{type(error).__name__}",
                                            "decisive_text": ""}
                            if (canonical and isinstance(semantic_budget_before, int)
                                    and isinstance(getattr(budget, "used", None), int)):
                                llm_calls += max(0, budget.used - semantic_budget_before)
                            if isinstance(semantic, dict):
                                attempt["metrics"] = dict(semantic.get("operational_metrics") or {})
                            if canonical and isinstance(semantic, dict) and semantic.get("infrastructure_failure") == "PROVIDER_RATE_LIMITED":
                                selection_producer = _deterministic("paper_selection")
                                recorder.start("stage_8_paper_selection", selection_producer)
                                recorder.finish("stage_8_paper_selection", selection_producer,
                                    domain_event=ev.PAPER_SELECTED, output_preview={"selections": selections})
                                reader_producer = StageProducer(
                                    kind="LLM", component="paper_context_enricher_v3", version="paper-context-enricher/3.0",
                                    model=call.get("model") or "unknown", prompt_version=call.get("prompt_version") or "unknown")
                                recorder.start("stage_9_paper_context_enricher", reader_producer)
                                recorder.finish("stage_9_paper_context_enricher", reader_producer,
                                    domain_event=ev.ENRICHMENT_PROPOSED,
                                    output_preview={"calls": enrichment_calls},
                                    metrics={"real_llm_calls": reader_model_calls, "reused_reader_responses": reader_reuses})
                                validation_producer = StageProducer(
                                    kind="HYBRID", component="enrichment_validator", version=ORCHESTRATOR_VERSION,
                                    model=semantic.get("model"), prompt_version=semantic.get("prompt_version"))
                                recorder.start("stage_10_enrichment_validation", validation_producer)
                                recorder.finish("stage_10_enrichment_validation", validation_producer,
                                    status="FAILED", artifact_origin=em.GENERATED_NOW,
                                    domain_event=ev.ENRICHMENT_VALIDATED,
                                    reason_codes=("PROVIDER_RATE_LIMITED",),
                                    errors=("Semantic verifier HTTP 429 persisted after bounded infrastructure retry.",),
                                    output_preview={"validations": validations, "failed_call": semantic,
                                                    "semantic_verification": {"attempted_calls": len(semantic_attempts),
                                                                              "attempts": semantic_attempts},
                                                    "failed_document_id": paper["document_id"]})
                                return _finalize("FAILED", "PROVIDER_RATE_LIMITED")
                        # A controlled provider is held to the same output contract as a live one.
                        from backend.research_pipeline.enrichment.semantic_alignment import validate_output
                        from backend.research_pipeline.enrichment.semantic_contract import assessment_payload
                        if call_semantic_alignment_fn is not None and isinstance(semantic, dict):
                            attempt.update(model=semantic.get("model") if isinstance(semantic.get("model"), str) else None,
                                           prompt_version=semantic.get("prompt_version") if isinstance(semantic.get("prompt_version"), str) else None)
                        if semantic is not None:
                            try:
                                validate_output(assessment_payload(semantic),
                                                structural["GEP_snapshot"])
                            except (AttributeError, ValueError):
                                semantic = {"relation_alignment": "AMBIGUOUS", "assertion_scope": "UNKNOWN",
                                            "reason": "SEMANTIC_OUTPUT_INVALID", "decisive_text": ""}
                    verification = admit_document_relation(structural, semantic)
                    verification["verification_policy"] = policy_for(candidate).to_dict()
                    validation_record["document_verification"] = verification
                    support_level = verification["support_result"]
                    validation_record["candidate_support"] = {
                        "result": support_level,
                        "reason": verification["final_admission"],
                        "verification_trace": verification,
                        "verification_policy": policy_for(candidate).to_dict(),
                    }
                elif "observed_evidence_type" in call["enrichment"]:
                    validation_record["candidate_support"] = _assess_v3_quoted_relation(
                        candidate, call["enrichment"], source_unit_text
                    )
                else:
                    validation_record["candidate_support"] = assess_candidate_support(
                        candidate,
                        call["enrichment"],
                        source_unit_text=source_unit_text,
                        paper_id=paper["document_id"] if canonical else paper["bundle_id"],
                    )
            validations.append(validation_record)
            validation_entries.append({"paper_id": paper["bundle_id"], **validation_record})
            gate_outcome = _accepted_for_gates(
                validation["outcome"],
                validation_record.get("candidate_support"),
            )
            enrichment_entries.append(_reader_attempt_record(
                call, validation_record, document_id=paper["document_id"],
                gate_accepted=gate_outcome is not None,
                public_source_identity=(paper.get("requested_document_id") or paper.get("document_id")),
                source_unit_text=source_unit_text,
            ))
            if gate_outcome is not None:
                validated.append({"validation_outcome": gate_outcome,
                                  "enrichment": call["enrichment"],
                                  "original_outcome": validation["outcome"]})

        evaluation = detpipe.evaluate_association(
            case_context.get("query_intent"), candidate, validated)
        if candidate_selection_failed:
            evaluation = dict(evaluation)
            evaluation["warnings"] = list(evaluation["warnings"])
            if "NO_RELEVANT_SOURCE_UNIT" not in evaluation["warnings"]:
                evaluation["warnings"].append("NO_RELEVANT_SOURCE_UNIT")
        evaluations.append({"candidate_id": candidate["candidate_id"], **evaluation})
        family = classify_relation_family(candidate)
        if family == PAPER_EVIDENCE:
            selected_source_units = [
                unit_id
                for paper in selection["selected_papers"]
                for unit_id in paper.get("resolved_source_unit_ids", [])
            ]
            resolved_documents = [
                resolution.records_by_bundle_id.get(paper.get("bundle_id"))
                for paper in selection["selected_papers"]
            ] if resolution is not None else []
            resolved_document = next((item for item in resolved_documents if item is not None), None)
            selected_paper = next(iter(selection["selected_papers"]), {})
            frozen_document_type = {
                "FULLTEXT_LOCAL_CONTEXT_BUNDLE": "PMC_FULLTEXT",
                "ABSTRACT_BUNDLE": "PUBMED_ABSTRACT",
            }.get(selected_paper.get("bundle_type"), selected_paper.get("bundle_type"))
            # Preserve every document/SourceUnit observation.  The previous
            # implementation projected only the last list element, making the
            # dossier order-dependent and able to hide a contradiction.
            evidence_records = []
            evidence_records = [dict(record) for record in enrichment_entries]
            aggregation = dossier_mod.aggregate_evidence_records(evidence_records)
            ordered_records = sorted(
                evidence_records,
                key=lambda item: (str(item.get("paper_id") or ""), str(item.get("source_unit_id") or "")),
            )
            summary_record = ordered_records[0] if ordered_records else {}
            latest_validation = validation_entries[0] if validation_entries else {}
            from .documents.bibliography import resolved_bibliography

            relation_paper_results[candidate["candidate_id"]] = {
                "source_bibliography": resolved_bibliography(
                    resolved_documents, document_runtime.manifest_by_document_id if document_runtime else {}),
                "document_id": (
                    resolved_document.document_id
                    if resolved_document else selected_paper.get("document_id")
                ),
                "requested_document_id": (
                    resolved_document.lineage.get("requested_document_id")
                    if resolved_document else selected_paper.get("document_id")
                ),
                "pmcid": (
                    resolved_document.lineage.get("derived_pmcid")
                    if resolved_document else None
                ),
                "document_type": resolved_document.document_type if resolved_document else frozen_document_type,
                "document_source": resolved_document.source if resolved_document else candidate.get("source_type"),
                "document_resolution_status": (
                    resolved_document.availability
                    if resolved_document else
                    ("RESOLVED_FROZEN_BUNDLE" if selected_source_units else "DOCUMENT_UNAVAILABLE")
                ),
                "selected_source_units": selected_source_units,
                "enrichment": summary_record,
                "validation": latest_validation,
                "quote_valid": summary_record.get("quote_valid") is True,
                "candidate_support": {
                    **(summary_record.get("candidate_support") or {}),
                    "result": aggregation["support_level"],
                } if summary_record else None,
                "evidence_records": evidence_records,
                "reader_attempts": [dict(record) for record in enrichment_entries],
                "contradiction_present": aggregation["contradiction_present"],
            }
        elif family == CLINICAL_TRIAL:
            trial_reader_attempts[candidate["candidate_id"]] = [dict(record) for record in enrichment_entries]
        candidate_therapies.append(dossier_mod.build_candidate_therapy_entry(
            candidate, graph_relation=candidate.get("predicate", ""),
            document_support={"selected_papers": [pp["bundle_id"] for pp in selection["selected_papers"]],
                              "excluded_papers": selection["excluded_papers"]},
            enrichments=enrichment_entries, validation_results=validation_entries,
            evaluation=evaluation,
        ))
        work_progress("CANDIDATE_COMPLETED", "stage_12_status", candidate_index + 1, association)

    for association in trial_associations:
        candidate = association["candidate"]
        nct_id = next(
            (item.get("nct") for item in candidate.get("document_identifiers") or [] if item.get("nct")),
            None,
        )
        raw_record = (
            dict(document_runtime.manifest_by_document_id.get(f"nct:{nct_id}", {}))
            if document_runtime is not None and nct_id else {}
        )
        resolved_trial_document = (
            resolution.records_by_document_id.get(f"nct:{nct_id}")
            if resolution is not None and nct_id else None
        )
        if document_runtime is not None and resolved_trial_document and resolved_trial_document.resolved:
            try:
                raw_record.update(read_trial_structure(document_runtime.cache.root, raw_record))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                raw_record.update(arm_groups=[], arm_group_status='UNAVAILABLE')
        record = resolve_trial_record(
            nct_id, raw_record,
            resolved_payload=(resolved_trial_document.resolved if resolved_trial_document else False)
            if document_runtime is not None else None,
        )
        record["reader_attempts"] = trial_reader_attempts.get(candidate["candidate_id"], [])
        relation_trial_results[candidate["candidate_id"]] = record

    retrieval_fallbacks = [
        fallback
        for selection in selections
        for fallback in selection.get("retrieval_fallbacks", [])
    ]
    p = _deterministic("paper_selection")
    planned_deferrals = any(s.get('deferred_documents') or any(
        p.get('reader_text_deferred_source_unit_ids') for p in s.get('selected_papers', [])) for s in selections)
    for item in selections:
        for paper in item.get('selected_papers', []):
            if 'trial_facts' in paper:
                paper['trial_fact_provenance'] = {k: v for k, v in paper.pop('trial_facts').items() if k != 'units'}
    recorder.start("stage_8_paper_selection", p)
    recorder.finish("stage_8_paper_selection", p,
                    status="WARNING" if selection_failed_candidates or retrieval_fallbacks or planned_deferrals else "SUCCEEDED",
                    artifact_origin=em.GENERATED_NOW if select_papers_fn is None else replay_origin,
                    domain_event=ev.PAPER_SELECTED,
                    reason_codes=tuple((
                        (["SOURCEUNIT_SELECTION_FAILED"] if selection_failed_candidates else [])
                        + (["MEDCPT_RRF_FALLBACK_BM25_STRUCTURE"] if retrieval_fallbacks else [])
                        + (["DOCUMENT_OR_TEXT_WORK_DEFERRED"] if planned_deferrals else [])
                    )),
                    warnings=tuple(
                        f"NO_RELEVANT_SOURCE_UNIT:{candidate_id}"
                        for candidate_id in sorted(selection_failed_candidates)
                    ),
                    output_preview={"selections": selections,
                                    "max_papers_per_association": MAX_PAPERS_PER_ASSOCIATION,
                                    "max_source_units_per_paper": 5 if canonical else 4,
                "retrieval_strategy_requested": LIVE_RETRIEVAL_STRATEGY if canonical else "BM25_STRUCTURE_RECORDED_REPLAY",
                                    "recomputed_during_run": select_papers_fn is None},
                    metrics={"selection_wall_ms": sum(item.get("selection_wall_ms", 0) for item in selections),
                             "selection_cpu_ms": sum(item.get("selection_cpu_ms", 0) for item in selections)})

    enricher_producer = StageProducer(
        kind="LLM", component="paper_context_enricher_v3",
        version="paper-context-enricher/3.0",
        model=(enrichment_calls[0].get("model") if enrichment_calls else None) or "unknown",
        prompt_version=(enrichment_calls[0].get("prompt_version") if enrichment_calls else None) or "unknown",
        transport_version=(enrichment_calls[0].get("transport_version") if enrichment_calls else None),
    )
    recorder.start("stage_9_paper_context_enricher", enricher_producer)
    recorder.finish("stage_9_paper_context_enricher", enricher_producer,
                    status="WARNING" if budget_exhausted else "SUCCEEDED",
                    artifact_origin=(replay_origin if enrichment_calls else
                                     em.NOT_EXECUTED if budget_exhausted else em.NOT_APPLICABLE),
                    domain_event=ev.ENRICHMENT_PROPOSED,
                    reason_codes=(("CALL_BUDGET_EXCEEDED",) if budget_exhausted else
                                  () if enrichment_calls else ("NO_PAPER_SELECTED_FOR_ENRICHMENT",)),
                    output_preview={"calls": [
                        {k: v for k, v in call.items() if k != "raw_response"}
                        for call in enrichment_calls],
                                    "pending_requests": pending_reader_requests},
                    # ``enricher_calls`` conta le proposte prodotte, reali o
                    # rigiocate; ``real_llm_calls`` solo quelle che hanno
                    # davvero raggiunto il modello. In REPLAY la seconda è zero,
                    # e chiamarle entrambe "llm_calls" le rendeva indistinguibili.
                    metrics={"enricher_calls": len(enrichment_calls),
                             "real_llm_calls": reader_model_calls if canonical else 0,
                             "reused_reader_responses": reader_reuses,
                             "reader_transport_ms": sum(float(c.get("latency_ms") or 0) for c in enrichment_calls),
                             "retries": sum(int(c.get("retry_count") or 0) for c in enrichment_calls)})

    from backend.research_pipeline.enrichment.semantic_contract import POLICY_VERSION
    semantic_models = {item["model"] for item in semantic_attempts if item["model"]}
    semantic_prompts = {item["prompt_version"] for item in semantic_attempts if item["prompt_version"]}
    p = (StageProducer(kind="HYBRID", component="enrichment_validator", version=ORCHESTRATOR_VERSION,
                       model=next(iter(semantic_models)) if len(semantic_models) == 1 else None,
                       prompt_version=next(iter(semantic_prompts)) if len(semantic_prompts) == 1 else None)
         if semantic_attempts else _deterministic("enrichment_validator"))
    recorder.start("stage_10_enrichment_validation", p)
    recorder.finish("stage_10_enrichment_validation", p,
                    status="WARNING" if budget_exhausted else "SUCCEEDED",
                    artifact_origin=(
                        (em.GENERATED_NOW if validate_fn is None else replay_origin)
                        if validations else
                        em.NOT_EXECUTED if budget_exhausted else em.NOT_APPLICABLE
                    ),
                    domain_event=ev.ENRICHMENT_VALIDATED,
                    reason_codes=("CALL_BUDGET_EXCEEDED",) if budget_exhausted else (),
                    output_preview={
                        "validations": validations,
                        "pending_reader_requests": pending_reader_requests,
                        "semantic_verification": {
                            **semantic_attempt_summary(),
                            "policy_version": POLICY_VERSION,
                        },
                        "accepted_outcomes": list(_V1_ACCEPTED + _V2_ACCEPTED + _V3_ACCEPTED),
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
    relation_aware_report = dossier_mod.build_relation_aware_report(
        {**case_context, 'entity_resolution': retrieval_case_context.get('entity_resolution')},
        [association["candidate"] for association in retrieval_result["associations"]],
        paper_results=relation_paper_results,
        trial_results=relation_trial_results,
        run_status="PARTIAL" if budget_exhausted else "COMPLETED",
        retrieval_summary=retrieval_result.get("retrieval_summary"),
        extra_limitations=[
            f"INVALID_PROVENANCE:{candidate_id}" for candidate_id in invalid_candidate_ids
        ],
    )
    relation_aware_report["pipeline_accounting"] = build_pipeline_accounting(
        mention_accounting=(chain or {}).get("mention_accounting") or {},
        retrieval_result=retrieval_result,
        selections=selections,
        paper_results=relation_paper_results,
        trial_results=relation_trial_results,
        report=relation_aware_report,
        pending_reader_requests=pending_reader_requests,
    )
    relation_aware_report["pending_reader_requests"] = list(pending_reader_requests)
    from .dossier.observations import project_documentary_findings
    relation_aware_report = project_documentary_findings(relation_aware_report)
    relation_aware_report["source_unit_retrieval"] = {
        "version": "live-sourceunit-selector/3.0" if canonical else "recorded-sourceunit-selector",
        "requested_strategy": LIVE_RETRIEVAL_STRATEGY if canonical else "BM25_STRUCTURE_RECORDED_REPLAY",
        "strategies_used": sorted({
            strategy for selection in selections
            for strategy in selection.get("retrieval_strategy", [])
        }),
        "document_cap": MAX_PAPERS_PER_ASSOCIATION if canonical else None,
        "selected_document_count": sum(len(selection.get("selected_papers", [])) for selection in selections),
        "selected_source_unit_count": sum(
            len(paper.get("resolved_source_unit_ids", []))
            for selection in selections for paper in selection.get("selected_papers", [])
        ),
        "fallbacks": [
            {"candidate_id": selection.get("candidate_id"), **fallback}
            for selection in selections for fallback in selection.get("retrieval_fallbacks", [])
        ],
        "attempts": [
            {"candidate_id": selection.get("candidate_id"), **attempt}
            for selection in selections for attempt in selection.get("retrieval_attempts", [])
        ],
        "selections": [
            {"candidate_id": selection.get("candidate_id"),
             "retrieval_strategy": selection.get("retrieval_strategy", []),
             "documents": [{
                 "document_id": paper.get("document_id"),
                 "source_unit_ids": paper.get("resolved_source_unit_ids", []),
                 "retrieval_strategy": paper.get("retrieval_strategy"),
                 "fallback_reason": paper.get("retrieval_fallback_reason"),
                 "selector_version": paper.get("selector_version"),
                 "ranking_trace": paper.get("selector", {}).get("matched_features", {}).get("retrieval", {}),
             } for paper in selection.get("selected_papers", [])],
             "excluded_documents": [{
                 "document_id": paper.get("document_id"),
                 "reason_codes": paper.get("reason_codes", []),
                 "retrieval_strategy": paper.get("retrieval_strategy"),
                 "fallback_reason": paper.get("retrieval_fallback_reason"),
             } for paper in selection.get("excluded_papers", [])]}
            for selection in selections
        ],
    }
    # Documentary findings (including absent, negative or unresolved findings)
    # do not change technical execution completeness. Budget/unexecuted work
    # already determines run_status; reconciliation independently gates publication.
    # Accounting is a publication invariant, not a scientific support judgment.
    relation_aware_report = apply_publication_integrity(relation_aware_report)
    reconciliation = relation_aware_report["publication_integrity"]
    accounting_failed = reconciliation["reconciliation_status"] != "PASS"
    publication_incomplete = relation_aware_report["publication_status"] == "INCOMPLETE"
    accounting_reason_codes = list(reconciliation["reason_codes"])
    if accounting_failed and not accounting_reason_codes:
        accounting_reason_codes = ["RECONCILIATION_NOT_CONFIRMED_PASS"]
    elif publication_incomplete and not accounting_failed:
        accounting_reason_codes = ["PUBLICATION_INCOMPLETE_RUN_PARTIAL"]
    dossier = dossier_mod.build_dossier_preview(
        case_id, case_context,
        {"records": [r.to_dict() for r in records], "essential_fields_pass": essential_ok,
         "warnings": list(match_warnings)},
        candidate_therapies,
        limitations=["research_only_pilot",
                     "live_document_resolution_cache_first" if canonical else "no_new_document_fetched",
                     "gemma_used_only_as_enricher",
                     *( ["CALL_BUDGET_EXCEEDED"] if budget_exhausted else [] )],
    )
    # Il dossier completo, non solo i conteggi: ``GET /runs/{id}/dossier`` legge
    # questa preview, e senza il contenuto potrebbe soltanto dichiarare quante
    # candidate esistono — non mostrarle. Le tre sezioni che la UI deve tenere
    # separate (evidenza deterministica, author context, limitazioni) sono già
    # distinte nella struttura prodotta da ``build_dossier_preview``.
    recorder.finish("stage_13_dossier", p, domain_event=ev.DOSSIER_BUILT,
                    status="WARNING" if publication_incomplete else "SUCCEEDED",
                    reason_codes=tuple(accounting_reason_codes) if publication_incomplete else (),
                    output_preview={"candidate_count": len(candidate_therapies),
                                    "dossier": dossier,
                                    "relation_aware_report": relation_aware_report,
                                    "limitations": dossier["limitations"]})

    # STAGE 14-15 — Narrazione e verifica.
    #
    # Il dossier canonico **esiste già**: quanto segue produce una vista di
    # presentazione e non può modificarlo. Un fallimento qui non invalida la run
    # — attiva il fallback strutturato — perché la narrativa non è evidenza.
    if call_narrator_fn is not None and not budget_exhausted:
        # The relation-aware report is the single canonical source for
        # narrative projection and verification.  Keep the legacy preview
        # fields only as compatibility data for existing quote checks; they
        # are never used to build the narrator input.
        narrative_dossier = dict(relation_aware_report)
        narrative_dossier.update({
            "case_id": case_id,
            "case_context": case_context,
            "candidate_therapies": dossier.get("candidate_therapies", []),
            "provenance": dossier.get("provenance", {}),
        })
        narrator_budget_before = getattr(budget, 'used', 0)
        narrator_transports_before = len(getattr(budget, 'transport_attempts', ()))
        _narrate_and_verify(recorder, case_id, narrative_dossier, call_narrator_fn,
                            verify_narrative_fn, canonical, replay_origin,
                            narrative_verifier_mode)
        narrator_transports = len(getattr(budget, 'transport_attempts', ())) - narrator_transports_before
        llm_calls += narrator_transports or max(0, getattr(budget, 'used', 0) - narrator_budget_before)
    elif call_narrator_fn is not None and budget_exhausted:
        narrator_producer = StageProducer(
            kind="LLM", component="dossier_narrator",
            version=narrative_prompt.NARRATOR_PROMPT_VERSION,
            model="not_executed", prompt_version=narrative_prompt.NARRATOR_PROMPT_VERSION,
        )
        recorder.finish(
            "stage_14_narrator", narrator_producer, status="SKIPPED",
            artifact_origin=em.NOT_EXECUTED,
            reason_codes=("CALL_BUDGET_EXCEEDED",),
        )
        recorder.finish(
            "stage_15_narrative_verifier",
            _deterministic("narrative_verifier", narrative_verifier.VERIFIER_VERSION),
            status="SKIPPED", artifact_origin=em.NOT_EXECUTED,
            reason_codes=("CALL_BUDGET_EXCEEDED",),
        )
    else:
        narrator_producer = StageProducer(
            kind="LLM", component="dossier_narrator",
            version=narrative_prompt.NARRATOR_PROMPT_VERSION,
            model="not_configured", prompt_version=narrative_prompt.NARRATOR_PROMPT_VERSION,
        )
        recorder.finish(
            "stage_14_narrator", narrator_producer, status="SKIPPED",
            artifact_origin=em.NOT_EXECUTED,
            reason_codes=("NARRATOR_NOT_CONFIGURED",),
        )
        recorder.finish(
            "stage_15_narrative_verifier",
            _deterministic("narrative_verifier", narrative_verifier.VERIFIER_VERSION),
            status="SKIPPED", artifact_origin=em.NOT_EXECUTED,
            reason_codes=("NARRATOR_NOT_CONFIGURED",),
        )

    has_warning = any(stage.status == "WARNING" for stage in recorder.stages)
    if narrative_verifier_mode == "OFFLINE_ABLATION_BYPASS":
        has_warning = True
    return _finalize(
        "PARTIAL" if has_warning or budget_exhausted else "COMPLETED",
        "CALL_BUDGET_EXCEEDED" if budget_exhausted else None,
        dossier_id=case_id, relation_aware_report=relation_aware_report,
    )
