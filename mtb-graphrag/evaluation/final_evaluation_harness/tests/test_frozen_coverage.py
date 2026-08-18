from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

from evaluation.final_evaluation_harness.common.frozen_coverage import build_coverage_report, require_complete_coverage
from evaluation.final_evaluation_harness.common.execution import ProductionAdapterFactory


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_missing_document_is_detected_before_execution(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    index = tmp_path / "source_units.jsonl"
    payload = tmp_path / "doc.xml"
    payload.write_text("document", encoding="utf-8")
    _write_jsonl(manifest, [{
        "document_id": "pmid:1", "local_cache_path": "doc.xml",
        "content_hash": hashlib.sha256(payload.read_bytes()).hexdigest(),
    }])
    _write_jsonl(index, [{"document_id": "pmid:1", "source_unit_id": "su-1"}])
    plan = [SimpleNamespace(run_id="run_1", case_id="GCA-1|pmid:2", execution_class="SELECTOR_ONLY")]

    report = build_coverage_report(plan, manifest_path=manifest, source_unit_index_path=index, payload_root=tmp_path)
    assert report.total_planned_units == 1
    assert report.units_with_zero_document_coverage == 1
    assert "pmid:2" in report.missing_document_identifiers


def test_payload_hash_and_source_unit_binding_are_verified(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    index = tmp_path / "source_units.jsonl"
    payload = tmp_path / "doc.xml"
    payload.write_text("document", encoding="utf-8")
    _write_jsonl(manifest, [{
        "document_id": "pmid:1", "local_cache_path": "doc.xml", "content_hash": "wrong",
    }])
    _write_jsonl(index, [])
    plan = [SimpleNamespace(run_id="run_1", case_id="GCA-1|pmid:1", execution_class="SELECTOR_ONLY")]

    report = build_coverage_report(plan, manifest_path=manifest, source_unit_index_path=index, payload_root=tmp_path)
    assert report.units_with_zero_document_coverage == 1
    assert any("PAYLOAD_SHA256_MISMATCH" in item for item in report.rows[0].missing)
    assert any("SOURCE_UNITS_MISSING" in item for item in report.rows[0].missing)


def test_non_document_unit_is_explicitly_not_required(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    index = tmp_path / "source_units.jsonl"
    _write_jsonl(manifest, [])
    _write_jsonl(index, [])
    plan = [SimpleNamespace(run_id="run_1", case_id="GCA_REPOSITORY_2_0_46864", execution_class="DETERMINISTIC_ONLY")]

    report = build_coverage_report(plan, manifest_path=manifest, source_unit_index_path=index, payload_root=tmp_path)
    assert report.complete
    require_complete_coverage(report)


def test_document_runtime_uses_manifest_bound_by_protocol(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_jsonl(manifest, [{"document_id": "pmid:1", "local_cache_path": "doc.xml"}])
    protocol = SimpleNamespace(root=tmp_path, manifest={
        "frozen_document_manifest_path": "manifest.jsonl",
        "frozen_document_cache_root": "cache",
        "frozen_document_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    })

    runtime = ProductionAdapterFactory.document_runtime(protocol)
    assert runtime.manifest_hash == protocol.manifest["frozen_document_manifest_sha256"]
    assert runtime.network_enabled is False
    assert set(runtime.manifest_by_document_id) == {"pmid:1"}


def test_semantic_document_obligation_uses_protocol_counts_and_whole_gca_closure(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    index = tmp_path / "source_units.jsonl"
    _write_jsonl(manifest, [{"document_id": "pmid:1", "frozen_availability": "UNAVAILABLE_FROZEN"}])
    _write_jsonl(index, [])
    plan = [SimpleNamespace(run_id=f"run_{i}", case_id=f"CASE-{i}", execution_class="CANONICAL_RUNTIME") for i in range(4)]

    report = build_coverage_report(
        plan,
        manifest_path=manifest,
        source_unit_index_path=index,
        payload_root=tmp_path,
        semantic_obligation={"required": 1, "conditional": 1, "not_required": 2},
        conditional_closure_complete=True,
    )

    assert report.semantic_obligation == {"required": 1, "conditional": 1, "not_required": 2}
    assert report.semantic_coverage == {
        "required_covered": 1,
        "conditional_covered": 1,
        "not_required_valid": 2,
    }
    assert report.complete
    require_complete_coverage(report)


def test_source_unit_index_nested_document_id_is_supported(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    index = tmp_path / "source_units.jsonl"
    payload = tmp_path / "doc.xml"
    payload.write_text("document", encoding="utf-8")
    payload_hash = hashlib.sha256(payload.read_bytes()).hexdigest()
    _write_jsonl(manifest, [{
        "document_id": "pmid:1", "local_cache_path": "doc.xml", "content_hash": payload_hash,
        "frozen_availability": "PAYLOAD_AVAILABLE",
    }])
    _write_jsonl(index, [{"source_unit": {"document_id": "pmid:1", "source_unit_id": "su-1"}}])
    plan = [SimpleNamespace(run_id="run_1", case_id="GCA-1|pmid:1", execution_class="SELECTOR_ONLY")]

    report = build_coverage_report(plan, manifest_path=manifest, source_unit_index_path=index, payload_root=tmp_path)

    assert report.rows[0].coverage == "COMPLETE"
