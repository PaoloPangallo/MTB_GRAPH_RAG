"""Bridge the H02 recorder contract to the strict campaign ledger contract."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .lifecycle import CampaignLedger


class H02LedgerAdapter:
    """Expose the legacy H02 ``EventLedger.append`` shape to ``RunRecorder``.

    H02 retains its own run identity and event namespace in the campaign event
    payload.  The surrounding Final Evaluation attempt/run identity is supplied
    separately and is never replaced by the H02 ``run_id``.
    """

    def __init__(self, ledger: Any, *, attempt_id: str | None, final_run_id: str | None):
        self._ledger = ledger
        self._attempt_id = attempt_id
        self._final_run_id = final_run_id

    def append(
        self,
        h02_run_id: str,
        event_type: str,
        actor: str,
        payload: Mapping[str, Any],
        *,
        action_id: str | None = None,
        parent_action_id: str | None = None,
        tool_name: str | None = None,
        tool_version: str | None = None,
        query_or_arguments: Mapping[str, Any] | None = None,
        pagination_state: Mapping[str, Any] | None = None,
        completeness_status: str | None = None,
        generating_action_id: str | None = None,
    ) -> Any:
        if not isinstance(h02_run_id, str) or not h02_run_id:
            raise TypeError("H02 run_id must be a non-empty string")
        if not isinstance(event_type, str) or not event_type:
            raise TypeError("H02 event_type must be a non-empty string")
        if not isinstance(actor, str) or not actor:
            raise TypeError("H02 actor must be a non-empty string")
        if not isinstance(payload, Mapping):
            raise TypeError("H02 payload must be a mapping")

        # Preserve compatibility for the native H02 SQLite ledger.  The bridge
        # is only a translation layer when the official CampaignLedger is used.
        if not isinstance(self._ledger, CampaignLedger):
            return self._ledger.append(
                h02_run_id,
                event_type,
                actor,
                dict(payload),
                action_id=action_id,
                parent_action_id=parent_action_id,
                tool_name=tool_name,
                tool_version=tool_version,
                query_or_arguments=dict(query_or_arguments) if query_or_arguments is not None else None,
                pagination_state=dict(pagination_state) if pagination_state is not None else None,
                completeness_status=completeness_status,
                generating_action_id=generating_action_id,
            )

        if not self._attempt_id or not self._final_run_id:
            raise RuntimeError("H02_CAMPAIGN_IDENTITY_NOT_CONFIGURED")

        extra: dict[str, Any] = {
            "h02_namespace": "research_pipeline",
            "h02_run_id": h02_run_id,
            "h02_event_type": event_type,
            "h02_component": actor,
            "h02_payload": dict(payload),
            "h02_tool_name": tool_name,
            "h02_tool_version": tool_version,
        }
        if action_id is not None:
            extra["h02_action_id"] = action_id
        if parent_action_id is not None:
            extra["h02_parent_action_id"] = parent_action_id
        if query_or_arguments is not None:
            extra["h02_query_or_arguments"] = dict(query_or_arguments)
        if pagination_state is not None:
            extra["h02_pagination_state"] = dict(pagination_state)
        if completeness_status is not None:
            extra["h02_completeness_status"] = completeness_status
        if generating_action_id is not None:
            extra["h02_generating_action_id"] = generating_action_id

        return self._ledger.append(
            event_type,
            attempt_id=self._attempt_id,
            run_id=self._final_run_id,
            **extra,
        )
