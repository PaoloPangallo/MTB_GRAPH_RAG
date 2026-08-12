from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.path_audit import (
    enumerate_execution_paths,
    validate_representative_dispatches,
)


def test_distinct_frozen_execution_paths_cover_all_units():
    paths = enumerate_execution_paths(load_protocol())
    assert len(paths) == 28
    assert sum(path["covered_unit_count"] for path in paths) == 222
    assert sum(bool(path["representative_unit_id"]) for path in paths) == 28


def test_representative_dispatches_enter_real_registry_dispatch_boundary():
    report = validate_representative_dispatches(load_protocol())
    assert report["distinct_paths"] == 28
    assert report["tested_paths"] == 28
    assert report["coverage_percent"] == 100.0
    assert report["covered_units"] == 222
    assert report["uncovered_units"] == 0
    assert report["dispatch_entry_point"] == "BoundExecutor.execute -> RealExecutionContext.execute -> ProductionUnitDispatcher.execute"
    assert report["external_calls"] == {"runtime": 0, "selector": 0, "gemma": 0, "narrator": 0, "verifier": 0, "network": 0}
