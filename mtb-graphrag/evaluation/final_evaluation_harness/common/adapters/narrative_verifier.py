"""Canonical narrative verifier and ablated no-call adapter."""

from __future__ import annotations

from typing import Any, Callable


class NarrativeVerifierAdapter:
    def __init__(self, verifier: Callable[[Any], Any] | None, *, bypass: bool = False) -> None:
        self._verifier = verifier
        self.bypass = bypass

    def verify(self, narrative: dict[str, Any]) -> Any:
        if self.bypass:
            if narrative.get("transport") != "VALID":
                return narrative
            return {**narrative, "presentation": "PRESENTED_IN_OFFLINE_ABLATION"}
        if self._verifier is None:
            raise ValueError("canonical narrative verifier delegate is required")
        return self._verifier(narrative)
