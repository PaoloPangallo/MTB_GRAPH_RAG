from pathlib import Path

import evaluation.final_evaluation_harness.start as start
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol


def _metadata(_model):
    return {
        "details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
        "model_info": {"gemma4.context_length": 262144},
        "modified_at": "fixture",
    }


def test_official_start_wires_pre_before_dispatch(tmp_path: Path, monkeypatch):
    protocol = load_protocol()
    plans = [{"run_id": "run_fixture", "case_id": "fixture"}]
    plan_sha = "p" * 64
    events = []

    def fake_dispatch(plan, _protocol, campaign_root, **_kwargs):
        assert (campaign_root / "ledger.jsonl").exists()
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
