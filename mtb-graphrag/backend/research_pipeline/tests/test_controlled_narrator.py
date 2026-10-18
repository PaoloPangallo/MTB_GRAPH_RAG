import json
from copy import deepcopy
from unittest.mock import patch

from backend.research_pipeline.narrative import controlled_narrator as cn
from backend.research_pipeline.narrative.controlled import verify_controlled


def projection(count=3):
    return {"narrator_input_hash": "input", "candidates": [
        {"candidate_id": f"C-{i}", "branch": "KG_ONLY", "canonical_status": "KG_ONLY",
         "support_direction": "", "warnings": ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"],
         "critical_warnings": ["DOCUMENT_PROVENANCE_NOT_AVAILABLE"], "validated_quotes": [],
         "kg_context": {"document_provenance": "NOT_AVAILABLE"}}
        for i in range(count)], "limitations": []}


def response(args):
    return 200, {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [
        {"type": "function", "function": {"name": cn.TOOL_NAME, "arguments": json.dumps(args)}}]}}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10}}, None, 0


def valid_provider(payload):
    data = json.loads(payload["messages"][-1]["content"])
    return response({"entries": [{"fact_id": e["fact_id"], "variant": "detailed"}
                                  for e in data["entries"]]})


def test_complete_model_plan_is_verified_and_input_unchanged():
    source = projection(43)
    before = deepcopy(source)
    with patch.object(cn.tr, "post_with_infra_retry", side_effect=valid_provider):
        result = cn.call_controlled_narrator("C", source)
    assert result["model_plan_valid"] is True
    assert result["model_call_count"] == 2
    assert result["input_tokens"] == 40
    assert result["deterministic_fallback"] is None
    assert verify_controlled(source, result["narrative"])["status"] == "PASS"
    assert source == before


def test_fabricated_reference_never_becomes_model_success():
    source = projection(2)
    with patch.object(cn.tr, "post_with_infra_retry", return_value=response({
            "entries": [{"fact_id": "invented", "variant": "detailed"}]})):
        result = cn.call_controlled_narrator("C", source)
    assert result["model_plan_valid"] is False
    assert result["narrative"] is None
    assert result["model_call_count"] == 1
    assert verify_controlled(source, result["deterministic_fallback"])["status"] == "PASS"
    assert result["generation_mode"] == "DETERMINISTIC_FALLBACK"


def test_tool_ignored_recovery_is_bounded_and_all_calls_counted():
    sizes = []

    def provider(payload):
        data = json.loads(payload["messages"][-1]["content"])
        sizes.append(len(data["entries"]))
        if len(data["entries"]) > 20:
            return 200, {"choices": [{"message": {"content": "No tool"}}],
                         "usage": {"prompt_tokens": 20, "completion_tokens": 10}}, None, 0
        return valid_provider(payload)

    with patch.object(cn.tr, "post_with_infra_retry", side_effect=provider):
        result = cn.call_controlled_narrator("C", projection(40))
    assert sizes == [40, 20, 20]
    assert result["model_call_count"] == 3
    assert result["model_plan_valid"] is True
    assert len(result["attempts"]) == 3


def test_failed_later_batch_preserves_failure_and_complete_fallback():
    calls = 0

    def provider(payload):
        nonlocal calls
        calls += 1
        return valid_provider(payload) if calls == 1 else (401, {}, None, 0)

    source = projection(41)
    with patch.object(cn.tr, "post_with_infra_retry", side_effect=provider):
        result = cn.call_controlled_narrator("C", source)
    assert result["narrative"] is None
    assert result["model_plan_valid"] is False
    assert result["model_call_count"] == 2
    assert len(result["deterministic_fallback"]["candidate_narratives"]) == 41


def test_no_candidates_requires_no_model_call_and_is_not_model_success():
    with patch.object(cn.tr, "post_with_infra_retry") as provider:
        result = cn.call_controlled_narrator("C", projection(0))
    provider.assert_not_called()
    assert result["model_call_count"] == 0
    assert result["model_plan_valid"] is False
    assert verify_controlled(projection(0), result["deterministic_fallback"])["status"] == "PASS"
