"""Scrittore unico del ledger per una singola esecuzione.

Prima di questo modulo il ramo agentico apriva *due* ``EventLedger`` distinti
sullo stesso ``run_id``: uno dentro la raccolta e uno nel servizio di
confronto. Due scrittori sulla stessa catena sono una sorgente silenziosa di
race sulla sequenza e rendono ambigua la nozione di "run".

``ActionRecorder`` è l'unico punto di scrittura: il runner ne crea uno per
esecuzione e lo passa a tutte le fasi, strategia di raccolta compresa.
"""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4

from backend.pipeline.agentic.ledger import ChainReport, EventLedger
from backend.pipeline.control.events import sanitize_text


class ActionRecorder:
    """Adapter di scrittura su un ledger, vincolato a un solo ``run_id``."""

    def __init__(self, ledger: EventLedger, run_id: str | None = None) -> None:
        self._ledger = ledger
        self._run_id = run_id or str(uuid4())

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def ledger(self) -> EventLedger:
        return self._ledger

    @staticmethod
    def new_action_id() -> str:
        return str(uuid4())

    def record(
        self,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any] | None = None,
        *,
        action_id: str | None = None,
        parent_action_id: str | None = None,
        tool_name: str | None = None,
        tool_version: str | None = None,
        query_or_arguments: Mapping[str, Any] | None = None,
        pagination_state: Mapping[str, Any] | None = None,
        completeness_status: str | None = None,
        generating_action_id: str | None = None,
    ) -> dict[str, Any]:
        return self._ledger.append(
            self._run_id,
            event_type,
            actor,
            dict(payload or {}),
            action_id=action_id,
            parent_action_id=parent_action_id,
            tool_name=tool_name,
            tool_version=tool_version,
            query_or_arguments=dict(query_or_arguments) if query_or_arguments else None,
            pagination_state=dict(pagination_state) if pagination_state else None,
            completeness_status=completeness_status,
            generating_action_id=generating_action_id,
        )

    def record_error(
        self,
        event_type: str,
        actor: str,
        message: str,
        *,
        category: str = "other",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Registra un errore già sanitizzato.

        I messaggi di eccezione grezzi possono contenere host interni e
        credenziali; una volta nel ledger non sarebbero più rimovibili.
        """
        return self.record(
            event_type,
            actor,
            {"error_category": category, "message": sanitize_text(message)},
            **kwargs,
        )

    def events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._ledger.events(self._run_id))

    def chain_report(self) -> ChainReport:
        return self._ledger.chain_report(self._run_id)

    def chain_valid(self) -> bool:
        return self._ledger.verify_chain(self._run_id)
