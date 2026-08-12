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
        raw = self._run_case(unit, context, gold_access=False)
        if context.protocol is None:
            raise RuntimeError("H01_PROTOCOL_REQUIRED")
        from .adapters.h01_evaluator import H01EvaluatorAdapter
        import json
        gold_path = context.protocol.root.parents[1] / "final_protocol" / "heldout" / "architectural_challenge_gold.json"
        gold_rows = json.loads(gold_path.read_text(encoding="utf-8"))["gold"]
        challenge = next(row for row in gold_rows if row["case_id"] == unit.case_id)
        evaluator = H01EvaluatorAdapter(
            context.protocol.root.parents[1],
            context.protocol.amendment["H01"]["normative_sha256"],
        )
        evaluated = evaluator.evaluate(raw, challenge)
        return {"raw_pipeline_run": raw, "h01_evaluation": evaluated,
                "gold_join_phase": "POST_INFERENCE"}

    def _RQ1DeterministicExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        """Delegate RQ1 to the frozen comparator and aggregation functions."""
        from evaluation.run_rq1 import CANDIDATES, KG_ROOT
        from evaluation.rq1.compare import MaterializationComparator, aggregate, load_candidates
        from evaluation.rq1.kg_source import EligiblePathBuilder, FrozenKnowledgeGraph
        graph = FrozenKnowledgeGraph(KG_ROOT)
        paths = EligiblePathBuilder(graph).build()
        candidates = list(load_candidates(CANDIDATES))
        comparison = MaterializationComparator(paths, candidates).compare()
        return {"testbed": unit.testbed, "case_id": unit.case_id,
                "arm": unit.arm, "comparisons": comparison,
                "metrics": aggregate(comparison, paths, len(candidates))}

    def _RQ2SelectorExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_rq2_offline(unit, context)

    def _RQ2GemmaExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_rq2_downstream(unit, context)

    def _run_rq2_data(self, unit: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        from pathlib import Path
        import json
        root = Path(__file__).resolve().parents[3]
        candidates_path = root / "evaluation" / "sourceunit_selector_independent" / "candidate_inventory.jsonl"
        rows_path = root / "evaluation" / "final_protocol" / "supplements" / "S01" / "sourceunits_1697.jsonl"
        candidate_id, document_id = unit.case_id.split("|", 1)
        candidate = next(json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines()
                         if line and json.loads(line).get("candidate_id") == candidate_id)
        all_units = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line]
        units = [row for row in all_units if row.get("candidate_id") == candidate_id
                 and row.get("document_id") == document_id]
        if not units:
            inventory_path = root / "evaluation" / "sourceunit_selector_independent" / "document_inventory.jsonl"
            inventory = next((json.loads(line) for line in inventory_path.read_text(encoding="utf-8").splitlines()
                              if line and json.loads(line).get("candidate_id") == candidate_id), None)
            canonical_document = inventory.get("document_id") if inventory else None
            units = [row for row in all_units if row.get("candidate_id") == candidate_id
                     and row.get("document_id") == canonical_document]
        if not units:
            raise RuntimeError(f"REAL_EXECUTION_INPUT_NOT_RESOLVED:{unit.case_id}")
        return candidate, units

    def _run_rq2_offline(self, unit: Any, context: "RealExecutionContext") -> Any:
        from backend.research_pipeline.experimental.sourceunit_selector import (
            SourceUnitSelectionInput, select_bm25, select_first_k,
        )
        candidate, units = self._run_rq2_data(unit)
        selection = SourceUnitSelectionInput(
            candidate_id=str(candidate.get("candidate_id")),
            document_id=unit.case_id.split("|", 1)[1],
            disease=tuple(candidate.get("disease") or ()),
            genes=tuple(candidate.get("genes") or ()),
            alterations=tuple(candidate.get("alterations") or ()),
            interventions=tuple(candidate.get("interventions") or ()),
            graph_relation=candidate.get("graph_relation"),
            source_units=tuple(units),
        )
        if unit.arm == "GOLD":
            selected = [str(row.get("source_unit_id")) for row in units]
            ranked = []
        elif unit.arm == "FIRST_K":
            selected = select_first_k(selection, top_k=5)
            ranked = []
        elif unit.arm == "BM25":
            selected = select_bm25(selection, top_k=5)
            ranked = []
        elif unit.arm == "DETERMINISTIC_SELECTOR":
            result = context.selector.select(selection)
            selected = list(result.selected_source_unit_ids)
            ranked = [item.__dict__ for item in result.ranked_source_units]
        else:
            raise RuntimeError(f"REAL_EXECUTION_ARM_NOT_IMPLEMENTED:{unit.arm}")
        return {"candidate_id": selection.candidate_id, "document_id": selection.document_id,
                "arm": unit.arm, "selected_source_unit_ids": list(selected), "ranking": ranked}

    def _run_rq2_downstream(self, unit: Any, context: "RealExecutionContext") -> Any:
        candidate, units = self._run_rq2_data(unit)
        offline = self._run_rq2_offline(unit, context)
        selected_ids = set(offline["selected_source_unit_ids"])
        selected_units = [row for row in units if row.get("source_unit_id") in selected_ids]
        # The provider and validator remain the reviewed adapters; no resolver
        # or network path is introduced for S01.
        enrichment = context.gemma.call(
            unit.case_id, candidate.get("candidate_id"), candidate.get("document_id_from_provenance"),
            candidate, "", (candidate.get("interventions") or [""])[0], selected_units,
            run_index=0,
        )
        validated = context.quote_validator.validate(enrichment)
        return {"candidate_id": candidate.get("candidate_id"), "document_id": unit.case_id.split("|", 1)[1],
                "arm": unit.arm, "selected_source_unit_ids": list(selected_ids),
                "enrichment": enrichment, "validation": validated}

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

    def _OperationalExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        from .operational_executor import execute_operational_scenario
        return execute_operational_scenario(context.protocol, unit.case_id, context)

    def _ControlledFailureExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        from .operational_executor import execute_operational_scenario
        return execute_operational_scenario(context.protocol, unit.case_id, context)

    def _ReliabilityStratumAExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_case(unit, context)

    def _ReliabilityStratumBExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        return self._run_rq2_downstream(unit, context)

    def _LatencyExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        if context.timing is None:
            return self._run_case(unit, context)
        from .timing import timed_call
        result, elapsed_ms = timed_call(self._run_case, unit, context)
        return {"native_result": result, "end_to_end_latency_ms": elapsed_ms}

    def _NarrativeHostileExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        case = self._load_narrative_case(unit, hostile=True)
        verified = context.narrative_verifier.verify_authority(
            case["canonical_authority_context"], case["narrator_input"],
            case["candidate_narrative"],
        )
        return {"case_id": unit.case_id, "stratum": "H", "verifier": verified,
                "candidate_narrative_sha256": case["candidate_narrative_sha256"],
                "authority_hash": case["canonical_authority_hash"]}

    def _NarrativeControlExecutor(self, unit: Any, context: "RealExecutionContext") -> Any:
        case = self._load_narrative_case(unit, hostile=False)
        output = context.narrator.call(unit.case_id, case["narrator_input"], run_index=0)
        verified = context.narrative_verifier.verify_authority(
            case["canonical_dossier"], case["narrator_input"], output,
        )
        return {"case_id": unit.case_id, "stratum": "C", "narrative": output,
                "verifier": verified, "canonical_dossier_sha256": case["canonical_dossier_sha256"],
                "narrator_input_sha256": case["narrator_input_sha256"]}

    @staticmethod
    def _load_narrative_case(unit: Any, *, hostile: bool) -> dict[str, Any]:
        from pathlib import Path
        import json
        root = Path(__file__).resolve().parents[3] / "evaluation" / "final_protocol_v1_5_candidates" / "narrative"
        path = root / ("hostile" if hostile else "controls") / f"{unit.case_id}.json"
        if not path.is_file():
            raise RuntimeError(f"NARRATIVE_CORPUS_IDENTITY_FAILURE:{unit.case_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _run_case(self, unit: Any, context: "RealExecutionContext", *, gold_access: bool = True, ablation: str | None = None) -> Any:
        from evaluation.final_evaluation_harness.common.case_resolution import resolve_production_case

        resolved_case_id, case = resolve_production_case(unit.case_id)
        from backend.research_pipeline.pipeline import CallBudget
        from backend.research_pipeline import orchestrator
        parser = lambda budget, case_id, text: context.casecontext_parser(case_id, text, run_index=0)
        kwargs = {"case_id": resolved_case_id, "clinical_text": case["clinical_text"],
                  "call_parser_fn": parser, "call_enricher_fn": context.gemma.call,
                  "source_units_by_id": {}, "budget": CallBudget(), "ledger": context.ledger,
                  "document_runtime": context.cache_factory, "call_narrator_fn": context.narrator.call,
                  "retrieve_fn": None}
        if ablation == "B":
            kwargs["source_unit_selector_fn"] = lambda selection, *, top_k: context.selector.select(selection, top_k=top_k)
        elif ablation == "C":
            from backend.research_pipeline.enrichment.validator_v2 import (
                identity_semantic_validator,
                validate_enrichment_v2,
            )
            kwargs["validate_fn"] = lambda transport, enrichment, **kw: validate_enrichment_v2(
                transport,
                enrichment,
                candidate=kw["candidate"],
                paper_bundle=kw["paper_bundle"],
                source_units_by_id=kw["source_units_by_id"],
                requested_drug=kw["requested_drug"],
                semantic_validator=identity_semantic_validator,
            )
        elif ablation == "D":
            kwargs.update(
                research_frozen_artifacts=True,
                narrative_verifier_mode="OFFLINE_ABLATION_BYPASS",
                call_narrator_fn=context.narrator.call,
            )
        if ablation == "A":
            kwargs["match_verifier_fn"] = lambda *_: {"records": [], "essential_fields_pass": False, "warnings": [], "bypassed": True}
            kwargs["eligibility_gate_fn"] = lambda *_: None
        return orchestrator.run_case(**kwargs).to_dict()


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
    runtime_guard: Any | None = None
    ledger: Any | None = None
    raw_writer: Any | None = None
    timing: Any | None = None
    production_dispatcher: Any | None = None

    def assert_production_guards(self, planned_unit: Any, executor: Any) -> None:
        """Fail closed before any adapter can perform a real side effect."""
        if self.network_guard is None or self.model_guard is None or self.runtime_guard is None:
            raise RuntimeError("REAL_EXECUTION_GUARDS_NOT_CONFIGURED")
        for guard in (self.network_guard, self.model_guard, self.runtime_guard):
            bind = getattr(guard, "bind", None)
            if callable(bind):
                bind(planned_unit)
        check_network = getattr(self.network_guard, "assert_configured", None)
        if callable(check_network):
            check_network()
        check_model = getattr(self.model_guard, "assert_configured", None)
        if callable(check_model):
            check_model(role="gemma")
            check_model(role="narrator")
        check_runtime = getattr(self.runtime_guard, "assert_configured", None)
        if callable(check_runtime):
            check_runtime()
        if "canonical_runtime" in getattr(executor, "adapter_names", ()):
            assert_runtime = getattr(self.runtime_guard, "assert_allowed", None)
            if callable(assert_runtime):
                assert_runtime("REQUIRED")

    def execute(self, planned_unit: Any, executor: Any) -> ScientificExecutionResult:
        if self.production_dispatcher is None:
            raise RuntimeError("REAL_EXECUTION_DISPATCHER_NOT_CONFIGURED")
        result = self.production_dispatcher.execute(planned_unit, self, executor)
        return ScientificExecutionResult.from_native(result)

    @classmethod
    def from_production(cls, protocol: Any, *, ledger: Any = None, raw_writer: Any = None,
                        network_guard: Any = None, model_guard: Any = None, runtime_guard: Any = None,
                        production_dispatcher: Any = None, generation_config: dict[str, Any] | None = None) -> "RealExecutionContext":
        config = generation_config or {}
        if network_guard is None or model_guard is None or runtime_guard is None:
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
                    cache_factory=document_runtime, network_guard=network_guard, model_guard=model_guard, runtime_guard=runtime_guard,
                    ledger=ledger, raw_writer=raw_writer, timing=None,
                    production_dispatcher=production_dispatcher or ProductionUnitDispatcher())
