"""Esecuzione dei compiti di ruolo su un modello e valutazione degli esiti.

Separato dal CLI perche' i test devono poterlo esercitare con un client scriptato:
tutta la logica di scoring vive qui, il CLI si limita a orchestrare e scrivere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from backend.pipeline.llm.ollama_adapter import (
    OllamaUnavailable,
    StructuredOutputError,
    request_structured,
)

from ..pilot.audit_lib.normalize import norm_text
from .roles import FREE_REPORT, KNOWN_TOOLS, PLANNER, VERIFIER, RoleTask


@dataclass
class TaskOutcome:
    """Esito di un singolo compito su un singolo modello e seed."""

    task_id: str
    role: str
    case_id: str
    model: str
    seed: int | None
    valid_output: bool
    parsed: Any = None
    raw_outputs: tuple[str, ...] = ()
    retries: int = 0
    structured_output_mode: str = ""
    latency_ms: float = 0.0
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "role": self.role,
            "case_id": self.case_id,
            "model": self.model,
            "seed": self.seed,
            "valid_output": self.valid_output,
            "parsed": self.parsed,
            "raw_outputs": list(self.raw_outputs),
            "retries": self.retries,
            "structured_output_mode": self.structured_output_mode,
            "latency_ms": round(self.latency_ms, 2),
            "error": self.error,
        }


def run_task(
    client: Any,
    model: str,
    task: RoleTask,
    *,
    mode: str,
    seed: int | None = None,
    temperature: float = 0.0,
    num_ctx: int = 16384,
) -> TaskOutcome:
    """Esegue un compito, catturando i fallimenti invece di propagarli.

    Un modello che non produce output valido e' un dato dell'esperimento, non un
    errore dello script: interrompere qui perderebbe le misure degli altri modelli.
    """
    started = time.perf_counter()
    try:
        result = request_structured(
            client,
            model,
            [dict(message) for message in task.messages],
            dict(task.schema),
            mode=mode,
            seed=seed,
            temperature=temperature,
            num_ctx=num_ctx,
        )
    except (StructuredOutputError, OllamaUnavailable) as error:
        return TaskOutcome(
            task_id=task.task_id,
            role=task.role,
            case_id=task.case_id,
            model=model,
            seed=seed,
            valid_output=False,
            structured_output_mode=mode,
            latency_ms=(time.perf_counter() - started) * 1000,
            error=f"{type(error).__name__}: {error}",
        )
    return TaskOutcome(
        task_id=task.task_id,
        role=task.role,
        case_id=task.case_id,
        model=model,
        seed=seed,
        valid_output=True,
        parsed=result.parsed,
        raw_outputs=tuple(result.raw_outputs),
        retries=result.retries,
        structured_output_mode=result.mode,
        latency_ms=result.latency_ms,
    )


# ── Valutazione per ruolo ──────────────────────────────────────────────────────


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def evaluate_planner(outcomes: Sequence[TaskOutcome], tasks: Mapping[str, RoleTask]):
    """Metriche del planner sugli esiti di tutti i casi e seed."""
    valid = [outcome for outcome in outcomes if outcome.valid_output]
    actions: list[dict[str, Any]] = []
    completions: list[float] = []
    conditional: list[float] = []
    required_hits = required_total = 0
    unnecessary_hits = called_total = 0
    stop_correct: list[float] = []
    per_case_plans: dict[str, list[str]] = {}

    for outcome in valid:
        task = tasks.get(outcome.task_id)
        if task is None:
            continue
        plan = outcome.parsed.get("plan") or []
        tools = [str(step.get("tool", "")) for step in plan]
        actions.extend({"tool": tool} for tool in tools)
        expectation = task.expectation
        required = set(expectation.get("required_tools") or ())
        unnecessary = set(expectation.get("unnecessary_tools") or ())
        called = set(tools) - {"stop"}
        abstention = bool(expectation.get("expected_abstention"))

        if abstention:
            stopped = bool(outcome.parsed.get("stop_after_plan")) or tools in ([], ["stop"])
            completions.append(1.0 if stopped else 0.0)
            stop_correct.append(1.0 if stopped else 0.0)
        else:
            completions.append(1.0 if required <= called else 0.0)
            stop_correct.append(1.0 if called else 0.0)

        if expectation.get("category") == "ADAPTIVE":
            conditional.append(
                1.0 if (required <= called and not (called & unnecessary)) else 0.0
            )

        required_hits += len(called & required)
        required_total += len(required)
        unnecessary_hits += len(called & unnecessary)
        called_total += len(called)
        per_case_plans.setdefault(outcome.case_id, []).append(",".join(sorted(called)))

    agreements = [
        max(plans.count(plan) for plan in set(plans)) / len(plans)
        for plans in per_case_plans.values()
        if len(plans) > 1
    ]
    return {
        "valid_action_rate": _ratio(
            sum(1 for a in actions if a["tool"] in KNOWN_TOOLS), len(actions)
        ),
        "valid_output_rate": _ratio(len(valid), len(outcomes)),
        "task_completion": _ratio(sum(completions), len(completions)),
        "conditional_step_accuracy": _ratio(sum(conditional), len(conditional)),
        "required_tool_recall": _ratio(required_hits, required_total),
        "unnecessary_tool_rate": _ratio(unnecessary_hits, called_total),
        "stop_condition_accuracy": _ratio(sum(stop_correct), len(stop_correct)),
        "run_to_run_agreement": _ratio(sum(agreements), len(agreements)),
        "planner_failure_rate": _ratio(len(outcomes) - len(valid), len(outcomes)),
        "fallback_rate": 0.0,
        "median_latency_ms": _median([o.latency_ms for o in outcomes]),
    }


def evaluate_verifier(outcomes: Sequence[TaskOutcome], tasks: Mapping[str, RoleTask]):
    valid = [outcome for outcome in outcomes if outcome.valid_output]
    doc_hits = doc_total = 0
    app_hits = app_total = 0
    qual_hits = qual_total = 0
    context_hits = context_total = 0
    overstated = not_compatible_total = 0
    per_task: dict[str, list[str]] = {}

    for outcome in valid:
        task = tasks.get(outcome.task_id)
        if task is None:
            continue
        expectation = task.expectation
        parsed = outcome.parsed

        expected_doc = norm_text(expectation.get("documentary_status"))
        if expected_doc:
            doc_total += 1
            doc_hits += int(norm_text(parsed.get("documentary_status")) == expected_doc)

        expected_app = norm_text(expectation.get("applicability"))
        predicted_app = norm_text(parsed.get("applicability"))
        if expected_app:
            app_total += 1
            app_hits += int(predicted_app == expected_app)
            if expected_app == "not_compatible":
                not_compatible_total += 1
                overstated += int(predicted_app == "compatible")

        for field_name in ("setting", "therapy_line"):
            expected_value = norm_text(expectation.get(field_name))
            if not expected_value:
                continue
            qual_total += 1
            predicted_value = norm_text(parsed.get(field_name))
            tokens = [token for token in expected_value.split() if len(token) > 3]
            qual_hits += int(
                bool(predicted_value)
                and any(token in predicted_value for token in tokens)
            )

        context_total += 1
        declared_missing = bool(parsed.get("missing_context"))
        should_declare = expected_app == "not_compatible"
        context_hits += int(declared_missing == should_declare)

        per_task.setdefault(outcome.task_id, []).append(predicted_app)

    agreements = [
        max(values.count(value) for value in set(values)) / len(values)
        for values in per_task.values()
        if len(values) > 1
    ]
    return {
        "valid_output_rate": _ratio(len(valid), len(outcomes)),
        "documentary_status_accuracy": _ratio(doc_hits, doc_total),
        "applicability_status_accuracy": _ratio(app_hits, app_total),
        "qualifier_extraction_accuracy": _ratio(qual_hits, qual_total),
        "missing_context_detection": _ratio(context_hits, context_total),
        "compatible_overstatement_rate": _ratio(overstated, not_compatible_total),
        "run_to_run_agreement": _ratio(sum(agreements), len(agreements)),
        "median_latency_ms": _median([o.latency_ms for o in outcomes]),
    }


def evaluate_free_report(
    outcomes: Sequence[TaskOutcome],
    tasks: Mapping[str, RoleTask],
    available_pmids_by_case: Mapping[str, set[str]],
):
    from ..pilot.audit_lib.normalize import norm_pmid_set

    valid = [outcome for outcome in outcomes if outcome.valid_output]
    cited_ok = cited_total = 0
    unsupported = claims_total = 0
    abstention_hits = abstention_total = 0
    qualifier_hits = qualifier_total = 0
    per_case: dict[str, list[str]] = {}

    for outcome in valid:
        task = tasks.get(outcome.task_id)
        if task is None:
            continue
        parsed = outcome.parsed
        claims = parsed.get("claims") or []
        available = available_pmids_by_case.get(outcome.case_id, set())

        for claim in claims:
            claims_total += 1
            pmids = set(norm_pmid_set([claim.get("pmid", "")]))
            if pmids:
                cited_total += len(pmids)
                cited_ok += len(pmids & available)
            if pmids and not (pmids & available):
                unsupported += 1
            qualifier_total += 1
            qualifier_hits += int(bool(norm_text(claim.get("qualifiers"))))

        abstention_total += 1
        expected_abstention = bool(task.expectation.get("expected_abstention"))
        abstention_hits += int(bool(parsed.get("abstained")) == expected_abstention)
        per_case.setdefault(outcome.case_id, []).append(
            f"{bool(parsed.get('abstained'))}|{len(claims)}"
        )

    agreements = [
        max(values.count(value) for value in set(values)) / len(values)
        for values in per_case.values()
        if len(values) > 1
    ]
    return {
        "valid_output_rate": _ratio(len(valid), len(outcomes)),
        "citation_accuracy": _ratio(cited_ok, cited_total),
        "claim_precision": _ratio(claims_total - unsupported, claims_total),
        "claim_recall": _ratio(claims_total - unsupported, max(claims_total, 1)),
        "qualifier_preservation": _ratio(qualifier_hits, qualifier_total),
        "context_omission_rate": _ratio(qualifier_total - qualifier_hits, qualifier_total),
        "unsupported_claim_rate": _ratio(unsupported, claims_total),
        "abstention_accuracy": _ratio(abstention_hits, abstention_total),
        "run_to_run_agreement": _ratio(sum(agreements), len(agreements)),
        "median_latency_ms": _median([o.latency_ms for o in outcomes]),
    }


def _median(values: Sequence[float]) -> float | None:
    from statistics import median

    cleaned = [value for value in values if value]
    return float(median(cleaned)) if cleaned else None


ROLE_EVALUATORS = {
    PLANNER: evaluate_planner,
    VERIFIER: evaluate_verifier,
    FREE_REPORT: evaluate_free_report,
}
