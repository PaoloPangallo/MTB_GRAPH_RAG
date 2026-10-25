from __future__ import annotations

import json

from backend.research_pipeline.dossier.builder import (
    aggregate_evidence_records,
    build_relation_aware_report,
)


def _candidate() -> dict:
    return {
        "candidate_id": "GCA-CLAIM-1",
        "predicate": "associated_with_sensitivity_to",
        "disease": [{"label": "NSCLC"}],
        "biomarkers": [
            {"type": "Gene", "label": "EGFR"},
            {"type": "Variant", "label": "L858R", "linked_gene": "EGFR"},
        ],
        "interventions": [{"label": "osimertinib"}],
        "document_identifiers": [{"pmid": "123"}],
        "source_record_ids": ["row:evidence:1"],
        "source_datasets": ["edge_has_evidence.csv"],
        "semantic_key": "EVIDENCE_STATEMENT|Evidence:1",
        "node_ids": ["Gene:1", "Variant:1", "Evidence:1"],
        "edge_ids": ["edge:1"],
        "graph_path": ["Gene:1", "Variant:1", "Evidence:1"],
        "materialization_rule": "gca/4.0/evidence_statement",
    }


def _record(level: str, *, valid: bool = True, paper: str = "pmid:123", unit: str = "SU-1") -> dict:
    return {
        "evidence_id": f"E-{paper}-{unit}",
        "candidate_id": "GCA-CLAIM-1",
        "paper_id": paper,
        "source_unit_id": unit,
        "validation_outcome": "ENRICHMENT_V3_ACCEPTED" if valid else "QUOTE_INVALID",
        "quote_valid": valid,
        "accepted_for_gates": valid,
        "presentation_state": "VALIDATED_QUOTE" if valid else "REJECTED_QUOTE",
        "candidate_support": {"result": level},
        "quote": "EGFR L858R supports response to osimertinib.",
        "observed_relation": {
            "subject_pairings": [{"gene": "EGFR", "alteration": "L858R"}],
            "caveats": ["observed in a cohort"],
            "uncertainty": None,
            "conflict_markers": [],
        },
    }


def test_rejected_full_support_is_audit_only_and_cannot_inflate_state():
    result = aggregate_evidence_records([_record("FULL_SUPPORT", valid=False)])
    assert result["support_level"] == "UNVERIFIABLE"
    assert result["accepted_evidence_ids"] == []
    assert len(result["rejected_evidence"]) == 1


def test_claim_contains_accounting_pairing_and_provenance():
    report = build_relation_aware_report(
        {}, [_candidate()],
        {"GCA-CLAIM-1": {"evidence_records": [_record("FULL_SUPPORT")]}}
    )
    entry = report["paper_evidence"][0]
    claim = entry["claim"]
    assert claim["status"] == "FULL_SUPPORT"
    assert claim["gene_variant_pairings"] == [{"gene": "EGFR", "alteration": "L858R"}]
    assert claim["source_record_ids"] == ["row:evidence:1"]
    assert claim["source_datasets"] == ["edge_has_evidence.csv"]
    assert claim["supporting_evidence_ids"]
    assert claim["partial_evidence_ids"] == []
    assert claim["contradicting_evidence_ids"] == []
    assert entry["representative_evidence_id"] in claim["supporting_evidence_ids"]


def test_conflict_claim_preserves_supporting_and_contradicting_ids():
    records = [_record("FULL_SUPPORT", paper="pmid:123", unit="SU-1"),
               _record("CONTRADICTORY", paper="pmid:456", unit="SU-2")]
    report = build_relation_aware_report(
        {}, [_candidate()], {"GCA-CLAIM-1": {"evidence_records": records}}
    )
    claim = report["paper_evidence"][0]["claim"]
    assert claim["status"] == "PARTIAL_SUPPORT"
    assert claim["contradiction_present"] is True
    assert len(claim["supporting_evidence_ids"]) == 1
    assert len(claim["contradicting_evidence_ids"]) == 1


def test_valid_no_support_evidence_is_still_accounted_in_claim():
    record = _record("NO_SUPPORT", unit="SU-NO")
    report = build_relation_aware_report(
        {}, [_candidate()], {"GCA-CLAIM-1": {"evidence_records": [record]}}
    )
    claim = report["paper_evidence"][0]["claim"]
    assert claim["status"] == "NO_SUPPORT"
    assert claim["no_support_evidence_ids"] == [record["evidence_id"]]


def test_multiple_quotes_from_same_source_unit_are_one_distinct_passage():
    first = _record("FULL_SUPPORT", unit="SU-SAME")
    second = {**_record("FULL_SUPPORT", unit="SU-SAME"), "evidence_id": "E-SECOND",
              "quote": "A second quote from the same passage."}
    result = aggregate_evidence_records([first, second])
    assert result["evidence_count"] == 2
    assert result["distinct_source_unit_count"] == 1
    assert set(result["same_source_unit_evidence_ids"]) == {first["evidence_id"], second["evidence_id"]}


def test_dossier_claim_id_and_serialization_are_deterministic():
    payload = {"GCA-CLAIM-1": {"evidence_records": [_record("FULL_SUPPORT")]}}
    first = build_relation_aware_report({}, [_candidate()], payload)
    second = build_relation_aware_report({}, [_candidate()], payload)
    assert first == second
    assert json.dumps(first, sort_keys=True, ensure_ascii=False)
    assert first["paper_evidence"][0]["claim_id"] == second["paper_evidence"][0]["claim_id"]


def test_abstention_does_not_create_invalid_quote_global_limitation():
    from backend.research_pipeline.narrative.input_projection import build_narrator_input
    from backend.research_pipeline.narrative.controlled import build_catalog
    report = build_relation_aware_report({}, [_candidate()], {'GCA-CLAIM-1': {'enrichment': {'decision': 'ABSTAIN'}, 'quote_valid': False}})
    assert 'READER_ABSTAINED' in report['limitations']
    assert 'QUOTE_INVALID' not in report['limitations']
    catalog = build_catalog(build_narrator_input(report))
    assert 'citazione non valida' not in catalog['globals']['limitations_summary']
