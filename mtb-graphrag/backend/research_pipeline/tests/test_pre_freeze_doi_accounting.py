"""DOI-like values in PMID fields remain typed and explicitly unsupported."""

from backend.research_pipeline.documents.authorized_cache import AuthorizedDocumentCache, expand_identifier
from backend.research_pipeline.retrieval.kg_retrieval import _live_provenance_bundles
from backend.research_pipeline.dossier.builder import build_relation_aware_report


def test_doi_like_pmid_keeps_original_field_provenance() -> None:
    candidate = {"candidate_id": "C-DOI", "document_identifiers": [{"pmid": "10.1234/example"}]}
    expanded = expand_identifier(candidate["document_identifiers"][0])
    assert expanded[0]["doi"] == "10.1234/example"
    bundle = _live_provenance_bundles(candidate)[0]
    assert bundle["document_id"] == "doi:10.1234/example"
    assert bundle["provenance_identifier"]["original_identifier_type"] == "pmid"
    assert bundle["provenance_identifier"]["identifier_status"] == "DOI_LIKE_IN_PMID_FIELD"
    resolver = AuthorizedDocumentCache.__new__(AuthorizedDocumentCache)
    record = resolver.resolve_identifier(bundle["provenance_identifier"])
    assert record["availability"] == "DOI_IDENTIFIER_UNSUPPORTED"
    dossier_entry = build_relation_aware_report({}, [{
        **candidate, "predicate": "has_evidence_statement",
    }])["paper_evidence"][0]
    assert dossier_entry["declared_source_identity"] == "doi:10.1234/example"
