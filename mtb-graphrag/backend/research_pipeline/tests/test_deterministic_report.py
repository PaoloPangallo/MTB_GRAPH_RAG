import json

from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.retrieval.kg_retrieval import load_candidates


def _real_candidates():
    all_candidates = load_candidates()
    return [
        all_candidates["GCA4-000b81b1296a2cd3d24bdd8b"],
        all_candidates["GCA4-164f35fb5930b2ca59e7efb9"],
        all_candidates["GCA4-000074f3d4ea7d88759bc423"],
    ]


def test_report_separates_real_paper_trial_and_kg_only_candidates():
    report = build_relation_aware_report(
        {"case_id": "CASE-REPORT", "disease": {"raw_value": "lung cancer"},
         "biomarkers": [{"gene": "KRAS", "alteration": "G12D"}],
         "target_intervention": {"raw_value": "drug"}, "query_intent": "THERAPY_EVALUATION"},
        _real_candidates(),
    )

    assert len(report["paper_evidence"]) == 1
    assert len(report["clinical_trials"]) == 1
    assert len(report["kg_only_relations"]) == 1
    assert report["paper_evidence"][0]["relation_family"] == "PAPER_EVIDENCE"
    assert report["clinical_trials"][0]["relation_family"] == "CLINICAL_TRIAL"
    assert report["kg_only_relations"][0]["relation_family"] == "KG_ONLY"


def test_kg_only_has_no_paper_evidence_fields_or_invented_document():
    entry = build_relation_aware_report({}, [_real_candidates()[2]])["kg_only_relations"][0]

    assert entry["document_provenance"] == "NOT_AVAILABLE"
    assert entry["verification_status"] == "KG_ONLY"
    assert entry["document_id"] is None
    assert "quote" not in entry
    assert "support_level" not in entry


def test_kg_only_preserves_companion_diagnostic_context_without_document_provenance():
    candidate = {
        "candidate_id": "GCA-CDX",
        "predicate": "has_companion_diagnostic",
        "biomarkers": [{"label": "IDH1"}],
        "interventions": [], "disease": [], "document_identifiers": [],
        "object": {"label": "Abbott RealTime IDH1", "type": "CompanionDiagnostic"},
        "diagnostic_scope": "CompanionDiagnostic",
        "source_properties": {"diagnostic": {
            "device_id": "cdx:IDH1:IVOSIDENIB", "device_name": "Abbott RealTime IDH1",
            "drug": "Ivosidenib", "gene": "IDH1", "platform_type": "PCR",
            "specimen_types": "Bone marrow;Peripheral Blood", "internal_only": "drop-me",
        }},
    }
    entry = build_relation_aware_report({}, [candidate])["kg_only_relations"][0]

    assert entry["diagnostic_scope"] == "CompanionDiagnostic"
    assert entry["diagnostic_context"] == {
        "device_id": "cdx:IDH1:IVOSIDENIB", "device_name": "Abbott RealTime IDH1",
        "drug": "Ivosidenib", "gene": "IDH1", "platform_type": "PCR",
        "specimen_types": "Bone marrow;Peripheral Blood",
    }
    assert entry["verification_status"] == "KG_ONLY"
    assert entry["document_provenance"] == "NOT_AVAILABLE"


def test_trial_has_non_efficacy_interpretation():
    entry = build_relation_aware_report({}, [_real_candidates()[1]])["clinical_trials"][0]

    assert entry["evidence_interpretation"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"
    assert entry["nct_id"] == "NCT05176665"


def test_unenriched_paper_is_explicitly_not_evaluated():
    entry = build_relation_aware_report({}, [_real_candidates()[0]])["paper_evidence"][0]

    assert entry["support_status"] == "NOT_EVALUATED"
    assert entry["quote"] is None
    assert entry["support_level"] == "UNVERIFIABLE"


def test_enrichment_is_projected_without_being_invented():
    candidate = _real_candidates()[0]
    report = build_relation_aware_report(
        {}, [candidate],
        paper_results={candidate["candidate_id"]: {
            "quote": "literal source quote", "quote_validation": "VALIDATED",
            "support_fields": {"gene": "CONFIRMED"}, "support_level": "PARTIAL_SUPPORT",
            "reason": "alteration not explicit",
            "evidence_records": [{
                "candidate_id": candidate["candidate_id"],
                "document_id": "pmid:20619739", "source_unit_id": "SU-PAPER-1",
                "quote": "literal source quote", "quote_valid": True,
                "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
                "presentation_state": "VALIDATED_QUOTE",
                "candidate_support": {"result": "PARTIAL_SUPPORT"},
            }],
        }},
    )
    entry = report["paper_evidence"][0]

    assert entry["quote"] == "literal source quote"
    assert entry["quote_validation"] == "ENRICHMENT_V3_ACCEPTED"
    assert entry["support_fields"] == {"gene": "CONFIRMED"}
    assert entry["support_level"] == "PARTIAL_SUPPORT"
    assert entry["reason"] == "alteration not explicit"


def test_paper_report_distinguishes_requested_and_resolved_document_identity():
    candidate = _real_candidates()[0]
    requested = next(
        f"pmid:{identifier['pmid']}"
        for identifier in candidate["document_identifiers"]
        if identifier.get("pmid")
    )
    report = build_relation_aware_report(
        {}, [candidate],
        paper_results={candidate["candidate_id"]: {
            "document_id": "pmcid:PMC1234567",
            "requested_document_id": requested,
            "support_level": "UNVERIFIABLE",
        }},
    )

    entry = report["paper_evidence"][0]
    assert entry["document_id"] == "pmcid:PMC1234567"
    assert entry["requested_document_id"] == requested


def test_report_order_is_deterministic_and_json_serializable():
    candidates = list(reversed(_real_candidates()))
    first = build_relation_aware_report({}, candidates)
    second = build_relation_aware_report({}, candidates)

    assert first == second
    assert json.dumps(first, sort_keys=True)
