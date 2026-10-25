"""Regressions derived from observed ablation failures, without provider calls."""
import copy
import json

import pytest

from backend.research_pipeline.casecontext import parser, prompt
from backend.research_pipeline.budget import CallBudget, CallBudgetExceeded


def arguments(gene="TP53", alteration="D281E", assertion="PRESENT"):
    return {
        "disease": None,
        "biomarkers": [{
            "gene": {"raw_value": gene, "quote": gene},
            "alteration": {"raw_value": alteration, "quote": alteration} if alteration else None,
            "assertion_status": assertion,
        }],
        "previous_interventions": [], "target_intervention": None,
        "query_intent": None, "clinical_question": None,
    }


def install(monkeypatch, values):
    requests = []

    def post(payload):
        budget = parser.tr.active_budget()
        if budget is not None:
            budget.before_transport(payload)
        requests.append(copy.deepcopy(payload))
        value = values[min(len(requests) - 1, len(values) - 1)]
        body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
        return 200, body, None, 0, {"http_status": 200, "raw_response_body": copy.deepcopy(body)}

    monkeypatch.setattr(parser.tr, "post_with_infra_retry_with_diagnostics", post)
    return requests


@pytest.mark.parametrize("extra", ["clinical_role", "submit_case_context"])
def test_observed_top_level_schema_error_gets_one_fresh_request(monkeypatch, extra):
    bad = {**arguments(), extra: None}
    calls = install(monkeypatch, [bad, arguments()])
    result = parser.call_parser("FORMAT", "TP53 D281E")
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert len(calls) == 2
    assert result["model_call_count"] == 2
    assert result["input_tokens"] == 20
    assert result["parser_attempts"][0]["transport_result"] == "INVALID_TOOL_ARGUMENTS"
    assert result["parser_attempts"][0]["raw_response_hash"] != result["raw_response_hash"]
    assert calls[0]["messages"][-1]["content"] == calls[1]["messages"][-2]["content"]


def test_persistent_schema_failure_stays_rejected_after_two_requests(monkeypatch):
    bad = {**arguments(), "clinical_role": "UNKNOWN"}
    calls = install(monkeypatch, [bad])
    result = parser.call_parser("FORMAT", "TP53 D281E")
    assert len(calls) == 2
    assert result["transport_result"] == "INVALID_TOOL_ARGUMENTS"
    assert result["case_context_raw"] is None


@pytest.mark.parametrize("gene", ["EGFR", "NRAS"])
def test_gene_copied_into_alteration_is_reextracted_not_silently_accepted(monkeypatch, gene):
    calls = install(monkeypatch, [arguments(gene, gene), arguments(gene, None)])
    result = parser.call_parser("GENE_ONLY", f"Molecular report: {gene}.")
    assert len(calls) == 2
    assert result["case_context_raw"]["biomarkers"][0]["alteration"] is None
    assert "DUPLICATE_GENE_ALTERATION" in result["parser_attempts"][0]["reason_codes"][0]


def test_recovery_does_not_turn_uncertainty_into_presence(monkeypatch):
    good = arguments("IDH1", "R132H", "UNCERTAIN")
    install(monkeypatch, [{**good, "submit_case_context": None}, good])
    result = parser.call_parser("UNCERTAIN", "Possible IDH1 R132H, unconfirmed.")
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["case_context_raw"]["biomarkers"][0]["assertion_status"] == "UNCERTAIN"


@pytest.mark.parametrize("label", ["molecular finding", "Reported biomarker", "dichiarato", "unknown"])
def test_reporting_words_cannot_be_used_as_a_molecular_alteration(monkeypatch, label):
    calls = install(monkeypatch, [arguments("JAK2", label), arguments("JAK2", None)])
    result = parser.call_parser("REPORT_LABEL", f"Reported biomarker JAK2; {label}.")
    assert len(calls) == 2
    assert result["case_context_raw"]["biomarkers"][0]["alteration"] is None
    assert "ALTERATION_IS_REPORT_LABEL" in result["parser_attempts"][0]["reason_codes"][0]


def test_schema_recovery_cannot_exceed_physical_budget(monkeypatch):
    calls = install(monkeypatch, [{**arguments(), "clinical_role": None}, arguments()])
    with CallBudget(1).activate(), pytest.raises(CallBudgetExceeded):
        parser.call_parser("CAP", "TP53 D281E")
    assert len(calls) == 1


def test_live_parser_reextracts_omitted_assertion_before_routing(monkeypatch):
    from backend.research_pipeline.live_providers import parser_fn
    good = arguments("TP53", "R175H", "UNCERTAIN")
    good["biomarkers"][0]["clinical_role"] = "UNKNOWN"
    missing = copy.deepcopy(good)
    missing["biomarkers"][0].pop("assertion_status")
    calls = install(monkeypatch, [missing, good])
    result = parser_fn(CallBudget(4), "LONG", "Possible TP53 R175H, unconfirmed.")
    assert len(calls) == 2
    assert result["case_context_raw"]["biomarkers"][0]["assertion_status"] == "UNCERTAIN"


def test_live_parser_never_accepts_persistently_missing_assertion(monkeypatch):
    from backend.research_pipeline.live_providers import parser_fn
    missing = arguments()
    missing["biomarkers"][0].pop("assertion_status")
    install(monkeypatch, [missing])
    result = parser_fn(CallBudget(4), "MISSING", "TP53 D281E")
    assert result["transport_result"] == "INVALID_TOOL_ARGUMENTS"
    assert result["case_context_raw"] is None


def test_provider_schema_requires_biomarker_assertion_and_role():
    # A valid literal pair alone must not instruct the provider to omit assertion.
    from jsonschema import Draft202012Validator
    value = arguments()
    errors = list(Draft202012Validator(prompt.CASECONTEXT_TOOL_SCHEMA).iter_errors(value))
    assert any(error.validator == "required" and "clinical_role" in error.message for error in errors)
    value["biomarkers"][0]["clinical_role"] = "UNKNOWN"
    assert not list(Draft202012Validator(prompt.CASECONTEXT_TOOL_SCHEMA).iter_errors(value))


@pytest.mark.parametrize("field,value", [("assertion_status", None), ("assertion_status", "POSITIVEISH"),
                                          ("clinical_role", None), ("clinical_role", "")])
def test_provider_and_live_validator_agree_on_invalid_annotations(field, value):
    from jsonschema import Draft202012Validator
    args = arguments()
    args["biomarkers"][0]["clinical_role"] = "UNKNOWN"
    args["biomarkers"][0][field] = value
    assert prompt.tool_argument_errors(args, require_annotations=True)
    assert list(Draft202012Validator(prompt.CASECONTEXT_TOOL_SCHEMA).iter_errors(args))


@pytest.mark.parametrize("malformed_first", [True, False])
def test_reader_recovers_missing_tool_call_but_never_retries_valid_abstention(monkeypatch, malformed_first):
    from backend.research_pipeline.enrichment import enricher_v3, prompt_v3, transport
    abstention = {"decision": "ABSTAIN", "abstain_reason": "NO_RELEVANT_EVIDENCE"}
    valid = {"choices": [{"finish_reason": "tool_calls", "message": {"tool_calls": [{
        "function": {"name": prompt_v3.TOOL_NAME, "arguments": json.dumps(abstention)},
    }]}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    invalid = {"choices": [{"finish_reason": "stop", "message": {"content": "No tool call"}}],
               "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
    bodies = [invalid, valid] if malformed_first else [valid]
    calls = []

    def post(payload):
        calls.append(copy.deepcopy(payload))
        return 200, copy.deepcopy(bodies[len(calls) - 1]), None, 0

    monkeypatch.setattr(transport, "post_with_infra_retry", post)
    payload = {"messages": [{"role": "user", "content": "Unchanged source evidence"}]}
    original = copy.deepcopy(payload)
    result, telemetry = transport.post_with_format_retry(
        payload, lambda status, body, error: enricher_v3._transport(status, body, error)[0])
    assert len(calls) == (2 if malformed_first else 1)
    assert enricher_v3._transport(result[0], result[1], result[2])[1]["decision"] == "ABSTAIN"
    assert telemetry["model_call_count"] == len(calls)
    assert payload == original
    if malformed_first:
        assert telemetry["format_attempts"][0]["outcome"] == "INVALID_TOOL_CALL"
        assert calls[1]["messages"][0] == original["messages"][0]
