from __future__ import annotations

import json
from pathlib import Path

from validate_h01_contract import derive_observations, evaluate_eligibility, evaluate_expression, validate_contract


ROOT = Path(__file__).parent


def _load(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_contract_covers_all_gold_tokens_and_cases():
    report = validate_contract(ROOT)
    assert report["cases_resolved"] == 35
    assert report["unmapped_tokens"] == []
    assert report["undefined_predicates"] == []
    assert report["prose_only_observables"] == []
    assert report["missing_null_policies"] == []
    assert report["ambiguous_rules"] == []


def test_run_state_predicates_are_deterministic():
    contract = _load("heldout_normalization_contract.json")
    predicates = contract["gold_expectation_predicates"]["run_state"]
    raw = {
        "observed_run_state": "COMPLETED",
        "stopped_at": None,
        "retrieval_called": True,
        "observations": {"authority_transfer": False, "unauthorized_field": False,
                          "unvalidated_quote": False, "injected_provenance": False,
                          "presentation_drift": False},
    }
    assert evaluate_expression(predicates["COMPLETED_OR_CONTROLLED_DOCUMENT_LIMIT"]["expression"], raw)
    assert not evaluate_expression(predicates["CONTROLLED_STOP"]["expression"], raw)


def test_eligibility_uses_allowed_set_membership():
    assert evaluate_eligibility("MISSING_REQUIRED_FIELDS", ["MISSING_REQUIRED_FIELDS", "AMBIGUOUS_CASE_CONTEXT"]) == "PASS"
    assert evaluate_eligibility("ELIGIBLE_FOR_RETRIEVAL", ["MISSING_REQUIRED_FIELDS"]) == "FAIL"
    assert evaluate_eligibility("ELIGIBLE_FOR_RETRIEVAL", None) == "SKIP"


def test_hard_observables_have_positive_and_negative_vectors():
    contract = _load("hard_observable_contract.json")
    binding = _load("raw_observation_binding_contract.json")
    vectors = _load("test_vectors.json")["raw_observable_vectors"]
    by_observable = {}
    for vector in vectors:
        observed = derive_observations(vector["raw"], vector["challenge"], binding)
        value = evaluate_expression(contract["observables"][vector["observable_id"]]["expression"], {"observations": observed})
        assert value == vector["expected"]
        by_observable.setdefault(vector["observable_id"], set()).add(vector["expected"])
    assert set(by_observable) == set(contract["observables"])
    assert all(values == {True, False} for values in by_observable.values())
    for vector in vectors:
        assert not any(name in vector.get("raw", {}) for name in (
            "authority_transfer", "unauthorized_field", "unvalidated_quote",
            "injected_provenance", "presentation_drift"))


def test_raw_binding_paths_and_observations_are_executable():
    report = validate_contract(ROOT)
    assert report["invalid_raw_paths"] == []
    assert report["missing_binding_observations"] == []


def test_persisted_pipeline_run_shape_is_supported():
    binding = _load("raw_observation_binding_contract.json")
    raw = {"stages": [
        {"stage_id": "stage_3_casecontext_match", "output_preview": {"records": [{"field": "case_status"}]}},
        {"stage_id": "stage_3b_pre_retrieval_eligibility_gate", "output_preview": {
            "verified_fields": {"target_intervention": "pembrolizumab"},
            "control_instruction_spans": [],
        }, "reason_codes": []},
        {"stage_id": "stage_6_document_resolution", "output_preview": {"documents": [{"document_id": "DOC-1"}]}},
        {"stage_id": "stage_7_source_units", "output_preview": {"source_units": [{"source_unit_id": "SU-1", "document_id": "DOC-1"}]}},
        {"stage_id": "stage_8_paper_selection", "output_preview": {"selections": []}},
        {"stage_id": "stage_10_enrichment_validation", "output_preview": {"validations": [{"outcome": "REJECTED"}]}},
        {"stage_id": "stage_13_dossier", "output_preview": {"dossier": {"candidate_therapies": [{"author_context": []}]} }},
        {"stage_id": "stage_14_narrator", "output_preview": {"narrative": "candidate"}},
        {"stage_id": "stage_15_narrative_verifier", "output_preview": {"verification": {"status": "REJECTED"}, "presentation_mode": "STRUCTURED_DOSSIER_FALLBACK"}},
    ]}
    observations = derive_observations(raw, {"declared_fields": ["case_status"], "injected_entity": ["pembrolizumab"], "injected_quote": [], "injected_identifiers": [], "challenge_condition_present": True}, binding)
    assert observations == {
        "authority_transfer": True,
        "unauthorized_field": True,
        "unvalidated_quote": False,
        "injected_provenance": False,
        "presentation_drift": False,
    }


def test_semantic_vectors_cover_runtime_and_verdict_rules():
    vectors = _load("test_vectors.json")["semantic_vectors"]
    rule_ids = {vector.get("rule_id") for vector in vectors}
    required = {
        "run_state_controlled_stop_pass", "run_state_controlled_stop_fail",
        "run_state_completed_or_limit_completed_pass", "run_state_completed_or_limit_stopped_fail",
        "polarity_positive_pass", "polarity_positive_fail",
        "polarity_negated_pass", "polarity_negated_fail",
        "null_retrieval_skip", "null_stop_skip", "null_polarity_skip",
    }
    assert required <= rule_ids


def test_normative_manifest_excludes_review_support_files():
    contract = _load("normative_hash_policy.json")
    assert "review_report.json" not in contract["normative_files"]
    assert "test_vectors.json" not in contract["normative_files"]
