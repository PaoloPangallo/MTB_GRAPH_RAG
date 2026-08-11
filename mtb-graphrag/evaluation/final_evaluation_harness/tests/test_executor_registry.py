from evaluation.final_evaluation_harness.common.protocol_loader import load_protocol
from evaluation.final_evaluation_harness.common.registry import ExecutionAdapterRegistry, binding_manifest_sha256
from evaluation.final_evaluation_harness.common.runner import build_full_plan


def test_real_frozen_plan_has_one_binding_per_unit():
    protocol = load_protocol()
    plan = build_full_plan(protocol)
    registry = ExecutionAdapterRegistry(protocol)
    bindings = [registry.resolve(unit) for unit in plan]
    assert len(bindings) == 222
    assert len({binding.name for binding in bindings}) >= 8
    assert binding_manifest_sha256(plan, registry) == binding_manifest_sha256(plan, registry)


def test_representative_executor_names():
    protocol = load_protocol()
    registry = ExecutionAdapterRegistry(protocol)
    plan = build_full_plan(protocol)
    by = {(unit.rq, unit.execution_class, unit.arm, unit.testbed): registry.resolve(unit).name for unit in plan}
    assert any(name == "RQ1DeterministicExecutor" for name in by.values())
    assert any(name == "RQ2SelectorExecutor" for name in by.values())
    assert any(name == "RQ2GemmaExecutor" for name in by.values())
    assert any(name == "RQ3FullSystemExecutor" for name in by.values())
    assert {name for name in by.values() if "Ablation" in name} == {"RQ3AblationAExecutor", "RQ3AblationBExecutor", "RQ3AblationCExecutor", "RQ3AblationDExecutor"}
    assert {name for name in by.values() if name.startswith("RQ4")} == {"RQ4DevelopmentExecutor", "RQ4HeldoutExecutor"}
    assert any(name == "NarrativeExecutor" for name in by.values())
    assert any(name == "OperationalExecutor" for name in by.values())
    assert any(name == "LatencyExecutor" for name in by.values())
