from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import pytest

from evaluation.final_evaluation_harness.common.cache_factory import create_operational_cache
from evaluation.final_evaluation_harness.common.heldout import join_gold_after_inference, load_case_only
from evaluation.final_evaluation_harness.common.identities import attempt_id, evaluation_id, run_id
from evaluation.final_evaluation_harness.common.ledger import AppendOnlyLedger
from evaluation.final_evaluation_harness.common.protocol_loader import ProtocolGap, load_a01_bindings, load_protocol, load_s01_rows
from evaluation.final_evaluation_harness.common.raw_writer import DuplicateAttempt, write_raw_once
from evaluation.final_evaluation_harness.common.runner import dry_run
from evaluation.final_evaluation_harness.common.schemas import validate_envelope
from evaluation.final_evaluation_harness.common.timing import timed_call
from evaluation.final_evaluation_harness.common.guards import CallCounts, ForbiddenOperation, ModelGuard, NetworkGuard
from evaluation.final_evaluation_harness.statistics import paired_percentile_bootstrap, ranking_metrics, wilson


@pytest.fixture(scope="module")
def protocol():
    return load_protocol()


@pytest.fixture
def local_tmp():
    path = Path(__file__).parent / f"_tmp_{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_protocol_sha_accepted(protocol): assert protocol.hashes["protocol_sha256"] == "ac296a924a39b58caf3427f47153348566d21bcadb6fef94bfa8c6105400ac1d"
def test_runtime_exact(protocol): assert protocol.hashes["runtime_commit"] == "eb20fdfab35724f3b84651d8c02f1ec3970db615"
def test_lineage_exact(protocol): assert protocol.hashes["inherited_protocol_1_1_sha256"].startswith("83fcf870")
def test_a01_exact(protocol): assert protocol.hashes["inherited_A01_sha256"].startswith("48c60928")
def test_s01_exact(protocol): assert protocol.hashes["S01_raw_sha256"].startswith("83babfa5")
def test_frozen_gate(protocol): assert protocol.manifest["frozen"] is True and protocol.manifest["review_status"] == "ACCEPTED"
def test_a01_loaded_direct(protocol): assert len(load_a01_bindings(protocol)["scenarios"]) == 9
def test_s01_loaded_direct(protocol): assert len(load_s01_rows(protocol)) == 1697
def test_operational_cache_plans(protocol): assert all(create_operational_cache(protocol, s["scenario_id"]).isolated for s in load_a01_bindings(protocol)["scenarios"])
def test_a01_cache_is_read_only(protocol): assert create_operational_cache(protocol, "A_cache_hit").read_only_baseline
def test_identity_evaluation_deterministic(protocol):
    commit = "a" * 40
    assert evaluation_id(protocol, commit) == evaluation_id(protocol, commit)
def test_identity_requires_full_git_sha(protocol):
    full = "0" * 40
    assert evaluation_id(protocol, full).startswith("fe_")
    for abbreviated in ("0" * 7, "0" * 8, "0" * 12, "not-a-sha"):
        with pytest.raises(ValueError):
            evaluation_id(protocol, abbreviated)
def test_identity_changes_when_full_harness_commit_changes(protocol):
    assert evaluation_id(protocol, "0" * 40) != evaluation_id(protocol, "1" * 40)
def test_identity_run_deterministic(protocol): assert run_id("e", "t", "c", "a", "r") == run_id("e", "t", "c", "a", "r")
def test_attempt_ordinal(): assert attempt_id("run_x", 1).endswith("/a0001")
def test_attempt_ordinal_rejects_zero():
    with pytest.raises(ValueError): attempt_id("run_x", 0)
def test_network_prohibited():
    with pytest.raises(ForbiddenOperation): NetworkGuard("PROHIBITED").record()
def test_network_allowed_counts():
    counts = CallCounts(); NetworkGuard("CANONICAL_RUNTIME_POLICY", counts).record(); assert counts.network == 1
def test_model_call_accounting():
    counts = CallCounts(); guard = ModelGuard(counts); guard.record("gemma"); guard.record("narrator"); assert counts.gemma == 1 and counts.narrator == 1
def test_timing_transparent():
    value, duration = timed_call(lambda: 7); assert value == 7 and duration >= 0
def test_gold_inaccessible():
    with pytest.raises(ValueError): load_case_only({"case_id": "x", "gold": {}})
def test_gold_join_after_inference(): assert join_gold_after_inference({"x": 1}, {"y": 2})["gold"]["y"] == 2
_ATTEMPT = "run_" + "a" * 64 + "/a0001"
def test_raw_create_if_absent(local_tmp): write_raw_once(local_tmp, _ATTEMPT, {"x": 1})
def test_raw_duplicate_hard_fail(local_tmp):
    write_raw_once(local_tmp, _ATTEMPT, {"x": 1})
    with pytest.raises(DuplicateAttempt): write_raw_once(local_tmp, _ATTEMPT, {"x": 2})
def test_ledger_append_only(local_tmp):
    ledger = AppendOnlyLedger(local_tmp / "ledger.jsonl"); ledger.append({"event": "ATTEMPT_RESERVED", "attempt_id": "a"}); assert len(ledger.events()) == 1
def test_ledger_reconcile_orphan(local_tmp):
    ledger = AppendOnlyLedger(local_tmp / "ledger.jsonl"); ledger.append({"event": "ATTEMPT_RESERVED", "attempt_id": "a"}); assert ledger.reconcile() == ["a"]
def test_ledger_reconcile_preserves_event(local_tmp):
    ledger = AppendOnlyLedger(local_tmp / "ledger.jsonl"); ledger.append({"event": "ATTEMPT_RESERVED", "attempt_id": "a"}); ledger.reconcile(); assert len(ledger.events()) == 2
def test_envelope_required(protocol):
    required = protocol.schemas["common_execution_envelope"]["required_fields"]; envelope = {key: {} for key in required}; envelope["normative_identity"] = {"protocol_version": "1.6"}; envelope["identity"] = {field: "x" for field in protocol.schemas["common_execution_envelope"]["identity_required"]}; envelope["dataset_hashes"] = {"dataset_bundle_sha256": "x"}; envelope["status"] = "COMPLETE"; validate_envelope(protocol, envelope)
def test_envelope_rejects_missing(protocol):
    with pytest.raises(ValueError): validate_envelope(protocol, {})
def test_ranking_precision_denominator_k(): assert ranking_metrics(["a"], ["a"], 5)["Precision@5"] == 0.2
def test_ranking_mrr_miss_zero(): assert ranking_metrics(["a"], ["b"], 5)["MRR"] == 0.0
def test_wilson_zero(): assert wilson(0, 5) is not None
def test_bootstrap_seed_deterministic(): assert paired_percentile_bootstrap([1.0, 2.0], 10000, 20260809) == paired_percentile_bootstrap([1.0, 2.0], 10000, 20260809)
def test_protocol_dry_run_zero_calls(): assert dry_run("rq1")["calls"] == {"runtime": 0, "selector": 0, "model": 0, "network": 0}
def test_rq2_dry_run_count(): assert dry_run("rq2")["planned_executions"] == 80
def test_operational_dry_run_count(): assert dry_run("operational")["planned_executions"] == 9
def test_operational_cache_materialization_isolated(protocol, local_tmp):
    first = create_operational_cache(protocol, "A_cache_hit", execute=True, root=local_tmp)
    second = create_operational_cache(protocol, "B_cache_miss_success", execute=True, root=local_tmp)
    assert first.isolated and second.isolated
    assert (local_tmp / "operational_cache_A_cache_hit").exists()
    assert (local_tmp / "operational_cache_B_cache_miss_success").exists()
def test_reliability_dry_run_count(): assert dry_run("reliability")["planned_executions"] == 30
def test_latency_dry_run_count(): assert dry_run("latency")["planned_executions"] == 2
def test_result_directory_absent(protocol): assert not (protocol.root.parent / "final_evaluation").exists()
def test_no_scientific_payloads(): assert protocol_result_dir_absent()


def protocol_result_dir_absent() -> bool:
    return not (Path(__file__).resolve().parents[3] / "evaluation" / "final_evaluation").exists()
