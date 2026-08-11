"""Production execution context and transport-only scientific result wrapper."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .adapters.canonical_runtime import CanonicalRuntimeAdapter
from .adapters.document_resolver import DocumentResolverAdapter
from .adapters.gemma import GemmaAdapter
from .adapters.narrative_verifier import NarrativeVerifierAdapter
from .adapters.narrator import NarratorAdapter
from .adapters.quote_validator import QuoteValidatorAdapter
from .adapters.selector import SelectorAdapter


class ProductionUnitDispatcher:
    """Real dispatch boundary; missing scientific input bindings fail closed."""

    def execute(self, planned_unit: Any, context: "RealExecutionContext", executor: Any) -> ScientificExecutionResult:
        context.assert_production_guards(planned_unit, executor)
        method = getattr(self, f"_{executor.name}", None)
        if method is None:
            raise RuntimeError(f"REAL_EXECUTION_EXECUTOR_NOT_IMPLEMENTED:{executor.name}")
        return ScientificExecutionResult.from_native(method(planned_unit, context))

    def coverage(self, plan: list[Any], registry: Any) -> tuple[int, list[str]]:
        """Static callable coverage; no executor or adapter is invoked."""
        missing: list[str] = []
        for unit in plan:
            bound = registry.resolve(unit)
            if not callable(getattr(self, f"_{bound.name}", None)):
                missing.append(bound.name)
        return len(plan) - len(missing), missing

    def _RQ4DevelopmentExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context)

    def _RQ4HeldoutExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context, gold_access=False)

    def _RQ3FullSystemExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context)

    def _RQ3AblationAExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context, ablation="A")

    def _RQ3AblationBExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context, ablation="B")

    def _RQ3AblationCExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context, ablation="C")

    def _RQ3AblationDExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context, ablation="D")

    def _run_case(self, unit: Any, context: "RealExecutionContext", *, gold_access: bool = True, ablation: str | None = None) -> Any:
        if ablation in {"B", "C", "D"}:
            # These ablations require distinct frozen stage wiring.  Never
            # silently execute the canonical path under an ablation label.
            raise RuntimeError(f"REAL_EXECUTION_ABLATION_NOT_IMPLEMENTED:{ablation}")
        from backend.research_pipeline.cases.definitions import CASES
        case = next((item for item in CASES if item.get("case_id") == unit.case_id), None)
        if case is None:
            raise RuntimeError(f"REAL_EXECUTION_INPUT_NOT_RESOLVED:{unit.case_id}")
        from backend.research_pipeline.pipeline import CallBudget
        from backend.research_pipeline import orchestrator
        parser = lambda budget, case_id, text: context.casecontext_parser(case_id, text, run_index=0)
        kwargs = {"case_id": unit.case_id, "clinical_text": case["clinical_text"],
                  "call_parser_fn": parser, "call_enricher_fn": context.gemma.call,
                  "source_units_by_id": {}, "budget": CallBudget(), "ledger": context.ledger,
                  "document_runtime": context.cache_factory, "call_narrator_fn": context.narrator.call,
                  "retrieve_fn": None}
        if ablation == "A":
            kwargs["match_verifier_fn"] = lambda *_: {"records": [], "essential_fields_pass": False, "warnings": [], "bypassed": True}
            kwargs["eligibility_gate_fn"] = lambda *_: None
        return orchestrator.run_case(**kwargs).__dict__


@dataclass(frozen=True)
class ScientificExecutionResult:
    scientific_payload: Any
    status: str = "COMPLETE"
    failure_class: str | None = None
    raw_reason_code: str | None = None
    calls: dict[str, int] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_native(cls, payload: Any, **metadata: Any) -> "ScientificExecutionResult":
        if isinstance(payload, cls):
            return payload
        if isinstance(payload, dict):
            status = payload.get("status") or payload.get("terminal_class") or "COMPLETE"
            failure = payload.get("failure_class")
            reason = payload.get("raw_reason_code")
        else:
            status, failure, reason = "COMPLETE", None, None
        return cls(payload, status, failure, reason, metadata.get("calls", {}), metadata.get("artifacts", {}), metadata.get("timing", {}))

    def to_dict(self) -> dict[str, Any]:
        return {"scientific_payload": self.scientific_payload, "status": self.status,
                "failure_class": self.failure_class, "raw_reason_code": self.raw_reason_code,
                "calls": dict(self.calls), "artifacts": dict(self.artifacts), "timing": dict(self.timing)}


@dataclass
class ProductionAdapterFactory:
    """Creates only delegates to already frozen runtime/provider components."""

    @staticmethod
    def parser() -> Callable[..., Any]:
        from backend.research_pipeline.casecontext.parser import call_parser
        return call_parser

    @staticmethod
    def canonical_runtime() -> CanonicalRuntimeAdapter:
        from backend.pipeline.evidence.retrieval.pipeline import EvidenceRetrievalPipeline
        return CanonicalRuntimeAdapter.from_runtime(EvidenceRetrievalPipeline())

    @staticmethod
    def selector() -> SelectorAdapter:
        from backend.research_pipeline.experimental.sourceunit_selector import select
        return SelectorAdapter(select, k=5)

    @staticmethod
    def gemma(configuration: dict[str, Any], provider: Callable[..., Any] | None = None, model_guard: Any | None = None) -> GemmaAdapter:
        if provider is None:
            from backend.research_pipeline.enrichment.enricher_v2 import call_enricher_v2
            def provider(*args: Any, configuration: dict[str, Any] | None = None, **kwargs: Any) -> Any:
                del configuration
                return call_enricher_v2(*args, **kwargs)
        return GemmaAdapter(provider, configuration, model_guard=model_guard)

    @staticmethod
    def narrator(configuration: dict[str, Any], provider: Callable[..., Any] | None = None, model_guard: Any | None = None) -> NarratorAdapter:
        if provider is None:
            from backend.research_pipeline.narrative.narrator import call_narrator
            def provider(*args: Any, configuration: dict[str, Any] | None = None, **kwargs: Any) -> Any:
                del configuration
                return call_narrator(*args, **kwargs)
        return NarratorAdapter(provider, configuration, model_guard=model_guard)

    @staticmethod
    def quote_validator(validator: Callable[..., Any] | None = None, *, identity_semantic: bool = False) -> QuoteValidatorAdapter:
        if validator is None:
            from backend.research_pipeline.enrichment.validator_v2 import validate_enrichment_v2
            def validator(*args: Any, **kwargs: Any) -> Any:
                return validate_enrichment_v2(*args, **kwargs)
        return QuoteValidatorAdapter(validator, identity_semantic=identity_semantic)

    @staticmethod
    def narrative_verifier(verifier: Callable[..., Any] | None = None, *, bypass: bool = False) -> NarrativeVerifierAdapter:
        if verifier is None:
            from backend.research_pipeline.narrative.verifier import verify_narrative
            verifier = verify_narrative
        return NarrativeVerifierAdapter(verifier, bypass=bypass)

    @staticmethod
    def document_runtime() -> Any:
        from backend.research_pipeline.documents.live_resolution import DocumentRuntime
        return DocumentRuntime.open()


@dataclass
class RealExecutionContext:
    protocol: Any | None = None
    canonical_runtime: CanonicalRuntimeAdapter | None = None
    selector: SelectorAdapter | None = None
    casecontext_parser: Callable[..., Any] | None = None
    gemma: GemmaAdapter | None = None
    narrator: NarratorAdapter | None = None
    document_resolver: DocumentResolverAdapter | None = None
    quote_validator: QuoteValidatorAdapter | None = None
    narrative_verifier: NarrativeVerifierAdapter | None = None
    cache_factory: Any | None = None
    network_guard: Any | None = None
    model_guard: Any | None = None
    ledger: Any | None = None
    raw_writer: Any | None = None
    timing: Any | None = None
    production_dispatcher: Any | None = None

    def assert_production_guards(self, planned_unit: Any, executor: Any) -> None:
        """Fail closed before any adapter can perform a real side effect."""
        if self.network_guard is None or self.model_guard is None:
            raise RuntimeError("REAL_EXECUTION_GUARDS_NOT_CONFIGURED")
        check_network = getattr(self.network_guard, "assert_allowed", None)
        if callable(check_network):
            check_network(getattr(planned_unit, "network_policy", None))
        check_model = getattr(self.model_guard, "assert_allowed", None)
        if callable(check_model):
            check_model(getattr(planned_unit, "gemma_requirement", None))

    def execute(self, planned_unit: Any, executor: Any) -> ScientificExecutionResult:
        if self.production_dispatcher is None:
            raise RuntimeError("REAL_EXECUTION_DISPATCHER_NOT_CONFIGURED")
        result = self.production_dispatcher.execute(planned_unit, self, executor)
        return ScientificExecutionResult.from_native(result)

    @classmethod
    def from_production(cls, protocol: Any, *, ledger: Any = None, raw_writer: Any = None,
                        network_guard: Any = None, model_guard: Any = None,
                        production_dispatcher: Any = None, generation_config: dict[str, Any] | None = None) -> "RealExecutionContext":
        config = generation_config or {}
        if network_guard is None or model_guard is None:
            raise RuntimeError("REAL_EXECUTION_GUARDS_NOT_CONFIGURED")
        document_runtime = ProductionAdapterFactory.document_runtime()
        return cls(protocol=protocol,
                    canonical_runtime=ProductionAdapterFactory.canonical_runtime(),
                    selector=ProductionAdapterFactory.selector(),
                    casecontext_parser=ProductionAdapterFactory.parser(),
                    gemma=ProductionAdapterFactory.gemma(config, model_guard=model_guard),
                    narrator=ProductionAdapterFactory.narrator(config, model_guard=model_guard),
                    document_resolver=DocumentResolverAdapter(document_runtime.resolve, network_guard),
                    quote_validator=ProductionAdapterFactory.quote_validator(),
                    narrative_verifier=ProductionAdapterFactory.narrative_verifier(),
                    cache_factory=document_runtime, network_guard=network_guard, model_guard=model_guard,
                    ledger=ledger, raw_writer=raw_writer, timing=None,
                    production_dispatcher=production_dispatcher or ProductionUnitDispatcher())
