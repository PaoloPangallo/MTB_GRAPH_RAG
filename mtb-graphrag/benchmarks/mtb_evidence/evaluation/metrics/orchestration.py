"""Metriche di orchestrazione: come il percorso e' stato scelto ed eseguito.

Calcolate separatamente per categoria di caso, perche' la domanda cambia. Su
KNOWN_TRAVERSAL la questione e' se il percorso fisso basti; su ADAPTIVE se il
planner sappia diramare; su NO_ANSWER se sappia fermarsi. Aggregarle produrrebbe un
numero che non risponde a nessuna delle tre.
"""

from __future__ import annotations

from statistics import median
from typing import Mapping, Sequence

from ..contracts import ClinicalGoldCase, MetricResult, RetrievalPrediction

CATEGORY_KNOWN = "KNOWN_TRAVERSAL"
CATEGORY_ADAPTIVE = "ADAPTIVE"
CATEGORY_CONTEXT = "CONTEXT_OR_CONFLICT"
CATEGORY_NO_ANSWER = "NO_ANSWER_OR_INSUFFICIENT"

CATEGORIES = (CATEGORY_KNOWN, CATEGORY_ADAPTIVE, CATEGORY_CONTEXT, CATEGORY_NO_ANSWER)


def task_completion(case: ClinicalGoldCase, prediction: RetrievalPrediction) -> MetricResult:
    """Il compito e' completo se tutti gli strumenti obbligatori sono stati usati.

    Per un caso di astensione il completamento e' l'astensione stessa: aver eseguito
    piu' strumenti non lo rende piu' completo.
    """
    if case.expected_abstention:
        complete = prediction.abstained
        return MetricResult(
            name="task_completion",
            numerator=1.0 if complete else 0.0,
            denominator=1.0,
            notes=("caso di astensione: il completamento e' l'astensione",),
        )
    required = set(case.required_tools)
    called = set(prediction.tools_called)
    return MetricResult(
        name="task_completion",
        numerator=1.0 if required <= called else 0.0,
        denominator=1.0,
        missing_items=tuple(sorted(required - called)),
    )


def conditional_step_accuracy(
    case: ClinicalGoldCase, prediction: RetrievalPrediction
) -> MetricResult:
    """Diramazione corretta rispetto al piano condizionale dichiarato dal caso.

    Ha senso solo dove il gold prevede un ramo: sui casi a percorso noto ogni
    esecuzione conforme e' banalmente corretta, e includerli gonfierebbe il valore.
    """
    if case.category != CATEGORY_ADAPTIVE:
        return MetricResult(
            name="conditional_step_accuracy",
            numerator=0.0,
            denominator=0.0,
            notes=(f"categoria {case.category}: nessun ramo condizionale da valutare",),
        )
    required = set(case.required_tools)
    called = set(prediction.tools_called)
    unnecessary = set(case.unnecessary_tools)
    correct = required <= called and not (called & unnecessary)
    return MetricResult(
        name="conditional_step_accuracy",
        numerator=1.0 if correct else 0.0,
        denominator=1.0,
        missing_items=tuple(sorted(required - called)),
        notes=(f"strumenti superflui invocati: {sorted(called & unnecessary)}",),
    )


def stop_condition_accuracy(
    case: ClinicalGoldCase, prediction: RetrievalPrediction
) -> MetricResult:
    """Il sistema si ferma quando deve, e non prima."""
    if case.expected_abstention:
        correct = prediction.abstained
    else:
        correct = not prediction.abstained and bool(prediction.tools_called)
    return MetricResult(
        name="stop_condition_accuracy",
        numerator=1.0 if correct else 0.0,
        denominator=1.0,
        notes=(
            f"astensione attesa={case.expected_abstention}, "
            f"osservata={prediction.abstained}",
        ),
    )


def valid_action_rate(
    actions: Sequence[Mapping[str, object]], known_tools: Sequence[str]
) -> MetricResult:
    """Quota di azioni del planner che nominano uno strumento esistente.

    Un'azione che invoca uno strumento inesistente non e' una scelta discutibile: e'
    un output non eseguibile, e va contato prima di qualunque giudizio di merito.
    """
    if not actions:
        return MetricResult(
            name="valid_action_rate",
            numerator=0.0,
            denominator=0.0,
            notes=("nessuna azione registrata: il planner non e' stato invocato",),
        )
    allowed = set(known_tools)
    valid = [
        action for action in actions if str(action.get("tool") or "") in allowed
    ]
    return MetricResult(
        name="valid_action_rate",
        numerator=len(valid),
        denominator=len(actions),
        missing_items=tuple(
            str(action.get("tool") or "?")
            for action in actions
            if str(action.get("tool") or "") not in allowed
        ),
    )


def planner_failure_rate(runs: Sequence[Mapping[str, object]]) -> MetricResult:
    failed = [run for run in runs if run.get("planner_failed")]
    return MetricResult(
        name="planner_failure_rate",
        numerator=len(failed),
        denominator=max(len(runs), 1) if runs else 0,
        missing_items=tuple(str(run.get("run_id") or "?") for run in failed),
    )


def fallback_rate(runs: Sequence[Mapping[str, object]]) -> MetricResult:
    fell_back = [run for run in runs if run.get("used_fallback")]
    return MetricResult(
        name="fallback_rate",
        numerator=len(fell_back),
        denominator=max(len(runs), 1) if runs else 0,
        missing_items=tuple(str(run.get("run_id") or "?") for run in fell_back),
    )


def run_to_run_agreement(outputs: Sequence[object]) -> MetricResult:
    """Quota di run che concordano con l'esito piu' frequente.

    Con tre seed il valore puo' valere solo 1/3, 2/3 o 1: va letto come indicatore
    grezzo di stabilita', non come una stima di varianza.
    """
    if len(outputs) < 2:
        return MetricResult(
            name="run_to_run_agreement",
            numerator=0.0,
            denominator=0.0,
            notes=("meno di due run: accordo non calcolabile",),
        )
    counts: dict[str, int] = {}
    for output in outputs:
        key = repr(output)
        counts[key] = counts.get(key, 0) + 1
    return MetricResult(
        name="run_to_run_agreement",
        numerator=max(counts.values()),
        denominator=len(outputs),
        notes=(f"{len(counts)} esiti distinti su {len(outputs)} run",),
    )


def median_planner_latency(latencies_ms: Sequence[float]) -> MetricResult:
    if not latencies_ms:
        return MetricResult(
            name="median_planner_latency_ms",
            numerator=0.0,
            denominator=0.0,
            notes=("nessuna latenza registrata",),
        )
    return MetricResult(
        name="median_planner_latency_ms",
        numerator=float(median(latencies_ms)),
        denominator=1.0,
        notes=(f"su {len(latencies_ms)} osservazioni",),
    )


def orchestration_metrics(
    case: ClinicalGoldCase,
    prediction: RetrievalPrediction,
    *,
    actions: Sequence[Mapping[str, object]] = (),
    known_tools: Sequence[str] = (),
    runs: Sequence[Mapping[str, object]] = (),
    latencies_ms: Sequence[float] = (),
    outputs: Sequence[object] = (),
) -> dict[str, MetricResult]:
    from .retrieval_fidelity import tool_metrics

    metrics = dict(tool_metrics(case, prediction))
    for metric in (
        task_completion(case, prediction),
        conditional_step_accuracy(case, prediction),
        stop_condition_accuracy(case, prediction),
        valid_action_rate(actions, known_tools),
        planner_failure_rate(runs),
        fallback_rate(runs),
        run_to_run_agreement(outputs),
        median_planner_latency(latencies_ms),
    ):
        metrics[metric.name] = metric
    return metrics
