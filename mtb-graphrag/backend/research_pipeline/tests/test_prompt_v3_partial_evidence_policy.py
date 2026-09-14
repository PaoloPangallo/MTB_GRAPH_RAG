from backend.research_pipeline.enrichment import prompt_v3
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3


def test_v48_prompt_extracts_literal_observations_without_deciding_gca_support():
    policy = " ".join(prompt_v3.SYSTEM_PROMPT.split())
    assert prompt_v3.PROMPT_VERSION == "paper-context-enricher-prompt/4.8"
    for phrase in (
        "Do not decide whether the challenged GCA is supported",
        "relevant literal statement",
        "exact contiguous quote",
        "Do not infer gene-alteration links",
        "For ABSTAIN set abstain_reason",
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
