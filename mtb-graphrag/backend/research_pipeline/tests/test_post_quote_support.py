from __future__ import annotations

from backend.research_pipeline.enrichment.post_quote_support import (
    CONTEXT_ONLY,
    CONTRADICTORY,
    PARTIAL_SUPPORT,
    STRONG_SUPPORT,
    UNVERIFIABLE,
    assess_candidate_support,
)


def _candidate(*, direction: str = "Resistance", drug: str = "panitumumab") -> dict:
    return {
        "candidate_id": "GCA-test",
        "disease": [{"label": "metastatic colorectal cancer"}],
        "biomarkers": [
            {"label": "KRAS", "type": "Gene"},
            {"label": "G12D", "type": "Variant"},
        ],
        "interventions": [{"label": drug, "type": "Drug"}],
        "direction": direction,
    }


def _quote(*, text: str, evidence_kind: str | None = "RESISTANCE") -> dict:
    return {
        "author_claim_quote": text,
        "source_unit_id": "SU-1",
        "evidence_kind": evidence_kind,
    }


def test_complete_quote_is_strong_support() -> None:
    result = assess_candidate_support(
        _candidate(),
        _quote(text="mCRC KRAS G12D tumors showed resistance to panitumumab."),
        source_unit_text="mCRC KRAS G12D tumors showed resistance to panitumumab.",
    )

    assert result["result"] == STRONG_SUPPORT
    assert all(result["fields"][key] == "CONFIRMED" for key in ("gene", "alteration", "drug", "direction"))


def test_gene_family_without_specific_variant_is_partial_support() -> None:
    text = "patients with mCRC bearing KRAS mutations are clinically resistant to therapy with panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text), source_unit_text=text)

    assert result["result"] == PARTIAL_SUPPORT
    assert result["fields"]["gene"] == "CONFIRMED"
    assert result["fields"]["alteration"] == "NOT_CONFIRMED"
    assert result["fields"]["drug"] == "CONFIRMED"
    assert result["fields"]["direction"] == "CONFIRMED"


def test_drug_only_context_is_context_only() -> None:
    text = "The monoclonal antibodies panitumumab and cetuximab have proven valuable for treatment of metastatic colorectal cancer."
    result = assess_candidate_support(
        _candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text,
    )

    assert result["result"] == CONTEXT_ONLY
    assert result["fields"]["drug"] == "CONFIRMED"
    assert result["fields"]["gene"] == "NOT_CONFIRMED"
    assert result["fields"]["alteration"] == "NOT_CONFIRMED"
    assert result["fields"]["direction"] == "UNKNOWN"


def test_structured_opposite_direction_is_contradictory() -> None:
    result = assess_candidate_support(
        _candidate(direction="Resistance"),
        _quote(text="KRAS G12D tumors responded to panitumumab.", evidence_kind="RESPONSE"),
        source_unit_text="KRAS G12D tumors responded to panitumumab.",
    )

    assert result["fields"]["direction"] == "OPPOSITE"
    assert result["result"] == CONTRADICTORY


def test_unknown_drug_alias_does_not_become_contradictory() -> None:
    candidate = _candidate(direction="Sensitivity/Response", drug="ivosidenib")
    text = "The patient received a mutant IDH1 inhibitor (AG-120), but with no response."
    result = assess_candidate_support(
        candidate,
        _quote(text=text, evidence_kind=None),
        source_unit_text=text,
    )

    assert result["fields"]["drug"] == "UNKNOWN"
    assert result["result"] == UNVERIFIABLE


def test_false_literal_quote_is_rejected_before_support_check() -> None:
    from backend.research_pipeline.enrichment import validator_v2

    result = validator_v2.validate_enrichment_v2(
        "V2_TRANSPORT_VALID",
        {
            "decision": "QUOTE",
            "source_unit_id": "SU-1",
            "author_claim_quote": "not present",
            "author_context_summary": "The quote reports resistance.",
            "abstention_reason": "",
        },
        candidate=_candidate(),
        paper_bundle={"bundle_id": "B-1", "resolved_source_unit_ids": ["SU-1"]},
        source_units_by_id={"SU-1": {"text": "KRAS G12D resistance to panitumumab."}},
        requested_drug="panitumumab",
    )

    assert result["outcome"] == "REJECTED_QUOTE_NOT_FOUND"


def test_textual_clinically_resistant_to_candidate_drug_confirms_resistance() -> None:
    text = "Patients are clinically resistant to therapy with panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "CONFIRMED"


def test_textual_resistant_to_candidate_drug_confirms_resistance() -> None:
    text = "The tumor was resistant to panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "CONFIRMED"


def test_negated_resistance_is_not_confirmed() -> None:
    text = "The tumor was not resistant to panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "UNKNOWN"


def test_no_evidence_of_resistance_is_not_confirmed() -> None:
    text = "There was no evidence of resistance to panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "UNKNOWN"


def test_resistance_to_a_different_drug_is_not_bound_to_candidate() -> None:
    text = "The tumor was resistant to cetuximab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "UNKNOWN"


def test_no_response_is_not_mapped_to_resistance() -> None:
    text = "The tumor showed no response to panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "UNKNOWN"


def test_does_not_support_is_not_mapped_to_resistance() -> None:
    text = "The evidence does not support panitumumab."
    result = assess_candidate_support(_candidate(), _quote(text=text, evidence_kind=None), source_unit_text=text)

    assert result["fields"]["direction"] == "UNKNOWN"


def test_structured_evidence_kind_has_precedence_over_textual_fallback() -> None:
    text = "The tumor was resistant to panitumumab."
    result = assess_candidate_support(
        _candidate(direction="Sensitivity/Response"),
        _quote(text=text, evidence_kind="RESPONSE"),
        source_unit_text=text,
    )

    assert result["fields"]["direction"] == "CONFIRMED"
