"""Costruzione delle metriche, unica per entrambe le architetture.

``build_metrics`` non ha argomenti oltre al risultato della pipeline: per
costruzione non può più esistere un valore letterale come i vecchi
``tool_calls=1/4/5``, che rendevano il confronto una comparazione fra una
costante e una misura.
"""

from __future__ import annotations

from typing import Any

from backend.pipeline.control.runner import PipelineResult


def _support_counts(result: PipelineResult) -> dict[str, int]:
    counts = {
        "supported_as_written": 0,
        "supported_after_contextualization": 0,
        "uncertain": 0,
        "contradicted": 0,
    }
    for verification in result.source_outcome.verifications:
        key = str(getattr(verification, "source_support_status", "uncertain"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _applicability_counts(result: PipelineResult) -> dict[str, int]:
    counts = {"compatible": 0, "indeterminate": 0, "not_compatible": 0}
    for verification in result.source_outcome.verifications:
        key = str(getattr(verification, "applicability_status", "indeterminate"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_metrics(result: PipelineResult, *, elapsed_ms: int) -> Any:
    """Costruisce ``ArchitectureMetrics`` da una run, senza letterali."""
    from backend.api.schemas import ArchitectureMetrics

    support = _support_counts(result)
    applicability = _applicability_counts(result)
    telemetry = result.telemetry
    collection = result.collection

    retrieval_calls = len(collection.tool_path) + sum(
        1 for action in result.repair_actions if action.kind == "collection"
    )
    supported_total = (
        support["supported_as_written"] + support["supported_after_contextualization"]
    )

    return ArchitectureMetrics(
        elapsed_ms=elapsed_ms,
        # Alias deprecato mantenuto per i consumatori esistenti; il nuovo
        # frontend legge retrieval_tool_calls. Non è più un letterale.
        tool_calls=retrieval_calls,
        retrieval_tool_calls=retrieval_calls,
        planner_calls=collection.planner_calls,
        llm_synthesis_calls=1 if result.narration_applied else 0,
        source_verifier_calls=telemetry.llm_calls,
        pipeline_nodes_executed=result.pipeline_nodes_executed,
        repair_attempts=result.repair_attempts,
        evidence_count=len(result.evidence_items),
        verified_claims=supported_total,
        blocked_claims=support["contradicted"],
        review_claims=support["uncertain"],
        ledger_events=len(result.events),
        ledger_valid=result.ledger_valid,
        stage_timings_ms=result.timings_dict(),
        planning_mode=collection.planning_mode,
        fallback_reason=collection.fallback_reason,
        mandatory_tools=list(collection.mandatory_tools),
        missing_mandatory_tools=list(collection.missing_mandatory_tools),
        source_supported_count=supported_total,
        source_uncertain_count=support["uncertain"],
        source_unsupported_count=support["contradicted"],
        source_supported_as_written_count=support["supported_as_written"],
        source_supported_after_contextualization_count=support[
            "supported_after_contextualization"
        ],
        applicability_compatible_count=applicability["compatible"],
        applicability_indeterminate_count=applicability["indeterminate"],
        applicability_not_compatible_count=applicability["not_compatible"],
        structural_coverage=round(result.final_verdict.coverage, 4),
        structural_violations=len(result.final_verdict.violations)
        + len(result.dossier_verdict.violations),
        structural_warnings=len(result.final_verdict.warnings),
        spurious_citations=len(result.final_verdict.spurious_citations),
        canonical_records_in=result.canonical_view.records_in,
        canonical_records_out=result.canonical_view.records_out,
        canonical_conflicts=sum(
            len(record.conflict_annotations) for record in result.canonical_view.records
        ),
        projection_admitted=len(result.projection.admitted),
        projection_excluded=len(result.projection.excluded),
        replay_fidelity=result.canonical_view.replay_fidelity,
        escalated=result.escalation is not None,
        model_revision=result.source_outcome.model_revision,
        prompt_version=result.source_outcome.prompt_version,
        cache_hits=telemetry.cache_hits,
        cache_misses=telemetry.cache_misses,
        verifier_batches=telemetry.verifier_batches,
        failed_batches=telemetry.failed_batches,
        retry_items=telemetry.retry_items,
        recovered_items=telemetry.recovered_items,
        permanently_failed_items=telemetry.permanently_failed_items,
        source_profile_elapsed_ms=telemetry.source_profile_elapsed_ms,
        applicability_elapsed_ms=telemetry.applicability_elapsed_ms,
    )


def llm_roles(result: PipelineResult) -> list[str]:
    """Ruoli LLM **effettivamente eseguiti** in questa run.

    Prima era una lista hard-coded per architettura, che dichiarava un
    "narratore opzionale post-verifica" anche nelle run in cui la narrazione
    non veniva mai eseguita.
    """
    roles: list[str] = []
    if result.collection.planner_calls > 0:
        roles.append("Planner della raccolta")
    if result.source_outcome.verifications:
        roles.append("Source verifier semantico")
    if result.narration_applied:
        roles.append("Narratore post-verifica")
    return roles
