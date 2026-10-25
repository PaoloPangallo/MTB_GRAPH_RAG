"""Il seam: pipeline verificabile condivisa dalle due architetture.

Dopo ``strategy.collect()`` il runner non legge più lo stato della strategia
per costruire la vista: la vista canonica nasce dal **replay del ledger**. È
questo a rendere la verificabilità una proprietà controllabile dall'esterno,
non una dichiarazione della pipeline su sé stessa.

Un solo ``ActionRecorder`` per esecuzione, condiviso con la strategia: una
catena, un ``run_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

from backend.pipeline.control import events as E
from backend.pipeline.control.contracts import (
    CanonicalView,
    CaseContext,
    Escalation,
    Projection,
    RepairAction,
    StageTiming,
    StructuralVerdict,
    stage_timings_dict,
)
from backend.pipeline.control.projection import (
    evidence_items_from,
    project_for_case,
    projection_payload,
)
from backend.pipeline.control.recorder import ActionRecorder
from backend.pipeline.control.rendering.candidate import candidate_payload, render_candidate
from backend.pipeline.control.repair import (
    CollectionRepairPlanner,
    RenderingRepairPlanner,
    escalation_for,
    execute_repair,
)
from backend.pipeline.control.replay import replay_to_canonical_view
from backend.pipeline.control.strategies.protocol import (
    CollectionContext,
    CollectionOutcome,
    CollectionStrategy,
)
from backend.pipeline.control.verification.dossier_invariants import DossierInvariantVerifier
from backend.pipeline.control.verification.source_port import (
    SourceVerificationOutcome,
    SourceVerifierPort,
    VerifierTelemetry,
    build_case_context,
)
from backend.pipeline.control.verification.structural_text import TextStructuralVerifier


@dataclass(frozen=True)
class PipelineResult:
    """Esito completo di una run, sufficiente a costruire metriche e trace."""

    run_id: str
    architecture_id: str
    orchestration_mode: str
    case: CaseContext
    collection: CollectionOutcome
    canonical_view: CanonicalView
    projection: Projection
    candidate_report: str
    candidate_verdict: StructuralVerdict
    final_verdict: StructuralVerdict
    dossier_verdict: StructuralVerdict
    source_outcome: SourceVerificationOutcome
    report: str
    dossier: Any = None
    claim_checks: tuple[Any, ...] = ()
    evidence_items: tuple[Any, ...] = ()
    repair_attempts: int = 0
    repair_actions: tuple[RepairAction, ...] = ()
    escalation: Escalation | None = None
    narration_verdict: StructuralVerdict | None = None
    narration_applied: bool = False
    events: tuple[Mapping[str, Any], ...] = ()
    ledger_valid: bool = False
    stage_timings: tuple[StageTiming, ...] = ()
    pipeline_nodes_executed: int = 0

    @property
    def telemetry(self) -> VerifierTelemetry:
        return self.source_outcome.telemetry

    def timings_dict(self) -> dict[str, int]:
        return stage_timings_dict(self.stage_timings)


class _Clock:
    """Accumula i tempi per fase senza sparpagliare perf_counter nel runner."""

    def __init__(self) -> None:
        self.timings: list[StageTiming] = []
        self.nodes = 0

    def measure(self, stage: str, fn: Callable[[], Any]) -> Any:
        started = perf_counter()
        try:
            return fn()
        finally:
            self.timings.append(StageTiming(stage, int((perf_counter() - started) * 1000)))
            self.nodes += 1


def run_verified_pipeline(
    case: CaseContext,
    strategy: CollectionStrategy,
    *,
    recorder: ActionRecorder,
    tools: Mapping[str, Any],
    source_verifier: SourceVerifierPort,
    build_dossier: Callable[..., Any],
    build_claim_checks: Callable[[Sequence[Any], Sequence[Any]], list[Any]],
    render_verified: Callable[[str, Sequence[Any], Sequence[Any]], str],
    mandatory_tools: Sequence[str] = (),
    max_repair_cycles: int = 1,
    narration: Callable[[str], str] | None = None,
) -> PipelineResult:
    """Esegue raccolta + strato di controllo condiviso e restituisce l'esito."""
    clock = _Clock()
    text_verifier = TextStructuralVerifier()
    dossier_verifier = DossierInvariantVerifier()

    # --- Raccolta: l'unica fase che differisce fra le due architetture ---
    ctx = CollectionContext(
        case=case, recorder=recorder, tools=tools,
        mandatory_tools=tuple(mandatory_tools),
    )
    collection: CollectionOutcome = clock.measure("collection", lambda: strategy.collect(ctx))

    def build_view() -> tuple[CanonicalView, Projection, str, StructuralVerdict]:
        view = clock.measure(
            "replay", lambda: replay_to_canonical_view(recorder.events())
        )
        recorder.record(E.CANONICAL_VIEW_CREATED, E.ACTOR_CANONICALIZER, {
            "records_in": view.records_in,
            "records_out": view.records_out,
            "replay_fidelity": view.replay_fidelity,
            "completeness_status": view.completeness_status,
            "conflicts": sum(len(r.conflict_annotations) for r in view.records),
        })
        projection = clock.measure("projection", lambda: project_for_case(view, case))
        recorder.record(
            E.PROJECTION_CREATED, E.ACTOR_PROJECTOR, projection_payload(projection)
        )
        report = clock.measure("candidate_rendering", lambda: render_candidate(projection))
        recorder.record(
            E.CANDIDATE_REPORT_RENDERED, E.ACTOR_RENDERER,
            candidate_payload(projection, report),
        )
        verdict = clock.measure(
            "structural_verification",
            lambda: text_verifier.verify_candidate(projection, report),
        )
        recorder.record(
            E.STRUCTURAL_VERIFICATION_COMPLETED, E.ACTOR_STRUCTURAL_VERIFIER,
            E.structural_verification_payload(verdict),
        )
        return view, projection, report, verdict

    view, projection, candidate_report, candidate_verdict = build_view()

    # --- Riparazione bounded: al massimo un ciclo, contato qui ---
    repair_attempts = 0
    repair_actions: list[RepairAction] = []
    escalation: Escalation | None = None

    if max_repair_cycles > 0:
        action = _plan_repair(
            candidate_verdict, projection, recorder.events(),
            collection.missing_mandatory_tools, attempt=repair_attempts,
        )
        if action is not None:
            repair_actions.append(action)
            recorder.record(E.REPAIR_PLANNED, E.ACTOR_REPAIR_PLANNER, {
                "kind": action.kind,
                "tool_name": action.tool_name,
                "rationale": action.rationale,
                "triggered_by": list(action.triggered_by),
                "target_record_ids": list(action.target_record_ids),
            })

            def apply_repair() -> None:
                if action.kind == "collection":
                    # Solo la riparazione di raccolta può richiamare strumenti.
                    new_state = execute_repair(action, tools, collection.terminal_state)
                    _record_repair_tool(recorder, action, new_state)
                recorder.record(E.REPAIR_EXECUTED, E.ACTOR_REPAIR_PLANNER, {
                    "kind": action.kind, "triggered_by": list(action.triggered_by),
                })

            try:
                clock.measure("repair", apply_repair)
                repair_attempts = 1
                # Replay dell'intera lista eventi: la vista riparata si
                # ricostruisce da zero, senza patch incrementali che possano
                # far divergere vista e ledger.
                view, projection, candidate_report, candidate_verdict = build_view()
            except Exception as exc:  # noqa: BLE001 - sanitizzata nel ledger
                recorder.record_error(
                    E.REPAIR_FAILED, E.ACTOR_REPAIR_PLANNER,
                    f"Riparazione non riuscita: {type(exc).__name__}.",
                    category="repair_error",
                )
                repair_attempts = 1

    # --- Verifica documentale e applicabilità: identiche per le due architetture ---
    evidence_items = evidence_items_from(projection)
    source_outcome: SourceVerificationOutcome = clock.measure(
        "source_verification",
        lambda: source_verifier.verify(evidence_items, build_case_context(case)),
    )
    verifications = list(source_outcome.verifications)
    recorder.record(E.SOURCE_VERIFICATION_COMPLETED, E.ACTOR_SOURCE_VERIFIER, {
        "items": len(evidence_items),
        "model_revision": source_outcome.model_revision,
        "prompt_version": source_outcome.prompt_version,
        "support_counts": _count(verifications, "source_support_status"),
    })
    recorder.record(E.APPLICABILITY_EVALUATED, E.ACTOR_SOURCE_VERIFIER, {
        "applicability_counts": _count(verifications, "applicability_status"),
    })

    claim_checks = clock.measure(
        "applicability", lambda: build_claim_checks(evidence_items, verifications)
    )

    report = clock.measure(
        "final_rendering",
        lambda: render_verified(projection.case_label, evidence_items, verifications),
    )
    recorder.record(E.VERIFIED_REPORT_RENDERED, E.ACTOR_RENDERER, {
        "characters": len(report), "claims": len(evidence_items),
    })

    final_verdict = clock.measure(
        "structural_verification",
        lambda: text_verifier.verify_final(projection, report, verifications),
    )
    recorder.record(
        E.STRUCTURAL_VERIFICATION_COMPLETED, E.ACTOR_STRUCTURAL_VERIFIER,
        E.structural_verification_payload(final_verdict),
    )

    dossier = clock.measure(
        "dossier",
        lambda: build_dossier(evidence_items, claim_checks, verifications=verifications,
                              state=collection.terminal_state),
    )
    dossier_verdict = dossier_verifier.verify(projection, verifications, dossier)
    recorder.record(
        E.DOSSIER_BUILT, E.ACTOR_STRUCTURAL_VERIFIER,
        E.structural_verification_payload(dossier_verdict),
    )

    # --- Narrazione opzionale, disattivata di default ---
    narration_verdict: StructuralVerdict | None = None
    narration_applied = False
    if narration is not None:
        narrated = narration(report)
        narration_verdict = text_verifier.verify_final(
            projection, narrated, verifications, stage="narration"
        )
        recorder.record(
            E.NARRATION_RENDERED, E.ACTOR_RENDERER,
            E.structural_verification_payload(narration_verdict),
        )
        # Una narrazione che non supera la verifica non entra nel dossier né
        # sostituisce il report controllato.
        if narration_verdict.status == "pass":
            report = narrated
            narration_applied = True

    combined = final_verdict.merged_with(dossier_verdict)
    if combined.requires_human_review or combined.requires_repair:
        escalation = escalation_for(combined, attempted=repair_attempts > 0)
        recorder.record(E.ESCALATION_RAISED, E.ACTOR_CONTROLLER, {
            "reason_category": escalation.reason_category,
            "detail": escalation.detail,
            "triggered_by": list(escalation.triggered_by),
        })

    recorder.record(E.RUN_COMPLETED, E.ACTOR_CONTROLLER, {
        "orchestration_mode": strategy.orchestration_mode,
        "tool_path": list(collection.tool_path),
        "repair_attempts": repair_attempts,
        "escalated": escalation is not None,
    })

    return PipelineResult(
        run_id=recorder.run_id,
        architecture_id=strategy.architecture_id,
        orchestration_mode=strategy.orchestration_mode,
        case=case,
        collection=collection,
        canonical_view=view,
        projection=projection,
        candidate_report=candidate_report,
        candidate_verdict=candidate_verdict,
        final_verdict=final_verdict,
        dossier_verdict=dossier_verdict,
        source_outcome=source_outcome,
        report=report,
        dossier=dossier,
        claim_checks=tuple(claim_checks),
        evidence_items=tuple(evidence_items),
        repair_attempts=repair_attempts,
        repair_actions=tuple(repair_actions),
        escalation=escalation,
        narration_verdict=narration_verdict,
        narration_applied=narration_applied,
        events=tuple(recorder.events()),
        ledger_valid=recorder.chain_valid(),
        stage_timings=tuple(clock.timings),
        pipeline_nodes_executed=clock.nodes,
    )


def _plan_repair(
    verdict: StructuralVerdict,
    projection: Projection,
    events: Sequence[Mapping[str, Any]],
    missing_mandatory: Sequence[str],
    *,
    attempt: int,
) -> RepairAction | None:
    """Sceglie il regime di riparazione. La raccolta ha la precedenza.

    Se mancano dati, rigenerare il testo non servirebbe: si recuperano prima i
    dati. Se i dati ci sono, un difetto di rendering non giustifica una nuova
    interrogazione del grafo.
    """
    collection_action = CollectionRepairPlanner().plan(
        verdict, projection, attempt=attempt,
        events=events, missing_mandatory=missing_mandatory,
    )
    if collection_action is not None:
        return collection_action
    return RenderingRepairPlanner().plan(verdict, projection, attempt=attempt)


def _record_repair_tool(
    recorder: ActionRecorder, action: RepairAction, state: Mapping[str, Any]
) -> None:
    from backend.pipeline.control.strategies.tool_registry import (
        records_from_state,
        tool_version,
    )

    tool = str(action.tool_name)
    action_id = recorder.new_action_id()
    recorder.record(
        E.TOOL_STARTED, tool, {"repair": True},
        action_id=action_id, tool_name=tool, tool_version=tool_version(tool),
        query_or_arguments=dict(action.arguments),
    )
    record_kind, records = records_from_state(tool, state)
    payload = E.tool_completed_payload(tool=tool, record_kind=record_kind, records=records)
    payload["repair"] = True
    recorder.record(
        E.TOOL_COMPLETED, tool, payload,
        action_id=recorder.new_action_id(), parent_action_id=action_id,
        tool_name=tool, tool_version=tool_version(tool),
        query_or_arguments=dict(action.arguments),
        completeness_status=payload["completeness_status"],
    )


def _count(verifications: Sequence[Any], attribute: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for verification in verifications:
        key = str(getattr(verification, attribute, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return counts
