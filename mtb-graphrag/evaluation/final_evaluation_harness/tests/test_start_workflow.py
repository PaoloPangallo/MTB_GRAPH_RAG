import json
import tempfile
from pathlib import Path

import pytest

from evaluation.final_evaluation_harness.common.arming import ExecutionDisarmed
from evaluation.final_evaluation_harness.common.lifecycle import CampaignState, LifecycleError
from evaluation.final_evaluation_harness.start import (
    CampaignStartError,
    validate_start_confirmation,
    run_fake_campaign,
)


def test_arming_requires_all_explicit_confirmations():
    expected_id = "fe_" + "a" * 64
    expected_plan = "b" * 64
    with pytest.raises(ExecutionDisarmed):
        validate_start_confirmation([], expected_id, expected_plan)
    with pytest.raises(ExecutionDisarmed):
        validate_start_confirmation(["--arm"], expected_id, expected_plan)
    with pytest.raises(CampaignStartError):
        validate_start_confirmation(["--arm", "--confirm-evaluation-id", "fe_" + "c" * 64,
                                     "--confirm-plan-sha", expected_plan,
                                     "--confirm-start", "FINAL_EVALUATION_1_6"], expected_id, expected_plan)
    validate_start_confirmation(["--arm", "--confirm-evaluation-id", expected_id,
                                 "--confirm-plan-sha", expected_plan,
                                 "--confirm-start", "FINAL_EVALUATION_1_6"], expected_id, expected_plan)


def test_cli_without_arguments_remains_disarmed():
    from evaluation.final_evaluation_harness.start import main
    with pytest.raises(ExecutionDisarmed):
        main([])


@pytest.fixture
def campaign_root():
    with tempfile.TemporaryDirectory(prefix="campaign-test-", dir="C:\\tmp", ignore_cleanup_errors=True) as value:
        yield Path(value)


def test_post_metadata_drift_preserves_raw_and_blocks_promotion(campaign_root):
    plan = [{"plan_index": 1, "run_id": "run_1", "testbed": "T", "case_id": "C", "arm": "A"}]
    good = {"details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"}, "model_info": {"gemma4.context_length": 262144}}
    drifted = {"details": {"family": "other", "parameter_size": "32682372656", "quantization_level": "BF16"}, "model_info": {"gemma4.context_length": 262144}}
    responses = iter([good, drifted])
    result = run_fake_campaign(campaign_root, plan, lambda _alias: next(responses), lambda _unit: None)
    assert result.state == CampaignState.PROVIDER_MODEL_METADATA_DRIFT
    assert (campaign_root / "evaluation" / "final_evaluation" / "post_snapshot.json").exists()
    assert "PROMOTED" not in [event["event"] for event in result.ledger_events]


def test_pre_failure_opens_no_campaign_and_reserves_no_runs(campaign_root):
    plan = [{"plan_index": 1, "run_id": "run_1", "testbed": "T", "case_id": "C", "arm": "A"}]
    with pytest.raises(CampaignStartError, match="PROVIDER_MODEL_METADATA_MISMATCH"):
        run_fake_campaign(campaign_root, plan, lambda _alias: {"details": {"family": "wrong"}},
                          lambda _unit: None)
    assert not (campaign_root / "evaluation" / "final_evaluation").exists()


def test_fake_campaign_orders_pre_open_runs_post_and_promotes(campaign_root):
    plan = [{"plan_index": i, "run_id": f"run_{i}", "testbed": "T", "case_id": f"C{i}", "arm": "A"} for i in range(1, 4)]
    raw = {"details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
           "model_info": {"gemma4.context_length": 262144}}
    calls = []
    result = run_fake_campaign(campaign_root, plan, lambda alias: calls.append(("metadata", alias)) or raw,
                               lambda unit: calls.append(("run", unit["plan_index"])))
    assert result.state == CampaignState.PROMOTED
    assert calls == [("metadata", "gemma4:31b-cloud"), ("run", 1), ("run", 2), ("run", 3), ("metadata", "gemma4:31b-cloud")]
    assert result.events[:3] == ["PREFLIGHT_VALIDATED", "PLAN_SEALED", "PRE_PROVIDER_SNAPSHOT_VALIDATED"]
    assert result.events[-3:] == ["POST_PROVIDER_SNAPSHOT_COMPLETE", "PROMOTION_PENDING", "PROMOTED"]


def test_resume_reconciles_orphan_skips_completed_and_keeps_ids(campaign_root):
    plan = [{"plan_index": i, "run_id": f"run_{i}", "testbed": "T", "case_id": f"C{i}", "arm": "A"} for i in range(1, 4)]
    raw = {"details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
           "model_info": {"gemma4.context_length": 262144}}
    result = run_fake_campaign(campaign_root, plan, lambda _alias: raw, lambda _unit: None)
    ledger = campaign_root / "evaluation" / "final_evaluation" / "ledger.jsonl"
    events = [json.loads(line) for line in ledger.read_text().splitlines()]
    events = [event for event in events if event["event"] not in {"POST_PROVIDER_SNAPSHOT_COMPLETE", "PROMOTION_PENDING", "PROMOTED"} and not (event["event"] == "COMPLETE" and event.get("run_id") != "run_1")]
    events.append({"event": "ATTEMPT_RESERVED", "attempt_id": "run_2/a0001"})
    ledger.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    calls = []
    resumed = run_fake_campaign(campaign_root, plan, lambda _alias: raw, lambda unit: calls.append(unit["run_id"]), resume=True)
    assert calls == ["run_2", "run_3"]
    assert resumed.state == CampaignState.PROMOTED
    assert "INCOMPLETE" in [event["event"] for event in resumed.ledger_events]
