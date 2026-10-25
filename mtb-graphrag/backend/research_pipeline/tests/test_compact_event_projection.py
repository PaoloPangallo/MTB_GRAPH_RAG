from backend.api.research_routes import _public_event
from backend.api import research_routes


def test_work_counters_survive_compact_sse_projection():
    payload = {"stage_id": "stage_9_paper_context_enricher", "phase": "READER",
               "completed_candidates": 4, "total_candidates": 30, "reader_calls": 8,
               "reader_reuses": 2, "candidate_id": "c", "document_id": "nct:NCT12345678"}
    event = {"event_id": "e", "sequence": 3, "created_at": "now", "actor": "test",
             "event_type": "PIPELINE_WORK_PROGRESS", "payload": {**payload, "output_preview": {"large": "artifact"}}}
    projected = _public_event(event, compact=True)
    assert all(projected["payload"][key] == value for key, value in payload.items())
    assert "output_preview" not in projected["payload"]


def test_reader_metrics_count_model_calls_not_reused_proposals(monkeypatch):
    snapshot = {"llm_calls": 1, "stages": [{"stage_id": "stage_9_paper_context_enricher",
        "output_preview": {"calls": [{"model_call_count": 1}, {"model_call_count": 0, "reader_response_reused": True}]},
        "duration_ms": 0, "warnings": [], "errors": []}]}
    monkeypatch.setattr(research_routes, "_snapshot_or_404", lambda run_id: snapshot)
    metrics = research_routes.get_metrics("r")
    assert metrics["llm_calls"] == 1
    assert metrics["reused_reader_responses"] == 1


def test_compact_event_preserves_progress_without_copying_large_artifacts():
    event = {
        "event_id": "e1", "sequence": 1, "event_type": "STAGE_COMPLETED",
        "created_at": "now", "actor": "test", "payload_hash": "hash",
        "payload": {
            "stage_id": "stage_5_kg_retrieval", "stage_type": "KG_RETRIEVAL",
            "status": "SUCCEEDED", "producer": {"kind": "DETERMINISTIC"},
            "output_preview": {"candidates": ["large"]}, "reason_codes": [],
        },
    }
    full = _public_event(event)
    compact = _public_event(event, compact=True)
    assert full["payload"]["output_preview"] == {"candidates": ["large"]}
    assert "output_preview" not in compact["payload"]
    assert compact["payload"]["status"] == "SUCCEEDED"
    for key in ("event_id", "sequence", "stage_id", "payload_hash", "producer"):
        assert compact[key] == full[key]
    assert event["payload"]["output_preview"] == {"candidates": ["large"]}


def test_compact_snapshot_preserves_stage_status_and_dossier_availability(monkeypatch):
    snapshot = {"run_id": "r1", "relation_aware_report": {}, "stages": [
        {"stage_id": "s1", "status": "SUCCEEDED", "output_preview": {"large": "artifact"}, "input_preview": {"input": "artifact"}}
    ]}
    monkeypatch.setattr(research_routes, "_snapshot_or_404", lambda run_id: snapshot)
    compact = research_routes.get_run("r1", compact=True)
    assert compact["dossier_available"] is True
    assert compact["relation_aware_report"] is None
    assert compact["stages"][0]["status"] == "SUCCEEDED"
    assert compact["stages"][0]["output_preview"] == {}
    assert research_routes.get_run("r1") is snapshot
    assert snapshot["stages"][0]["output_preview"] == {"large": "artifact"}
