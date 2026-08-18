import hashlib
import json
from pathlib import Path

from evaluation.final_evaluation_harness.common.identities import evaluation_id
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import build_full_plan, execution_plan_sha256


def test_protocol_171_seal_is_bound_and_deterministic(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7.1")
    protocol = load_protocol()
    plans = build_full_plan(protocol)
    plan_sha = execution_plan_sha256(plans)
    seal = json.loads((protocol.root / "seal_manifest.json").read_text(encoding="utf-8"))
    assert protocol.manifest["protocol_version"] == "1.7.1"
    assert protocol.manifest["evaluation_boundary"] == "FINAL_EVALUATION_1_7_1"
    assert len(plans) == 222
    assert plan_sha == protocol.manifest["sealed_plan_sha256"]
    assert evaluation_id(protocol, protocol.hashes["runtime_commit"]) == seal["evaluation_id"]
    assert seal["real_evaluation_units_executed"] == 0


def test_protocol_171_frozen_identity_is_hash_bound(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7.1")
    protocol = load_protocol()
    manifest = protocol.root / "seal_manifest.json"
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == (protocol.root / "seal_manifest.sha256").read_text(encoding="utf-8").split()[0]
    assert protocol.manifest["frozen_document_manifest_sha256"] == "56b30e59ede6f36493f061a3c02bc46f30741f7f2df3df290293a6efebceefc9"
    assert protocol.manifest["document_network_allowed"] is False


def test_protocol_171_output_namespace_has_no_prior_campaign(monkeypatch):
    monkeypatch.setenv("MTB_EVALUATION_PROTOCOL_VERSION", "1.7.1")
    protocol = load_protocol()
    output = Path(protocol.root.parents[1]) / protocol.manifest["output_directory"]
    assert not output.exists()
