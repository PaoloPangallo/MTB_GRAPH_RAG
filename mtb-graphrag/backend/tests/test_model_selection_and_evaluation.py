"""Test della catena di valutazione e della selezione del modello.

Nessun test richiede Neo4j, Ollama o un modello reale: il client di grafo e quello
LLM sono sostituiti da stub scriptati. Le integrazioni vere sono separate e attive
solo con RUN_NEO4J_INTEGRATION / RUN_LLM_INTEGRATION / RUN_CLOUD_MODEL_INTEGRATION.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import TestCase

from backend.pipeline.llm.model_capabilities import (
    detect_structured_output_mode,
    from_show_response,
    parse_version,
)
from backend.pipeline.llm.model_registry import (
    ROLES,
    ModelConfigurationError,
    ModelRegistry,
    ModelSpec,
    RunConfig,
    assert_experiment_safe,
    endpoint_for_model,
    resolve_model_name,
)
from backend.pipeline.llm.ollama_adapter import (
    JSON_SCHEMA,
    MAX_STRUCTURED_RETRIES,
    PROMPT_VALIDATED,
    OllamaEndpoint,
    StructuredOutputError,
    parse_strict_json,
    request_structured,
    sanitize_endpoint,
)
from benchmarks.mtb_evidence.evaluation.aggregation import aggregate, combine
from benchmarks.mtb_evidence.evaluation.clinical_gold import (
    build_from_pilot,
    load_clinical_gold,
    verify_no_loss,
)
from benchmarks.mtb_evidence.evaluation.contracts import (
    ABSENT,
    CORRECTLY_ABSTAINED,
    LOSS_STATES,
    MISSED_BY_RETRIEVAL,
    MISSING_FROM_KG,
    PARTIALLY_PRESENT,
    PRESENT,
    CaseEvaluation,
    LossDecomposition,
    MetricResult,
    ReportPrediction,
    RetrievalPrediction,
    SnapshotGoldCase,
    SnapshotGoldClaim,
    ensure_exhaustive_loss,
)
from benchmarks.mtb_evidence.evaluation.loss_decomposition import decompose_case, summarize
from benchmarks.mtb_evidence.evaluation.matching import normalize_pmids, score_sets
from benchmarks.mtb_evidence.evaluation.metrics.applicability import (
    compatible_overstatement_rate,
    not_compatible_leakage_rate,
)
from benchmarks.mtb_evidence.evaluation.metrics.kg_coverage import (
    pmid_coverage,
    therapy_coverage,
)
from benchmarks.mtb_evidence.evaluation.metrics.orchestration import (
    conditional_step_accuracy,
    run_to_run_agreement,
    stop_condition_accuracy,
    task_completion,
    valid_action_rate,
)
from benchmarks.mtb_evidence.evaluation.metrics.retrieval_fidelity import (
    negative_case_accuracy,
    retrieval_metrics,
    tool_metrics,
)
from benchmarks.mtb_evidence.evaluation.snapshot_gold import (
    KIND_PMID,
    KIND_THERAPY,
    AuditArtifacts,
    build_snapshot_gold,
)
from benchmarks.mtb_evidence.evaluation.source_profiles import (
    ProfileNotFound,
    default_repository,
)
from benchmarks.mtb_evidence.model_selection.roles import (
    KNOWN_TOOLS,
    GoldLeakageError,
    assert_no_leakage,
    free_report_task,
    leakage_overlap,
    planner_task,
    verifier_tasks,
)
from benchmarks.mtb_evidence.model_selection.scoring import (
    STATUS_NO_MODEL_QUALIFIED,
    check_admissibility,
    rank,
    score_role,
    select_single_model,
    selection_status,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DATA = PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "evaluation" / "data"
PILOT_GOLD = (
    PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "pilot" / "input"
    / "mtb_evidence_gold_pilot_v1.jsonl"
)
AUDIT_DIR = PROJECT_ROOT / "benchmarks" / "mtb_evidence" / "pilot" / "audit"


def _clinical():
    return load_clinical_gold(EVAL_DATA / "clinical_gold_v1.jsonl")


def _case(case_id: str):
    return next(case for case in _clinical() if case.case_id == case_id)


def _snapshot(case_id: str) -> SnapshotGoldCase:
    for path in EVAL_DATA.glob("snapshot_gold_*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            if payload["case_id"] != case_id:
                continue
            items = tuple(
                SnapshotGoldClaim(
                    **{
                        key: (tuple(value) if isinstance(value, list) else value)
                        for key, value in item.items()
                        if key != "is_retrievable"
                    }
                )
                for item in payload["items"]
            )
            return SnapshotGoldCase(
                case_id=payload["case_id"],
                snapshot_fingerprint=payload["snapshot_fingerprint"],
                items=items,
                retrievable_therapies=tuple(payload["retrievable_therapies"]),
                retrievable_pmids=tuple(payload["retrievable_pmids"]),
                retrievable_nct_ids=tuple(payload["retrievable_nct_ids"]),
                expected_abstention=payload["expected_abstention"],
                notes=tuple(payload["notes"]),
            )
    raise AssertionError(f"snapshot gold non trovato per {case_id}")


class _ScriptedChatClient:
    """Client LLM finto: restituisce risposte preordinate."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, model, messages, **kwargs):
        self.calls.append({"model": model, "messages": messages, **kwargs})
        content = self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]
        return {"message": {"content": content}}


# ── Model registry ─────────────────────────────────────────────────────────────


class ModelRegistryTest(TestCase):
    def test_all_five_roles_are_declared(self):
        self.assertEqual(len(ROLES), 5)
        self.assertIn("planner", ROLES)
        self.assertIn("source_verifier", ROLES)

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(ModelConfigurationError):
            resolve_model_name("nonexistent_role")

    def test_role_env_var_overrides_fallback(self):
        os.environ["OLLAMA_PLANNER_MODEL"] = "test-model:1b"
        try:
            self.assertEqual(resolve_model_name("planner"), "test-model:1b")
        finally:
            os.environ.pop("OLLAMA_PLANNER_MODEL", None)

    def test_cloud_suffix_routes_to_cloud_endpoint(self):
        self.assertEqual(endpoint_for_model("gemma4:31b-cloud").kind, "cloud")
        self.assertEqual(endpoint_for_model("qwen3:14b").kind, "local")

    def test_model_revision_uses_digest(self):
        spec = ModelSpec(
            role="planner",
            model_name="qwen3:14b",
            endpoint=OllamaEndpoint("http://localhost:11434"),
            capabilities=from_show_response(
                "qwen3:14b",
                {"name": "qwen3:14b", "digest": "abc123"},
                {"digest": "abc123", "capabilities": ["completion", "tools"]},
                endpoint=OllamaEndpoint("http://localhost:11434"),
                ollama_version="0.9.0",
            ),
        )
        self.assertEqual(spec.model_revision, "ollama:qwen3:14b:abc123")

    def test_model_revision_falls_back_to_explicit_value(self):
        spec = ModelSpec(
            role="planner",
            model_name="qwen3:14b",
            endpoint=OllamaEndpoint("http://localhost:11434"),
            explicit_revision="manual-1",
        )
        self.assertEqual(spec.model_revision, "ollama:qwen3:14b:manual-1")

    def test_temperature_is_not_part_of_the_revision(self):
        endpoint = OllamaEndpoint("http://localhost:11434")
        cold = ModelSpec("planner", "m:1b", endpoint, config=RunConfig(temperature=0.0),
                         explicit_revision="r1")
        warm = ModelSpec("planner", "m:1b", endpoint, config=RunConfig(temperature=0.8),
                         explicit_revision="r1")
        self.assertEqual(cold.model_revision, warm.model_revision)

    def test_source_verifier_revision_override(self):
        os.environ["SOURCE_VERIFIER_MODEL_REVISION"] = "pinned-revision"
        try:
            spec = ModelSpec(
                "source_verifier", "m:1b", OllamaEndpoint("http://localhost:11434")
            )
            self.assertEqual(spec.model_revision, "pinned-revision")
            planner = ModelSpec("planner", "m:1b", OllamaEndpoint("http://localhost:11434"))
            self.assertNotEqual(planner.model_revision, "pinned-revision")
        finally:
            os.environ.pop("SOURCE_VERIFIER_MODEL_REVISION", None)

    def test_latest_tag_is_flagged_as_unsafe(self):
        spec = ModelSpec("planner", "mistral:latest", OllamaEndpoint("http://x:1"))
        self.assertTrue(spec.uses_forbidden_tag)
        self.assertTrue(assert_experiment_safe({"planner": spec}))

    def test_registry_without_probe_does_not_touch_the_network(self):
        registry = ModelRegistry(probe=False)
        spec = registry.spec("planner", model_name="whatever:1b")
        self.assertIsNone(spec.capabilities)
        self.assertEqual(spec.model_name, "whatever:1b")

    def test_missing_model_yields_no_capabilities(self):
        registry = ModelRegistry(probe=True)
        spec = registry.spec(
            "planner", model_name="definitely-not-installed-model:0b"
        )
        self.assertIn(spec.digest, ("",))


class CapabilityDetectionTest(TestCase):
    def test_version_parsing(self):
        self.assertEqual(parse_version("0.9.0"), (0, 9, 0))
        self.assertEqual(parse_version("0.5"), (0, 5, 0))
        self.assertEqual(parse_version(""), (0, 0, 0))

    def test_local_recent_version_gets_json_schema(self):
        mode, _ = detect_structured_output_mode(
            OllamaEndpoint("http://localhost:11434"), "0.9.0"
        )
        self.assertEqual(mode, JSON_SCHEMA)

    def test_local_old_version_falls_back_to_prompt(self):
        mode, reason = detect_structured_output_mode(
            OllamaEndpoint("http://localhost:11434"), "0.4.2"
        )
        self.assertEqual(mode, PROMPT_VALIDATED)
        self.assertIn("0.4.2", reason)

    def test_cloud_is_always_prompt_validated(self):
        mode, reason = detect_structured_output_mode(
            OllamaEndpoint("https://api.ollama.com"), "9.9.9"
        )
        self.assertEqual(mode, PROMPT_VALIDATED)
        self.assertIn("cloud", reason)

    def test_tool_calling_read_from_capabilities(self):
        capabilities = from_show_response(
            "m", {}, {"capabilities": ["completion", "tools"]},
            endpoint=OllamaEndpoint("http://localhost:11434"), ollama_version="0.9.0",
        )
        self.assertTrue(capabilities.tool_calling)

    def test_context_length_extracted_from_model_info(self):
        capabilities = from_show_response(
            "m", {}, {"model_info": {"qwen2.context_length": 32768}},
            endpoint=OllamaEndpoint("http://localhost:11434"), ollama_version="0.9.0",
        )
        self.assertEqual(capabilities.context_length, 32768)

    def test_endpoint_is_sanitized(self):
        self.assertIn("[REDACTED]", sanitize_endpoint("https://user:pw@api.ollama.com"))


# ── Output strutturati ─────────────────────────────────────────────────────────


class StructuredOutputTest(TestCase):
    SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}},
              "required": ["ok"]}

    def test_valid_json_is_parsed_on_first_attempt(self):
        client = _ScriptedChatClient(['{"ok": true}'])
        result = request_structured(
            client, "m", [{"role": "user", "content": "x"}], self.SCHEMA, mode=JSON_SCHEMA
        )
        self.assertEqual(result.parsed, {"ok": True})
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.retries, 0)

    def test_fenced_json_is_accepted(self):
        self.assertEqual(parse_strict_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_permissive_extraction_is_refused(self):
        with self.assertRaises(ValueError):
            parse_strict_json('ecco il risultato: {"a": 1} spero vada bene')

    def test_prompt_validated_retries_then_succeeds(self):
        client = _ScriptedChatClient(["non json", '{"ok": true}'])
        result = request_structured(
            client, "m", [{"role": "user", "content": "x"}], self.SCHEMA,
            mode=PROMPT_VALIDATED,
        )
        self.assertEqual(result.retries, 1)
        self.assertEqual(len(result.raw_outputs), 2)
        self.assertTrue(result.validation_errors)

    def test_fails_closed_after_two_retries(self):
        client = _ScriptedChatClient(["nope", "still nope", "nope again", "nope"])
        with self.assertRaises(StructuredOutputError):
            request_structured(
                client, "m", [{"role": "user", "content": "x"}], self.SCHEMA,
                mode=PROMPT_VALIDATED,
            )
        self.assertEqual(len(client.calls), MAX_STRUCTURED_RETRIES + 1)

    def test_raw_output_is_preserved_even_on_failure(self):
        client = _ScriptedChatClient(["bad-1", "bad-2", "bad-3"])
        try:
            request_structured(
                client, "m", [{"role": "user", "content": "x"}], self.SCHEMA,
                mode=PROMPT_VALIDATED,
            )
        except StructuredOutputError as error:
            self.assertIn("bad-1", str(error) + repr(client.calls))
        self.assertEqual(len(client.calls), 3)

    def test_repair_prompt_carries_only_output_error_and_schema(self):
        client = _ScriptedChatClient(["bad", '{"ok": true}'])
        request_structured(
            client, "m", [{"role": "user", "content": "contesto originale"}],
            self.SCHEMA, mode=PROMPT_VALIDATED,
        )
        repair = client.calls[1]["messages"][-1]["content"]
        self.assertIn("bad", repair)
        self.assertIn("schema", repair.casefold())

    def test_validation_failure_triggers_retry(self):
        def validate(payload):
            if "ok" not in payload:
                raise ValueError("campo ok mancante")
            return payload

        client = _ScriptedChatClient(['{"altro": 1}', '{"ok": false}'])
        result = request_structured(
            client, "m", [{"role": "user", "content": "x"}], self.SCHEMA,
            mode=PROMPT_VALIDATED, validate=validate,
        )
        self.assertEqual(result.parsed, {"ok": False})
        self.assertEqual(result.retries, 1)


# ── Gold ───────────────────────────────────────────────────────────────────────


class GoldSeparationTest(TestCase):
    def test_clinical_gold_matches_the_pilot_without_loss(self):
        records = [
            json.loads(line)
            for line in PILOT_GOLD.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(verify_no_loss(records, build_from_pilot(PILOT_GOLD)), [])

    def test_clinical_gold_is_independent_of_the_snapshot(self):
        """Il clinical gold non contiene alcun riferimento al grafo."""
        text = (EVAL_DATA / "clinical_gold_v1.jsonl").read_text(encoding="utf-8")
        for marker in ("snapshot_fingerprint", "graph_record_ids", "presence_status"):
            self.assertNotIn(marker, text)

    def test_snapshot_gold_carries_the_fingerprint(self):
        snapshot = _snapshot("PILOT-K1-FGFR2-iCCA")
        self.assertEqual(len(snapshot.snapshot_fingerprint), 64)

    def test_no_clinical_item_is_dropped_by_the_mapping(self):
        mapping = [
            json.loads(line)
            for line in (EVAL_DATA / "clinical_snapshot_mapping.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        for case in _clinical():
            mapped = {
                row["clinical_item_id"] for row in mapping if row["case_id"] == case.case_id
            }
            for claim in case.expected_claims:
                self.assertIn(claim.claim_id, mapped, f"{claim.claim_id} non mappata")

    def test_amendments_are_not_applied_to_the_clinical_gold(self):
        manifest = json.loads(
            (EVAL_DATA / "gold_build_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["amendments_seen_but_not_applied"], 9)


class CoverageDistinctionsTest(TestCase):
    def test_absent_source_lowers_kg_coverage(self):
        coverage = pmid_coverage(_snapshot("PILOT-K1-FGFR2-iCCA"))
        self.assertLess(coverage.value, 1.0)
        self.assertTrue(coverage.missing_items or coverage.partial_items)

    def test_pmid_only_in_citation_is_partially_present(self):
        snapshot = _snapshot("PILOT-A2-ALK-G1202R")
        partial = [
            item
            for item in snapshot.by_kind(KIND_PMID)
            if item.presence_status == PARTIALLY_PRESENT
        ]
        self.assertTrue(partial, "atteso almeno un PMID solo come citazione")
        self.assertTrue(any("citation_id" in note for item in partial for note in item.coverage_notes))

    def test_drug_present_but_unreachable_is_partially_present(self):
        snapshot = _snapshot("PILOT-K1-FGFR2-iCCA")
        partial = [
            item
            for item in snapshot.by_kind(KIND_THERAPY)
            if item.presence_status == PARTIALLY_PRESENT
        ]
        self.assertTrue(partial, "futibatinib atteso come presente ma non raggiungibile")
        self.assertFalse(partial[0].reachable_by_fixed_plan)

    def test_absent_nct_is_marked_absent(self):
        snapshot = _snapshot("PILOT-K1-FGFR2-iCCA")
        self.assertTrue(
            any(item.presence_status == ABSENT for item in snapshot.by_kind("nct_id"))
        )

    def test_unmodelled_qualifier_is_distinguished_from_absent_record(self):
        snapshot = _snapshot("PILOT-C1-EGFR-L858R-CONTEXT")
        qualifiers = snapshot.by_kind("qualifier")
        self.assertTrue(qualifiers)
        self.assertTrue(
            any("non modellato" in note for item in qualifiers for note in item.coverage_notes)
        )


# ── Retrieval ──────────────────────────────────────────────────────────────────


class RetrievalFidelityTest(TestCase):
    def test_precision_recall_f1(self):
        score = score_sets("therapy", {"a", "b"}, {"b", "c"})
        self.assertAlmostEqual(score.precision, 0.5)
        self.assertAlmostEqual(score.recall, 0.5)
        self.assertAlmostEqual(score.f1, 0.5)

    def test_absent_element_is_not_counted_against_the_retriever(self):
        """Cio' che non e' nello snapshot non entra nel denominatore del recall."""
        with_unreachable = score_sets(
            "therapy", {"pemigatinib"}, {"pemigatinib"}, unreachable={"futibatinib"}
        )
        self.assertEqual(with_unreachable.recall, 1.0)
        self.assertEqual(with_unreachable.false_negatives, ())

    def test_predicting_an_unreachable_item_is_not_a_false_positive_here(self):
        score = score_sets(
            "therapy", {"pemigatinib", "futibatinib"}, {"pemigatinib"},
            unreachable={"futibatinib"},
        )
        self.assertEqual(score.false_positives, ())

    def test_negative_case_requires_empty_output(self):
        case = _case("PILOT-N1-RMI2-SNAPSHOT")
        good = negative_case_accuracy(
            case, RetrievalPrediction(case.case_id, "deterministic", abstained=True)
        )
        self.assertEqual(good.value, 1.0)
        bad = negative_case_accuracy(
            case,
            RetrievalPrediction(
                case.case_id, "deterministic", therapies=("osimertinib",), abstained=False
            ),
        )
        self.assertEqual(bad.value, 0.0)

    def test_required_and_unnecessary_tools(self):
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        metrics = tool_metrics(
            case,
            RetrievalPrediction(
                case.case_id,
                "agentic",
                tools_called=("interpret_variant", "identify_targets", "match_trials"),
            ),
        )
        self.assertGreater(metrics["unnecessary_tool_rate"].value, 0.0)


# ── Report e applicabilita' ────────────────────────────────────────────────────


class ApplicabilityTest(TestCase):
    def test_overstatement_is_detected(self):
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        report = ReportPrediction(
            case_id=case.case_id,
            branch="free_llm_summary",
            applicability_by_claim={"C1-C2": "compatible", "C1-C3": "compatible"},
        )
        metric = compatible_overstatement_rate(case, report)
        self.assertEqual(metric.numerator, 2)

    def test_correct_qualification_scores_zero_overstatement(self):
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        report = ReportPrediction(
            case_id=case.case_id,
            branch="structured_report_verified",
            applicability_by_claim={
                "C1-C1": "compatible",
                "C1-C2": "not_compatible",
                "C1-C3": "not_compatible",
            },
        )
        self.assertEqual(compatible_overstatement_rate(case, report).numerator, 0)

    def test_unqualified_claim_counts_as_leakage(self):
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        report = ReportPrediction(case_id=case.case_id, branch="free_llm_summary")
        self.assertGreater(not_compatible_leakage_rate(case, report).numerator, 0)


# ── Loss decomposition ─────────────────────────────────────────────────────────


class LossDecompositionTest(TestCase):
    def _predictions(self, case_id, **kwargs):
        return (
            RetrievalPrediction(case_id=case_id, architecture="deterministic",
                                **kwargs.get("retrieval", {})),
            ReportPrediction(case_id=case_id, branch="structured_report_verified",
                             **kwargs.get("report", {})),
        )

    def test_every_claim_receives_exactly_one_state(self):
        for case in _clinical():
            retrieval, report = self._predictions(
                case.case_id, report={"abstained": case.expected_abstention}
            )
            result = decompose_case(case, _snapshot(case.case_id), retrieval, report)
            self.assertEqual(len(result), len(case.expected_claims))
            self.assertEqual(
                len({item.claim_id for item in result}), len(case.expected_claims)
            )

    def test_states_are_from_the_declared_vocabulary(self):
        case = _case("PILOT-K1-FGFR2-iCCA")
        retrieval, report = self._predictions(case.case_id)
        for item in decompose_case(case, _snapshot(case.case_id), retrieval, report):
            self.assertIn(item.state, LOSS_STATES)

    def test_missing_from_kg_takes_precedence_over_retrieval(self):
        case = _case("PILOT-K1-FGFR2-iCCA")
        retrieval, report = self._predictions(case.case_id)
        states = summarize(decompose_case(case, _snapshot(case.case_id), retrieval, report))
        self.assertIn(MISSING_FROM_KG, states)

    def test_abstention_case_is_correctly_abstained(self):
        case = _case("PILOT-N1-RMI2-SNAPSHOT")
        retrieval, report = self._predictions(
            case.case_id, report={"abstained": True}
        )
        states = summarize(decompose_case(case, _snapshot(case.case_id), retrieval, report))
        self.assertEqual(states, {CORRECTLY_ABSTAINED: 1})

    def test_abstention_violated_is_misrepresentation(self):
        case = _case("PILOT-N1-RMI2-SNAPSHOT")
        retrieval, report = self._predictions(
            case.case_id,
            report={"abstained": False, "claims": ({"object": "qualcosa"},)},
        )
        result = decompose_case(case, _snapshot(case.case_id), retrieval, report)
        self.assertEqual(result[0].state, "misrepresented_in_report")

    def test_retrieved_but_unreported_is_lost_in_report(self):
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        retrieval = RetrievalPrediction(
            case_id=case.case_id,
            architecture="deterministic",
            therapies=("osimertinib",),
            pmids=("32955177", "27959700"),
        )
        report = ReportPrediction(case_id=case.case_id, branch="raw_records")
        states = summarize(decompose_case(case, _snapshot(case.case_id), retrieval, report))
        self.assertIn("lost_in_report", states)

    def test_partition_check_rejects_duplicates(self):
        item = LossDecomposition("C1", "case", MISSED_BY_RETRIEVAL, "retrieval", "x")
        with self.assertRaises(ValueError):
            ensure_exhaustive_loss(["C1"], [item, item])

    def test_partition_check_rejects_missing(self):
        with self.assertRaises(ValueError):
            ensure_exhaustive_loss(["C1", "C2"], [])


# ── Orchestrazione ─────────────────────────────────────────────────────────────


class OrchestrationTest(TestCase):
    def test_fixed_plan_needs_no_planner_calls(self):
        case = _case("PILOT-K1-FGFR2-iCCA")
        prediction = RetrievalPrediction(
            case.case_id, "deterministic",
            tools_called=tuple(case.required_tools), planner_calls=0,
        )
        self.assertEqual(task_completion(case, prediction).value, 1.0)

    def test_conditional_accuracy_only_applies_to_adaptive(self):
        known = conditional_step_accuracy(
            _case("PILOT-K1-FGFR2-iCCA"),
            RetrievalPrediction("x", "deterministic"),
        )
        self.assertIsNone(known.value)
        adaptive_case = _case("PILOT-A2-ALK-G1202R")
        adaptive = conditional_step_accuracy(
            adaptive_case,
            RetrievalPrediction(
                adaptive_case.case_id, "agentic",
                tools_called=tuple(adaptive_case.required_tools),
            ),
        )
        self.assertEqual(adaptive.value, 1.0)

    def test_stop_condition_on_negative_case(self):
        case = _case("PILOT-N1-RMI2-SNAPSHOT")
        stopped = stop_condition_accuracy(
            case, RetrievalPrediction(case.case_id, "agentic", abstained=True)
        )
        self.assertEqual(stopped.value, 1.0)

    def test_invalid_tool_name_lowers_valid_action_rate(self):
        metric = valid_action_rate(
            [{"tool": "interpret_variant"}, {"tool": "invent_something"}], KNOWN_TOOLS
        )
        self.assertEqual(metric.value, 0.5)
        self.assertIn("invent_something", metric.missing_items)

    def test_run_to_run_agreement(self):
        self.assertEqual(run_to_run_agreement(["a", "a", "b"]).value, 2 / 3)
        self.assertIsNone(run_to_run_agreement(["a"]).value)


# ── Leakage ────────────────────────────────────────────────────────────────────


class LeakageControlTest(TestCase):
    def test_no_prompt_contains_gold_labels(self):
        profiles = list(default_repository())
        for case in _clinical():
            planner_task(case)
            verifier_tasks(case, profiles)
            free_report_task(case, [{"drug": "x", "pmid": "1"}])

    def test_expected_pmid_in_prompt_is_rejected(self):
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        with self.assertRaises(GoldLeakageError):
            assert_no_leakage("secondo il PMID 29151359", case)

    def test_audit_decision_in_prompt_is_rejected(self):
        case = _case("PILOT-K1-FGFR2-iCCA")
        with self.assertRaises(GoldLeakageError):
            assert_no_leakage("la decisione e' AMEND", case)

    def test_therapy_named_in_the_question_is_input_not_leakage(self):
        """La domanda di C1 cita osimertinib: e' input clinico, non gold."""
        case = _case("PILOT-C1-EGFR-L858R-CONTEXT")
        assert_no_leakage("parliamo di osimertinib", case)
        self.assertIn("osimertinib", leakage_overlap(case))

    def test_therapy_not_in_the_question_is_leakage(self):
        case = _case("PILOT-K1-FGFR2-iCCA")
        self.assertEqual(leakage_overlap(case), [])
        with self.assertRaises(GoldLeakageError):
            assert_no_leakage("consigliamo pemigatinib", case)

    def test_free_report_prompt_has_identical_records_across_models(self):
        case = _case("PILOT-K1-FGFR2-iCCA")
        records = [{"drug": "a", "pmid": "1"}, {"drug": "b", "pmid": "2"}]
        first = free_report_task(case, records)
        second = free_report_task(case, records)
        self.assertEqual(first.messages, second.messages)


# ── Selezione del modello ──────────────────────────────────────────────────────


class SelectionScoringTest(TestCase):
    def test_below_threshold_model_is_rejected(self):
        check = check_admissibility("m", "planner", {"valid_action_rate": 0.80})
        self.assertFalse(check.passed)
        self.assertTrue(check.failures)

    def test_unmeasured_metric_counts_as_failure(self):
        check = check_admissibility("m", "planner", {})
        self.assertFalse(check.passed)
        self.assertIn("valid_action_rate", check.missing_metrics)

    def test_passing_model_is_admitted(self):
        self.assertTrue(check_admissibility("m", "planner", {"valid_action_rate": 0.99}).passed)

    def test_score_is_weighted_and_penalised(self):
        clean = score_role("a", "planner", {
            "task_completion": 1.0, "conditional_step_accuracy": 1.0,
            "required_tool_recall": 1.0, "stop_condition_accuracy": 1.0,
            "run_to_run_agreement": 1.0, "unnecessary_tool_rate": 0.0,
        })
        noisy = score_role("b", "planner", {
            "task_completion": 1.0, "conditional_step_accuracy": 1.0,
            "required_tool_recall": 1.0, "stop_condition_accuracy": 1.0,
            "run_to_run_agreement": 1.0, "unnecessary_tool_rate": 1.0,
        })
        self.assertAlmostEqual(clean.score, 1.0)
        self.assertLess(noisy.score, clean.score)

    def test_ranking_excludes_inadmissible_models(self):
        good = score_role("good", "planner", {"task_completion": 1.0}, admissible=True)
        bad = score_role("bad", "planner", {"task_completion": 1.0}, admissible=False)
        self.assertEqual([item.model for item in rank([good, bad])], ["good"])

    def test_no_model_qualified_when_all_rejected(self):
        rejected = [score_role("m", "planner", {}, admissible=False)]
        self.assertEqual(selection_status({"planner": rejected}), STATUS_NO_MODEL_QUALIFIED)

    def test_single_model_requires_being_within_tolerance(self):
        by_role = {
            "planner": [
                score_role("a", "planner", {"task_completion": 1.0}),
                score_role("b", "planner", {"task_completion": 0.5}),
            ],
            "free_report": [
                score_role("a", "free_report", {"claim_precision": 1.0}),
                score_role("b", "free_report", {"claim_precision": 1.0}),
            ],
        }
        model, reason = select_single_model(by_role)
        self.assertEqual(model, "a")
        self.assertIn("perdita", reason)

    def test_single_model_refused_when_loss_too_large(self):
        by_role = {
            "planner": [score_role("a", "planner", {"task_completion": 1.0})],
            "free_report": [score_role("b", "free_report", {"claim_precision": 1.0})],
        }
        model, reason = select_single_model(by_role)
        self.assertIsNone(model)
        self.assertIn("ammissibile", reason)


# ── Riproducibilita' ───────────────────────────────────────────────────────────


class ReproducibilityTest(TestCase):
    def test_aggregate_sums_terms_instead_of_averaging_ratios(self):
        first = MetricResult("m", numerator=1, denominator=2)
        second = MetricResult("m", numerator=1, denominator=8)
        combined = combine("m", [first, second])
        self.assertEqual(combined.numerator, 2)
        self.assertEqual(combined.denominator, 10)
        self.assertAlmostEqual(combined.value, 0.2)
        self.assertNotAlmostEqual(combined.value, (0.5 + 0.125) / 2)

    def test_aggregate_carries_small_sample_caveats(self):
        evaluation = CaseEvaluation(
            case_id="c", category="KNOWN_TRAVERSAL", architecture="deterministic",
            metrics={"m": MetricResult("m", 1, 1)},
        )
        result = aggregate([evaluation])
        self.assertTrue(result.caveats)
        self.assertTrue(
            any("quattro casi" in caveat.casefold() for caveat in result.caveats)
        )

    def test_run_config_records_seed_and_context(self):
        config = RunConfig(seed=13, num_ctx=16384)
        payload = config.as_dict()
        self.assertEqual(payload["seed"], 13)
        self.assertEqual(payload["num_ctx"], 16384)
        self.assertIn("prompt_version", payload)

    def test_model_metadata_records_everything_needed_to_reproduce(self):
        spec = ModelSpec(
            "planner", "qwen3:14b", OllamaEndpoint("http://localhost:11434"),
            config=RunConfig(seed=991), explicit_revision="r1",
        )
        metadata = spec.as_metadata()
        for key in (
            "model_name", "model_revision", "structured_output_mode", "endpoint_type",
            "temperature", "num_ctx", "seed", "prompt_version", "schema_version",
        ):
            self.assertIn(key, metadata)

    def test_metadata_contains_no_api_key(self):
        endpoint = OllamaEndpoint("https://api.ollama.com", api_key="super-secret-key")
        spec = ModelSpec("planner", "m:1b", endpoint)
        self.assertNotIn("super-secret-key", json.dumps(spec.as_metadata()))


class SourceProfileTest(TestCase):
    def test_eight_profiles_exist(self):
        self.assertEqual(len(default_repository()), 8)

    def test_lookup_by_three_keys(self):
        repo = default_repository()
        self.assertIsNotNone(repo.by_pmid("29151359"))
        self.assertIsNotNone(repo.by_source_id("S-C1-1"))
        self.assertIsNotNone(repo.by_nct("NCT02296125"))

    def test_none_is_frozen_before_second_review(self):
        self.assertEqual(default_repository().frozen_count(), 0)

    def test_missing_profile_raises_with_guidance(self):
        with self.assertRaises(ProfileNotFound) as ctx:
            default_repository().require("99999999")
        self.assertIn("annotazione umana", str(ctx.exception))

    def test_profiles_are_not_machine_extracted(self):
        for profile in default_repository():
            self.assertEqual(profile.review_status, "human_reviewed")
            self.assertIn("human", profile.extraction_method)
