"""Malformed HTTP-success envelopes fail at the common boundary, not in consumers."""
import copy
from unittest.mock import Mock

import pytest

from backend.research_pipeline.budget import CallBudget
from backend.research_pipeline.casecontext import parser
from backend.research_pipeline.enrichment import enricher_v3, transport
from backend.research_pipeline.llm_config import LLMEndpoint


MALFORMED = [
    [], [None], None, "not an envelope",
    {"choices": {}}, {"choices": [None]},
    {"choices": [{"message": []}]},
    {"choices": [{"message": {"tool_calls": {}}}]},
    {"choices": [{"message": {"tool_calls": [None]}}]},
    {"choices": [{"message": {"tool_calls": [{"function": []}]}}]},
    {"choices": [], "usage": []},
]


@pytest.fixture(autouse=True)
def offline_endpoint(monkeypatch):
    monkeypatch.setattr(transport, "endpoint", lambda: LLMEndpoint("https://example.invalid/v1/chat/completions", "test"))
    monkeypatch.setattr(transport.llm_config, "api_key", lambda: "test-only")
    monkeypatch.setattr(transport, "_wait_for_rate_limit", lambda: None)


def response(body, status=200):
    result = Mock(status_code=status, headers={}, text="not JSON")
    result.json.return_value = copy.deepcopy(body)
    return result


@pytest.mark.parametrize("body", MALFORMED)
@pytest.mark.parametrize("diagnostics", [False, True])
def test_common_http_boundary_rejects_malformed_envelope_without_retry(monkeypatch, body, diagnostics):
    post = Mock(return_value=response(body))
    monkeypatch.setattr(transport.requests, "post", post)
    function = transport.post_with_infra_retry_with_diagnostics if diagnostics else transport.post_with_infra_retry
    budget = CallBudget(1)
    with budget.activate():
        result = function({"messages": []})
    assert result[:4] == (200, None, "INVALID_RESPONSE_ENVELOPE", 0)
    assert post.call_count == 1
    assert budget.transport_snapshot()["physical_calls"] == 1
    if diagnostics:
        assert result[4]["raw_response_body"] == body


@pytest.mark.parametrize("body", MALFORMED)
@pytest.mark.parametrize("reader", [False, True])
def test_public_parser_and_reader_reject_malformed_envelopes_without_crashing(monkeypatch, body, reader):
    post = Mock(return_value=response(body))
    monkeypatch.setattr(transport.requests, "post", post)
    budget = CallBudget(1)
    with budget.activate():
        if reader:
            result = enricher_v3.call_enricher_v3("CASE", "CANDIDATE", "PAPER", {}, {}, [],
                                                request_payload={"messages": []})
        else:
            result = parser.call_parser("CASE", "Possible TP53 R175H.")
    assert result["transport_result"] == "HTTP_ERROR"
    assert result["transport_reason_codes"] == ["INVALID_RESPONSE_ENVELOPE"]
    assert result["model_call_count"] == 1
    assert post.call_count == 1
    assert budget.transport_snapshot()["physical_calls"] == 1


def test_malformed_diagnostic_body_is_preserved_and_sanitized(monkeypatch):
    body = {"choices": [None], "provider_note": "Bearer private-token"}
    monkeypatch.setattr(transport.requests, "post", Mock(return_value=response(body)))
    result = transport.post_with_infra_retry_with_diagnostics({})
    assert result[1:3] == (None, "INVALID_RESPONSE_ENVELOPE")
    assert result[4]["raw_response_body"] == {"choices": [None], "provider_note": "Bearer REDACTED"}


@pytest.mark.parametrize("reader", [False, True])
def test_null_usage_is_missing_telemetry_not_a_failed_valid_tool_call(monkeypatch, reader):
    import json
    from backend.research_pipeline.casecontext import prompt as parser_prompt
    from backend.research_pipeline.enrichment import prompt_v3 as reader_prompt

    arguments = {"decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"} if reader else {
        "disease": None, "biomarkers": [], "previous_interventions": [],
        "target_intervention": None, "query_intent": None, "clinical_question": None,
    }
    name = reader_prompt.TOOL_NAME if reader else parser_prompt.TOOL_NAME
    body = {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }]}}], "usage": None}
    post = Mock(return_value=response(body))
    monkeypatch.setattr(transport.requests, "post", post)
    budget = CallBudget(1)
    with budget.activate():
        result = (enricher_v3.call_enricher_v3("CASE", "CANDIDATE", "PAPER", {}, {}, [],
                                             request_payload={"messages": []}) if reader
                  else parser.call_parser("CASE", "Research case."))
    assert result["transport_result"] == ("V3_TRANSPORT_VALID" if reader else "FORCED_TOOL_VALID")
    assert result["input_tokens"] is None and result["output_tokens"] is None
    assert result["token_usage_complete"] is False
    assert post.call_count == 1
    assert budget.transport_snapshot()["usage_complete"] is False


@pytest.mark.parametrize("diagnostics", [False, True])
def test_http_5xx_retries_remain_bounded_even_with_malformed_body(monkeypatch, diagnostics):
    valid = {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
    post = Mock(side_effect=[response([None], 503), response(valid)])
    monkeypatch.setattr(transport.requests, "post", post)
    monkeypatch.setattr(transport.time, "sleep", lambda _: None)
    function = transport.post_with_infra_retry_with_diagnostics if diagnostics else transport.post_with_infra_retry
    budget = CallBudget(2)
    with budget.activate():
        result = function({"messages": []})
    assert result[:4] == (200, valid, None, 1)
    assert post.call_count == 2
    assert budget.transport_snapshot()["physical_calls"] == 2


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {}}]},
    {"choices": [{"message": {"tool_calls": [{"function": {"name": "wrong_tool", "arguments": "{}"}}]}}]}])
def test_well_shaped_missing_or_wrong_tool_stays_with_existing_classifier(monkeypatch, body):
    monkeypatch.setattr(transport.requests, "post", Mock(return_value=response(body)))
    result = transport.post_with_infra_retry({})
    assert result[:4] == (200, body, None, 0)


@pytest.mark.parametrize("diagnostics", [False, True])
@pytest.mark.parametrize("body,parser_outcome", [
    ({"choices": None}, "NO_TOOL_CALL"),
    ({"choices": [{"message": None}]}, "FORCED_TOOL_IGNORED"),
    ({"choices": [{"message": {"tool_calls": None}}]}, "FORCED_TOOL_IGNORED"),
    ({"choices": [{"message": {"tool_calls": [{"function": None}]}}]}, "WRONG_TOOL_NAME"),
])
def test_previously_tolerated_null_containers_keep_existing_classification(monkeypatch, body, parser_outcome, diagnostics):
    monkeypatch.setattr(transport.requests, "post", Mock(return_value=response(body)))
    function = transport.post_with_infra_retry_with_diagnostics if diagnostics else transport.post_with_infra_retry
    result = function({})
    assert result[:4] == (200, body, None, 0)
    assert transport.transport_result(*result[:3], "submit_case_context", lambda _: [])[0] == parser_outcome
    assert enricher_v3._transport(*result[:3])[0] == "INVALID_TOOL_CALL"
