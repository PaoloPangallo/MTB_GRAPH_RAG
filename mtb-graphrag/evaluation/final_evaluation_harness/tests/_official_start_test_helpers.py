from __future__ import annotations

from collections.abc import Callable

from evaluation.final_evaluation_harness.common.runner import build_full_plan


def full_plan_with_selected_units(protocol, selected_run_ids: set[str]):
    """Return the sealed full plan and its selected test-only subset."""
    full_plan = build_full_plan(protocol)
    selected = [unit for unit in full_plan if unit.run_id in selected_run_ids]
    assert len(selected) == len(selected_run_ids)
    return full_plan, selected


def dispatch_selected_only(dispatch: Callable, selected_run_ids: set[str]) -> Callable:
    """Keep official-start coverage full while executing only fixture units."""
    def _dispatch(plan, protocol, campaign_root, **kwargs):
        selected = [unit for unit in plan if unit.run_id in selected_run_ids]
        assert len(selected) == len(selected_run_ids)
        result = dispatch(selected, protocol, campaign_root, **kwargs)
        ledger = kwargs.get("ledger")
        assert ledger is not None
        for unit in plan:
            if unit.run_id in selected_run_ids:
                continue
            attempt_id = f"{unit.run_id}/fixture-skip"
            ledger.append(
                "COMPLETE",
                attempt_id=attempt_id,
                run_id=unit.run_id,
                unit_status="SKIPPED_FOR_FIXTURE",
                failure_class="TEST_FIXTURE",
                raw_reason_code="NOT_EXECUTED_BY_FIXTURE",
            )
        return result

    return _dispatch
