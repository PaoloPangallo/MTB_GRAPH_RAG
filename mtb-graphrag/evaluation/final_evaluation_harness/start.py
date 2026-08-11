"""Future explicit start boundary; intentionally disarmed in this phase."""

from __future__ import annotations

from .common.arming import ExecutionGate
from .common.protocol_loader import load_protocol
from .common.runner import build_full_plan, execution_plan_sha256


def materialize_execution_plan() -> tuple[list[dict], str]:
    """Build the frozen serialized order without creating result artifacts."""
    protocol = load_protocol()
    plans = build_full_plan(protocol)
    return [plan.__dict__ for plan in plans], execution_plan_sha256(plans)


def main() -> None:
    # The gate is checked before any future start-side materialization.
    ExecutionGate().require_armed()
    materialize_execution_plan()


if __name__ == "__main__":
    main()
