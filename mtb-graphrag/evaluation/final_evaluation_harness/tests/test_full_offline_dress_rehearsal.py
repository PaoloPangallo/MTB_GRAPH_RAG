from __future__ import annotations

import json
import re
from types import SimpleNamespace

import evaluation.final_evaluation_harness.start as start
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import build_full_plan


class _FakeRuntime:
    descriptor = {"document_cache_available": True, "retrieval_mode": "OFFLINE_FIXTURE"}

    def __init__(self):
        self._associations = []

    def resolve(self, value):
        self._associations = list(value)
        documents = tuple(
            SimpleNamespace(
                document_id=bundle.get("document_id"), resolved=True,
                cache_hit=True, bundle_id=bundle.get("bundle_id"),
                candidate_id=association.get("candidate_id"),
                reason_codes=(), lineage={"retrieval_mode": "CACHE_HIT"},
                to_dict=lambda: {"document_id": bundle.get("document_id")},
            )
            for association in self._associations
            for bundle in association.get("available_bundles", [])
        )
        return SimpleNamespace(
            documents=documents,
            cache_hits=len(documents), cache_misses=0,
            manifest_hash="offline-fixture", network_fetch_count=0,
            to_preview=lambda: {"documents": [], "resolved_count": 0,
                                "unavailable_count": 0, "cache_hits": len(documents),
                                "cache_misses": 0, "network_fetch_used": False},
        )

    def load_units(self, _resolution):
        from backend.research_pipeline.documents.live_resolution import SourceUnitBundle
        units = {}
        for association in self._associations:
            for bundle in association.get("available_bundles", []):
                for unit_id in bundle.get("source_unit_ids", []):
                    units[str(unit_id)] = {
                        "source_unit_id": str(unit_id),
                        "document_id": bundle.get("document_id"),
                        "unit_type": "ABSTRACT",
                        "text": "Offline source evidence for the requested intervention.",
                    }
        previews = tuple({"source_unit_id": uid, "exact_text_available": True}
                        for uid in units)
        return SourceUnitBundle(units_by_id=units, previews=previews,
                                documents_parsed=len(units))

    def execute(self, *args, **kwargs):
        return {"status": "CONTROLLED_FIXTURE"}


class _FakeAdapters:
    def call(self, *args, **kwargs):
        return {"transport_result": "OFFLINE_FIXTURE", "enrichment": {}}

    def select(self, *args, **kwargs):
        selection = args[0]
        units = list(selection.source_units)
        return SimpleNamespace(
            selected_source_unit_ids=[str(row.get("source_unit_id")) for row in units[:5]],
            ranked_source_units=[],
        )

    def validate(self, *args, **kwargs):
        return {"outcome": "ENRICHMENT_V2_ABSTAINED"}

    def verify_authority(self, *args, **kwargs):
        return {"status": "REJECTED_OFFLINE_FIXTURE"}

    def execute(self, *args, **kwargs):
        return {"status": "CONTROLLED_FIXTURE"}


def _tool_response(name: str, arguments: dict) -> tuple[int, dict, None, int]:
    return 200, {"choices": [{"finish_reason": "tool_calls", "message": {
        "tool_calls": [{"function": {"name": name, "arguments": json.dumps(arguments)}}]
    }}]}, None, 0


def _transport_fixture_factory(counters: dict[str, int]):
    """Fake only the HTTP/model transport; all LLM internals remain real."""
    from backend.research_pipeline import replay

    def fake_transport(payload):
        name = payload["tool_choice"]["function"]["name"]
        if name == "submit_case_context":
            counters["parser_transport"] += 1
            user = payload["messages"][-1]["content"]
            match = re.search(r'\{"case_id":\s*"([^"]+)"\}', user)
            case_id = match.group(1) if match else "CASE-1-therapy-evaluation-strong-match"
            frozen = replay._parser_outputs_by_case().get(case_id)
            if frozen is None:
                frozen = next(iter(replay._parser_outputs_by_case().values()))
            return _tool_response(name, frozen["case_context_raw"])
        if name == "submit_paper_context_enrichment_v2":
            counters["enricher_transport"] += 1
            return _tool_response(name, {
                "decision": "ABSTAIN", "source_unit_id": "",
                "author_claim_quote": "", "author_context_summary": "",
                "abstention_reason": "OFFLINE_TRANSPORT_FIXTURE",
            })
        if name == "emit_dossier_narrative":
            counters["narrator_transport"] += 1
            return _tool_response(name, {
                "narrative_summary": "Sintesi del dossier disponibile.",
                "candidate_narratives": [],
                "limitations_summary": "Limitazioni dichiarate nel dossier.",
                "closing_note": "Nessuna raccomandazione.",
            })
        raise AssertionError(f"unexpected LLM tool: {name}")

    return fake_transport


def test_full_offline_dress_rehearsal_reaches_post_without_external_calls(tmp_path, monkeypatch):
    from evaluation.final_evaluation_harness.common.execution import ProductionAdapterFactory
    from evaluation.final_evaluation_harness.common.lifecycle import CampaignLedger as CanonicalCampaignLedger
    from backend.research_pipeline.data_access import (
        _EXPECTED_CANDIDATES_SHA256,
        candidates_path,
        read_candidate_corpus_utf8,
    )

    # The rehearsal must touch the same physical frozen candidate corpus as
    # production.  This identity check prevents a substituted/in-place
    # transformed checkout from being hidden by offline fixtures.
    candidate_text = read_candidate_corpus_utf8()
    assert candidate_text
    assert candidates_path().resolve().is_file()
    assert _EXPECTED_CANDIDATES_SHA256 == "d6c65c2682313652b736f1f82968078292c12588823e2f79309e76d6e671235d"

    class CachedCampaignLedger(CanonicalCampaignLedger):
        """Test-only index; delegates writes and validation to CampaignLedger."""
        def __init__(self, path):
            super().__init__(path)
            self._event_cache = super().events()

        def events(self):
            return list(self._event_cache)

        def append(self, event, **kwargs):
            super().append(event, **kwargs)
            self._event_cache.append({"event": event, **kwargs})

    monkeypatch.setattr(start, "CampaignLedger", CachedCampaignLedger)

    fake = _FakeAdapters()
    monkeypatch.setattr(ProductionAdapterFactory, "canonical_runtime", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "selector", staticmethod(lambda: fake))
    monkeypatch.setattr(ProductionAdapterFactory, "document_runtime", staticmethod(lambda: _FakeRuntime()))
    counters = {"parser_transport": 0, "enricher_transport": 0, "narrator_transport": 0}
    monkeypatch.setattr(
        "backend.research_pipeline.enrichment.transport.post_with_infra_retry",
        _transport_fixture_factory(counters),
    )

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
    assert counters["parser_transport"] > 0
    assert counters["enricher_transport"] > 0
    assert counters["narrator_transport"] > 0

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
    assert len(rows_by_family["RQ4_DEVELOPMENT"]) == 35
    assert len(rows_by_family["RQ4_HELDOUT"]) == 35
    assert len(rows_by_family["NARRATIVE"]) == 25
    assert len(rows_by_family["OPERATIONAL_A01"]) == 9
    assert len(rows_by_family["RELIABILITY"]) == 30
    assert len(rows_by_family["LATENCY"]) == 2
    assert sorted(path.stem for path in aggregate_root.glob("*.json")) == sorted(rows_by_family)
