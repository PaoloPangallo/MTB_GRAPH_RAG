"""Trial retrieval identity and availability must be independent of record truthiness."""

from __future__ import annotations

from backend.research_pipeline.documents.trial_resolution import resolve_trial_record
from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate
from backend.research_pipeline.documents import trial_context


def test_resolution_failed_record_is_not_available() -> None:
    record = {"document_id": "nct:NCT12345678", "availability": "RESOLUTION_FAILED"}
    resolved = resolve_trial_record("NCT12345678", record)
    assert resolved["trial_resolution_status"] == "RESOLUTION_FAILED"
    assert resolved["provenance_status"] != "TRIAL_RECORD_RESOLVED"


def test_metadata_only_flag_without_payload_is_not_available() -> None:
    record = {"document_id": "nct:NCT12345678", "availability": "METADATA_ONLY",
              "local_cache_path": None, "title": None, "conditions": []}
    resolved = resolve_trial_record("NCT12345678", record)
    assert resolved["trial_resolution_status"] != "AVAILABLE"


def test_stale_manifest_path_cannot_override_failed_document_resolution() -> None:
    record = {
        "document_id": "nct:NCT12345678", "availability": "METADATA_ONLY",
        "local_cache_path": "stale/path/trial.json",
    }
    resolved = resolve_trial_record("NCT12345678", record, resolved_payload=False)
    assert resolved["trial_resolution_status"] == "RESOLUTION_FAILED"
    assert resolved["provenance_status"] == "TRIAL_PAYLOAD_MISSING"


def test_wrong_trial_gene_cannot_match_shared_drug_and_disease() -> None:
    candidate = {
        "candidate_id": "GCA4-TRIAL-PROBE", "predicate": "studies_drug",
        "document_identifiers": [{"nct": "NCT12345678"}],
        "trial_context": {
            "nct_id": "NCT12345678", "genes": ["KRAS"],
            "conditions": ["lung cancer"],
            "interventions_raw": ["drug X"],
            "interventions_normalized": ["drug X"],
        },
    }
    case = {
        "biomarkers": [{"gene": "EGFR", "assertion_status": "PRESENT"}],
        "disease": {"raw_value": "lung cancer"},
        "target_intervention": {"raw_value": "drug X"},
        "query_intent": "THERAPY_EVALUATION",
    }
    matched, reasons = _match_candidate(case, candidate)
    assert matched is False
    assert "TRIAL_SOURCE_GENE_NOT_COMPATIBLE" in reasons


def test_matching_trial_gene_can_anchor_variant_level_case_context() -> None:
    candidate = {
        "candidate_id": "GCA4-TRIAL-EGFR-PROBE", "predicate": "studies_drug",
        "document_identifiers": [{"nct": "NCT12345678"}],
        "trial_context": {
            "nct_id": "NCT12345678", "genes": ["EGFR"],
            "conditions": ["lung cancer"],
            "interventions_raw": ["erlotinib"],
            "interventions_normalized": ["erlotinib"],
        },
    }
    case = {
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R", "assertion_status": "PRESENT"}],
        "disease": {"raw_value": "lung cancer"},
        "target_intervention": {"raw_value": "erlotinib"},
        "query_intent": "THERAPY_EVALUATION",
    }
    matched, reasons = _match_candidate(case, candidate)
    assert matched is True, reasons
    assert "BIOMARKER_GENE_NOT_COMPATIBLE" not in reasons


def test_matching_trial_gene_is_a_positive_anchor_without_drug_or_disease() -> None:
    candidate = {
        "candidate_id": "GCA4-TRIAL-GENE-ONLY-PROBE",
        "document_identifiers": [{"nct": "NCT12345678"}],
        "trial_context": {"nct_id": "NCT12345678", "genes": ["EGFR"]},
    }
    case = {
        "biomarkers": [{"gene": "EGFR", "alteration": "L858R",
                        "assertion_status": "PRESENT"}],
        "query_intent": "BIOMARKER_INTERPRETATION",
    }
    matched, reasons = _match_candidate(case, candidate)
    assert matched is True, reasons
    assert "TRIAL_SOURCE_GENE_COMPATIBLE" in reasons


def test_intervention_only_trial_remains_eligible_without_declared_molecular_anchor() -> None:
    candidate = {
        "candidate_id": "GCA4-TRIAL-INTERVENTION-ONLY",
        "document_identifiers": [{"nct": "NCT00000001"}],
        "biomarkers": [],
        "interventions": [{"label": "EMB-01", "type": "Drug"}],
        "trial_context": {"genes": [], "conditions": ["gastrointestinal cancer"],
                           "interventions_raw": ["EMB-01"], "interventions_normalized": []},
    }
    case = {
        "biomarkers": [{"gene": "ERBB2", "assertion_status": "PRESENT"}],
        "disease": {"raw_value": "gastrointestinal cancer"},
        "target_intervention": {"raw_value": "EMB-01"},
        "query_intent": "THERAPY_EVALUATION",
    }
    matched, reasons = _match_candidate(case, candidate)
    assert matched is True, reasons
    assert "INTERVENTION_COMPATIBLE" in reasons


def test_unlinked_conflicting_alteration_cannot_downgrade_to_same_gene_match() -> None:
    candidate = {
        "candidate_id": "GCA4-UNLINKED-MOLECULAR-PROBE",
        "biomarkers": [{"label": "KRAS", "type": "Gene"},
                       {"label": "G13D", "type": "Variant"}],
        "document_identifiers": [],
    }
    case = {"biomarkers": [{"gene": "KRAS", "alteration": "G12D",
                             "assertion_status": "PRESENT"}]}
    matched, reasons = _match_candidate(case, candidate)
    assert matched is False, reasons


def test_enrichment_propagates_trial_gene_without_mutating_source(monkeypatch) -> None:
    record = trial_context.TrialContextRecord(
        nct_id="NCT12345678", genes=("KRAS",), conditions=("lung cancer",),
        interventions_raw=("drug X",), interventions_normalized=("drug X",),
    )
    class Index:
        def lookup(self, nct):
            return record
    monkeypatch.setattr(trial_context, "load_trial_context_index", lambda: Index())
    source = {"candidate_id": "T", "document_identifiers": [{"nct": "NCT12345678"}]}
    enriched, status = trial_context.enrich_trial_candidate(source)
    assert status == "TRIAL_CONTEXT_AVAILABLE"
    assert enriched["trial_context"]["genes"] == ("KRAS",)
    assert "trial_context" not in source
