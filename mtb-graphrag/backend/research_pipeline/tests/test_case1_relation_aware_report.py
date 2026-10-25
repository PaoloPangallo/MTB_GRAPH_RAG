import json

from backend.research_pipeline.cases.definitions import CASES
from backend.research_pipeline.data_access import load_frozen_enricher_runs, load_supporting_maps
from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.enrichment.post_quote_support import assess_candidate_support
from backend.research_pipeline.enrichment.validator_v2 import validate_enrichment_v2
from backend.research_pipeline.retrieval.kg_retrieval import _load_historical_candidates as load_candidates


CASE_ID = "CASE-1-therapy-evaluation-strong-match"
CANDIDATE_ID = "GCA-008ae3aad1a64c118318ef79"
SOURCE_UNIT_ID = "SU-6e4d5a52c9be05f545487ad0"
QUOTE = "patients with mCRC bearing KRAS mutations are clinically resistant to therapy with panitumumab or cetuximab."
SOURCE_TEXT = (
    "metastatic colorectal cancer. "
    "patients with mCRC bearing KRAS mutations are clinically resistant to "
    "therapy with panitumumab or cetuximab."
)


def test_case1_real_paper_pipeline_reaches_relation_aware_report():
    case = next(item for item in CASES if item["case_id"] == CASE_ID)
    candidate = load_candidates()[CANDIDATE_ID]
    bundle = next(item for item in load_supporting_maps()["bundles"] if item["bundle_id"] == "EB-b4c48ba003913f278ff182a6")
    frozen_call = next(item for item in load_frozen_enricher_runs() if item["case_id"] == CASE_ID)
    enrichment = frozen_call["enrichment"]
    validation = validate_enrichment_v2(
        "V2_TRANSPORT_VALID", enrichment, candidate=candidate, paper_bundle=bundle,
        source_units_by_id={SOURCE_UNIT_ID: {"source_unit_id": SOURCE_UNIT_ID, "text": SOURCE_TEXT}},
        requested_drug="panitumumab",
    )
    support = assess_candidate_support(
        candidate, enrichment, source_unit_text=SOURCE_TEXT, paper_id=bundle["bundle_id"],
    )

    report = build_relation_aware_report(
        {
            "case_id": case["case_id"],
            "disease": {"raw_value": "metastatic colorectal cancer"},
            "biomarkers": [{"gene": "KRAS", "alteration": "G12D"}],
            "target_intervention": {"raw_value": "panitumumab"},
            "query_intent": case["expected_query_intent"],
        },
        [candidate],
        paper_results={CANDIDATE_ID: {
            "document_source": "AUTHORIZED_CACHE",
            "document_resolution_status": "DOCUMENT_RESOLVED_FROM_CACHE",
            "selected_source_units": [SOURCE_UNIT_ID],
            "enrichment": enrichment,
            "validation": validation,
            "candidate_support": support,
        }},
    )
    entry = report["paper_evidence"][0]

    # A declared identifier is not a resolved document identity until the
    # resolver has independently confirmed it.
    assert entry["document_id"] is None
    assert entry["declared_source_identity"] == "pmid:19223544"
    assert entry["resolved_source_identity"] is None
    assert entry["selected_source_units"] == [SOURCE_UNIT_ID]
    assert entry["reader_status"] == "QUOTE"
    # Legacy flat metadata is not an aggregation-eligible evidence record.
    # Its scalar interpretation cannot publish a source quotation as verified.
    assert entry["quote"] is None
    assert entry["quote_validation"] == "ENRICHMENT_V2_ACCEPTED"
    assert entry["support_fields"] == {
        "disease": "CONFIRMED", "gene": "CONFIRMED", "alteration": "NOT_CONFIRMED",
        "drug": "CONFIRMED", "direction": "CONFIRMED",
    }
    assert entry["support_level"] == "UNVERIFIABLE"
    assert json.dumps(report, sort_keys=True)
