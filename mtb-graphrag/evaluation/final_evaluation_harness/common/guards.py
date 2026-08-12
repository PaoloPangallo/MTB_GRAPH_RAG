"""Fail-closed network and model accounting guards."""

from __future__ import annotations

from dataclasses import dataclass


class ForbiddenOperation(RuntimeError):
    """Raised when a forbidden external/model operation is attempted."""


@dataclass
class CallCounts:
    runtime: int = 0
    parser: int = 0
    gemma: int = 0
    narrator: int = 0
    other_model: int = 0
    network: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "runtime": self.runtime,
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
        self._unit_policy = None

    def bind(self, unit: object) -> None:
        self._unit_policy = getattr(unit, "network_policy", None)

    def assert_allowed(self, requested: str) -> None:
        policy = self._unit_policy or self.policy
        if policy not in {"PROHIBITED", "CANONICAL_RUNTIME_POLICY"}:
            raise ForbiddenOperation(f"unknown network policy: {policy}")
        if policy == "PROHIBITED" and requested == "CANONICAL_RUNTIME_POLICY":
            raise ForbiddenOperation("network prohibited by frozen protocol")

    def record(self) -> None:
        self.assert_allowed("CANONICAL_RUNTIME_POLICY")
        self.counts.network += 1


class ModelGuard:
    def __init__(self, counts: CallCounts | None = None) -> None:
        self.counts = counts or CallCounts()
        self._unit = None

    def bind(self, unit: object) -> None:
        self._unit = unit

    def assert_allowed(self, requirement: str, *, role: str = "gemma") -> None:
        if requirement not in {"REQUIRED", "PROHIBITED", "PATH_DEPENDENT"}:
            raise ForbiddenOperation(f"unknown model requirement: {requirement}")
        if requirement == "PROHIBITED":
            raise ForbiddenOperation("model prohibited by frozen protocol")
        if self._unit is not None and role == "gemma" and getattr(self._unit, "gemma_requirement", "") == "PROHIBITED":
            raise ForbiddenOperation("gemma prohibited by frozen protocol")
        if self._unit is not None and role == "narrator" and getattr(self._unit, "narrator_requirement", "") == "PROHIBITED":
            raise ForbiddenOperation("narrator prohibited by frozen protocol")

    def record(self, model: str) -> None:
        if model == "gemma":
            self.counts.gemma += 1
        elif model == "narrator":
            self.counts.narrator += 1
        elif model == "parser":
            self.counts.parser += 1
        elif model == "other_model":
            self.counts.other_model += 1
        else:
            raise ForbiddenOperation(f"unknown model category: {model}")


class RuntimeGuard:
    def __init__(self) -> None:
        self._unit = None

    def bind(self, unit: object) -> None:
        self._unit = unit

    def assert_allowed(self, requirement: str) -> None:
        if requirement not in {"REQUIRED", "PROHIBITED", "PATH_DEPENDENT"}:
            raise ForbiddenOperation(f"unknown runtime requirement: {requirement}")
        if requirement == "REQUIRED" and self._unit is not None and getattr(self._unit, "canonical_runtime_requirement", "") == "PROHIBITED":
            raise ForbiddenOperation("runtime prohibited by frozen protocol")
