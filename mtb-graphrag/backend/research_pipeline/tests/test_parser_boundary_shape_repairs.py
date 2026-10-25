"""Malformed model enum values must remain validation failures, not crashes."""
from copy import deepcopy
import json

import pytest

from backend.research_pipeline.casecontext import parser, prompt


def arguments(query_intent):
    return {
        "disease": None,
        "biomarkers": [],
        "previous_interventions": [],
        "target_intervention": None,
        "query_intent": query_intent,
        "clinical_question": None,
    }


@pytest.mark.parametrize("intent", [[], {}, ["THERAPY_EVALUATION"], {"raw_value": "THERAPY_EVALUATION"},
                                    True, 12, "Find therapy"])
def test_invalid_intent_json_types_are_rejected_without_validator_exception(intent):
    assert "QUERY_INTENT_INVALID" in prompt.tool_argument_errors(arguments(intent), require_annotations=True)


@pytest.mark.parametrize("intent", [None, "THERAPY_EVALUATION", "THERAPY_DISCOVERY"])
def test_declared_intent_enum_contract_is_preserved(intent):
    assert prompt.tool_argument_errors(arguments(intent), require_annotations=True) == []


@pytest.mark.parametrize("intent", [[], {}])
@pytest.mark.parametrize("channel", ["tool", "text"])
def test_parser_classifies_invalid_intent_instead_of_crashing(monkeypatch, intent, channel):
    value = arguments(intent)
    message = {"content": json.dumps(value)} if channel == "text" else {
        "tool_calls": [{"function": {"name": prompt.TOOL_NAME, "arguments": json.dumps(value)}}],
    }
    body = {"choices": [{"finish_reason": "stop", "message": message}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    calls = []

    def post(payload):
        calls.append(deepcopy(payload))
        return 200, deepcopy(body), None, 0, {"http_status": 200, "raw_response_body": deepcopy(body)}

    monkeypatch.setattr(parser.tr, "post_with_infra_retry_with_diagnostics", post)
    result = parser.call_parser("INVALID-INTENT", "Review the research case.", require_annotations=True)
    assert result["transport_result"] == "INVALID_TOOL_ARGUMENTS"
    assert result["transport_reason_codes"] == ["QUERY_INTENT_INVALID"]
    assert result["case_context_raw"] is None
    assert result["parser_diagnostics"]["raw_response_body"] == body
    assert result["model_call_count"] == len(calls) == 1
