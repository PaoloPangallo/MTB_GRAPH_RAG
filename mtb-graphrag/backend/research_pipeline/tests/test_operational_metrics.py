from copy import deepcopy

from backend.research_pipeline.operational_metrics import operational_summary


def stage(
    identity, *, metrics=None, output=None, origin="GENERATED_NOW", status="SUCCEEDED"
):
    return {
        "stage_id": identity,
        "metrics": metrics or {},
        "output_preview": output or {},
        "artifact_origin": origin,
        "status": status,
        "duration_ms": 15,
        "warnings": [],
        "errors": [],
    }


def snapshot(stages):
    return {
        "started_at": "2026-10-14T08:58:28+00:00",
        "completed_at": "2026-10-14T08:59:27+00:00",
        "stages": stages,
        "llm_calls": 5,
    }


def test_all_model_stages_including_narrator_and_retry_are_counted_once(monkeypatch):
    run = snapshot(
        [
            stage(
                "stage_2_casecontext_parser",
                metrics={
                    "real_llm_calls": 1,
                    "input_tokens": 2313,
                    "output_tokens": 214,
                    "latency_ms": 2108.67,
                },
            ),
            stage(
                "stage_9_paper_context_enricher",
                metrics={"real_llm_calls": 4, "reader_transport_ms": 7075.715},
                output={
                    "calls": [
                        {"model_call_count": 1, "input_tokens": x, "output_tokens": y}
                        for x, y in [(4572, 231), (3827, 37), (8575, 37), (8589, 37)]
                    ]
                },
            ),
            stage(
                "stage_10_enrichment_validation",
                output={"semantic_verification": {"attempts": []}},
            ),
            stage(
                "stage_14_narrator",
                metrics={
                    "real_llm_calls": 4,
                    "input_tokens": 7172,
                    "output_tokens": 3883,
                    "latency_ms": 20649.506,
                },
            ),
        ]
    )
    before = deepcopy(run)
    metrics = operational_summary(run)
    assert metrics["llm_calls"] == 9
    assert metrics["llm_calls_complete"] is True
    assert metrics["tokens_input"] == 35048
    assert metrics["tokens_output"] == 4439
    assert metrics["token_usage_complete"] is True
    assert metrics["duration_ms_total"] == 59000
    assert metrics["duration_ms_by_stage"]["stage_2_casecontext_parser"] == 2108.67
    assert (
        metrics["recorded_stage_duration_ms_by_stage"]["stage_2_casecontext_parser"]
        == 15
    )
    assert run == before
    from backend.api import research_routes

    monkeypatch.setattr(research_routes, "_snapshot_or_404", lambda _: run)
    api_metrics = research_routes.get_metrics("fixture")
    assert api_metrics["llm_calls"] == 9
    assert api_metrics["tokens_input"] == 35048
    assert api_metrics["duration_ms_total"] == 59000
    run["stages"][2]["output_preview"]["validations"] = [
        {"outcome": "QUOTE_INVALID"},
        {"outcome": "ENRICHMENT_V3_ABSTAINED"},
    ]
    api_metrics = research_routes.get_metrics("fixture")
    assert api_metrics["quotes_rejected"] == 1
    assert api_metrics["abstentions"] == 1


def test_legacy_final_parser_attempt_is_an_explicit_lower_bound():
    run = snapshot(
        [
            stage(
                "stage_2_casecontext_parser",
                output={"transport_result": "FORCED_TOOL_VALID"},
                metrics={"retry_count": 0, "input_tokens": 2313, "output_tokens": 214},
            )
        ]
    )
    run["llm_calls"] = 1
    result = operational_summary(run)
    assert result["llm_calls"] == 1
    assert result["llm_calls_complete"] is False
    assert result["token_usage_complete"] is False


def test_semantic_attempt_metrics_count_retries_but_budget_rejection_is_not_a_call():
    run = snapshot(
        [
            stage(
                "stage_10_enrichment_validation",
                output={
                    "semantic_verification": {
                        "attempts": [
                            {
                                "status": "EXECUTED",
                                "metrics": {
                                    "model_call_count": 2,
                                    "retry_count": 1,
                                    "input_tokens": 12,
                                    "output_tokens": 7,
                                    "token_usage_complete": False,
                                    "latency_ms": 1000,
                                },
                            },
                            {"status": "NOT_EXECUTED_BUDGET"},
                        ]
                    }
                },
            )
        ]
    )
    run["llm_calls"] = 0
    result = operational_summary(run)
    assert result["llm_calls"] == 2
    assert result["tokens_input"] == 12
    assert result["token_usage_complete"] is False


def test_reader_reuse_and_recorded_replay_do_not_add_model_calls_or_tokens():
    run = snapshot(
        [
            stage(
                "stage_9_paper_context_enricher",
                metrics={"real_llm_calls": 1},
                output={
                    "calls": [
                        {"model_call_count": 1, "input_tokens": 10, "output_tokens": 2},
                        {
                            "model_call_count": 1,
                            "input_tokens": 10,
                            "output_tokens": 2,
                            "reader_response_reused": True,
                        },
                    ]
                },
            ),
            stage(
                "stage_14_narrator",
                origin="RECORDED_REAL_RUN",
                metrics={
                    "real_llm_calls": 4,
                    "input_tokens": 200,
                    "output_tokens": 100,
                },
            ),
        ]
    )
    run["llm_calls"] = 1
    result = operational_summary(run)
    assert result["llm_calls"] == 1
    assert result["tokens_input"] == 10


def test_absent_measurements_are_not_reported_as_zero():
    result = operational_summary({"stages": [], "started_at": "unknown"})
    assert result["tokens_input"] is None
    assert result["tokens_output"] is None
    assert result["duration_ms_total"] is None


def test_reader_counter_without_records_is_not_complete_token_accounting():
    run = snapshot(
        [stage("stage_9_paper_context_enricher", metrics={"real_llm_calls": 5})]
    )
    result = operational_summary(run)
    assert result["llm_calls"] == 5
    assert result["llm_calls_complete"] is False
    assert result["token_usage_complete"] is False


def test_failed_reader_telemetry_is_not_lost_or_counted_twice():
    failed = {
        "model_call_count": 2,
        "input_tokens": 40,
        "output_tokens": 5,
        "latency_ms": 900,
    }
    run = snapshot(
        [
            stage(
                "stage_9_paper_context_enricher",
                status="FAILED",
                metrics={"real_llm_calls": 2},
                output={"calls": [], "failed_call": failed},
            )
        ]
    )
    run["llm_calls"] = 2
    metrics = operational_summary(run)
    assert metrics["llm_calls"] == 2
    assert metrics["tokens_input"] == 40
    assert metrics["tokens_output"] == 5
    assert metrics["llm_transport_ms_by_stage"]["stage_9_paper_context_enricher"] == 900
    run["stages"][0]["output_preview"]["calls"] = [failed]
    assert operational_summary(run)["tokens_input"] == 40


def test_narrator_exception_without_telemetry_is_not_exact_zero_usage():
    run = snapshot(
        [
            stage(
                "stage_14_narrator",
                status="WARNING",
                origin="NOT_EXECUTED",
                metrics={"real_llm_calls": 0},
            )
        ]
    )
    run["llm_calls"] = 0
    metrics = operational_summary(run)
    assert metrics["llm_calls_complete"] is False
    assert metrics["token_usage_complete"] is False
    assert metrics["tokens_input"] is None
