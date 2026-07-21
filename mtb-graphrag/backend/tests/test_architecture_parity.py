"""Le due architetture differiscono solo nella raccolta.

È l'affermazione centrale della tesi, quindi va verificata direttamente: stessi
nodi di controllo, stessi tipi di evento, stesso ledger, stessa verifica —
e come unica differenza osservabile chi decide l'ordine degli strumenti.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

from backend.api.schemas import ClaimCheck
from backend.pipeline.agentic.ledger import EventLedger
from backend.pipeline.control.contracts import CaseContext
from backend.pipeline.control.recorder import ActionRecorder
from backend.pipeline.control.runner import run_verified_pipeline
from backend.pipeline.control.strategies.agentic_plan import AgenticPlanStrategy
from backend.pipeline.control.strategies.fixed_plan import (
    FIXED_PLANS_BY_GOAL,
    FixedPlanStrategy,
    plan_for_goal,
)
from backend.pipeline.control.verification.source_port import (
    ScriptedSourceVerifier,
    default_model_revision,
)

_EVIDENCE = {
    "subject": "Osimertinib",
    "relation": "SENSITIVITY",
    "object": "EGFR L858R",
    "context": "Lung Adenocarcinoma",
    "pmid": 27959700,
    "evidence_level": "A",
}


def _case(goal: str = "general-review") -> CaseContext:
    return CaseContext(
        gene="EGFR", variant="L858R", tumor_type="Lung Adenocarcinoma",
        alteration_type="point_mutation", therapy_line="first-line", mtb_goal=goal,
    )


def _tools() -> dict:
    return {
        "assess_complexity": lambda s: {**s, "complexity": "moderate"},
        "interpret_variant": lambda s: {
            **s, "escat_tier": "I-A",
            "variant_data": {"evidence_records": [dict(_EVIDENCE)]},
        },
        "identify_targets": lambda s: {
            **s, "drug_candidates": [{"drug_name": "Osimertinib", "evidence_level": "A"}]},
        "match_trials": lambda s: {
            **s, "trial_candidates": [{"nct_id": "NCT02296125", "title": "FLAURA"}]},
        "check_resistance": lambda s: {
            **s, "resistance_data": [{"variant": "T790M", "pmid": 28779021,
                                      "drug_name": "Osimertinib", "evidence_level": "A"}]},
        "enrich_oncokb": lambda s: {**s, "oncokb_enrichment": []},
    }


class _Response:
    def __init__(self, content: str) -> None:
        self.content = content


class _ScriptedPlanner:
    """Planner scriptato con un vero ciclo plan–act–observe.

    Decide uno strumento alla volta osservando lo stato, e non è il piano fisso
    con un altro nome: se lo fosse, la parità passerebbe per la ragione
    sbagliata.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke(self, messages: list[tuple[str, str]]) -> _Response:
        observed = json.loads(messages[1][1])
        self.calls.append(observed)
        allowed = observed["strumenti_consentiti"]
        completed = set(observed["stato"].get("completed_tools", []))
        for candidate in (
            "interpret_variant", "identify_targets", "match_trials", "check_resistance",
        ):
            if candidate in allowed and candidate not in completed:
                return _Response(json.dumps(
                    {"tool": candidate, "rationale": f"serve {candidate}"}
                ))
        return _Response(json.dumps({"tool": "finish", "rationale": "obiettivo raggiunto"}))


def _verification(status: str = "supported_as_written", applicability: str = "compatible"):
    return SimpleNamespace(
        source_support_status=status, applicability_status=applicability,
        source_support_reason="La fonte sostiene la claim.",
        applicability_reason="Contesto coincidente.",
        verification_level="pubmed_abstract", requires_source_review=False,
        requires_clinical_review=False, derived_verified_claim=None,
        source_population=None, source_line=None, source_setting=None,
        source_prerequisites=None,
    )


def _claim_checks(items, verifications) -> list[ClaimCheck]:
    return [
        ClaimCheck(
            claim=f"{item.subject} — {item.relation} — {item.object} ({item.context}).",
            status="supported", reason=v.source_support_reason, source_id=item.source_id,
            verification_level=v.verification_level, requires_human_review=False,
        )
        for item, v in zip(items, verifications)
    ]


def _render_verified(case_label, items, verifications) -> str:
    lines = [
        f"Caso: {case_label}.",
        f"Evidenze documentalmente supportate ({len(items)} come formulate, 0 dopo contestualizzazione):",
    ]
    for item in items:
        lines.append(
            f"- {item.subject} — {item.relation} — {item.object} ({item.context}). [{item.source_id}]"
        )
    return "\n".join(lines)


def _dossier(items, checks, *, verifications=None, state=None):
    entries = [
        SimpleNamespace(
            evidence_id=item.source_id or f"item-{index}",
            claim=f"{item.subject} — {item.relation} — {item.object}",
            source_id=item.source_id,
            source_support_status="supported_as_written",
            applicability_status="compatible",
            dossier_section="supported_compatible",
        )
        for index, item in enumerate(items)
    ]
    return SimpleNamespace(evidence=entries, trial_findings=[], resistance_findings=[])


def _run(strategy, tmp: str, goal: str = "general-review"):
    recorder = ActionRecorder(EventLedger(Path(tmp) / f"{id(strategy)}.sqlite3"))
    verifier = ScriptedSourceVerifier([_verification()] * 6)
    return run_verified_pipeline(
        _case(goal), strategy, recorder=recorder, tools=_tools(),
        source_verifier=verifier, build_dossier=_dossier,
        build_claim_checks=_claim_checks, render_verified=_render_verified,
        mandatory_tools=("interpret_variant", "identify_targets",
                         "check_resistance", "match_trials"),
    )


class ExposedArchitecturesTest(TestCase):
    def test_only_two_orchestration_modes_exist(self) -> None:
        modes = {
            FixedPlanStrategy.orchestration_mode,
            AgenticPlanStrategy.orchestration_mode,
        }

        self.assertEqual(modes, {"deterministic", "agentic"})

    def test_no_d0_d1_a1_terminology_in_the_control_layer(self) -> None:
        root = Path(__file__).resolve().parents[1] / "pipeline" / "control"
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8").casefold()
            for banned in (" d0 ", " d1 ", " a1 ", '"d0"', '"d1"', '"a1"'):
                self.assertNotIn(banned, text, f"{path.name} contiene {banned!r}")


class FixedPlanTest(TestCase):
    def test_plans_are_declared_per_goal_not_a_single_maximal_plan(self) -> None:
        self.assertNotEqual(
            plan_for_goal("treatment-evidence"), plan_for_goal("general-review")
        )
        self.assertEqual(plan_for_goal("resistance"), ("interpret_variant", "check_resistance"))

    def test_unknown_goal_falls_back_to_general_review(self) -> None:
        self.assertEqual(plan_for_goal("sconosciuto"), FIXED_PLANS_BY_GOAL["general-review"])

    def test_clinical_trials_plan_respects_the_dependency_on_targets(self) -> None:
        plan = plan_for_goal("clinical-trials")

        self.assertIn("identify_targets", plan)
        self.assertLess(plan.index("identify_targets"), plan.index("match_trials"))

    def test_deterministic_run_never_invokes_a_planner(self) -> None:
        with TemporaryDirectory() as tmp:
            result = _run(FixedPlanStrategy(), tmp)

            self.assertEqual(result.collection.planner_calls, 0)
            self.assertEqual(result.collection.planning_mode, "fixed_plan")
            actors = {e["actor"] for e in result.events}
            self.assertNotIn("llm_planner", actors)

    def test_fixed_plan_still_emits_plan_decision_events(self) -> None:
        with TemporaryDirectory() as tmp:
            result = _run(FixedPlanStrategy(), tmp)

            decisions = [e for e in result.events if e["event_type"] == "plan_decision"]
            self.assertEqual(len(decisions), 4)
            self.assertEqual(decisions[0]["actor"], "fixed_plan_controller")
            self.assertEqual(decisions[0]["payload"]["planning_mode"], "fixed_plan")

    def test_a_plan_that_misses_a_mandatory_tool_is_visible(self) -> None:
        with TemporaryDirectory() as tmp:
            result = _run(FixedPlanStrategy(plan=("interpret_variant",)), tmp)

            self.assertIn("identify_targets", result.collection.missing_mandatory_tools)
            self.assertIsNotNone(result.collection.incompleteness_reason)


class AgenticPlanTest(TestCase):
    def test_agentic_run_invokes_the_planner(self) -> None:
        with TemporaryDirectory() as tmp:
            result = _run(AgenticPlanStrategy(_ScriptedPlanner()), tmp)

            self.assertGreater(result.collection.planner_calls, 0)
            self.assertEqual(result.collection.planning_mode, "llm_dynamic")
            self.assertIn("llm_planner", {e["actor"] for e in result.events})

    def test_scripted_planner_really_observes_state_between_steps(self) -> None:
        planner = _ScriptedPlanner()
        with TemporaryDirectory() as tmp:
            _run(AgenticPlanStrategy(planner), tmp)

            # Il numero di strumenti già completati cresce fra una chiamata e
            # l'altra: è un vero ciclo plan-act-observe, non un piano fisso.
            completed = [len(c["stato"].get("completed_tools", [])) for c in planner.calls]
            self.assertEqual(completed, sorted(completed))
            self.assertGreater(completed[-1], completed[0])

    def test_fallback_run_is_not_described_as_dynamic_planning(self) -> None:
        class _Failing:
            def invoke(self, messages):
                raise RuntimeError("planner non raggiungibile")

        with TemporaryDirectory() as tmp:
            result = _run(AgenticPlanStrategy(_Failing()), tmp)

            self.assertEqual(result.collection.planning_mode, "safe_fallback")
            self.assertIsNotNone(result.collection.fallback_reason)


class ControlLayerParityTest(TestCase):
    def _both(self, tmp: str):
        return (
            _run(FixedPlanStrategy(), tmp),
            _run(AgenticPlanStrategy(_ScriptedPlanner()), tmp),
        )

    def test_both_architectures_execute_the_same_control_nodes(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            self.assertEqual(
                deterministic.pipeline_nodes_executed, agentic.pipeline_nodes_executed
            )

    def test_both_emit_the_same_control_event_types(self) -> None:
        control_events = {
            "canonical_view_created", "projection_created", "candidate_report_rendered",
            "structural_verification_completed", "source_verification_completed",
            "applicability_evaluated", "verified_report_rendered", "dossier_built",
            "run_completed",
        }
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            det_types = {e["event_type"] for e in deterministic.events}
            ag_types = {e["event_type"] for e in agentic.events}

            self.assertTrue(control_events <= det_types)
            self.assertTrue(control_events <= ag_types)
            # L'unica differenza ammessa riguarda l'orchestrazione.
            self.assertEqual(det_types - ag_types - {"collection_completed"}, set())

    def test_both_write_a_valid_append_only_chain(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            self.assertTrue(deterministic.ledger_valid)
            self.assertTrue(agentic.ledger_valid)
            self.assertGreater(len(deterministic.events), 0)
            self.assertGreater(len(agentic.events), 0)

    def test_both_report_the_same_stage_keys(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            self.assertEqual(
                set(deterministic.timings_dict()), set(agentic.timings_dict())
            )

    def test_both_produce_a_canonical_view_by_replay(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            for result in (deterministic, agentic):
                self.assertGreater(result.canonical_view.records_out, 0)
                self.assertEqual(result.canonical_view.run_id, result.run_id)
                self.assertEqual(result.canonical_view.replay_fidelity, "full")

    def test_both_run_the_same_structural_and_source_verification(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            for result in (deterministic, agentic):
                self.assertEqual(result.candidate_verdict.stage, "candidate")
                self.assertEqual(result.final_verdict.stage, "final")
                self.assertEqual(result.dossier_verdict.stage, "dossier")
                self.assertGreater(len(result.source_outcome.verifications), 0)

    def test_the_only_difference_is_who_decides_the_tool_order(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            self.assertEqual(deterministic.collection.planner_calls, 0)
            self.assertGreater(agentic.collection.planner_calls, 0)
            # Stesso insieme di strumenti raggiunto per vie diverse.
            self.assertEqual(
                set(deterministic.collection.tool_path),
                set(agentic.collection.tool_path),
            )

    def test_narration_is_not_applied_by_default(self) -> None:
        with TemporaryDirectory() as tmp:
            deterministic, agentic = self._both(tmp)

            for result in (deterministic, agentic):
                self.assertFalse(result.narration_applied)
                self.assertIsNone(result.narration_verdict)


class ModelRevisionTest(TestCase):
    def test_model_revision_uses_the_real_model_identifier(self) -> None:
        revision = default_model_revision()

        self.assertNotEqual(revision, "default")
        self.assertTrue(revision.startswith("ollama:"))

    def test_temperature_is_not_part_of_the_model_revision(self) -> None:
        # La temperatura non è una revisione del modello: mescolarla renderebbe
        # la chiave di cache incomparabile con l'identificatore del provider.
        self.assertNotIn("0.0", default_model_revision())

    def test_explicit_override_wins(self) -> None:
        import os

        os.environ["SOURCE_VERIFIER_MODEL_REVISION"] = "ollama:pinned-model@sha256"
        try:
            self.assertEqual(default_model_revision(), "ollama:pinned-model@sha256")
        finally:
            del os.environ["SOURCE_VERIFIER_MODEL_REVISION"]
