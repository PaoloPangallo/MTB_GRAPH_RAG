from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from evaluation.final_evaluation_harness.common.final_manifest import build_final_results_manifest


def test_final_manifest_requires_all_units_accounted(tmp_path):
    (tmp_path / "ledger.jsonl").write_text(
        json.dumps({"event": "COMPLETE", "unit_status": "FAILED"}) + "\n",
        encoding="utf-8",
    )
    protocol = SimpleNamespace(
        hashes={"runtime_commit": "a" * 40},
        manifest={"protocol_version": "1.7.1", "evaluation_boundary": "FINAL_EVALUATION_1_7_1"},
    )
    with pytest.raises(RuntimeError, match="FINAL_RESULTS_NOT_ACCOUNTED:1/2"):
        build_final_results_manifest(
            protocol=protocol, campaign_root=tmp_path, expected_units=2,
            evaluation_id="fe_test", output_directory="evaluation/final_evaluation_v1_7_1",
        )


def test_final_manifest_contains_direct_provenance_and_counts(tmp_path):
    (tmp_path / "ledger.jsonl").write_text(
        "\n".join([
            json.dumps({"event": "COMPLETE", "unit_status": "FAILED"}),
            json.dumps({"event": "COMPLETE", "unit_status": "COMPLETE"}),
        ]) + "\n",
        encoding="utf-8",
    )
    protocol = SimpleNamespace(
        hashes={"runtime_commit": "a" * 40},
        manifest={
            "protocol_version": "1.7.1",
            "evaluation_boundary": "FINAL_EVALUATION_1_7_1",
            "evaluation_protocol_commit": "b" * 40,
            "sealed_plan_sha256": "c" * 64,
            "gca_sha256": "d" * 64,
            "frozen_document_manifest_sha256": "e" * 64,
            "dependency_lock_sha256": "f" * 64,
        },
    )
    result = build_final_results_manifest(
        protocol=protocol, campaign_root=tmp_path, expected_units=2,
        evaluation_id="fe_test", output_directory="evaluation/final_evaluation_v1_7_1",
    )
    assert result["canonical_runtime_commit"] == "a" * 40
    assert result["protocol_version"] == "1.7.1"
    assert result["unit_status_counts"] == {"COMPLETE": 1, "FAILED": 1}
    assert result["accounted_units"] == 2
