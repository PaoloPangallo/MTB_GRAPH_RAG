"""Figure plan validators; no figures are generated before final results."""

from __future__ import annotations

FIGURES = ("selector comparison", "ablation failure-mode reduction", "held-out routing", "stage latency")


def validate_figure_plan(plan: list[str]) -> None:
    if tuple(plan) != FIGURES:
        raise ValueError("figure plan diverges from frozen protocol")
