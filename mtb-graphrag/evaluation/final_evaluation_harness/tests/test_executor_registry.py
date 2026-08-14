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
    assert {name for name in by.values() if name.startswith("Narrative")} == {"NarrativeHostileExecutor", "NarrativeControlExecutor"}
    assert any(name == "OperationalExecutor" for name in by.values())
    assert any(name == "LatencyExecutor" for name in by.values())


def test_required_components_are_present_in_each_binding():
    protocol = load_protocol()
    plan = build_full_plan(protocol)
    registry = ExecutionAdapterRegistry(protocol)
    fields = {
        "canonical_runtime_requirement": "canonical_runtime",
        "selector_requirement": "selector",
        "casecontext_parser_requirement": "casecontext_parser",
        "gemma_requirement": "gemma",
        "narrator_requirement": "narrator",
        "quote_validator_requirement": "quote_validator",
        "narrative_verifier_requirement": "narrative_verifier",
    }
    for unit in plan:
        binding = registry.resolve(unit)
        for field, adapter_name in fields.items():
            if getattr(unit, field) == "REQUIRED":
                assert adapter_name in binding.adapter_names, (unit.plan_index, field)


def test_latency_binding_routes_only_to_document_resolver():
    protocol = load_protocol()
    unit = next(unit for unit in build_full_plan(protocol) if unit.rq == "LATENCY")
    binding = ExecutionAdapterRegistry(protocol).resolve(unit)
    assert binding.name == "LatencyExecutor"
    assert binding.adapter_names == ("document_resolver",)
