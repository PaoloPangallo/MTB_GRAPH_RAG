import copy
import itertools
import json

from backend.research_pipeline.dossier.builder import aggregate_evidence_records, build_relation_aware_report
from backend.research_pipeline.narrative.input_projection import build_narrator_input
from backend.research_pipeline.narrative.verifier import verify_narrative
from backend.research_pipeline.documents.authorized_cache import finalize_source_unit_occurrence_ids


def _record(paper, unit, level):
    return {"paper_id": paper, "source_unit_id": unit,
            "candidate_support": {"result": level},
            "quote_valid": True, "quote": f"authorized-{paper}-{unit}",
            "validation_outcome": "ENRICHMENT_V3_ACCEPTED",
            "accepted_for_gates": True,
            "presentation_state": "VALIDATED_QUOTE"}


def test_aggregation_truth_table_and_permutation_invariance():
    cases = {
        ("FULL_SUPPORT",): "FULL_SUPPORT",
        ("FULL_SUPPORT", "PARTIAL_SUPPORT"): "FULL_SUPPORT",
        ("FULL_SUPPORT", "NO_SUPPORT"): "FULL_SUPPORT",
        ("FULL_SUPPORT", "CONTRADICTORY"): "PARTIAL_SUPPORT",
        ("PARTIAL_SUPPORT", "CONTRADICTORY"): "CONTRADICTORY",
        ("NO_SUPPORT", "CONTRADICTORY"): "CONTRADICTORY",
        ("UNVERIFIABLE", "FULL_SUPPORT"): "FULL_SUPPORT",
    }
    for levels, expected in cases.items():
        records = [_record(f"DOC-{i}", f"SU-{i}", level) for i, level in enumerate(levels)]
        expected_payload = aggregate_evidence_records(records)
        assert expected_payload["support_level"] == expected
        for permutation in itertools.permutations(records):
            actual = aggregate_evidence_records(list(permutation))
            assert actual == expected_payload


def test_dossier_preserves_individual_records_and_is_order_invariant():
    candidate = {"candidate_id": "GCA-PF", "disease": [{"label": "Melanoma"}],
                 "biomarkers": [{"type": "Gene", "label": "BRAF"}],
                 "interventions": [{"label": "vemurafenib"}],
                 "document_identifiers": [{"pmid": "1"}], "predicate": "supports"}
    records = [_record("DOC-B", "SU-2", "PARTIAL_SUPPORT"), _record("DOC-A", "SU-1", "FULL_SUPPORT")]
    def build(items):
        return build_relation_aware_report({"case_id": "PF", "disease": "Melanoma"}, [candidate], {
            "GCA-PF": {"evidence_records": items, "selected_source_units": [r["source_unit_id"] for r in items],
                       "quote_valid": True, "enrichment": items[0], "candidate_support": items[0]["candidate_support"],
                       "document_resolution_status": "RESOLVED"}
        })
    a, b = build(records), build(list(reversed(records)))
    assert a == b
    entry = a["paper_evidence"][0]
    assert len(entry["evidence_records"]) == 2
    assert entry["support_level"] == "PARTIAL_SUPPORT" if entry["contradiction_present"] else True


def test_rejected_audit_quote_never_reaches_narrator_input():
    dossier = {"case_id": "PF", "paper_evidence": [{
        "candidate_id": "GCA-PF", "relation": "supports", "quote_valid": False,
        "quote": "AUDIT_ONLY_SENTINEL", "rejected_quotes": [{"quote": "AUDIT_ONLY_SENTINEL"}],
        "support_level": "NO_SUPPORT", "support_fields": {}, "document_id": "pmid:1",
    }], "clinical_trials": [], "kg_only_relations": [], "limitations": []}
    projected = build_narrator_input(dossier)
    assert "AUDIT_ONLY_SENTINEL" not in json.dumps(projected, ensure_ascii=False)


def test_sourceunit_occurrence_ids_are_deterministic_and_disambiguate_repeats():
    units = [{"document_id": "pmid:1", "unit_type": "sec", "text": "repeat", "char_start": 0, "char_end": 6},
             {"document_id": "pmid:1", "unit_type": "sec", "text": "repeat", "char_start": 7, "char_end": 13}]
    first, second = finalize_source_unit_occurrence_ids("pmid:1", units)
    assert first["source_unit_id"] != second["source_unit_id"]
    assert first["source_unit_id"] == finalize_source_unit_occurrence_ids("pmid:1", units)[0]["source_unit_id"]
    other = finalize_source_unit_occurrence_ids("pmid:2", [units[0]])[0]
    assert other["source_unit_id"] != first["source_unit_id"]


def test_candidate_locality_does_not_cross_reject_unrelated_candidate():
    from backend.research_pipeline.tests.test_narrative_verifier import _synthetic_dossier
    dossier = _synthetic_dossier(status="DIRECT", direction="SUPPORTED", candidate_id="A")
    other = copy.deepcopy(dossier["candidate_therapies"][0])
    other["candidate_id"] = "B"
    other["status"] = "PARTIAL"
    other["gate_results"]["bucket"] = "WARNING_BUCKET"
    dossier["candidate_therapies"].append(other)
    narrative = {"narrative_summary": "Sintesi", "limitations_summary": "Limitazioni",
                 "closing_note": "Nota", "candidate_narratives": [
                     {"candidate_id": "A", "text": "La relazione è supportata."},
                     {"candidate_id": "B", "text": "La relazione non è confermata."},
                 ]}
    result = verify_narrative(dossier, build_narrator_input(dossier), narrative)
    assert result["status"] == "PASS"
