"""Fail-closed network and model accounting guards."""

from __future__ import annotations

from dataclasses import dataclass


class ForbiddenOperation(RuntimeError):
    """Raised when a forbidden external/model operation is attempted."""


@dataclass
class CallCounts:
    parser: int = 0
    gemma: int = 0
    narrator: int = 0
    other_model: int = 0
    network: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "casecontext_parser": self.parser,
            "gemma": self.gemma,
            "narrator": self.narrator,
            "other_model": self.other_model,
            "network": self.network,
        }


class NetworkGuard:
    def __init__(self, policy: str, counts: CallCounts | None = None) -> None:
        self.policy = policy
        self.counts = counts or CallCounts()

    def record(self) -> None:
        self.counts.network += 1
        if self.policy == "PROHIBITED":
            raise ForbiddenOperation("network prohibited by frozen protocol")


class ModelGuard:
    def __init__(self, counts: CallCounts | None = None) -> None:
        self.counts = counts or CallCounts()

    def record(self, model: str) -> None:
        if model == "gemma":
            self.counts.gemma += 1
        elif model == "narrator":
            self.counts.narrator += 1
        elif model == "parser":
            self.counts.parser += 1
        else:
            self.counts.other_model += 1
