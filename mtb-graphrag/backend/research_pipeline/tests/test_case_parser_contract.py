from __future__ import annotations

from backend.research_pipeline.casecontext import parser, prompt
from backend.research_pipeline.casecontext.mentions import build_mentions
from backend.research_pipeline.eligibility import gate


def _value(raw_value: str) -> dict[str, str]:
    return {"raw_value": raw_value, "quote": raw_value}


def _arguments(**overrides):
    value = {
        "disease": None,
        "biomarkers": [],
        "previous_interventions": [],
        "target_intervention": None,
        "query_intent": None,
        "clinical_question": None,
    }
    value.update(overrides)
    return value


def test_specific_therapy_question_uses_enum_and_preserves_question_text():
    arguments = _arguments(
        target_intervention=_value("panitumumab"),
        query_intent="THERAPY_EVALUATION",
        clinical_question="Can panitumumab be considered?",
    )

    assert prompt.tool_argument_errors(arguments) == []


def test_open_therapy_question_uses_discovery_enum():
    arguments = _arguments(
        query_intent="THERAPY_DISCOVERY",
        clinical_question="What treatment options are available?",
    )

    assert prompt.tool_argument_errors(arguments) == []


def test_unclear_question_uses_null_intent_and_preserves_free_text():
    arguments = _arguments(clinical_question="Could you review this case?")

    assert prompt.tool_argument_errors(arguments) == []


def test_free_text_query_intent_is_rejected():
    arguments = _arguments(
        query_intent="The clinical question concerns panitumumab.",
        clinical_question="The clinical question concerns panitumumab.",
    )

    assert prompt.tool_argument_errors(arguments) == ["QUERY_INTENT_INVALID"]


def test_explicit_gene_without_alteration_is_preserved():
    text = "The clinical question concerns the relation between CYP2D6 and raclopride."
    context = parser.adapt_case_context(
        "case-cyp2d6",
        _arguments(
            biomarkers=[{"gene": _value("CYP2D6"), "alteration": None}],
            clinical_question="The clinical question concerns the relation between CYP2D6 and raclopride.",
        ),
        text,
    )

    assert context["biomarkers"] == [{
        "gene": "CYP2D6",
        "alteration": None,
        "raw_value": "CYP2D6",
        "normalized_value": "CYP2D6",
        "source_spans": [{"quote": "CYP2D6", "start_offset": text.index("CYP2D6"), "end_offset": text.index("CYP2D6") + len("CYP2D6")}],
    }]
    assert context["clinical_question"] == text


def test_null_intent_with_sufficient_context_can_proceed_to_retrieval():
    text = "Patient with colorectal cancer and KRAS G12D mutation."
    context = parser.adapt_case_context(
        "case-null-intent",
        _arguments(
            disease=_value("colorectal cancer"),
            biomarkers=[{"gene": _value("KRAS"), "alteration": _value("G12D")}],
            clinical_question="",
        ),
        text,
    )

    decision = gate.evaluate(text, context, build_mentions(context, text), [], [], transport_ok=True)

    assert decision.eligibility_status == gate.ELIGIBLE_FOR_RETRIEVAL


def test_null_intent_with_empty_context_stops_for_insufficient_context():
    text = "Vorrei sapere quali opzioni ci sono per questo paziente."
    context = parser.adapt_case_context("case-empty", _arguments(clinical_question=text), text)

    from backend.research_pipeline.casecontext.pipeline import validate_minimal_case_context

    assert validate_minimal_case_context(context) == {
        "valid": False,
        "run_status": "INSUFFICIENT_CASE_CONTEXT",
        "missing": ["clinical_anchor"],
        "ambiguities": [],
    }


def test_semantically_empty_alteration_object_is_normalized_to_null():
    arguments = _arguments(
        biomarkers=[{
            "gene": _value("CYP2D6"),
            "alteration": {"raw_value": None, "quote": None},
        }]
    )

    normalized = parser.normalize_empty_alterations(arguments)

    assert normalized["biomarkers"][0]["alteration"] is None


def test_non_empty_alteration_object_is_preserved():
    alteration = {"raw_value": "G12D", "quote": "KRAS G12D"}
    arguments = _arguments(
        biomarkers=[{"gene": _value("KRAS"), "alteration": alteration}]
    )

    normalized = parser.normalize_empty_alterations(arguments)

    assert normalized["biomarkers"][0]["alteration"] == alteration


def test_gene_only_biomarker_remains_valid_after_empty_normalization():
    arguments = parser.normalize_empty_alterations(_arguments(
        biomarkers=[{
            "gene": _value("CYP2D6"),
            "alteration": {"raw_value": None, "quote": None},
        }]
    ))

    assert prompt.tool_argument_errors(arguments) == []
    assert parser.adapt_case_context("case-cyp2d6", arguments, "CYP2D6")["biomarkers"][0]["alteration"] is None


def test_malformed_non_empty_alteration_object_remains_rejected():
    arguments = _arguments(
        biomarkers=[{
            "gene": _value("KRAS"),
            "alteration": {"raw_value": "G12D"},
        }]
    )

    assert prompt.tool_argument_errors(arguments) == ["BIOMARKER_0_ALTERATION_KEYS_INVALID"]
