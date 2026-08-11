import json
from pathlib import Path

import pytest

from evaluation.final_evaluation_harness.common.model_identity import GenerationIdentityError, validate_execution_environment, validate_prompt_hashes
from evaluation.final_evaluation_harness.common.provider_snapshot import ProviderMetadataMismatch, collect_snapshot, compare_snapshots, parse_metadata, validate_metadata
from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.runner import build_full_plan, build_plan, execution_plan_sha256


def env(**changes):
    value={"RESEARCH_PIPELINE_MODEL":"gemma4:31b-cloud","RESEARCH_PIPELINE_LLM_BASE_URL":"","OLLAMA_BASE_URL":"","RESEARCH_PIPELINE_LLM_TIMEOUT":"","OLLAMA_API_KEY":"present"}
    value.update(changes); return value


@pytest.mark.parametrize("alias", ["gemma4:cloud", "other:model", ""])
def test_non_v13_alias_rejected(alias):
    with pytest.raises(GenerationIdentityError): validate_execution_environment(env(RESEARCH_PIPELINE_MODEL=alias))


@pytest.mark.parametrize("key,value", [("RESEARCH_PIPELINE_LLM_BASE_URL","https://other.example"),("OLLAMA_BASE_URL","https://other.example"),("RESEARCH_PIPELINE_LLM_TIMEOUT","61")])
def test_environment_semantic_override_rejected(key,value):
    with pytest.raises(GenerationIdentityError): validate_execution_environment(env(**{key:value}))


@pytest.mark.parametrize("key", ["case_context_parser", "paper_context_enricher", "dossier_narrator"])
def test_generation_role_is_locked(key):
    roles=validate_execution_environment(env())["roles"]
    assert roles[key]["model"]=="gemma4:31b-cloud" and roles[key]["temperature"]==0 and roles[key]["top_p"]==1 and roles[key]["seed_policy"]=="run_index" and roles[key]["timeout_seconds"]==60


def test_prompt_hashes_match_local_sources(): validate_prompt_hashes()


def metadata(**changes):
    details={"family":"gemma4","parameter_size":"32682372656","quantization_level":"BF16"}; info={"gemma4.context_length":262144}; details.update(changes.pop("details",{})); info.update(changes.pop("model_info",{})); return {"details":details,"model_info":info,"modified_at":changes.pop("modified_at","t")}


def test_metadata_contract_passes(): validate_metadata(parse_metadata("gemma4:31b-cloud",metadata()), {"model_alias":"gemma4:31b-cloud","family":"gemma4","parameter_size":"32682372656","quantization":"BF16","context_length":262144})


def test_metadata_snapshot_is_injected_and_metadata_only():
    calls=[]
    snapshot=collect_snapshot(lambda alias: calls.append(alias) or {**metadata(), "api_key": "DO_NOT_PERSIST"}, "gemma4:31b-cloud")
    assert calls == ["gemma4:31b-cloud"]
    assert snapshot["parsed_identity_fields"]["model_alias"] == "gemma4:31b-cloud"
    assert "secret" not in json.dumps(snapshot, sort_keys=True).lower()


@pytest.mark.parametrize("changes", [{"details":{"family":"other"}},{"details":{"parameter_size":"1"}},{"details":{"quantization_level":"Q4"}},{"model_info":{"gemma4.context_length":1}}])
def test_metadata_identity_mismatch_is_fail_closed(changes):
    with pytest.raises(ProviderMetadataMismatch): validate_metadata(parse_metadata("gemma4:31b-cloud",metadata(**changes)), {"model_alias":"gemma4:31b-cloud","family":"gemma4","parameter_size":"32682372656","quantization":"BF16","context_length":262144})


@pytest.mark.parametrize("field,value", [("family","other"),("parameter_size","1"),("quantization","Q4"),("context_length",1)])
def test_provider_drift_detected(field,value):
    pre=parse_metadata("gemma4:31b-cloud",metadata()); post=json.loads(json.dumps(pre)); post["parsed_identity_fields"][field]=value
    assert field in compare_snapshots(pre,post)


def test_modified_at_alone_is_not_identity_drift():
    pre=parse_metadata("gemma4:31b-cloud",metadata(modified_at="a")); post=parse_metadata("gemma4:31b-cloud",metadata(modified_at="b")); assert compare_snapshots(pre,post)==[]


def test_plan_counts_and_order():
    p=load_protocol(); plans=build_full_plan(p)
    assert len(plans)==222 and [x.plan_index for x in plans]==list(range(1,223)); assert [x.rq for x in plans[:1]]==["RQ1"]


def test_plan_sha_is_deterministic():
    p=load_protocol(); a=build_plan("rq2",p); assert execution_plan_sha256(a)==execution_plan_sha256(a)


def test_plan_metadata_required_fields():
    p=load_protocol(); plan=build_plan("rq4",p)[0]
    for field in ("execution_class","canonical_runtime_requirement","network_policy","network_expectation","cache_policy","dataset_hashes","gold_access","terminal_expectation"): assert getattr(plan,field)


def test_gold_is_prohibited_during_heldout():
    p=load_protocol(); assert {x.gold_access for x in build_plan("rq4",p)}=={"PROHIBITED"}


def test_s01_and_dataset_hashes_present_for_rq2():
    p=load_protocol(); assert all("s01_raw" in x.dataset_hashes and "s01_package" in x.dataset_hashes for x in build_plan("rq2",p))


def test_disarmed_gate_and_no_result_directory():
    from evaluation.final_evaluation_harness.common.arming import ExecutionGate
    assert ExecutionGate.status=="DISARMED" and not (Path("evaluation/final_evaluation").exists())


def test_future_start_plan_is_serialized_without_arming():
    from evaluation.final_evaluation_harness.start import materialize_execution_plan
    rows, digest = materialize_execution_plan()
    assert len(rows) == 222 and rows[0]["plan_index"] == 1 and rows[-1]["plan_index"] == 222
    assert len(digest) == 64 and not Path("evaluation/final_evaluation").exists()
