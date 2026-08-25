from __future__ import annotations

import json

from backend.research_pipeline.casecontext import match_verifier, parser, prompt
from backend.research_pipeline.enrichment import transport


def _minimal_output(**overrides):
    value = {
        "disease": None,
        "biomarkers": [],
        "previous_interventions": [],
        "target_intervention": None,
        "query_intent": None,
    }
    value.update(overrides)
    return value


def test_parser_v2_schema_accepts_absent_intent_and_omits_derived_fields():
    properties = prompt.CASECONTEXT_TOOL_SCHEMA["properties"]
    assert set(properties) == {
        "disease",
        "biomarkers",
        "previous_interventions",
        "target_intervention",
        "query_intent",
        "ambiguities",
    }
    assert prompt.tool_argument_errors(_minimal_output()) == []


def test_parser_v2_accepts_gene_without_alteration():
    value = _minimal_output(
        disease={"raw_value": "gastric cancer", "quote": "gastric cancer"},
        biomarkers=[
            {
                "gene": {"raw_value": "ERBB2", "quote": "ERBB2"},
                "alteration": None,
            }
        ],
    )
    assert prompt.tool_argument_errors(value) == []


def test_parser_v2_adapter_builds_legacy_context_and_offsets():
    text = "Metastatic colorectal cancer with KRAS G12D. Evaluating panitumumab."
    value = {
        "disease": {"raw_value": "metastatic colorectal cancer", "quote": "Metastatic colorectal cancer"},
        "biomarkers": [{
            "gene": {"raw_value": "KRAS", "quote": "KRAS G12D"},
            "alteration": {"raw_value": "G12D", "quote": "KRAS G12D"},
        }],
        "previous_interventions": [],
        "target_intervention": {"raw_value": "panitumumab", "quote": "panitumumab"},
        "query_intent": "THERAPY_EVALUATION",
    }
    context = parser.adapt_case_context("case-1", value, text)
    assert context["case_id"] == "case-1"
    assert context["clinical_question"] == text
    assert context["disease"]["source_spans"][0]["start_offset"] == 0
    assert context["target_intervention"]["source_spans"][0]["start_offset"] == text.index("panitumumab")
    assert context["biomarkers"][0]["gene"] == "KRAS"
    assert context["biomarkers"][0]["alteration"] == "G12D"


def test_query_intent_null_is_not_a_match_verifier_failure():
    text = "A patient with breast cancer and an ERBB2 abnormality."
    context = parser.adapt_case_context(
        "case-ambiguous",
        _minimal_output(
            disease={"raw_value": "breast cancer", "quote": "breast cancer"},
            biomarkers=[{
                "gene": {"raw_value": "ERBB2", "quote": "ERBB2"},
                "alteration": {"raw_value": "abnormality", "quote": "ERBB2 abnormality"},
            }],
        ),
        text,
    )
    records = match_verifier.verify_case_context(context, text)
    essential_ok, _ = match_verifier.essential_fields_pass(records)
    assert essential_ok is True


def test_evaluation_without_verified_target_remains_valid_but_not_eligible():
    value = _minimal_output(
        disease={"raw_value": "breast cancer", "quote": "breast cancer"},
        biomarkers=[{
            "gene": {"raw_value": "ERBB2", "quote": "ERBB2"},
            "alteration": None,
        }],
        query_intent="THERAPY_EVALUATION",
    )
    assert prompt.tool_argument_errors(value) == []


def test_quote_absent_is_rejected_by_match_verifier_after_valid_parsing():
    text = "A patient with breast cancer."
    context = parser.adapt_case_context(
        "case-bad-quote",
        _minimal_output(disease={"raw_value": "lung cancer", "quote": "lung cancer"}),
        text,
    )
    records = match_verifier.verify_case_context(context, text)
    assert any(record.reason_code == "QUOTE_NOT_IN_TEXT" for record in records)


def test_transport_failure_preserves_parser_diagnostic_fields(monkeypatch):
    def fake_post(_payload):
        return 200, {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}, None, 0, {
            "response_headers": {"content-type": "application/json"},
        }

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("case-forced", "A patient with cancer.")
    assert result["transport_result"] == "FORCED_TOOL_IGNORED"
    assert result["parser_diagnostics"]["finish_reason"] == "stop"
    assert result["parser_diagnostics"]["tool_calls_present"] is False


def test_malformed_json_remains_invalid_tool_arguments():
    result, _, _, reasons = transport.transport_result(
        200,
        {"choices": [{"message": {"tool_calls": [{"function": {"name": prompt.TOOL_NAME, "arguments": "{"}}]}}]},
        None,
        prompt.TOOL_NAME,
        prompt.tool_argument_errors,
    )
    assert result == "INVALID_TOOL_ARGUMENTS"
    assert reasons == ["ARGUMENTS_NOT_JSON"]


def test_scalar_disease_remains_invalid_tool_arguments():
    value = _minimal_output(disease="gastric cancer")
    assert prompt.tool_argument_errors(value) == ["DISEASE_NOT_OBJECT"]


def test_disease_scalar_is_normalized_only_when_literal_text_matches():
    arguments = _minimal_output(disease="gastric cancer")
    normalized, event = parser.normalize_disease_scalar(arguments, "A patient with gastric cancer.")
    assert normalized["disease"] == {"raw_value": "gastric cancer", "quote": "gastric cancer"}
    assert event == {"code": "DISEASE_SCALAR_NORMALIZED", "original_value": "gastric cancer", "matched_quote": "gastric cancer"}


def test_disease_scalar_is_not_normalized_when_unverifiable_or_empty():
    for value, text in (("gastric cancer", "A patient with lung cancer."), ("", "A patient with gastric cancer.")):
        arguments = _minimal_output(disease=value)
        normalized, event = parser.normalize_disease_scalar(arguments, text)
        assert normalized["disease"] == value
        assert event is None


def test_disease_null_and_object_are_unchanged_and_gene_scalar_is_rejected():
    null_args, null_event = parser.normalize_disease_scalar(_minimal_output(), "No disease stated.")
    assert null_args["disease"] is None
    assert null_event is None

    object_args = _minimal_output(disease={"raw_value": "gastric cancer", "quote": "gastric cancer"})
    object_out, object_event = parser.normalize_disease_scalar(object_args, "gastric cancer")
    assert object_out == object_args
    assert object_event is None

    gene_string = _minimal_output(biomarkers=[{"gene": "ERBB2", "alteration": None}])
    gene_out, gene_event = parser.normalize_disease_scalar(gene_string, "ERBB2")
    assert gene_out == gene_string
    assert gene_event is None


def test_target_intervention_scalar_is_normalized_only_when_literal_text_matches():
    arguments = _minimal_output(target_intervention="panitumumab")
    normalized, event = parser.normalize_target_intervention_scalar(
        arguments,
        "The oncologist is evaluating panitumumab.",
    )
    assert normalized["target_intervention"] == {
        "raw_value": "panitumumab",
        "quote": "panitumumab",
    }
    assert event == {
        "code": "TARGET_INTERVENTION_SCALAR_NORMALIZED",
        "original_value": "panitumumab",
        "matched_quote": "panitumumab",
    }
    assert prompt.tool_argument_errors(normalized) == []


def test_target_intervention_scalar_is_not_normalized_when_literal_text_is_absent():
    arguments = _minimal_output(target_intervention="panitumumab")
    normalized, event = parser.normalize_target_intervention_scalar(
        arguments,
        "The oncologist is evaluating cetuximab.",
    )
    assert normalized["target_intervention"] == "panitumumab"
    assert event is None
    assert prompt.tool_argument_errors(normalized) == ["TARGET_INTERVENTION_NOT_OBJECT"]


def test_target_intervention_object_is_unchanged():
    arguments = _minimal_output(
        target_intervention={"raw_value": "panitumumab", "quote": "panitumumab"}
    )
    normalized, event = parser.normalize_target_intervention_scalar(
        arguments,
        "The oncologist is evaluating panitumumab.",
    )
    assert normalized == arguments
    assert event is None


def test_target_intervention_null_is_unchanged():
    arguments = _minimal_output(target_intervention=None)
    normalized, event = parser.normalize_target_intervention_scalar(
        arguments,
        "No target therapy is named.",
    )
    assert normalized == arguments
    assert event is None


def test_target_intervention_ambiguous_text_match_fails_closed():
    arguments = _minimal_output(target_intervention="panitumumab")
    normalized, event = parser.normalize_target_intervention_scalar(
        arguments,
        "The text mentions panitumumab and panitumumab again.",
    )
    assert normalized["target_intervention"] == "panitumumab"
    assert event is None
    assert prompt.tool_argument_errors(normalized) == ["TARGET_INTERVENTION_NOT_OBJECT"]


def test_call_parser_normalizes_verifiable_target_intervention_scalar(monkeypatch):
    response = {
        "choices": [{
            "message": {"content": "", "tool_calls": [{
                "function": {
                    "name": prompt.TOOL_NAME,
                    "arguments": json.dumps(_minimal_output(target_intervention="panitumumab")),
                },
            }]},
            "finish_reason": "tool_calls",
        }],
    }

    monkeypatch.setattr(
        "backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics",
        lambda _payload: _fake_attempt(response),
    )
    result = parser.call_parser("case-target-scalar", "A patient is evaluating panitumumab.")
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["case_context_v2"]["target_intervention"] == {
        "raw_value": "panitumumab",
        "quote": "panitumumab",
    }
    assert result["parser_diagnostics"]["target_intervention_normalization"] == {
        "code": "TARGET_INTERVENTION_SCALAR_NORMALIZED",
        "original_value": "panitumumab",
        "matched_quote": "panitumumab",
    }


def test_call_parser_logs_disease_scalar_normalization(monkeypatch):
    response = {
        "choices": [{
            "message": {"content": "", "tool_calls": [{
                "function": {"name": prompt.TOOL_NAME, "arguments": '{"disease":"gastric cancer","biomarkers":[],"previous_interventions":[],"target_intervention":null,"query_intent":null}'},
            }]},
            "finish_reason": "tool_calls",
        }],
    }

    def fake_post(_payload):
        return 200, response, None, 0, {"response_headers": {}}

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("case-disease-scalar", "A patient with gastric cancer.")
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["case_context_v2"]["disease"] == {"raw_value": "gastric cancer", "quote": "gastric cancer"}
    assert result["parser_diagnostics"]["disease_normalization"] == {
        "code": "DISEASE_SCALAR_NORMALIZED",
        "original_value": "gastric cancer",
        "matched_quote": "gastric cancer",
    }


def _parser_response(arguments, *, finish_reason="tool_calls"):
    return {
        "choices": [{
            "message": {
                "content": "",
                "tool_calls": [{
                    "function": {
                        "name": prompt.TOOL_NAME,
                        "arguments": json.dumps(arguments),
                    },
                }],
            },
            "finish_reason": finish_reason,
        }],
    }


def _empty_parser_response():
    return {"choices": [{"message": {"content": ""}, "finish_reason": "stop"}]}


def _valid_parser_arguments():
    return _minimal_output(
        disease={"raw_value": "breast cancer", "quote": "breast cancer"},
        biomarkers=[{
            "gene": {"raw_value": "ERBB2", "quote": "ERBB2"},
            "alteration": None,
        }],
        query_intent=None,
    )


def _fake_attempt(response, status=200):
    return status, response, None, 0, {"http_status": status, "response_headers": {}}


def test_forced_tool_ignored_retries_once_and_recovers(monkeypatch):
    attempts = [_fake_attempt(_empty_parser_response()), _fake_attempt(_parser_response(_valid_parser_arguments()))]
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return attempts.pop(0)

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("retry-recovered", "A patient with breast cancer and ERBB2.")
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["retry_result"] == "FORCED_TOOL_IGNORED_RECOVERED"
    assert [item["attempt"] for item in result["parser_attempts"]] == [1, 2]
    assert result["parser_attempts"][0]["transport_result"] == "FORCED_TOOL_IGNORED"
    assert result["parser_attempts"][1]["transport_result"] == "FORCED_TOOL_VALID"


def test_forced_tool_ignored_stops_after_one_retry(monkeypatch):
    attempts = [_fake_attempt(_empty_parser_response()), _fake_attempt(_empty_parser_response())]
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return attempts.pop(0)

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("retry-final", "A patient with breast cancer.")
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert result["transport_result"] == "FORCED_TOOL_IGNORED"
    assert result["retry_result"] == "FORCED_TOOL_IGNORED_FINAL"
    assert result["parser_attempts"][1]["transport_result"] == "FORCED_TOOL_IGNORED"


def test_valid_first_attempt_does_not_retry(monkeypatch):
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return _fake_attempt(_parser_response(_valid_parser_arguments()))

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("no-retry-valid", "A patient with breast cancer and ERBB2.")
    assert len(calls) == 1
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["retry_result"] is None


def test_invalid_tool_arguments_do_not_retry(monkeypatch):
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return _fake_attempt(_parser_response({**_valid_parser_arguments(), "disease": 42}))

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("no-retry-invalid", "A patient with breast cancer.")
    assert len(calls) == 1
    assert result["transport_result"] == "INVALID_TOOL_ARGUMENTS"
    assert result["retry_result"] is None


def test_http_error_does_not_use_forced_tool_retry(monkeypatch):
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return _fake_attempt(None, status=500)

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("no-retry-http", "A patient with breast cancer.")
    assert len(calls) == 1
    assert result["transport_result"] == "HTTP_ERROR"
    assert result["retry_result"] is None


def test_valid_null_intent_does_not_retry(monkeypatch):
    calls = []

    def fake_post(payload):
        calls.append(payload)
        return _fake_attempt(_parser_response(_valid_parser_arguments()))

    monkeypatch.setattr("backend.research_pipeline.casecontext.parser.tr.post_with_infra_retry_with_diagnostics", fake_post)
    result = parser.call_parser("no-retry-null-intent", "A patient with breast cancer and ERBB2.")
    assert len(calls) == 1
    assert result["transport_result"] == "FORCED_TOOL_VALID"
    assert result["case_context_v2"]["query_intent"] is None
    assert result["retry_result"] is None


def test_null_intent_reaches_software_gate_as_ambiguous():
    from backend.research_pipeline.eligibility import gate
    from backend.research_pipeline.casecontext.mentions import build_mentions

    text = "A patient with breast cancer and an ERBB2 abnormality."
    context = parser.adapt_case_context(
        "case-ambiguous",
        _minimal_output(
            disease={"raw_value": "breast cancer", "quote": "breast cancer"},
            biomarkers=[{
                "gene": {"raw_value": "ERBB2", "quote": "ERBB2"},
                "alteration": {"raw_value": "abnormality", "quote": "ERBB2 abnormality"},
            }],
        ),
        text,
    )
    decision = gate.evaluate(text, context, build_mentions(context, text), [], [], transport_ok=True)
    assert decision.eligibility_status == gate.AMBIGUOUS_CASE_CONTEXT


def test_therapy_evaluation_without_target_is_not_parser_error():
    value = _minimal_output(query_intent="THERAPY_EVALUATION")
    assert prompt.tool_argument_errors(value) == []


def test_discovery_without_target_is_structurally_valid():
    value = _minimal_output(query_intent="THERAPY_DISCOVERY")
    assert prompt.tool_argument_errors(value) == []
