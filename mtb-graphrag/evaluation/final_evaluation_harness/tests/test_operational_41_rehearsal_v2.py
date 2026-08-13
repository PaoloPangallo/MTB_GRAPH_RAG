from __future__ import annotations

import json
from pathlib import Path

import evaluation.final_evaluation_harness.start as start
from evaluation.final_evaluation_harness.common.runner import build_plan, execution_plan_sha256
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol

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
    monkeypatch.setattr(ProductionAdapterFactory, "document_runtime", staticmethod(lambda: _FakeRuntime()))
    monkeypatch.setattr("backend.research_pipeline.enrichment.transport.post_with_infra_retry",
                        _transport_fixture_factory({"parser_transport": 0, "enricher_transport": 0, "narrator_transport": 0}))
    protocol = load_protocol()
    plans = build_plan("operational", protocol) + build_plan("reliability", protocol) + build_plan("latency", protocol)
    plans = [unit.__class__(**{**unit.__dict__, "plan_index": index}) for index, unit in enumerate(plans, 1)]
    campaign = tmp_path / "evaluation" / "final_evaluation"
    metadata = {"details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
                "model_info": {"gemma4.context_length": 262144}}
    plan_sha = execution_plan_sha256(plans)
    result = start.run_official_start(
        protocol=protocol, source_root=protocol.root.parents[1], expected_head="a" * 40,
        plans=[unit.__dict__ for unit in plans], plan_sha=plan_sha,
        expected_evaluation_id="fe_41_rehearsal", argv=["--arm", "--confirm-evaluation-id", "fe_41_rehearsal",
        "--confirm-plan-sha", plan_sha, "--confirm-start", "FINAL_EVALUATION_1_6"], campaign_root=campaign,
        metadata_request=lambda _model: metadata, dispatch=start.run_production_dispatch,
        environment_validator=lambda: None, prompt_validator=lambda: None,
        head_validator=lambda *_args: None)
    assert result == "DISPATCHED"
    events = [json.loads(line) for line in (campaign / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len([e for e in events if e.get("event") == "ATTEMPT_RESERVED"]) == 41
    assert len([e for e in events if e.get("event") == "COMPLETE"]) == 41
    assert len(list((campaign / "raw_attempts").glob("*.json"))) == 41
