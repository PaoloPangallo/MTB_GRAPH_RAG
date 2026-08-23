from __future__ import annotations

from pathlib import Path

from evaluation.final_evaluation_harness.common.support_levels import (
    CASE1_DOCUMENT_SUPPORT_LEVEL,
    compare_unit_ids,
    summarize_support_levels,
)


def _run(*checks: dict) -> dict:
    return {
        "raw_pipeline_run": {
            "dossier": {
                "candidate_therapies": [
                    {
                        "candidate_id": "C1",
                        "validation_results": list(checks),
                    }
                ]
            }
        }
    }


def test_case1_expected_document_support_is_partial_not_legacy_direct():
    assert CASE1_DOCUMENT_SUPPORT_LEVEL == "PARTIAL_SUPPORT"


def test_support_levels_are_counted_separately_from_quote_validation():
    result = summarize_support_levels(
        [
            _run({"outcome": "QUOTE_VALIDATED", "candidate_support": {"result": "STRONG_SUPPORT"}}),
            _run({"outcome": "QUOTE_VALIDATED", "candidate_support": {"result": "PARTIAL_SUPPORT"}}),
            _run({"outcome": "QUOTE_REJECTED", "candidate_support": {"result": "CONTEXT_ONLY"}}),
        ]
    )
    assert result["quote_validated"] == 2
    assert result["support_levels"] == {
        "STRONG_SUPPORT": 1,
        "PARTIAL_SUPPORT": 1,
        "CONTEXT_ONLY": 1,
        "CONTRADICTORY": 0,
        "UNVERIFIABLE": 0,
    }


def test_multi_paper_checks_remain_per_paper_without_aggregation():
    result = summarize_support_levels(
        [
            {
                "raw_pipeline_run": {
                    "dossier": {
                        "candidate_therapies": [
                            {
                                "candidate_id": "C1",
                                "validation_results": [
                                    {"paper_id": "P-A", "candidate_support": {"result": "STRONG_SUPPORT"}},
                                    {"paper_id": "P-B", "candidate_support": {"result": "CONTRADICTORY"}},
                                ],
                            }
                        ]
                    }
                }
            }
        ]
    )
    assert result["per_paper"] == [
        {"candidate_id": "C1", "paper_id": "P-A", "support_level": "STRONG_SUPPORT"},
        {"candidate_id": "C1", "paper_id": "P-B", "support_level": "CONTRADICTORY"},
    ]


def test_unit_identity_comparison_rejects_added_or_removed_units():
    assert compare_unit_ids(["u1", "u2"], ["u2", "u1"]) == {"same": True, "added": [], "removed": []}
    assert compare_unit_ids(["u1"], ["u1", "u2"])["same"] is False


def test_candidate_local_sourceunit_failure_is_not_run_abort_metric():
    result = summarize_support_levels(
        [{"raw_pipeline_run": {"status": "PARTIAL", "reason_codes": ["NO_RELEVANT_SOURCE_UNIT"]}}]
    )
    assert result["run_abort_from_no_relevant_source_unit"] == 0


def test_protocol_172_uses_clean_namespace_and_exact_model(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7.2")
    monkeypatch.setenv("RESEARCH_PIPELINE_MODEL", "gemma4:31b-cloud")
    from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
    from evaluation.final_evaluation_harness.common.model_identity import validate_execution_environment

    protocol = load_protocol()
    assert protocol.manifest["protocol_version"] == "1.7.2"
    assert protocol.manifest["output_directory"] == "evaluation/final_evaluation_v1_7_3"
    env = dict(__import__("os").environ)
    env["OLLAMA_API_KEY"] = "present-for-offline-guard-test"
    assert validate_execution_environment(env)["model"] == "gemma4:31b-cloud"


def test_protocol_172_preserves_experimental_unit_composition_after_runtime_freeze(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7.2")
    from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
    from evaluation.final_evaluation_harness.common.runner import build_full_plan

    protocol = load_protocol()
    assert protocol.manifest["unit_membership_unchanged"] is True
    assert protocol.manifest["total_units"] == 222
    plan = build_full_plan(protocol)
    assert len(plan) == 222
    assert protocol.hashes["runtime_commit"] == "586bf27885c11173510a6bd0b93db3f3ac0f222a"


def test_protocol_172_parent_plan_has_the_same_experimental_units(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7.1")
    from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
    from evaluation.final_evaluation_harness.common.runner import build_full_plan

    parent = build_full_plan(load_protocol())
    signatures = [(p.rq, p.testbed, p.case_id, p.arm, p.repetition_id) for p in parent]
    assert len(signatures) == 222
    assert len({item.case_id for item in parent if item.rq == "RQ4_DEVELOPMENT"}) == 35
    assert len({item.case_id for item in parent if item.rq == "RQ4_HELDOUT"}) == 35
    assert len(signatures) == len(set(signatures))
