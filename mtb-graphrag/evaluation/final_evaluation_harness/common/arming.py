"""Central disarmed execution gate."""

from __future__ import annotations


class ExecutionDisarmed(RuntimeError):
    """Raised for any real execution attempt before an explicit future phase."""


class ExecutionGate:
    status = "DISARMED"

    def require_armed(self) -> None:
        raise ExecutionDisarmed("final evaluation execution gate is DISARMED")

    def dry_run_allowed(self) -> bool:
        return True
