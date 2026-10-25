"""Costruzione delle due run verificabili sopra lo strato di controllo comune.

Entrambe le architetture passano da qui e da ``run_verified_pipeline``: la
scelta della strategia di raccolta è l'unica variazione. Non esiste più un
percorso deterministico che termina con la sola sintesi LLM e il filtro PMID.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from backend.api.schemas import ArchitectureComparisonRequest, ArchitectureRun, TraceStep
from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.control.contracts import CaseContext
from backend.pipeline.control.metrics import build_metrics, llm_roles
from backend.pipeline.control.recorder import ActionRecorder
from backend.pipeline.control.runner import PipelineResult, run_verified_pipeline
from backend.pipeline.control.strategies.agentic_plan import AgenticPlanStrategy
from backend.pipeline.control.strategies.fixed_plan import FixedPlanStrategy
from backend.pipeline.control.verification.source_port import (
    PubMedSourceVerifier,
    SourceVerifierPort,
)

TITLES = {
    "deterministic": (
        "GraphRAG deterministico verificabile",
        "Piano fisso e traversal tipizzato, seguiti dallo strato comune di "
        "provenienza, verifica e applicabilità.",
    ),
    "agentic": (
        "Agentic GraphRAG verificabile",
        "Planner adattivo e strumenti tipizzati, seguiti dal medesimo strato comune "
        "di provenienza, verifica e applicabilità.",
    ),
}


def default_tools() -> dict[str, Any]:
    from backend.pipeline.agents.complexity_check import complexity_check
    from backend.pipeline.agents.oncokb_enricher import oncokb_enricher
    from backend.pipeline.agents.resistance_checker import resistance_checker
    from backend.pipeline.agents.target_identifier import target_identifier
    from backend.pipeline.agents.trial_matcher import trial_matcher
    from backend.pipeline.agents.variant_interpreter import variant_interpreter_low

    return {
        "assess_complexity": complexity_check,
        "interpret_variant": variant_interpreter_low,
        "identify_targets": target_identifier,
        "match_trials": trial_matcher,
        "check_resistance": resistance_checker,
        "enrich_oncokb": oncokb_enricher,
    }


def build_run(
    req: ArchitectureComparisonRequest,
    architecture_id: str,
    *,
    tools: dict[str, Any] | None = None,
    source_verifier: SourceVerifierPort | None = None,
    ledger: EventLedger | None = None,
    planner_llm: Any | None = None,
    build_dossier: Callable[..., Any],
    build_claim_checks: Callable[..., list],
    render_verified: Callable[..., str],
) -> tuple[ArchitectureRun, PipelineResult]:
    """Esegue una delle due architetture e la adatta al modello dell'API."""
    from backend.pipeline.agentic.runtime import mandatory_tools_for_goal

    case = CaseContext.from_request(req)
    strategy = (
        FixedPlanStrategy()
        if architecture_id == "deterministic"
        else AgenticPlanStrategy(planner_llm)
    )
    recorder = ActionRecorder(ledger or EventLedger())

    started = perf_counter()
    result = run_verified_pipeline(
        case,
        strategy,
        recorder=recorder,
        tools=tools or default_tools(),
        source_verifier=source_verifier or PubMedSourceVerifier(),
        build_dossier=lambda items, checks, **kw: build_dossier(req, items, checks, **kw),
        build_claim_checks=build_claim_checks,
        render_verified=render_verified,
        mandatory_tools=mandatory_tools_for_goal(case.mtb_goal),
    )
    elapsed = int((perf_counter() - started) * 1000)

    title, subtitle = TITLES[architecture_id]
    return (
        ArchitectureRun(
            architecture_id=architecture_id,  # type: ignore[arg-type]
            title=title,
            subtitle=subtitle,
            llm_roles=llm_roles(result),
            trace=build_trace(result),
            evidence=list(result.evidence_items),
            report=result.report,
            dossier=result.dossier,
            claim_checks=list(result.claim_checks),
            metrics=build_metrics(result, elapsed_ms=elapsed),
            limitations=build_limitations(result),
            run_id=result.run_id,
            ledger_valid=result.ledger_valid,
            planning_mode=result.collection.planning_mode,
            fallback_reason=result.collection.fallback_reason,
            planner_attempts=result.collection.planner_calls,
            planner_elapsed_ms=result.collection.planner_elapsed_ms,
            tool_call_timings=[dict(t) for t in result.collection.tool_call_timings],
        ),
        result,
    )


def build_trace(result: PipelineResult) -> list[TraceStep]:
    """Trace costruita dai fatti della run, identica in struttura per entrambe.

    Nessuno stadio viene dichiarato se non è stato eseguito: la riparazione
    compare come 'non necessaria' quando non è servita, non come fase svolta.
    """
    collection = result.collection
    orchestration_detail = (
        f"Piano fisso dichiarato prima dell'esecuzione: {', '.join(collection.tool_path)}."
        if result.orchestration_mode == "deterministic"
        else _agentic_orchestration_detail(collection)
    )

    steps = [
        ("Normalizzazione", "Input adapter", "Caso convertito nel contesto clinico canonico."),
        ("Orchestrazione della raccolta",
         "Controller a piano fisso" if result.orchestration_mode == "deterministic" else "Planner LLM",
         orchestration_detail),
        ("Event log append-only", "Ledger",
         f"{len(result.events)} eventi con hash-chain "
         f"{'valida' if result.ledger_valid else 'non valida'}."),
        ("Vista canonica (replay)", "Canonicalizer",
         f"{result.canonical_view.records_in} record osservati ridotti a "
         f"{result.canonical_view.records_out}, genealogia conservata; "
         f"fedeltà {result.canonical_view.replay_fidelity}."),
        ("Proiezione pertinente", "Projector",
         f"{len(result.projection.admitted)} record ammessi, "
         f"{len(result.projection.excluded)} esclusi con motivazione."),
        ("Rendering candidato", "Renderer deterministico",
         f"Report candidato reso dalla proiezione ({len(result.candidate_report)} caratteri)."),
        ("Verifica strutturale del candidato", "Structural verifier",
         _verdict_detail(result.candidate_verdict)),
        ("Verifica claim–fonte", "Source verifier",
         f"{len(result.evidence_items)} claim valutate sul supporto documentale "
         f"(modello {result.source_outcome.model_revision})."),
        ("Valutazione di applicabilità", "Applicability validator",
         "Applicabilità al caso valutata separatamente dal supporto documentale."),
        ("Riparazione bounded", "Repair planner", _repair_detail(result)),
        ("Rendering verificato", "Renderer deterministico",
         _verdict_detail(result.final_verdict)),
        ("Dossier per la revisione MTB", "Dossier builder",
         _verdict_detail(result.dossier_verdict)),
    ]

    return [
        TraceStep(
            order=index,
            stage=stage,
            actor=actor,
            detail=detail,
            status=_step_status(stage, result),
        )
        for index, (stage, actor, detail) in enumerate(steps, start=1)
    ]


def _agentic_orchestration_detail(collection: Any) -> str:
    if collection.planning_mode == "safe_fallback":
        # Una run passata al percorso sicuro non va descritta come
        # pianificazione dinamica: questa esecuzione non dimostra
        # pianificazione agentica dinamica.
        return (
            f"Il planner non ha prodotto decisioni utilizzabili ({collection.fallback_reason}); "
            "la raccolta ha usato l'ordine tipizzato sicuro. Questa esecuzione non "
            "dimostra pianificazione agentica dinamica."
        )
    return (
        f"Il planner ha scelto iterativamente gli strumenti in {collection.planner_calls} "
        f"decisioni: {', '.join(collection.tool_path)}."
    )


def _verdict_detail(verdict: Any) -> str:
    if verdict.status == "pass":
        return f"Nessuna violazione; copertura {verdict.coverage:.0%}."
    codes = ", ".join(sorted({v.code for v in verdict.violations}))
    return f"Violazioni rilevate ({codes}); copertura {verdict.coverage:.0%}."


def _repair_detail(result: PipelineResult) -> str:
    if not result.repair_actions:
        return "Nessuna riparazione necessaria: la verifica del candidato non ha rilevato omissioni recuperabili."
    action = result.repair_actions[0]
    kind = "rigenerazione del report" if action.kind == "rendering" else f"nuova azione su {action.tool_name}"
    return f"Un ciclo di riparazione eseguito ({kind}), motivato da {', '.join(action.triggered_by)}."


def _step_status(stage: str, result: PipelineResult) -> str:
    if stage == "Riparazione bounded" and result.escalation is not None:
        return "blocked"
    if stage.startswith("Verifica strutturale") and result.candidate_verdict.violations:
        return "warning"
    if stage == "Rendering verificato" and result.final_verdict.violations:
        return "warning"
    return "completed"


def build_limitations(result: PipelineResult) -> list[str]:
    limitations = [
        "Prototipo di ricerca: il dossier è un artefatto destinato alla revisione del "
        "Molecular Tumor Board, non una raccomandazione terapeutica.",
        "Il ledger è append-only e tamper-evident nel threat model considerato "
        "(trigger di riga e hash-chain), non immutabile in senso assoluto.",
    ]
    if result.collection.missing_mandatory_tools:
        limitations.append(
            "Strumenti obbligatori non completati per l'obiettivo MTB: "
            + ", ".join(result.collection.missing_mandatory_tools) + "."
        )
    if result.collection.planning_mode == "safe_fallback":
        limitations.append(
            "La raccolta è passata al percorso sicuro: questa esecuzione non dimostra "
            "pianificazione agentica dinamica."
        )
    if result.canonical_view.replay_fidelity != "full":
        limitations.append(
            f"Fedeltà del replay ridotta ({result.canonical_view.replay_fidelity}): "
            "parte degli eventi non è pienamente ricostruibile."
        )
    if result.escalation is not None:
        limitations.append(
            f"Escalation alla revisione umana: {result.escalation.detail}"
        )
    if result.collection.errors:
        limitations.append("Errori durante la raccolta: " + "; ".join(result.collection.errors))
    return limitations
