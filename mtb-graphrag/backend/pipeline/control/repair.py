"""Riparazione bounded, deterministica, in due regimi distinti.

Nessun LLM pianifica le riparazioni: un repair planner generativo
reintrodurrebbe esattamente la non-verificabilità che questa pipeline esiste
per eliminare.

La distinzione fra i due regimi è sostanziale, non organizzativa. Un difetto di
rendering non giustifica una nuova interrogazione del grafo: rifare una tool
call per un conteggio sbagliato in intestazione costerebbe una query e, molto
peggio, potrebbe cambiare l'evidenza sotto un errore che non la riguarda.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol, Sequence

from backend.pipeline.control.contracts import (
    Escalation,
    Projection,
    RepairAction,
    RepairNotPermitted,
    StructuralVerdict,
)
from backend.pipeline.control.strategies.tool_registry import REPAIRABLE_TOOLS

#: Violazioni che si risolvono rigenerando il testo dagli stessi dati.
RENDERING_CODES = frozenset({"MISSING_CLAIM", "COUNT_MISMATCH", "CONFLICT_UNSURFACED"})

#: Violazioni che richiedono dati nuovi, e quindi una nuova azione autorizzata.
COLLECTION_CODES = frozenset({
    "TRUNCATED_VIEW", "MISSING_MANDATORY_TOOL", "RECOVERABLE_SOURCE_MISSING",
})


class RepairPlanner(Protocol):
    def plan(
        self, verdict: StructuralVerdict, projection: Projection, *, attempt: int
    ) -> RepairAction | None: ...


class RenderingRepairPlanner:
    """Ripianifica il solo rendering, senza toccare la raccolta."""

    def plan(
        self, verdict: StructuralVerdict, projection: Projection, *, attempt: int
    ) -> RepairAction | None:
        if attempt > 0 or not verdict.requires_repair:
            return None
        codes = {v.code for v in verdict.violations} & RENDERING_CODES
        if not codes:
            return None
        return RepairAction(
            kind="rendering",
            rationale=(
                "Il testo non rappresenta fedelmente i record attesi; si rigenera "
                "dagli stessi dati canonici, senza nuove chiamate a strumento."
            ),
            triggered_by=tuple(sorted(codes)),
            target_record_ids=tuple(verdict.missing_claims),
        )


class CollectionRepairPlanner:
    """Unico pianificatore autorizzato a richiamare strumenti."""

    def __init__(self, *, allowed_tools: frozenset[str] = REPAIRABLE_TOOLS) -> None:
        self._allowed = allowed_tools

    def plan(
        self,
        verdict: StructuralVerdict,
        projection: Projection,
        *,
        attempt: int,
        events: Sequence[Mapping[str, Any]] = (),
        missing_mandatory: Sequence[str] = (),
    ) -> RepairAction | None:
        if attempt > 0:
            return None

        codes = {v.code for v in verdict.violations} & COLLECTION_CODES
        if missing_mandatory:
            tool = next((t for t in missing_mandatory if t in self._allowed), None)
            if tool:
                return RepairAction(
                    kind="collection",
                    tool_name=tool,
                    arguments=_last_arguments(events, tool),
                    rationale=(
                        f"Strumento obbligatorio '{tool}' non completato: la raccolta è "
                        "incompleta rispetto alla policy dell'obiettivo MTB."
                    ),
                    triggered_by=("MISSING_MANDATORY_TOOL",),
                )

        if "TRUNCATED_VIEW" not in codes:
            return None

        tool, arguments = _truncated_action(events)
        if tool is None or tool not in self._allowed:
            return None
        return RepairAction(
            kind="collection",
            tool_name=tool,
            arguments=arguments,
            rationale=(
                f"La raccolta di '{tool}' è risultata troncata: si riprende dalla "
                "posizione registrata nell'azione generatrice."
            ),
            triggered_by=("TRUNCATED_VIEW",),
        )


def _last_arguments(events: Sequence[Mapping[str, Any]], tool: str) -> dict[str, Any]:
    for event in reversed(list(events)):
        if event.get("tool_name") == tool and event.get("query_or_arguments_json"):
            return json.loads(str(event["query_or_arguments_json"]))
    for event in reversed(list(events)):
        if event.get("query_or_arguments_json"):
            return json.loads(str(event["query_or_arguments_json"]))
    return {}


def _truncated_action(
    events: Sequence[Mapping[str, Any]],
) -> tuple[str | None, dict[str, Any]]:
    """Trova l'azione troncata e ricostruisce gli argomenti per riprenderla.

    Legge ``query_or_arguments_json`` e ``pagination_state_json`` dalla riga di
    ledger dell'azione generatrice: è la ragione per cui quelle colonne
    esistono.
    """
    for event in reversed(list(events)):
        if event.get("completeness_status") != "truncated":
            continue
        tool = event.get("tool_name")
        if not tool:
            continue
        arguments = json.loads(str(event.get("query_or_arguments_json") or "{}"))
        pagination = json.loads(str(event.get("pagination_state_json") or "{}"))
        if pagination.get("cursor"):
            arguments = {**arguments, "cursor": pagination["cursor"]}
        return str(tool), arguments
    return None, {}


def execute_repair(
    action: RepairAction,
    tools: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Esegue una riparazione di raccolta, rifiutando strumenti non autorizzati."""
    if action.kind != "collection":
        raise RepairNotPermitted("execute_repair gestisce solo le riparazioni di raccolta.")
    if not action.tool_name or action.tool_name not in REPAIRABLE_TOOLS:
        raise RepairNotPermitted(
            f"Strumento '{action.tool_name}' non incluso nell'allow-list di riparazione."
        )
    if action.tool_name not in tools:
        raise RepairNotPermitted(f"Strumento '{action.tool_name}' non disponibile nel registry.")
    return tools[action.tool_name](dict(state))


def escalation_for(
    verdict: StructuralVerdict, *, attempted: bool
) -> Escalation:
    blocking = [v for v in verdict.violations if v.severity == "blocking"]
    if blocking:
        return Escalation(
            reason_category="blocking_structural_violation",
            detail=(
                "Violazioni strutturali bloccanti: "
                + "; ".join(f"{v.code} — {v.detail}" for v in blocking)
            ),
            triggered_by=tuple(v.code for v in blocking),
        )
    if attempted:
        return Escalation(
            reason_category="repair_exhausted",
            detail=(
                "Il ciclo di riparazione consentito è stato esaurito senza risolvere "
                "le violazioni rilevate."
            ),
            triggered_by=tuple(v.code for v in verdict.violations),
        )
    return Escalation(
        reason_category="repair_not_available",
        detail=(
            "Nessuna riparazione autorizzata è applicabile alle violazioni rilevate; "
            "la decisione resta alla revisione umana."
        ),
        triggered_by=tuple(v.code for v in verdict.violations),
    )
