from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.final_evaluation_harness.common.adapters.ablations import pre_retrieval_authority_bypass, quote_validator_bypass
from evaluation.final_evaluation_harness.common.adapters.canonical_runtime import CanonicalRuntimeAdapter
from evaluation.final_evaluation_harness.common.adapters.document_resolver import DocumentResolverAdapter
from evaluation.final_evaluation_harness.common.adapters.gemma import GemmaAdapter
from evaluation.final_evaluation_harness.common.adapters.narrative_verifier import NarrativeVerifierAdapter
from evaluation.final_evaluation_harness.common.adapters.narrator import NarratorAdapter
from evaluation.final_evaluation_harness.common.adapters.quote_validator import QuoteValidatorAdapter
from evaluation.final_evaluation_harness.common.adapters.selector import SelectorAdapter
from evaluation.final_evaluation_harness.common.adapters.ablations import narrative_verifier_bypass
from evaluation.final_evaluation_harness.common.arming import ExecutionDisarmed, ExecutionGate
from evaluation.final_evaluation_harness.common.guards import CallCounts, ForbiddenOperation, NetworkGuard
from evaluation.final_evaluation_harness.common.operational_executor import plan_operational_scenario
from evaluation.final_evaluation_harness.common.protocol_loader import load_a01_bindings, load_protocol


def test_canonical_runtime_delegates_once():
    calls = []
    assert CanonicalRuntimeAdapter(lambda q, **kw: calls.append((q, kw)) or 3).execute("q", x=1) == 3
    assert len(calls) == 1 and calls[0] == ("q", {"x": 1})


def test_selector_preserves_input_and_k():
    seen = {}
    source = [{"id": "s"}]
    result = SelectorAdapter(lambda units, **kw: seen.update(units=units, kw=kw) or [], 5).select(source)
    assert result == [] and seen == {"units": source, "kw": {"top_k": 5}}


def test_gemma_preserves_configuration():
    seen = []
    GemmaAdapter(lambda prompt, **kw: seen.append((prompt, kw)) or "ok", {"model": "frozen"}).call("p")
    assert seen[0][1]["configuration"] == {"model": "frozen"}


def test_narrator_preserves_configuration():
    seen = []
    NarratorAdapter(lambda dossier, **kw: seen.append((dossier, kw)) or "ok", {"model": "frozen"}).call("d")
    assert seen[0][1]["configuration"] == {"model": "frozen"}


def test_quote_validator_full_delegates():
    calls = []
    out = QuoteValidatorAdapter(lambda value: calls.append(value) or "validated").validate({"transport": "VALID", "schema": "VALID", "decision": "QUOTE"})
    assert out == "validated" and len(calls) == 1


def test_quote_validator_ablation_identity():
    out = QuoteValidatorAdapter(None, identity_semantic=True).validate({"transport": "VALID", "schema": "VALID", "decision": "QUOTE"})
    assert out["semantic_validation"] == "IDENTITY_ACCEPTED"


def test_quote_validator_preserves_abstain():
    out = QuoteValidatorAdapter(None, identity_semantic=True).validate({"transport": "VALID", "schema": "VALID", "decision": "ABSTAIN"})
    assert out["decision"] == "ABSTAIN"


def test_quote_validator_preserves_schema_failure():
    out = QuoteValidatorAdapter(None, identity_semantic=True).validate({"transport": "VALID", "schema": "INVALID"})
    assert out["schema"] == "INVALID"


def test_narrative_verifier_full_calls_once():
    calls = []
    NarrativeVerifierAdapter(lambda value: calls.append(value) or "verified").verify({"transport": "VALID"})
    assert len(calls) == 1


def test_narrative_verifier_ablation_zero_calls():
    NarrativeVerifierAdapter(None, bypass=True).verify({"transport": "VALID"})


def test_narrative_adapter_delegate():
    calls = []
    NarrativeVerifierAdapter(lambda value: calls.append(value) or True).verify({"transport": "VALID"})
    assert len(calls) == 1


def test_document_resolver_transparent_output():
    args = []
    output, elapsed = DocumentResolverAdapter(lambda *a, **kw: args.append((a, kw)) or {"ok": True}).resolve("pmid")
    assert output == {"ok": True} and args == [(('pmid',), {})] and elapsed >= 0


def test_document_resolver_transparent_exception():
    def fail(*args, **kwargs): raise KeyError("same")
    with pytest.raises(KeyError, match="same"): DocumentResolverAdapter(fail).resolve("pmid")


def test_network_prohibited_provider_zero_calls():
    calls = []
    with pytest.raises(ForbiddenOperation): DocumentResolverAdapter(lambda value: calls.append(value), NetworkGuard("PROHIBITED")).resolve("x")
    assert calls == []


def test_network_allowed_delegate():
    calls = []
    DocumentResolverAdapter(lambda value: calls.append(value) or value, NetworkGuard("CANONICAL_RUNTIME_POLICY")).resolve("x")
    assert calls == ["x"]


def test_ablation_a_skips_boundary_and_retrieves_once():
    calls = []
    assert pre_retrieval_authority_bypass("parser", lambda value: calls.append(value) or "retrieved") == "retrieved"
    assert calls == ["parser"]


def test_ablation_c_transport_unchanged():
    out = quote_validator_bypass({"transport": "FAILED", "schema": "INVALID"})
    assert out["transport"] == "FAILED"


def test_ablation_d_marks_offline():
    assert narrative_verifier_bypass({"transport": "VALID"})["presentation"] == "PRESENTED_IN_OFFLINE_ABLATION"


def test_operational_ids_loaded_dynamically():
    protocol = load_protocol(); first = load_a01_bindings(protocol)["scenarios"][0]["scenario_id"]
    assert plan_operational_scenario(protocol, first)["scenario_id"] == first


def test_operational_runtime_adapter_separates_scenario_metadata_from_pipeline_kwargs():
    protocol = load_protocol()
    calls = []

    class Pipeline:
        def run(self, query, *, retrieval_backend=None):
            calls.append((query, retrieval_backend))
            return {"status": "CONTROLLED_FIXTURE"}

    from evaluation.final_evaluation_harness.common.adapters.canonical_runtime import CanonicalRuntimeAdapter
    from evaluation.final_evaluation_harness.common.operational_executor import execute_operational_scenario
    context = type("Context", (), {
        "canonical_runtime": CanonicalRuntimeAdapter.from_runtime(Pipeline()),
    })()
    result = execute_operational_scenario(protocol, "A_cache_hit", context)
    assert result["scenario_id"] == "A_cache_hit"
    assert result["native_outcome"] == {"status": "CONTROLLED_FIXTURE"}
    assert len(calls) == 1
    assert calls[0][1] is None
    assert calls[0][0]["scenario_id"] == "A_cache_hit"


def test_latency_pair_loaded_from_contract():
    protocol = load_protocol(); pair = protocol.latency["same_document_cache_latency_pair"]
    assert pair["case_id"] == "GCA-0000980ba01970f893f8e4d7" and pair["document_id"] == "pmid:15705718"


def test_execution_gate_disarmed():
    with pytest.raises(ExecutionDisarmed): ExecutionGate().require_armed()
