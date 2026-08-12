import json

import pytest

from evaluation.final_evaluation_harness.common.raw_writer import write_raw_once
from evaluation.final_evaluation_harness.common.path_audit import validate_representative_dispatches
from evaluation.rq1.compare import PathComparison


def test_path_comparison_is_serialized_as_canonical_structured_row(tmp_path):
    comparison = PathComparison(
        path_id="path-1", rule_id="rule-1", candidate_id="candidate-1", matched=True,
        field_results={"predicate": True}, findings=[], lineage_ok=True,
        graph_fidelity_findings=[],
    )
    path, _ = write_raw_once(
        tmp_path, "run_" + "a" * 64 + "/a0001",
        {"comparisons": [comparison]},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["comparisons"][0] == comparison.to_row()
    assert not isinstance(payload["comparisons"][0], str)


def test_unknown_domain_object_is_rejected_by_raw_serializer(tmp_path):
    class Unsupported:
        pass

    with pytest.raises(TypeError):
        write_raw_once(tmp_path, "run_" + "b" * 64 + "/a0001", {"value": Unsupported()})


def test_all_representative_dispatch_payloads_are_json_ready(tmp_path):
    report = validate_representative_dispatches()
    for index, proof in enumerate(report["proofs"], 1):
        write_raw_once(tmp_path, f"run_{index:064x}/a0001", proof)
    assert len(report["proofs"]) == 28
