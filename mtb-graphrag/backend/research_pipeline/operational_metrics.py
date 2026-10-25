"""Read-only operational accounting; never derives scientific support states.

Unknown provider attempts/token usage remain explicit. Historical ledger rows
are projected without rewriting the recorded events.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _number(value: Any) -> bool:
    return type(value) in (int, float) and value >= 0


def _sum(values: list[Any]) -> int | float | None:
    measured = [value for value in values if _number(value)]
    return sum(measured) if measured else None


def operational_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    stages = {stage["stage_id"]: stage for stage in snapshot.get("stages") or []}
    observations: dict[str, dict[str, Any]] = {}
    for stage_id in (
        "stage_2_casecontext_parser",
        "stage_9_paper_context_enricher",
        "stage_10_enrichment_validation",
        "stage_14_narrator",
    ):
        stage = stages.get(stage_id)
        if not stage:
            continue
        output = stage.get("output_preview") or {}
        metrics = stage.get("metrics") or {}
        origin = stage.get("artifact_origin")
        if origin == "RECORDED_REAL_RUN" or stage.get("status") == "SKIPPED":
            observations[stage_id] = {
                "calls": 0,
                "calls_complete": True,
                "input_tokens": None,
                "output_tokens": None,
                "token_usage_complete": True,
                "transport_ms": None,
            }
            continue
        if stage_id == "stage_9_paper_context_enricher":
            recorded = list(output.get("calls") or [])
            failed = output.get("failed_call")
            if isinstance(failed, dict) and not any(
                failed == item for item in recorded
            ):
                recorded.append(failed)
            calls = [
                call
                for call in recorded
                if not call.get("reader_response_reused") and not call.get("replayed")
            ]
            count = metrics.get("real_llm_calls")
            if not _number(count):
                count = sum(call.get("model_call_count", 1) for call in calls)
            complete = all(
                _number(call.get("model_call_count")) for call in calls
            ) and count == sum(call.get("model_call_count", 0) for call in calls)
            measured = calls
            transport_ms = metrics.get(
                "reader_transport_ms", _sum([c.get("latency_ms") for c in calls])
            )
        elif stage_id == "stage_10_enrichment_validation":
            attempts = (output.get("semantic_verification") or {}).get("attempts") or []
            measured = [
                item.get("metrics") or {}
                for item in attempts
                if item.get("status") != "NOT_EXECUTED_BUDGET"
            ]
            count = sum(item.get("model_call_count") or 0 for item in measured)
            complete = all(_number(item.get("model_call_count")) for item in measured)
            transport_ms = _sum([item.get("latency_ms") for item in measured])
        else:
            measured = [metrics]
            count = metrics.get("real_llm_calls")
            complete = _number(count)
            if (
                stage_id == "stage_14_narrator"
                and stage.get("status") == "WARNING"
                and not output.get("transport_result")
                and not output.get("attempts")
            ):
                complete = False
                count = None
            if not complete:
                # Legacy parser success metrics stored only the final attempt.
                # Report an observed lower bound, never claim an exact total.
                diagnostic = output.get("parser_diagnostics") or {}
                count = diagnostic.get("attempt_count")
                if not _number(count):
                    count = (
                        1 + (metrics.get("retry_count") or 0)
                        if output.get("transport_result")
                        else 0
                    )
            transport_ms = metrics.get("latency_ms")
        input_tokens = _sum([item.get("input_tokens") for item in measured])
        output_tokens = _sum([item.get("output_tokens") for item in measured])
        token_complete = (
            count == 0
            and complete
            or (
                complete
                and all(
                    _number(item.get("input_tokens"))
                    and _number(item.get("output_tokens"))
                    and item.get("token_usage_complete", not item.get("retry_count"))
                    for item in measured
                )
                and output.get("token_usage_complete", True) is not False
            )
        )
        observations[stage_id] = {
            "calls": int(count),
            "calls_complete": complete,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "token_usage_complete": bool(token_complete),
            "transport_ms": transport_ms,
        }
    recorded_durations = {
        key: stage.get("duration_ms") for key, stage in stages.items()
    }
    transport_durations = {
        key: item["transport_ms"] for key, item in observations.items()
    }
    effective_durations = dict(recorded_durations)
    for key in (
        "stage_2_casecontext_parser",
        "stage_9_paper_context_enricher",
        "stage_10_enrichment_validation",
    ):
        value = transport_durations.get(key)
        if _number(value):
            effective_durations[key] = value
    selection_stage = stages.get("stage_8_paper_selection") or {}
    selection_metrics = selection_stage.get("metrics") or {}
    selection_records = (selection_stage.get("output_preview") or {}).get(
        "selections"
    ) or []
    selection_ms = selection_metrics.get(
        "selection_wall_ms",
        _sum([item.get("selection_wall_ms") for item in selection_records]),
    )
    selection_cpu_ms = selection_metrics.get(
        "selection_cpu_ms",
        _sum([item.get("selection_cpu_ms") for item in selection_records]),
    )
    if _number(selection_ms):
        effective_durations["stage_8_paper_selection"] = selection_ms
    wall_ms = None
    try:
        start = datetime.fromisoformat(snapshot["started_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(snapshot["completed_at"].replace("Z", "+00:00"))
        wall_ms = max(0, (end - start).total_seconds() * 1000)
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    observed_calls = sum(item["calls"] for item in observations.values())
    recorded_calls = snapshot.get("llm_calls") or 0
    total_calls = max(observed_calls, recorded_calls)
    in_progress = snapshot.get("status") in {"RUNNING", "PENDING"}
    if in_progress:
        reader_progress = (snapshot.get("work_progress") or {}).get("reader_calls")
        if _number(reader_progress):
            recorded_reader = observations.get("stage_9_paper_context_enricher", {}).get("calls", 0)
            total_calls = max(total_calls, observed_calls + max(0, reader_progress - recorded_reader))
    return {
        "llm_calls": total_calls,
        "llm_calls_complete": not in_progress and total_calls == observed_calls
        and all(item["calls_complete"] for item in observations.values()),
        "tokens_input": _sum([item["input_tokens"] for item in observations.values()]),
        "tokens_output": _sum(
            [item["output_tokens"] for item in observations.values()]
        ),
        "token_usage_complete": not in_progress and all(
            item["token_usage_complete"] for item in observations.values()
        ),
        "llm_by_stage": observations,
        "duration_ms_total": wall_ms,
        "duration_ms_by_stage": effective_durations,
        "recorded_stage_duration_ms_by_stage": recorded_durations,
        "llm_transport_ms_by_stage": transport_durations,
        "selection_cpu_ms": selection_cpu_ms,
        "computed_by": "backend_operational_projection/1.0",
    }
