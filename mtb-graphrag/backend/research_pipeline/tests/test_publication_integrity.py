from copy import deepcopy

from backend.research_pipeline.dossier.accounting import apply_publication_integrity
from backend.research_pipeline.dossier.builder import aggregate_evidence_records
from backend.research_pipeline.narrative.markdown_renderer import render_dossier_markdown
from backend.research_pipeline.narrative.controlled import build_catalog


def test_insufficient_information_is_a_controlled_non_support_state():
    catalog = build_catalog({"candidates": [{"candidate_id": "C", "branch": "PAPER",
        "canonical_status": "INSUFFICIENT_INFORMATION", "candidate_support": {
            "result": "INSUFFICIENT_INFORMATION"}, "warnings": [], "validated_quotes": []}],
        "limitations": []})
    assert "informazioni insufficienti" in str(catalog)


def test_failed_reconciliation_is_incomplete_and_visible_with_narrative():
    report = {"run_status": "COMPLETED", "claims": [], "paper_evidence": [],
              "pipeline_accounting": {"bidirectional_reconciliation": {
                  "status": "FAIL", "reason_codes": ["EVIDENCE_CLAIM_RECONCILIATION_FAILED"],
                  "accepted_not_represented": ["E1"]}}}
    original = deepcopy(report)
    projected = apply_publication_integrity(report)
    assert projected["technical_run_status"] == "COMPLETED"
    assert projected["run_status"] == "PARTIAL"
    assert projected["publication_status"] == "INCOMPLETE"
    assert report == original
    assert apply_publication_integrity(projected) == projected
    markdown = render_dossier_markdown(projected, {"narrative_summary": "Run completa."})
    assert "FAIL" in markdown and "E1" in markdown
    assert "EVIDENCE_CLAIM_RECONCILIATION_FAILED" in markdown


def test_pass_does_not_promote_partial_technical_run():
    report = {"run_status": "PARTIAL", "pipeline_accounting": {
        "bidirectional_reconciliation": {"status": "PASS"}}}
    assert apply_publication_integrity(report)["publication_status"] == "INCOMPLETE"
    markdown = render_dossier_markdown(report)
    assert "esecuzione parziale" in markdown
    assert "riconciliazione non confermata" not in markdown
    assert "PASS" in markdown


def test_unavailable_reconciliation_is_not_published_as_complete():
    for accounting in (None, {}, {"bidirectional_reconciliation": {"status": "LEGACY_UNVERIFIED"}},
                       {"bidirectional_reconciliation": {"status": "NOT_AVAILABLE"}}):
        report = {"run_status": "COMPLETED", "pipeline_accounting": accounting}
        projected = apply_publication_integrity(report)
        assert projected["publication_status"] == "INCOMPLETE"
        assert projected["run_status"] == "PARTIAL"
        markdown = render_dossier_markdown(projected)
        assert "dossier incompleto" in markdown.lower()


def record(identity, level, document="pmid:1"):
    return {"evidence_id": identity, "document_id": document, "source_unit_id": identity,
            "quote_valid": True, "quote": "Validated quote", "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
            "reader_attempt_status": "READER_QUOTE_VALIDATED", "candidate_support": {"result": level}}


def test_mixed_composition_counts_records_separately_from_publications():
    result = aggregate_evidence_records([record("E1", "FULL_SUPPORT"), record("E2", "NO_SUPPORT")])
    assert result["support_level"] == "FULL_SUPPORT"
    assert result["evidence_composition"]["mixed_support"] is True
    assert result["evidence_composition"]["record_count"] == 2
    assert result["evidence_composition"]["unique_publication_count"] == 1
    assert result["evidence_composition"]["counts_by_support_result"]["NO_SUPPORT"] == 1


def test_partial_restricted_and_mixed_are_distinct():
    restricted = aggregate_evidence_records([record("E1", "PARTIAL_SUPPORT")])
    mixed = aggregate_evidence_records([record("E1", "FULL_SUPPORT"), record("E2", "CONTRADICTORY")])
    assert restricted["support_level"] == mixed["support_level"] == "PARTIAL_SUPPORT"
    assert restricted["evidence_composition"]["partial_support_origin"] == "RESTRICTED_EVIDENCE"
    assert mixed["evidence_composition"]["partial_support_origin"] == "MIXED_FULL_AND_CONTRADICTORY"
