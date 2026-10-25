"""Controller a piano fisso: l'orchestrazione dell'architettura deterministica.

Il percorso e l'ordine degli strumenti sono stabiliti **prima** dell'esecuzione.
Il controller emette però lo stesso vocabolario di eventi del planner — inclusa
``plan_decision`` — così il replay, la canonicalizzazione e la verifica sono
ciechi rispetto all'architettura, ed è davvero solo la raccolta a differire.

Il piano non è unico per tutti gli obiettivi MTB: un piano massimo applicato
indiscriminatamente falserebbe il confronto, perché il ramo deterministico
raccoglierebbe sempre almeno quanto l'agentico a prescindere dall'obiettivo.
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from backend.pipeline.control.events import (
    ACTOR_CONTROLLER,
    ACTOR_FIXED_PLAN,
    plan_decision_payload,
    tool_completed_payload,
)
from backend.pipeline.control.strategies.protocol import CollectionContext, CollectionOutcome
from backend.pipeline.control.strategies.tool_registry import (
    records_from_state,
    tool_version,
)

#: Piani dichiarati per obiettivo, allineati a MANDATORY_TOOLS_BY_GOAL.
#: 'clinical-trials' include identify_targets perché match_trials ne dipende.
FIXED_PLANS_BY_GOAL: dict[str, tuple[str, ...]] = {
    "general-review": ("interpret_variant", "identify_targets", "match_trials", "check_resistance"),
    "treatment-evidence": ("interpret_variant", "identify_targets"),
    "resistance": ("interpret_variant", "check_resistance"),
    "clinical-trials": ("interpret_variant", "identify_targets", "match_trials"),
}

_ARGUMENT_FIELDS = ("gene", "variant", "tumor_type", "alteration_type", "therapy_line")


def plan_for_goal(mtb_goal: str | None) -> tuple[str, ...]:
    return FIXED_PLANS_BY_GOAL.get(mtb_goal or "", FIXED_PLANS_BY_GOAL["general-review"])


class FixedPlanStrategy:
    """Esegue un piano tipizzato dichiarato, senza alcuna decisione LLM."""

    architecture_id = "deterministic"
    orchestration_mode = "deterministic"

    def __init__(self, plan: tuple[str, ...] | None = None) -> None:
        self._plan = plan

    def collect(self, ctx: CollectionContext) -> CollectionOutcome:
        plan = self._plan or plan_for_goal(ctx.case.mtb_goal)
        state: dict[str, Any] = dict(ctx.case.to_state())
        recorder = ctx.recorder

        recorder.record("run_started", ACTOR_CONTROLLER, {
            "case": {"gene": ctx.case.gene, "variant": ctx.case.variant,
                     "tumor_type": ctx.case.tumor_type},
            "orchestration_mode": "deterministic",
            "mandatory_tools": list(ctx.mandatory_tools),
            "declared_plan": list(plan),
        })

        completed: list[str] = []
        timings: list[dict[str, Any]] = []
        errors: list[str] = []

        for step, tool in enumerate(plan, start=1):
            if tool not in ctx.tools:
                errors.append(f"{tool}: strumento non disponibile nel registry.")
                continue

            recorder.record(
                "plan_decision",
                ACTOR_FIXED_PLAN,
                plan_decision_payload(
                    step=step,
                    selected_tool=tool,
                    # Il piano fisso non sceglie fra alternative: l'insieme
                    # consentito a questo passo è il solo strumento dichiarato.
                    allowed_tools=[tool],
                    rationale=(
                        f"Passo {step} del piano tipizzato dichiarato prima "
                        "dell'esecuzione; nessuna decisione LLM."
                    ),
                    planning_mode="fixed_plan",
                    fallback=False,
                ),
            )

            action_id = recorder.new_action_id()
            arguments = {field: state.get(field) for field in _ARGUMENT_FIELDS}
            recorder.record(
                "tool_started", tool, {"step": step},
                action_id=action_id, tool_name=tool, tool_version=tool_version(tool),
                query_or_arguments=arguments,
            )

            started = perf_counter()
            try:
                state = ctx.tools[tool](state)
            except Exception as exc:  # noqa: BLE001 - categorizzata e sanitizzata
                category = type(exc).__name__
                errors.append(f"{tool}: esecuzione non riuscita.")
                timings.append({
                    "tool": tool, "sequence": len(completed) + 1,
                    "elapsed_ms": int((perf_counter() - started) * 1000), "status": "failed",
                })
                recorder.record_error(
                    "tool_failed", tool, f"{tool}: esecuzione non riuscita ({category}).",
                    category="tool_error", parent_action_id=action_id, tool_name=tool,
                    tool_version=tool_version(tool), completeness_status="partial",
                )
                continue

            completed.append(tool)
            timings.append({
                "tool": tool, "sequence": len(completed),
                "elapsed_ms": int((perf_counter() - started) * 1000), "status": "completed",
            })
            record_kind, records = records_from_state(tool, state)
            payload = tool_completed_payload(
                tool=tool, record_kind=record_kind, records=records
            )
            payload["step"] = step
            recorder.record(
                "tool_completed", tool, payload,
                action_id=recorder.new_action_id(), parent_action_id=action_id,
                tool_name=tool, tool_version=tool_version(tool),
                query_or_arguments=arguments,
                completeness_status=payload["completeness_status"],
            )

        recorder.record("collection_completed", ACTOR_CONTROLLER, {
            "completed_tools": completed,
            "errors": errors,
        })

        missing = tuple(t for t in ctx.mandatory_tools if t not in completed)
        return CollectionOutcome(
            terminal_state=state,
            tool_path=tuple(completed),
            tool_call_timings=tuple(timings),
            planning_mode="fixed_plan",
            fallback_reason=None,
            planner_calls=0,
            planner_elapsed_ms=0,
            mandatory_tools=tuple(ctx.mandatory_tools),
            missing_mandatory_tools=missing,
            incompleteness_reason=(
                "Il piano fisso dichiarato non copre tutti gli strumenti obbligatori "
                f"per l'obiettivo MTB: mancano {', '.join(missing)}."
                if missing else None
            ),
            errors=tuple(errors),
        )
