"""Il seam dell'orchestrazione: l'unico punto in cui le due architetture differiscono.

Tutto ciò che segue ``collect()`` è codice condiviso. Se questa interfaccia
crescesse fino a includere rendering o verifica, il confronto smetterebbe di
misurare l'orchestrazione e tornerebbe a misurare due pipeline diverse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol

from backend.pipeline.control.contracts import CaseContext
from backend.pipeline.control.recorder import ActionRecorder


@dataclass(frozen=True)
class CollectionContext:
    case: CaseContext
    recorder: ActionRecorder
    tools: Mapping[str, Any]
    mandatory_tools: tuple[str, ...] = ()
    max_steps: int = 8


@dataclass(frozen=True)
class CollectionOutcome:
    """Esito della raccolta, nella stessa forma per entrambe le architetture."""

    terminal_state: Mapping[str, Any] = field(default_factory=dict)
    tool_path: tuple[str, ...] = ()
    tool_call_timings: tuple[Mapping[str, Any], ...] = ()
    #: "fixed_plan" | "llm_dynamic" | "safe_fallback"
    planning_mode: str = "fixed_plan"
    fallback_reason: str | None = None
    #: 0 per il piano fisso. È il numero che distingue davvero le due
    #: architetture, molto più del conteggio di tool call.
    planner_calls: int = 0
    planner_elapsed_ms: int = 0
    mandatory_tools: tuple[str, ...] = ()
    missing_mandatory_tools: tuple[str, ...] = ()
    incompleteness_reason: str | None = None
    errors: tuple[str, ...] = ()


class CollectionStrategy(Protocol):
    architecture_id: Literal["deterministic", "agentic"]
    orchestration_mode: Literal["deterministic", "agentic"]

    def collect(self, ctx: CollectionContext) -> CollectionOutcome: ...
