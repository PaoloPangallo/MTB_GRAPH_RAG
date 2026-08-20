from __future__ import annotations

import json
from pathlib import Path

import evaluation.final_evaluation_harness.start as start
from evaluation.final_evaluation_harness.common.runner import build_plan, execution_plan_sha256
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.tests._official_start_test_helpers import (
    dispatch_selected_only,
    full_plan_with_selected_units,
)

from .test_full_offline_dress_rehearsal import (
    _FakeAdapters, _FakeRuntime, _transport_fixture_factory,
)


def test_operational_reliability_latency_41_rehearsal(tmp_path, monkeypatch):
    from evaluation.final_evaluation_harness.common.execution import ProductionAdapterFactory
    from evaluation.final_evaluation_harness.common.lifecycle import CampaignLedger as CanonicalCampaignLedger

    class CachedCampaignLedger(CanonicalCampaignLedger):
        def __init__(self, path):
            super().__init__(path)
            self._event_cache = super().events()

        def events(self):
            return list(self._event_cache)

        def append(self, event, **kwargs):
            super().append(event, **kwargs)
            self._event_cache.append({"event": event, **kwargs})

    fake = _FakeAdapters()
    monkeypatch.setattr(start, "CampaignLedger", CachedCampaignLedger)
    monkeypatch.setattr(ProductionAdapterFactory, "canonical_runtime", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "selector", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "document_runtime", staticmethod(lambda protocol=None: _FakeRuntime()))
    offline_transport = _transport_fixture_factory({"parser_transport": 0, "enricher_transport": 0, "narrator_transport": 0})
    monkeypatch.setattr("backend.research_pipeline.enrichment.transport.post_with_infra_retry_with_diagnostics", offline_transport)
    monkeypatch.setattr("backend.research_pipeline.enrichment.transport.post_with_infra_retry",
                        lambda payload: offline_transport(payload)[:4])
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("operational rehearsal attempted requests.post")
    ))
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("operational rehearsal attempted requests.get")
    ))
    protocol = load_protocol()
    selected = build_plan("operational", protocol) + build_plan("reliability", protocol) + build_plan("latency", protocol)
    plans, selected = full_plan_with_selected_units(protocol, {unit.run_id for unit in selected})
    campaign = tmp_path / "evaluation" / "final_evaluation"
    metadata = {"details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
                "model_info": {"gemma4.context_length": 262144}}
    plan_sha = execution_plan_sha256(plans)
    result = start.run_official_start(
        protocol=protocol, source_root=protocol.root.parents[1], expected_head="a" * 40,
        plans=[unit.__dict__ for unit in plans], plan_sha=plan_sha,
        expected_evaluation_id="fe_41_rehearsal", argv=["--arm", "--confirm-evaluation-id", "fe_41_rehearsal",
        "--confirm-plan-sha", plan_sha, "--confirm-start", "FINAL_EVALUATION_1_7_2"], campaign_root=campaign,
        metadata_request=lambda _model: metadata,
        dispatch=dispatch_selected_only(start.run_production_dispatch, {unit.run_id for unit in selected}),
        environment_validator=lambda: None, prompt_validator=lambda: None,
        head_validator=lambda *_args: None)
    assert result == "DISPATCHED"
    selected_ids = {unit.run_id for unit in selected}
    events = [json.loads(line) for line in (campaign / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    selected_events = [e for e in events if e.get("run_id") in selected_ids]
    assert len([e for e in selected_events if e.get("event") == "ATTEMPT_RESERVED"]) == 41
    assert len([e for e in selected_events if e.get("event") == "COMPLETE"]) == 41
    assert len(list((campaign / "raw_attempts").glob("*.json"))) == 41
