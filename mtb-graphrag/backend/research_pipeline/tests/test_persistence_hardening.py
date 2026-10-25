"""Offline regressions for durable stage results and bounded run resources."""

from __future__ import annotations

import json
import threading
from unittest import mock

import pytest

from backend.pipeline.agentic.ledger import EventLedger
from backend.research_pipeline import events as ev, rehydration, run_store


@pytest.fixture
def ledger(tmp_path):
    return EventLedger(tmp_path / "research.sqlite3")


def test_terminal_memory_cache_is_bounded_without_losing_durable_history(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_LEDGER_PATH", str(tmp_path / "bounded.sqlite3"))
    store = run_store.RunStore(max_workers=1, queue_capacity=5, max_cached_runs=2)
    monkeypatch.setattr(store, "_execute", lambda handle, text: store._abort(handle))
    handles = [store.start(case_id=str(index), clinical_text="synthetic") for index in range(5)]
    store.shutdown()
    assert len(store.list_runs()) == 2
    assert len(store.list_all()) == 5
    evicted = next(handle for handle in handles if store.get(handle.run_id) is None)
    assert store.snapshot(evicted.run_id)["status"] == "FAILED"
    assert store.has_run(evicted.run_id)


def test_streaming_integrity_matches_sealed_ledger_without_full_event_materialization(ledger, monkeypatch):
    from backend.research_pipeline import ledger_reads
    for index in range(8):
        ledger.append("run", "TEST", "test", {"index": index})
    expected = ledger.verify_chain("run")
    monkeypatch.setattr(ledger, "events", mock.Mock(side_effect=AssertionError("no full payload read")))
    assert ledger_reads.verify_chain(ledger, "run") is expected is True
    monkeypatch.setattr(ledger, "_hash_for_row", lambda row: "corrupt")
    assert ledger_reads.verify_chain(ledger, "run") is False


def append_stage(ledger, run_id, stage_id, *, preview=None, terminal=ev.STAGE_COMPLETED):
    payload = {"stage_id": stage_id, "artifact_origin": "GENERATED_NOW"}
    if preview is not None:
        payload["output_preview"] = preview
    ledger.append(run_id, terminal, "test", payload)


@pytest.mark.parametrize("stage_id,preview,terminal", [
    ("stage_3b_pre_retrieval_eligibility_gate", {"eligibility": "OUT_OF_DOMAIN"}, ev.STAGE_COMPLETED),
    ("stage_2_casecontext_parser", {"transport_result": "HTTP_ERROR"}, ev.STAGE_FAILED),
    ("stage_15_narrative_verifier", {"presentation": {"mode": "STRUCTURED_FALLBACK"}}, ev.STAGE_WARNING),
])
def test_terminal_stage_preview_survives_without_domain_events(ledger, stage_id, preview, terminal):
    ledger.append("run", ev.RUN_CREATED, "test", {"case_id": "synthetic"})
    append_stage(ledger, "run", stage_id, preview=preview, terminal=terminal)
    snapshot = rehydration.rehydrate(ledger, "run")
    assert snapshot["stages"][0]["output_preview"] == preview
    assert snapshot["hash_chain_valid"] is True


def test_legacy_stage_uses_exact_artifact_and_ignores_later_progress(ledger):
    ledger.append("run", ev.RUN_CREATED, "test", {"case_id": "synthetic"})
    ledger.append("run", ev.DOSSIER_BUILT, "test", {
        "stage_id": "stage_13_dossier", "relation_aware_report": {"paper_evidence": []}})
    ledger.append("run", ev.DOCUMENT_FETCH_SUCCEEDED, "test", {
        "stage_id": "stage_13_dossier", "document_id": "unrelated-progress"})
    append_stage(ledger, "run", "stage_13_dossier")
    snapshot = rehydration.rehydrate(ledger, "run")
    assert snapshot["relation_aware_report"] == {"paper_evidence": []}
    assert snapshot["stages"][0]["output_preview"] == {
        "relation_aware_report": {"paper_evidence": []}}


def test_legacy_progress_is_not_promoted_to_stage_artifact(ledger):
    ledger.append("run", ev.RUN_CREATED, "test", {"case_id": "synthetic"})
    ledger.append("run", ev.STRUCTURED_FALLBACK_USED, "test", {
        "stage_id": "stage_15_narrative_verifier", "reason": "provider-offline"})
    append_stage(ledger, "run", "stage_15_narrative_verifier", terminal=ev.STAGE_WARNING)
    assert rehydration.rehydrate(ledger, "run")["stages"][0]["output_preview"] == {}


def test_explicit_empty_terminal_preview_overrides_legacy_domain_result(ledger):
    ledger.append("run", ev.RUN_CREATED, "test", {"case_id": "synthetic"})
    ledger.append("run", ev.NARRATION_VERIFIED, "test", {
        "stage_id": "stage_15_narrative_verifier", "presentation": "stale"})
    append_stage(ledger, "run", "stage_15_narrative_verifier", preview={})
    assert rehydration.rehydrate(ledger, "run")["stages"][0]["output_preview"] == {}


def test_terminal_run_snapshot_preserves_exact_run_projection(ledger):
    ledger.append("run", ev.RUN_CREATED, "test", {"case_id": "synthetic"})
    exact = {"run_id": "run", "case_id": "synthetic", "status": "STOPPED",
             "stages": [], "warnings": ["controlled"], "errors": [],
             "metrics": {"cache_hits": 3}, "versions": {"parser": "v4"},
             "relation_aware_report": {"paper_evidence": []}}
    ledger.append("run", ev.RUN_COMPLETED, "test", {"status": "STOPPED", "run_snapshot": exact})
    rebuilt = rehydration.rehydrate(ledger, "run")
    for key, value in exact.items():
        assert rebuilt[key] == value
    assert rebuilt["hash_chain_valid"] is True


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_LEDGER_PATH", str(tmp_path / "store.sqlite3"))
    result = run_store.RunStore()
    yield result
    shutdown = getattr(result, "shutdown", None)
    if shutdown:
        shutdown()


def test_canonical_execution_does_not_read_frozen_source_index(store, monkeypatch):
    handle = run_store.RunHandle("run", "synthetic", "CREATED", "2026-10-07T00:00:00+00:00")
    observed = {}

    def execute(**kwargs):
        observed.update(kwargs)
        return mock.Mock(status="COMPLETED")

    monkeypatch.setattr(run_store.da, "load_source_unit_index", lambda: pytest.fail("historical index read"))
    monkeypatch.setattr(run_store.DocumentRuntime, "open", lambda: None)
    monkeypatch.setattr(run_store.orchestrator, "run_case", execute)
    monkeypatch.setattr(store, "_canonical_providers", lambda: {})
    store._execute(handle, "synthetic text")
    assert handle.status == "COMPLETED"
    assert observed["source_units_by_id"] == {}


@pytest.mark.parametrize("failure_location", ["cache", "provider", "pipeline"])
def test_unexpected_failure_is_durable_and_sanitized(store, monkeypatch, failure_location):
    secret = "Bearer secret-api-credential"

    def fail(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(run_store.DocumentRuntime, "open", fail if failure_location == "cache" else lambda: None)
    monkeypatch.setattr(store, "_canonical_providers", fail if failure_location == "provider" else lambda: {})
    monkeypatch.setattr(run_store.orchestrator, "run_case", fail)
    handle = store.start(case_id="synthetic", clinical_text="synthetic input")
    handle.thread.join(timeout=5)
    assert not handle.thread.is_alive()
    rebuilt = rehydration.rehydrate(EventLedger(store.ledger.path), handle.run_id)
    assert rebuilt is not None
    assert rebuilt["status"] == "FAILED"
    assert rebuilt["recovery_status"] == "COMPLETE"
    assert "LIVE_STAGE_FAILED" in rebuilt["reason_codes"]
    assert rebuilt["errors"]
    assert secret not in json.dumps(rebuilt)
    assert secret not in json.dumps(store.ledger.events(handle.run_id))
    assert secret not in json.dumps(handle.snapshot())


def test_abort_after_pipeline_progress_preserves_only_recorded_stage_results(store, monkeypatch):
    monkeypatch.setattr(run_store.DocumentRuntime, "open", lambda: None)
    monkeypatch.setattr(store, "_canonical_providers", lambda: {})

    def fail_after_stage(**kwargs):
        append_stage(kwargs["ledger"], kwargs["run_id"], "stage_1_case_input",
                     preview={"input_chars": 15})
        raise RuntimeError("private provider details")

    monkeypatch.setattr(run_store.orchestrator, "run_case", fail_after_stage)
    handle = store.start(case_id="synthetic", clinical_text="synthetic input")
    handle.thread.join(timeout=5)
    rebuilt = rehydration.rehydrate(store.ledger, handle.run_id)
    assert rebuilt["status"] == "FAILED"
    assert rebuilt["stages"][0]["output_preview"] == {"input_chars": 15}
    assert rebuilt["relation_aware_report"] is None
    assert rebuilt["hash_chain_valid"] is True
    assert rebuilt["stages"] == handle.snapshot()["stages"]


def test_list_is_paginated_by_creation_time_without_loading_event_chains(store, monkeypatch):
    for run_id in ("older", "middle", "newer"):
        store.ledger.append(run_id, ev.RUN_CREATED, "test", {"case_id": run_id})
    # Per-run sequence is not a global chronological identifier.
    for _ in range(10):
        store.ledger.append("older", ev.PIPELINE_WORK_PROGRESS, "test", {"units": 1})
    monkeypatch.setattr(store.ledger, "events", lambda _: pytest.fail("full event chain loaded for list"))
    assert [row["run_id"] for row in store.list_all(limit=1, offset=1)] == ["middle"]
    assert [row["run_id"] for row in store.list_all(limit=2)] == ["newer", "middle"]


def test_event_pages_read_incrementally_and_report_cursor(store, monkeypatch):
    for i in range(5):
        store.ledger.append("run", ev.PIPELINE_WORK_PROGRESS, "test", {"units": i})
    monkeypatch.setattr(store.ledger, "events", lambda _: pytest.fail("full event chain loaded for page"))
    page = store.events_page("run", after_sequence=2, limit=2)
    assert [event["sequence"] for event in page["events"]] == [3, 4]
    assert page["has_more"] is True
    assert page["next_sequence"] == 4
    final = store.events_page("run", after_sequence=4, limit=2)
    assert [event["sequence"] for event in final["events"]] == [5]
    assert final["has_more"] is False
    assert final["next_sequence"] == 5


def test_execution_admits_only_worker_and_queue_capacity(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEARCH_LEDGER_PATH", str(tmp_path / "bounded.sqlite3"))
    store = run_store.RunStore(max_workers=1, queue_capacity=1)
    active = threading.Event()
    release = threading.Event()

    def blocked(handle, text):
        active.set()
        release.wait(timeout=5)

    monkeypatch.setattr(store, "_execute", blocked)
    try:
        first = store.start(case_id="one", clinical_text="one")
        assert active.wait(timeout=2)
        second = store.start(case_id="two", clinical_text="two")
        assert store.is_running(first.run_id)
        assert store.is_running(second.run_id)
        with pytest.raises(run_store.RunStoreOverloaded):
            store.start(case_id="three", clinical_text="three")
        assert len(store.list_all()) == 2
        release.set()
        first.thread.join(timeout=2)
        second.thread.join(timeout=2)
        assert not first.thread.is_alive()
        assert not second.thread.is_alive()
    finally:
        release.set()
        store.shutdown()


def test_shutdown_drains_accepted_work_and_closes_admission(store, monkeypatch):
    active = threading.Event()
    release = threading.Event()
    shutdown_started = threading.Event()
    shutdown_finished = threading.Event()

    def blocked(handle, text):
        active.set()
        release.wait(timeout=5)

    def stop():
        shutdown_started.set()
        store.shutdown()
        shutdown_finished.set()

    monkeypatch.setattr(store, "_execute", blocked)
    handle = store.start(case_id="accepted", clinical_text="accepted")
    assert active.wait(timeout=2)
    waiter = threading.Thread(target=stop)
    waiter.start()
    try:
        assert shutdown_started.wait(timeout=2)
        assert not shutdown_finished.wait(timeout=0.05)
        assert handle.thread.is_alive()
    finally:
        release.set()
        waiter.join(timeout=2)
    assert shutdown_finished.is_set()
    assert not store.is_running(handle.run_id)
    with pytest.raises(run_store.RunStoreOverloaded):
        store.start(case_id="rejected", clinical_text="rejected")
    assert [row["case_id"] for row in store.list_all()] == ["accepted"]


@pytest.mark.parametrize("limit,cursor", [(0, 0), (501, 0), (2, -1), (True, 0)])
def test_event_pages_reject_unbounded_or_invalid_windows(store, limit, cursor):
    with pytest.raises(ValueError):
        store.events_page("run", after_sequence=cursor, limit=limit)
