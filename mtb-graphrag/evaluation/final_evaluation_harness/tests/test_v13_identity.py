import hashlib

import pytest

from evaluation.final_evaluation_harness.common.model_identity import (
    GenerationIdentityError,
    validate_execution_environment,
)
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.provider_snapshot import (
    ProviderMetadataMismatch,
    compare_snapshots,
    parse_metadata,
)
from evaluation.final_evaluation_harness.common.runner import build_plan


def _env(**updates):
    base = {
        "RESEARCH_PIPELINE_MODEL": "gemma4:31b-cloud",
        "RESEARCH_PIPELINE_LLM_BASE_URL": "",
        "OLLAMA_BASE_URL": "",
        "RESEARCH_PIPELINE_LLM_TIMEOUT": "",
        "OLLAMA_API_KEY": "configured-but-never-read",
    }
    base.update(updates)
    return base


def test_protocol_loader_accepts_frozen_v14():
    protocol = load_protocol()
    assert protocol.manifest["protocol_version"] == "1.4"
    assert protocol.seal["protocol_1_4_sha256"] == "6aa8927e47181dc5b5b4fbf8e6390372f5de9e26d47a3a3bf86e7bd6f25aea3e"
    assert protocol.hashes["inherited_A01_sha256"] == "48c60928eafad33c4e2f8008db58fa543e3c17c04a8a73733f471c7c2bdacdcf"


def test_protocol_loader_uses_v14_not_parent_as_execution_source(monkeypatch):
    monkeypatch.setenv("FINAL_PROTOCOL_VERSION", "1.2")
    assert load_protocol().manifest["protocol_version"] == "1.4"


def test_model_identity_accepts_exact_alias_and_rejects_historical_alias():
    assert validate_execution_environment(_env())["model"] == "gemma4:31b-cloud"
    with pytest.raises(GenerationIdentityError, match="MODEL_IDENTITY_MISMATCH"):
        validate_execution_environment(_env(RESEARCH_PIPELINE_MODEL="gemma4:cloud"))


def test_generation_identity_rejects_endpoint_and_missing_credentials():
    with pytest.raises(GenerationIdentityError):
        validate_execution_environment(_env(RESEARCH_PIPELINE_LLM_BASE_URL="https://other.example"))
    with pytest.raises(GenerationIdentityError):
        validate_execution_environment(_env(OLLAMA_API_KEY=""))


def test_provider_metadata_matches_and_drift_is_detected():
    raw = {"details": {"family": "gemma4", "parameter_size": "32682372656", "quantization_level": "BF16"}, "model_info": {"gemma4.context_length": 262144}, "modified_at": "t"}
    first = parse_metadata("gemma4:31b-cloud", raw)
    assert first["raw_sha256"] == hashlib.sha256(__import__("json").dumps(raw, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert compare_snapshots(first, parse_metadata("gemma4:31b-cloud", raw)) == []
    changed = dict(raw, details=dict(raw["details"], parameter_size="1"))
    assert "parameter_size" in compare_snapshots(first, parse_metadata("gemma4:31b-cloud", changed))


def test_plan_units_expose_v13_audit_metadata_and_remain_222():
    protocol = load_protocol()
    plans = [p for kind in ("rq1", "rq2", "rq3", "rq4", "narrative", "operational", "reliability", "latency") for p in build_plan(kind, protocol)]
    assert len(plans) == 222
    assert all(p.dataset_hashes and p.network_policy and p.gold_access for p in plans)
    assert all(p.execution_class for p in plans)
