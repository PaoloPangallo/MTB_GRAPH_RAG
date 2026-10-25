"""Adapter dell'orchestrazione agentica sul seam comune.

Non riscrive il planner: incapsula ``run_agentic_collection``, che continua a
possedere allow-list, dipendenze, budget, timeout, retry bounded e fallback.
L'adattamento serve solo a far parlare la raccolta agentica la stessa lingua
di quella deterministica dal punto di vista del runner.
"""

from __future__ import annotations

from typing import Any

from backend.pipeline.control.strategies.protocol import CollectionContext, CollectionOutcome


class AgenticPlanStrategy:
    """Ciclo plan–act–observe guidato da un planner LLM controllato."""

    architecture_id = "agentic"
    orchestration_mode = "agentic"

    def __init__(self, planner_llm: Any | None = None, *, max_steps: int = 8) -> None:
        self._planner_llm = planner_llm
        self._max_steps = max_steps

    def collect(self, ctx: CollectionContext) -> CollectionOutcome:
        from backend.pipeline.agentic.runtime import run_agentic_collection

        result = run_agentic_collection(
            ctx.case.to_state(),
            recorder=ctx.recorder,
            planner_llm=self._planner_llm,
            tool_registry=dict(ctx.tools),
            max_steps=self._max_steps or ctx.max_steps,
        )

        return CollectionOutcome(
            terminal_state=result.state,
            tool_path=tuple(result.tool_path),
            tool_call_timings=tuple(result.tool_call_timings),
            planning_mode=result.planning_mode,
            # Il motivo di fallback resta esposto solo quando il fallback è
            # davvero avvenuto: una run che ha usato il percorso sicuro non
            # deve poter essere descritta come pianificazione dinamica.
            fallback_reason=result.fallback_reason,
            planner_calls=result.planner_attempts,
            planner_elapsed_ms=result.planner_elapsed_ms,
            mandatory_tools=tuple(result.mandatory_tools),
            missing_mandatory_tools=tuple(result.missing_mandatory_tools),
            incompleteness_reason=result.incompleteness_reason,
            errors=tuple(result.errors),
        )
