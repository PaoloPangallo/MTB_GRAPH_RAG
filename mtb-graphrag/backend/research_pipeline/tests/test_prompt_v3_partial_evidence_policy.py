from backend.research_pipeline.enrichment import prompt_v3
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3


def test_v31_prompt_requires_quote_for_partial_or_opposite_literal_evidence():
    policy = prompt_v3.SYSTEM_PROMPT
    assert prompt_v3.PROMPT_VERSION == "paper-context-enricher-prompt/4.0"
    for phrase in (
        "generic gene evidence",
        "opposite direction",
        "different intervention",
        "disease-only",
        "not a reason to ABSTAIN",
    ):
        assert phrase in policy


def test_abstain_with_populated_reader_fields_remains_invalid():
    result = validate_enrichment_v3(
        "V3_TRANSPORT_VALID",
        {"decision": "ABSTAIN", "source_unit_id": "SU-1", "quote": "", "observed_gene": "KRAS"},
        candidate={}, paper_bundle={}, source_units_by_id={},
    )
    assert result["outcome"] == "QUOTE_INVALID"
    assert result["reason_codes"] == ["FIELDS_POPULATED_DESPITE_ABSTAIN"]
