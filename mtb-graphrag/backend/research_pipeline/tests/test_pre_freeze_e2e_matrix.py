"""Sixteen controlled research journeys through the deterministic dossier.

The parser and Reader outputs are controlled inputs; every deterministic
projection, retrieval decision, SourceUnit selection, verifier decision and
claim aggregation used here is production code. No provider or evaluation
unit is called.
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch

from backend.research_pipeline.casecontext.pipeline import (
    build_retrieval_case_context, run as understand_case,
)
from backend.research_pipeline.documents.trial_resolution import resolve_trial_record
from backend.research_pipeline.dossier.builder import build_relation_aware_report
from backend.research_pipeline.enrichment.validator_v3 import validate_enrichment_v3
from backend.research_pipeline.experimental.sourceunit_selector import (
    SourceUnitSelectionInput, select,
)
from backend.research_pipeline.orchestrator import _assess_v3_quoted_relation
from backend.research_pipeline.retrieval.kg_retrieval import _match_candidate, load_candidates, retrieve


def paper_candidate(**changes: object) -> dict:
    candidate = {
        "candidate_id": "E2E-PAPER", "semantic_key": "EVIDENCE_STATEMENT|E2E",
        "predicate": "associated_with_sensitivity_to", "direction": "Supports",
        "disease": [{"label": "lung cancer", "type": "Disease"}],
        "biomarkers": [{"label": "EGFR", "type": "Gene"},
                       {"label": "L858R", "type": "Variant", "gene": "EGFR", "alteration": "L858R"}],
        "interventions": [{"label": "erlotinib", "type": "Drug"}],
        "document_identifiers": [{"pmid": "123"}],
        "source_record_ids": ["row:1"], "source_datasets": ["source.csv"],
        "edge_ids": ["edge:1"], "node_ids": ["Gene:1", "Evidence:1"],
    }
    candidate.update(changes)
    return candidate


def parsed_case(raw: str, *, disease: str = "Lung cancer",
                biomarkers: tuple[tuple[str, str], ...] = (("EGFR", "L858R"),),
                interventions: tuple[tuple[str, str], ...] = (("erlotinib", "TARGET"),),
                biomarker_quote: str | None = None) -> dict:
    return {
        "query_intent": "THERAPY_EVALUATION",
        "diseases": [{"value": disease, "source_spans": [{"quote": disease}]}],
        "biomarkers": [
            {"gene": gene, "alteration": variant,
             "gene_source_spans": [{"quote": biomarker_quote or gene}],
             "alteration_source_spans": [{"quote": biomarker_quote or variant}]}
            for gene, variant in biomarkers
        ],
        "interventions": [
            {"name": drug, "role": role, "source_spans": [{"quote": drug}]}
            for drug, role in interventions
        ],
    }


def positive_reader(quote: str) -> dict:
    return {
        "decision": "QUOTE", "quote": quote,
        "observed_relation": {
            "subjects": [{"type": "GENE", "surface_value": "EGFR"},
                         {"type": "ALTERATION", "surface_value": "L858R"}],
            "subject_pairings": [{"gene": "EGFR", "alteration": "L858R"}],
            "intervention": "erlotinib", "disease": None,
            "effect_direction": "SENSITIVITY_RESPONSE", "observed_stance": "SUPPORTS",
            "relation_scope": "SINGLE", "relation_assertion": "RELATION_ASSERTED",
        },
    }


def document_journey(
    raw: str, parsed: dict, candidate: dict, quotes: tuple[str, ...] = (), *,
    reader_failure: bool = False,
) -> dict:
    understood = understand_case(raw, parsed)
    retrieval_input = build_retrieval_case_context(parsed, understood["mentions"])
    with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates",
               return_value={candidate["candidate_id"]: candidate}):
        retrieval = retrieve(retrieval_input)
    matched = bool(retrieval["associations"])
    reasons = (retrieval["associations"][0]["match_reason_codes"] if matched else
               retrieval["excluded_candidates"][0]["reason_codes"])
    if matched:
        candidate = retrieval["associations"][0]["candidate"]
    trace: dict = {
        "input": raw,
        "retrieval_result": {"matched": matched, "reasons": reasons},
        "document_state": "NOT_RETRIEVED" if not matched else "UNAVAILABLE" if not quotes else "AVAILABLE",
        "selected_source_units": (), "reader_verifier": [],
        "aggregation": None, "final_deterministic_claim": None,
    }
    if not matched:
        report = build_relation_aware_report(retrieval_input, [])
        assert report["paper_evidence"] == []
        return trace

    units = [
        {"source_unit_id": f"SU-{index}", "document_id": "pmid:123",
         "unit_type": "FULLTEXT_SENTENCE", "section": "Results", "text": quote}
        for index, quote in enumerate(quotes)
    ]
    selected = select(SourceUnitSelectionInput.from_candidate(candidate, "pmid:123", units)) if units else None
    trace["selected_source_units"] = selected.selected_source_unit_ids if selected else ()
    records: list[dict] = []
    for unit in units:
        if unit["source_unit_id"] not in trace["selected_source_units"]:
            continue
        if reader_failure:
            records.append({
                "candidate_id": candidate["candidate_id"], "document_id": "pmid:123",
                "source_unit_id": unit["source_unit_id"], "quote_valid": False,
                "reader_attempt_status": "READER_PARSE_FAILED",
                "validation_outcome": "REJECTED_TRANSPORT",
            })
            trace["reader_verifier"].append("READER_PARSE_FAILED")
            continue
        observation = positive_reader(unit["text"])
        observation["source_unit_id"] = unit["source_unit_id"]
        validation = validate_enrichment_v3(
            "V3_TRANSPORT_VALID", observation, candidate=candidate,
            paper_bundle={"document_id": "pmid:123", "resolved_source_unit_ids": [unit["source_unit_id"]]},
            source_units_by_id={unit["source_unit_id"]: unit},
        )
        assert validation["outcome"] == "ENRICHMENT_V3_ACCEPTED", (unit, validation)
        support = _assess_v3_quoted_relation(candidate, observation, unit["text"])
        trace["reader_verifier"].append(support["result"])
        records.append({
            **observation, "candidate_id": candidate["candidate_id"],
            "document_id": "pmid:123", "source_unit_id": unit["source_unit_id"],
            "validation_outcome": validation["outcome"], "quote_valid": validation["quote_valid"],
            "presentation_state": "VALIDATED_QUOTE", "accepted_for_gates": True,
            "candidate_support": support,
        })
    report = build_relation_aware_report(
        retrieval_input, [candidate],
        {candidate["candidate_id"]: {"evidence_records": records}},
    )
    claim = report["paper_evidence"][0]["claim"]
    trace["aggregation"] = claim["status"]
    trace["final_deterministic_claim"] = claim
    return trace


POSITIVE = "EGFR L858R showed sensitivity to erlotinib in lung cancer."
CONTRARY = "EGFR L858R did not predict response to erlotinib in lung cancer."


@pytest.mark.parametrize("case_id,raw,parsed,candidate,quotes,expected_match,expected_status", [
    ("01_exact_variant", "Lung cancer, EGFR L858R; erlotinib.",
     parsed_case("Lung cancer, EGFR L858R; erlotinib."), paper_candidate(), (POSITIVE,), True, "FULL_SUPPORT"),
    ("02_wrong_variant", "Lung cancer, EGFR G719A; erlotinib.",
     parsed_case("Lung cancer, EGFR G719A; erlotinib.", biomarkers=(("EGFR", "G719A"),)),
     paper_candidate(), (POSITIVE,), False, None),
    ("03_wrong_disease", "Breast cancer, EGFR L858R; erlotinib.",
     parsed_case("Breast cancer, EGFR L858R; erlotinib.", disease="Breast cancer"),
     paper_candidate(), (POSITIVE,), False, None),
    ("04_multi_gene_variant", "Lung cancer, EGFR L858R and KRAS G12C; erlotinib.",
     parsed_case("Lung cancer, EGFR L858R and KRAS G12C; erlotinib.",
                 biomarkers=(("EGFR", "L858R"), ("KRAS", "G12C"))),
     paper_candidate(), (POSITIVE,), True, "FULL_SUPPORT"),
    ("05_negated_biomarker", "Lung cancer, no EGFR L858R detected; erlotinib.",
     parsed_case("Lung cancer, no EGFR L858R detected; erlotinib.",
                 biomarker_quote="no EGFR L858R detected"),
     paper_candidate(), (POSITIVE,), False, None),
    ("06_support_and_contradiction", "Lung cancer, EGFR L858R; erlotinib.",
     parsed_case("Lung cancer, EGFR L858R; erlotinib."),
     paper_candidate(), (POSITIVE, CONTRARY), True, "PARTIAL_SUPPORT"),
    ("07_same_relation_multi_source", "Lung cancer, EGFR L858R; erlotinib.",
     parsed_case("Lung cancer, EGFR L858R; erlotinib."),
     paper_candidate(candidate_group_candidate_ids=["GCA-A", "GCA-B"],
                     source_record_ids=["row:1", "row:2"], edge_ids=["edge:1", "edge:2"]),
     (POSITIVE,), True, "FULL_SUPPORT"),
    ("08_previous_not_current_drug", "Previously treated with gefitinib. Lung cancer EGFR L858R. Current target erlotinib.",
     parsed_case("Previously treated with gefitinib. Lung cancer EGFR L858R. Current target erlotinib.",
                 interventions=(("gefitinib", "PREVIOUS"), ("erlotinib", "TARGET"))),
     paper_candidate(interventions=[{"label": "gefitinib", "type": "Drug"}]),
     (POSITIVE,), False, None),
    ("14_cooccurrence", "Lung cancer, EGFR L858R; erlotinib.",
     parsed_case("Lung cancer, EGFR L858R; erlotinib."),
     paper_candidate(), ("EGFR L858R and erlotinib were studied in lung cancer.",), True, "NO_SUPPORT"),
    ("15_rejected_proposition", "Lung cancer, EGFR L858R; erlotinib.",
     parsed_case("Lung cancer, EGFR L858R; erlotinib."), paper_candidate(),
     ("The proposition that EGFR L858R showed sensitivity to erlotinib was rejected.",),
     True, "NO_SUPPORT"),
])
def test_document_cases_reconcile_to_dossier(
    case_id: str, raw: str, parsed: dict, candidate: dict, quotes: tuple[str, ...],
    expected_match: bool, expected_status: str | None,
) -> None:
    trace = document_journey(raw, parsed, candidate, quotes)
    assert trace["retrieval_result"]["matched"] is expected_match, (case_id, trace)
    if expected_match:
        assert trace["document_state"] == "AVAILABLE", (case_id, trace)
        assert trace["selected_source_units"], (case_id, trace)
        assert trace["reader_verifier"], (case_id, trace)
        assert trace["aggregation"] == expected_status, (case_id, trace)
        assert trace["final_deterministic_claim"]["status"] == expected_status
    else:
        assert trace["document_state"] == "NOT_RETRIEVED"
        assert trace["final_deterministic_claim"] is None
    if case_id == "06_support_and_contradiction":
        assert trace["final_deterministic_claim"]["contradiction_present"] is True
    if case_id == "07_same_relation_multi_source":
        assert set(trace["final_deterministic_claim"]["source_record_ids"]) == {"row:1", "row:2"}


def test_09_trial_wrong_gene_has_no_retrieved_claim() -> None:
    case = {"query_intent": "THERAPY_EVALUATION",
            "biomarkers": [{"gene": "EGFR", "assertion_status": "PRESENT"}],
            "disease": {"raw_value": "lung cancer"},
            "target_intervention": {"raw_value": "erlotinib"}}
    trial = {"candidate_id": "TRIAL-09", "predicate": "studies_drug",
             "document_identifiers": [{"nct": "NCT12345678"}],
             "trial_context": {"nct_id": "NCT12345678", "genes": ["KRAS"],
                               "conditions": ["lung cancer"],
                               "interventions_raw": ["erlotinib"],
                               "interventions_normalized": ["erlotinib"]}}
    matched, reasons = _match_candidate(case, trial)
    report = build_relation_aware_report(case, [trial] if matched else [])
    assert not matched and "TRIAL_SOURCE_GENE_NOT_COMPATIBLE" in reasons
    assert report["clinical_trials"] == []


def test_10_failed_trial_resolution_is_not_available_or_efficacy() -> None:
    trial = {"candidate_id": "TRIAL-10", "predicate": "studies_drug",
             "document_identifiers": [{"nct": "NCT12345678"}],
             "trial_context": {"nct_id": "NCT12345678", "genes": ["EGFR"],
                               "conditions": ["lung cancer"],
                               "interventions_raw": ["erlotinib"],
                               "interventions_normalized": ["erlotinib"]}}
    record = resolve_trial_record("NCT12345678", {
        "document_id": "nct:NCT12345678", "availability": "RESOLUTION_FAILED",
    })
    report = build_relation_aware_report({}, [trial], trial_results={"TRIAL-10": record})
    entry = report["clinical_trials"][0]
    assert record["trial_resolution_status"] == "RESOLUTION_FAILED"
    assert entry["trial_resolution_status"] != "AVAILABLE"
    assert entry["evidence_interpretation"] == "TRIAL_ASSOCIATION_NOT_EFFICACY_EVIDENCE"


def test_11_real_companion_diagnostic_stays_kg_only() -> None:
    diagnostic = next(row for row in load_candidates().values()
                      if row.get("relation_family") == "COMPANION_DIAGNOSTIC_GENE")
    report = build_relation_aware_report({}, [diagnostic])
    entry = report["kg_only_relations"][0]
    assert entry["verification_status"] == "KG_ONLY"
    assert entry["diagnostic_context"]["device_id"]
    assert entry["diagnostic_context"]["gene"] == "EGFR"


def test_12_kg_only_relation_does_not_become_document_verified() -> None:
    candidate = paper_candidate(document_identifiers=[], semantic_key="GENE_DRUG|E2E")
    report = build_relation_aware_report({}, [candidate])
    assert report["paper_evidence"] == []
    assert report["kg_only_relations"][0]["verification_status"] == "KG_ONLY"


def test_13_unavailable_document_has_no_supporting_evidence() -> None:
    raw = "Lung cancer, EGFR L858R; erlotinib."
    trace = document_journey(raw, parsed_case(raw), paper_candidate(), ())
    assert trace["retrieval_result"]["matched"] is True
    assert trace["document_state"] == "UNAVAILABLE"
    assert trace["selected_source_units"] == ()
    assert trace["reader_verifier"] == []
    assert trace["final_deterministic_claim"]["status"] != "FULL_SUPPORT"


def test_16_reader_failure_is_accounted_without_support() -> None:
    raw = "Lung cancer, EGFR L858R; erlotinib."
    trace = document_journey(raw, parsed_case(raw), paper_candidate(), (POSITIVE,),
                             reader_failure=True)
    assert trace["retrieval_result"]["matched"] is True
    assert trace["selected_source_units"]
    assert trace["reader_verifier"] == ["READER_PARSE_FAILED"]
    assert trace["final_deterministic_claim"]["status"] != "FULL_SUPPORT"
    assert trace["final_deterministic_claim"]["rejected_evidence_ids"]


def test_same_relation_multi_source_uses_real_retrieval_grouping() -> None:
    raw = "Lung cancer, EGFR L858R; erlotinib."
    parsed = parsed_case(raw)
    understood = understand_case(raw, parsed)
    retrieval_input = build_retrieval_case_context(parsed, understood["mentions"])
    first = paper_candidate(candidate_id="GCA-A", source_record_ids=["row:1"],
                            edge_ids=["edge:1"])
    second = paper_candidate(candidate_id="GCA-B", source_record_ids=["row:2"],
                             edge_ids=["edge:2"])
    with patch("backend.research_pipeline.retrieval.kg_retrieval.load_candidates",
               return_value={"GCA-A": first, "GCA-B": second}):
        retrieved = retrieve(retrieval_input)
    assert len(retrieved["associations"]) == 1
    association = retrieved["associations"][0]
    assert set(association["candidate_group_candidate_ids"]) == {"GCA-A", "GCA-B"}
    grouped = association["candidate"]
    quote = POSITIVE
    observation = positive_reader(quote)
    support = _assess_v3_quoted_relation(grouped, observation, quote)
    record = {
        **observation, "candidate_id": association["candidate_id"],
        "document_id": "pmid:123", "source_unit_id": "SU-1",
        "validation_outcome": "ENRICHMENT_V3_ACCEPTED", "quote_valid": True,
        "presentation_state": "VALIDATED_QUOTE", "accepted_for_gates": True,
        "candidate_support": support,
    }
    report = build_relation_aware_report(
        retrieval_input, [grouped],
        {association["candidate_id"]: {"evidence_records": [record]}},
    )
    claim = report["paper_evidence"][0]["claim"]
    assert claim["status"] == "FULL_SUPPORT"
    assert set(claim["source_record_ids"]) == {"row:1", "row:2"}


def test_controlled_dossier_is_byte_identical_on_identical_runs() -> None:
    raw = "Lung cancer, EGFR L858R; erlotinib."
    def run_once() -> str:
        trace = document_journey(raw, parsed_case(raw), paper_candidate(),
                                 (POSITIVE, CONTRARY))
        return json.dumps(trace["final_deterministic_claim"], sort_keys=True)

    assert run_once() == run_once()
