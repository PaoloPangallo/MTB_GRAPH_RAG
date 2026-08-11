"""Future explicit start boundary; intentionally disarmed in this phase."""

from __future__ import annotations

from .common.arming import ExecutionGate


def main() -> None:
    ExecutionGate().require_armed()


if __name__ == "__main__":
    main()
