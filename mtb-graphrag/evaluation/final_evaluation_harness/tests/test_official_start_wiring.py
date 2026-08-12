from pathlib import Path
import hashlib

import evaluation.final_evaluation_harness.start as start
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import PlannedRun, planned_runs_from_serialized


def _metadata(_model):
    return {
        "details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
        "model_info": {"gemma4.context_length": 262144},
        "modified_at": "fixture",
    }


def test_official_start_wires_pre_before_dispatch(tmp_path: Path, monkeypatch):
    protocol = load_protocol()
    from evaluation.final_evaluation_harness.common.runner import build_full_plan
    plans = [build_full_plan(protocol)[0].__dict__]
    plan_sha = "p" * 64
    events = []

    def fake_dispatch(plan, _protocol, campaign_root, **_kwargs):
        assert (campaign_root / "ledger.jsonl").exists()
        assert all(isinstance(unit, PlannedRun) for unit in plan)
        assert plan[0].execution_class and plan[0].case_id
        events.append("DISPATCH")
        return []

    result = start.run_official_start(
        protocol=protocol,
        source_root=protocol.root.parents[1],
        expected_head="a" * 40,
        plans=plans,
        plan_sha=plan_sha,
        expected_evaluation_id="fe_fixture",
        argv=["--arm", "--confirm-evaluation-id", "fe_fixture", "--confirm-plan-sha", plan_sha, "--confirm-start", "FINAL_EVALUATION_1_6"],
        campaign_root=tmp_path / "evaluation" / "final_evaluation",
        metadata_request=_metadata,
        dispatch=fake_dispatch,
        environment_validator=lambda: None,
        prompt_validator=lambda: None,
        head_validator=lambda *_: None,
    )
    assert result == "DISPATCHED"
    assert events == ["DISPATCH"]
    ledger = (tmp_path / "evaluation" / "final_evaluation" / "ledger.jsonl").read_text(encoding="utf-8")
    assert "PRE_PROVIDER_SNAPSHOT_VALIDATED" in ledger


def test_invalid_confirmation_creates_no_start_state(tmp_path: Path):
    protocol = load_protocol()
    try:
        start.run_official_start(
            protocol=protocol, source_root=protocol.root.parents[1], expected_head="a" * 40,
            plans=[], plan_sha="p" * 64, expected_evaluation_id="fe_fixture",
            argv=[], campaign_root=tmp_path / "evaluation" / "final_evaluation",
            metadata_request=_metadata, dispatch=lambda *_args, **_kwargs: None,
            environment_validator=lambda: None, prompt_validator=lambda: None,
            head_validator=lambda *_: None,
        )
    except start.ExecutionDisarmed:
        pass
    else:
        raise AssertionError("invalid confirmation was accepted")
    assert not (tmp_path / "evaluation" / "final_evaluation").exists()


def test_all_frozen_plan_records_deserialize_to_planned_runs():
    protocol = load_protocol()
    from evaluation.final_evaluation_harness.common.runner import build_full_plan
    original = build_full_plan(protocol)
    serialized = [unit.__dict__ for unit in original]
    restored = planned_runs_from_serialized(serialized)
    assert len(restored) == 222
    assert all(isinstance(unit, PlannedRun) for unit in restored)
    assert [unit.run_id for unit in restored] == [unit.run_id for unit in original]
    assert [unit.execution_class for unit in restored] == [unit.execution_class for unit in original]


def test_existing_campaign_is_not_overwritten(tmp_path: Path):
    campaign_a = tmp_path / "a" / "evaluation" / "final_evaluation"
    campaign_a.mkdir(parents=True)
    marker = campaign_a / "ledger.jsonl"
    marker.write_text('{"event":"CAMPAIGN_OPEN"}\n', encoding="utf-8")
    before = hashlib.sha256(marker.read_bytes()).hexdigest()
    protocol = load_protocol()
    try:
        start.run_official_start(
            protocol=protocol, source_root=protocol.root.parents[1], expected_head="a" * 40,
            plans=[], plan_sha="p" * 64, expected_evaluation_id="fe_fixture",
            argv=["--arm", "--confirm-evaluation-id", "fe_fixture", "--confirm-plan-sha", "p" * 64, "--confirm-start", "FINAL_EVALUATION_1_6"],
            campaign_root=campaign_a, metadata_request=_metadata, dispatch=lambda *_args, **_kwargs: None,
            environment_validator=lambda: None, prompt_validator=lambda: None,
            head_validator=lambda *_: None,
        )
    except start.CampaignStartError as error:
        assert str(error) == "CAMPAIGN_STORAGE_COLLISION"
    else:
        raise AssertionError("existing campaign was accepted")
    assert hashlib.sha256(marker.read_bytes()).hexdigest() == before
