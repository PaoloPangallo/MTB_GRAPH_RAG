from __future__ import annotations

from types import SimpleNamespace

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache, expand_identifier
from backend.research_pipeline.retrieval.live_sourceunit_selection import (
    select_live_papers_for_association,
)


def test_doi_like_value_in_pmid_field_is_classified_before_resolution() -> None:
    expanded = expand_identifier({"pmid": "10.1182/blood-2021-148205"})
    assert expanded == [{
        "doi": "10.1182/blood-2021-148205",
        "original_identifier_type": "pmid",
        "identifier_status": "DOI_LIKE_IN_PMID_FIELD",
    }]


def test_trial_source_units_can_be_selected_for_reader() -> None:
    candidate = {
        "candidate_id": "trial-1",
        "predicate": "trial_has_drug",
        "disease": [{"label": "lung cancer"}],
        "biomarkers": [{"label": "EGFR", "type": "Gene"}],
        "interventions": [{"label": "osimertinib"}],
        "document_identifiers": [{"nct": "NCT01234567"}],
    }
    association = {"candidate_id": "trial-1", "candidate": candidate}
    record = SimpleNamespace(
        candidate_id="trial-1", document_id="nct:NCT01234567", bundle_id="b1",
        resolved=True, full_text_available=False, lineage={"requested_document_id": "nct:NCT01234567"},
    )
    units = {
        "su-title": {"source_unit_id": "su-title", "document_id": "nct:NCT01234567", "unit_type": "TRIAL_TITLE", "text": "EGFR osimertinib lung cancer"},
        "su-summary": {"source_unit_id": "su-summary", "document_id": "nct:NCT01234567", "unit_type": "BRIEF_SUMMARY", "text": "This trial studies osimertinib in lung cancer."},
    }
    result = select_live_papers_for_association(
        association, units,
        resolution=SimpleNamespace(documents=(record,)),
        top_k=5,
    )
    assert result["selected_papers"]
    assert result["selected_papers"][0]["resolved_source_unit_ids"]


def test_classified_doi_is_preserved_as_unsupported_not_sent_as_pmid() -> None:
    item = expand_identifier({"pmid": "10.1182/blood-2021-148205"})[0]
    record = AuthorizedDocumentCache.resolve_identifier
    # The resolver method is exercised without constructing a writable cache.
    result = record.__get__(object(), AuthorizedDocumentCache)(item)
    assert result["availability"] == "DOI_IDENTIFIER_UNSUPPORTED"
    assert result["identifier_status"] == "DOI_LIKE_IN_PMID_FIELD"
