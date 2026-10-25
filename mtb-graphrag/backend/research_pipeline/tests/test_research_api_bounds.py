"""HTTP contracts and bounded event reads without provider or frozen data access."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import research_routes
from backend.research_pipeline.run_store import RunStoreOverloaded


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("VERIFIABLE_PIPELINE_RESEARCH_ENABLED", "1")
    store = Mock()
    store.has_run.return_value = True
    store.is_running.return_value = False
    store.snapshot.side_effect = AssertionError("event routes must not rehydrate snapshots")
    store.ledger.events.side_effect = AssertionError("event routes must use bounded reads")
    store.verify_chain.return_value = True
    monkeypatch.setattr(research_routes, "get_store", lambda: store)
    app = FastAPI()
    app.include_router(research_routes.router)
    return TestClient(app), store


def event(sequence):
    return {"event_id": f"e{sequence}", "sequence": sequence,
            "event_type": "STAGE_COMPLETED", "created_at": "2026-10-08T10:00:00Z",
            "actor": "runtime", "payload": {"stage_id": "stage", "artifact": "large"}}


def test_event_page_uses_database_cursor_and_preserves_integrity_contract(api):
    client, store = api
    store.events_page.return_value = {"events": [event(8), event(9)], "next_sequence": 9, "has_more": True}
    response = client.get("/runs/run/events?after_sequence=7&limit=2&compact=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next_after_sequence"] == 9 and body["has_more"] is True
    assert body["hash_chain_valid"] is True and body["append_only"] is True
    assert [row["sequence"] for row in body["events"]] == [8, 9]
    assert "artifact" not in body["events"][0]["payload"]
    store.events_page.assert_called_once_with("run", after_sequence=7, limit=2)
    store.verify_chain.assert_called_once_with("run")


def test_empty_event_page_keeps_cursor_and_failed_integrity(api):
    client, store = api
    store.events_page.return_value = {"events": [], "next_sequence": 19, "has_more": False}
    store.verify_chain.return_value = False
    response = client.get("/runs/run/events?after_sequence=19")
    assert response.status_code == 200
    assert response.json()["next_after_sequence"] == 19
    assert response.json()["hash_chain_valid"] is False


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "after_sequence=-1", "limit=abc"])
def test_event_bounds_reject_invalid_requests_before_store_reads(api, query):
    client, store = api
    assert client.get(f"/runs/run/events?{query}").status_code == 422
    store.events_page.assert_not_called()


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1", "offset=abc"])
def test_run_listing_bounds_reject_invalid_requests(api, query):
    client, store = api
    assert client.get(f"/runs?{query}").status_code == 422
    store.list_all.assert_not_called()


def test_run_listing_passes_explicit_and_default_pagination(api):
    client, store = api
    store.list_all.return_value = [{"run_id": "archived"}]
    assert client.get("/runs?limit=2&offset=3").json() == {"runs": [{"run_id": "archived"}]}
    store.list_all.assert_called_once_with(limit=2, offset=3)
    store.list_all.reset_mock()
    assert client.get("/runs").status_code == 200
    store.list_all.assert_called_once_with(limit=50, offset=0)


def test_sse_drains_bounded_pages_immediately_and_resumes(api, monkeypatch):
    client, store = api
    store.events_page.side_effect = [
        {"events": [event(8), event(9)], "next_sequence": 9, "has_more": True},
        {"events": [event(10)], "next_sequence": 10, "has_more": False},
        {"events": [], "next_sequence": 10, "has_more": False},
    ]
    monkeypatch.setattr(research_routes.time, "sleep", Mock(side_effect=AssertionError("completed streams must drain immediately")))
    response = client.get("/runs/run/stream?compact=true", headers={"Last-Event-ID": "7"})
    assert response.status_code == 200, response.text
    assert [line for line in response.text.splitlines() if line.startswith("id:")] == ["id: 8", "id: 9", "id: 10"]
    assert "artifact" not in response.text
    assert [call.kwargs["after_sequence"] for call in store.events_page.call_args_list] == [7, 9, 10]
    assert all(1 <= call.kwargs["limit"] <= 500 for call in store.events_page.call_args_list)
    store.verify_chain.assert_not_called()


def test_sse_reads_final_event_when_worker_finishes_during_empty_page_read(api):
    client, store = api
    # The terminal append can occur after the first SQL read, immediately
    # before the worker is observed finished. A second read must capture it.
    store.is_running.return_value = True
    pages = iter([
        {"events": [], "next_sequence": 0, "has_more": False},
        {"events": [event(1)], "next_sequence": 1, "has_more": False},
        {"events": [], "next_sequence": 1, "has_more": False},
    ])

    def page(*args, **kwargs):
        store.is_running.return_value = False
        return next(pages)

    store.events_page.side_effect = page
    response = client.get("/runs/run/stream")
    assert response.status_code == 200
    assert "id: 1\n" in response.text


@pytest.mark.parametrize("last_id", ["-4", "invalid"])
def test_sse_invalid_resume_header_starts_at_zero(api, last_id):
    client, store = api
    store.events_page.return_value = {"events": [], "next_sequence": 0, "has_more": False}
    assert client.get("/runs/run/stream", headers={"Last-Event-ID": last_id}).status_code == 200
    assert store.events_page.call_args.kwargs["after_sequence"] == 0


@pytest.mark.parametrize("path", ["events", "stream"])
def test_event_routes_check_existence_without_snapshot(api, path):
    client, store = api
    store.has_run.return_value = False
    assert client.get(f"/runs/missing/{path}").status_code == 404
    store.events_page.assert_not_called()


def test_admission_overload_returns_retryable_503(api, monkeypatch):
    client, store = api
    monkeypatch.setattr(research_routes.llm_config, "resolve_endpoint", lambda: ("model.invalid", "key"))
    store.start.side_effect = RunStoreOverloaded("capacity is full")
    response = client.post("/runs", json={"case_id": "case", "clinical_text": "clinical text"})
    assert response.status_code == 503
    assert int(response.headers["retry-after"]) > 0
    assert response.json()["detail"] == "capacity is full"


def test_oversized_case_is_rejected_before_admission(api):
    client, store = api
    assert client.post("/runs", json={"clinical_text": "x" * 100_001}).status_code == 422
    store.start.assert_not_called()


def test_legacy_events_are_projected_without_publishing_private_source_text(api):
    client, store = api
    old_event = event(1)
    old_event["payload"] = {"quote": "excerpt", "nested": {"source_unit_text": "private sentinel"}}
    store.events_page.return_value = {"events": [old_event], "next_sequence": 1, "has_more": False}
    response = client.get("/runs/run/events")
    assert "private sentinel" not in response.text
    assert response.json()["events"][0]["payload"]["quote"] == "excerpt"
    assert len(response.json()["events"][0]["payload"]["nested"]["source_unit_sha256"]) == 64


def test_public_response_models_preserve_absent_fields_and_extension_data(api):
    client, store = api
    store.snapshot.side_effect = None
    snapshot = {"run_id": "run", "case_id": "case", "status": "STOPPED", "stages": [], "future_metadata": {"provenance": "kept"}}
    store.snapshot.return_value = snapshot
    response = client.get("/runs/run")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert {key: payload[key] for key in snapshot} == snapshot
    assert payload['llm_calls'] == 0
    assert payload['metrics']['operational']['computed_by'] == 'backend_operational_projection/1.0'
    schemas = client.get("/openapi.json").json()["paths"]
    expected = {("/runs", "post"): "CreatedRunResponse", ("/runs/{run_id}", "get"): "PublicPipelineRun",
                ("/runs/{run_id}/events", "get"): "EventPage", ("/runs/{run_id}/stages/{stage_id}", "get"): "StageResponse",
                ("/runs/{run_id}/dossier", "get"): "DossierResponse"}
    for (path, method), name in expected.items():
        status = "201" if method == "post" else "200"
        assert schemas[path][method]["responses"][status]["content"]["application/json"]["schema"]["$ref"].endswith(f"/{name}")


def test_public_run_contract_rejects_invalid_authoritative_status(api):
    client, store = api
    store.snapshot.side_effect = None
    store.snapshot.return_value = {"run_id": "run", "case_id": "case", "status": "UNSUPPORTED", "stages": []}
    response = TestClient(client.app, raise_server_exceptions=False).get("/runs/run")
    assert response.status_code == 500
