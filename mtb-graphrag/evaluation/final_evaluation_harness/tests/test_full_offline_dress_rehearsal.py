from __future__ import annotations

import json
from types import SimpleNamespace

import evaluation.final_evaluation_harness.start as start
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import build_full_plan


class _FakeRuntime:
    descriptor = {"document_cache_available": True, "retrieval_mode": "OFFLINE_FIXTURE"}

    def resolve(self, value):
        return {"document_id": value, "status": "OFFLINE_FIXTURE"}

    def execute(self, *args, **kwargs):
        return {"status": "CONTROLLED_FIXTURE"}


class _FakeAdapters:
    def call(self, *args, **kwargs):
        return {"transport_result": "OFFLINE_FIXTURE", "enrichment": {}}

    def select(self, *args, **kwargs):
        return SimpleNamespace(selected_source_unit_ids=[], ranked_source_units=[])

    def validate(self, *args, **kwargs):
        return {"outcome": "ENRICHMENT_V2_ABSTAINED"}

    def verify_authority(self, *args, **kwargs):
        return {"status": "REJECTED_OFFLINE_FIXTURE"}

    def execute(self, *args, **kwargs):
        return {"status": "CONTROLLED_FIXTURE"}


def test_full_offline_dress_rehearsal_reaches_post_without_external_calls(tmp_path, monkeypatch):
    from evaluation.final_evaluation_harness.common.execution import ProductionAdapterFactory

    fake = _FakeAdapters()
    monkeypatch.setattr(ProductionAdapterFactory, "canonical_runtime", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "selector", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "parser", staticmethod(lambda: lambda *a, **k: {"transport_result": "TEXT_RESPONSE_INSTEAD_OF_TOOL_CALL"}))
    monkeypatch.setattr(ProductionAdapterFactory, "gemma", staticmethod(lambda *a, **k: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "narrator", staticmethod(lambda *a, **k: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "quote_validator", staticmethod(lambda *a, **k: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "narrative_verifier", staticmethod(lambda *a, **k: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "document_runtime", staticmethod(lambda: _FakeRuntime()))

    protocol = load_protocol()
    plans = build_full_plan(protocol)
    serialized = [unit.__dict__ for unit in plans]
    campaign = tmp_path / "evaluation" / "final_evaluation"
    metadata = {
        "details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"},
        "model_info": {"gemma4.context_length": 262144},
    }
    result = start.run_official_start(
        protocol=protocol,
        source_root=protocol.root.parents[1],
        expected_head="a" * 40,
        plans=serialized,
        plan_sha="p" * 64,
        expected_evaluation_id="fe_offline_dress",
        argv=["--arm", "--confirm-evaluation-id", "fe_offline_dress", "--confirm-plan-sha", "p" * 64,
              "--confirm-start", "FINAL_EVALUATION_1_6"],
        campaign_root=campaign,
        metadata_request=lambda _model: metadata,
        dispatch=start.run_production_dispatch,
        environment_validator=lambda: None,
        prompt_validator=lambda: None,
        head_validator=lambda *_args: None,
    )
    assert result == "DISPATCHED"
    events = [json.loads(line) for line in (campaign / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len([event for event in events if event.get("event") == "ATTEMPT_RESERVED"]) == 222
    assert len([event for event in events if event.get("event") == "COMPLETE"]) == 222
    assert len(list((campaign / "raw_attempts").glob("*.json"))) == 222
    assert events[-1]["event"] == "PROMOTED"

    # The official lifecycle has already completed fake POST/PROMOTION.  Run
    # the frozen reconciliation and aggregation boundaries over that exact
    # campaign state without changing production START wiring.
    from evaluation.final_evaluation_harness.common.lifecycle import CampaignLedger
    ledger = CampaignLedger(campaign / "ledger.jsonl")
    assert ledger.reconcile() == []
    complete = {event["run_id"] for event in ledger.events() if event.get("event") == "COMPLETE"}
    assert len(complete) == 222
    by_run = {unit.run_id: unit for unit in plans}
    aggregate_root = campaign / "aggregates"
    aggregate_root.mkdir()
    rows_by_family = {}
    for raw_path in sorted((campaign / "raw_attempts").glob("*.json")):
        row = json.loads(raw_path.read_text(encoding="utf-8"))
        unit = by_run[row["run_id"]]
        row = {**row, "family": unit.rq, "unit_id": unit.run_id}
        rows_by_family.setdefault(unit.rq, []).append(row)
    from evaluation.final_evaluation_harness.aggregate import aggregate
    for family, rows in rows_by_family.items():
        source = aggregate_root / f"{family}.jsonl"
        source.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
        result = aggregate(source, ["attempt_id", "run_id", "scientific_payload", "status"])
        (aggregate_root / f"{family}.json").write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
        assert result["observation_count"] == len(rows)
    assert {unit.rq for unit in plans} == set(rows_by_family)
    assert sorted(path.stem for path in aggregate_root.glob("*.json")) == sorted(rows_by_family)
