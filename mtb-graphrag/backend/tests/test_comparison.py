from types import SimpleNamespace
from unittest import TestCase

from backend.api.schemas import ArchitectureComparisonRequest, EvidenceItem
from backend.comparison.live_runs import build_limitations, build_trace
from backend.comparison.service import (
    _build_dossier,
    _canonical_evidence,
    _render_verified_report,
    compare_architectures,
)


_DOSSIER_SECTIONS = {
    "supported_compatible",
    "supported_indeterminate",
    "supported_not_compatible",
    "review",
    "excluded",
}


class ComparisonDemoTest(TestCase):
    def _request(self, gene="EGFR", variant="L858R", tumor="Lung Adenocarcinoma"):
        return ArchitectureComparisonRequest(
            gene=gene,
            variant=variant,
            tumor_type=tumor,
            alteration_type="point_mutation",
            therapy_line="first-line",
            enrich_with_oncokb=False,
            execution_mode="demo",
        )

    def test_demo_exposes_same_source_and_different_llm_roles(self):
        result = compare_architectures(self._request())
        self.assertEqual(result.summary.shared_sources, ["PMID:29151359"])
        self.assertEqual(result.deterministic.metrics.evidence_count, 1)
        self.assertEqual(result.deterministic.metrics.verified_claims, 0)
        self.assertEqual(result.agentic.metrics.blocked_claims, 1)
        self.assertNotEqual(result.deterministic.llm_roles, result.agentic.llm_roles)

    def test_demo_exposes_the_proposed_verifiable_control_layer(self):
        # Ambito demo invariato: questa fixture (inclusa la fault injection MET)
        # non viene qui usata come prova di validità clinica, solo come
        # dimostrazione del contratto architetturale.
        result = compare_architectures(self._request())
        stages = [step.stage for step in result.agentic.trace]
        self.assertIn("Event log append-only", stages)
        self.assertIn("Vista canonica", stages)
        self.assertIn("Proiezione pertinente", stages)
        self.assertIn("Rendering deterministico", stages)
        self.assertIn("Verifica delle claim", stages)
        self.assertIn("Narrazione opzionale", stages)
        blocked = [check for check in result.agentic.claim_checks if check.status == "blocked"]
        self.assertEqual([check.claim for check in blocked], ["Il caso presenta amplificazione di MET."])

    def test_demo_does_not_invent_evidence_for_unknown_case(self):
        result = compare_architectures(self._request("BRAF", "V600E", "Melanoma"))
        self.assertEqual(result.deterministic.evidence, [])
        self.assertEqual(result.agentic.evidence, [])
        self.assertEqual(result.summary.shared_sources, [])

    def test_common_dossier_separates_unverified_supported_and_excluded_items(self):
        result = compare_architectures(self._request())

        deterministic_review = [
            item for item in result.deterministic.dossier.evidence if item.dossier_section == "review"
        ]
        self.assertEqual(deterministic_review[0].source_support_status, "uncertain")

        # Senza un verificatore fonte-per-fonte reale (percorso demo), l'evidenza
        # EGFR/osimertinib resta documentalmente supportata ma con applicabilità
        # onestamente indeterminata — mai "compatible" per default fabbricato.
        agentic_supported = [
            item for item in result.agentic.dossier.evidence
            if item.dossier_section == "supported_indeterminate"
        ]
        self.assertEqual(agentic_supported[0].source_id, "PMID:29151359")
        self.assertEqual(agentic_supported[0].applicability_status, "indeterminate")

        agentic_excluded = [
            item for item in result.agentic.dossier.evidence if item.dossier_section == "excluded"
        ]
        self.assertEqual(agentic_excluded[0].claim, "Il caso presenta amplificazione di MET.")
        self.assertEqual(agentic_excluded[0].applicability_status, "indeterminate")

        self.assertIn("Stadio", result.agentic.dossier.missing_data)

    def test_complete_clinical_context_is_preserved_in_the_dossier(self):
        request = self._request()
        request.disease_stage = "IV"
        request.disease_setting = "metastatic"
        request.prior_therapies = ["Nessuno"]
        request.prior_response = "Non applicabile"
        request.ecog_status = 1
        request.cns_metastases = False
        request.co_alterations = ["Nessuna nota"]
        request.jurisdiction = "Italia"
        request.mtb_goal = "treatment-evidence"

        dossier = compare_architectures(request).agentic.dossier
        values = {field.key: field.value for field in dossier.case_summary}

        self.assertEqual(dossier.missing_data, [])
        self.assertEqual(values["ecog_status"], "1")
        self.assertEqual(values["cns_metastases"], "Assenti")

        # Anche con contesto clinico completo nella richiesta, senza una vera
        # verifica LLM l'applicabilità resta "indeterminate": un contesto
        # completo nella richiesta non fabbrica un "compatible" fittizio.
        supported = [item for item in dossier.evidence if item.source_support_status == "supported_as_written"]
        self.assertEqual(supported[0].applicability_status, "indeterminate")
        self.assertEqual(supported[0].dossier_section, "supported_indeterminate")

    def test_canonical_view_removes_exact_duplicate_evidence(self):
        item = EvidenceItem(
            subject="EGFR L858R",
            relation="Sensitivity/Response",
            object="OSIMERTINIB",
            context="Lung Non-small Cell Carcinoma",
            source_id="PMID:37937763",
            provenance="fixture",
        )

        canonical = _canonical_evidence([item, item.model_copy()])

        self.assertEqual(len(canonical), 1)
        self.assertEqual(canonical[0].source_id, "PMID:37937763")

    def test_dossier_evidence_sections_form_a_clean_partition(self):
        """Vista canonica unica: ogni evidenza compare in esattamente una
        sezione, nessuna evidenza è persa e gli evidence_id sono univoci."""
        result = compare_architectures(self._request())
        for run in (result.deterministic, result.agentic):
            dossier = run.dossier
            sections = {item.dossier_section for item in dossier.evidence}
            self.assertTrue(sections <= _DOSSIER_SECTIONS)
            ids = [item.evidence_id for item in dossier.evidence]
            self.assertEqual(len(ids), len(set(ids)))
            by_section: dict[str, list] = {}
            for item in dossier.evidence:
                by_section.setdefault(item.dossier_section, []).append(item)
            self.assertEqual(sum(len(items) for items in by_section.values()), len(dossier.evidence))

    def test_trial_findings_are_deduplicated_by_nct_id_in_the_final_projection(self):
        """NCT07183189 osservato due volte nel run reale: anche se
        trial_candidates nello stato aggregato contiene lo stesso NCT ID più
        volte (es. raccolta multi-step), la proiezione finale del dossier non
        deve mai mostrarlo due volte."""
        request = self._request()
        state = {
            "trial_candidates": [
                {"nct_id": "NCT07183189", "title": "Trial ripetuto", "phase": "2", "status": "Recruiting", "drug_tested": "osimertinib"},
                {"nct_id": "NCT07183189", "title": "Trial ripetuto", "phase": "2", "status": "Recruiting", "drug_tested": "amivantamab"},
            ],
            "resistance_data": [],
        }
        dossier = _build_dossier(request, [], [], state=state)
        nct_ids = [finding.title.split(":")[0] for finding in dossier.trial_findings]
        self.assertEqual(nct_ids.count("NCT07183189"), 1)
        self.assertEqual(len(dossier.trial_findings), 1)

class TraceBuilderTest(TestCase):
    """La trace e' costruita dai fatti della run e non dichiara fasi non eseguite.

    Le asserzioni cercano lo stadio per nome, non per posizione: l'accoppiamento
    posizionale era esso stesso un difetto.
    """

    def _result(self, **overrides):
        collection = SimpleNamespace(
            planning_mode="llm_dynamic", tool_path=["interpret_variant"],
            fallback_reason=None, planner_calls=3, planner_elapsed_ms=120,
            errors=[], mandatory_tools=[], missing_mandatory_tools=[],
            incompleteness_reason=None, tool_call_timings=(),
        )
        for key in ("planning_mode", "tool_path", "fallback_reason", "planner_calls",
                    "errors", "mandatory_tools", "missing_mandatory_tools"):
            if key in overrides:
                setattr(collection, key, overrides.pop(key))

        verdict = SimpleNamespace(status="pass", coverage=1.0, violations=(), warnings=())
        base = dict(
            orchestration_mode="agentic", collection=collection,
            events=[{}] * 12, ledger_valid=True,
            canonical_view=SimpleNamespace(records_in=5, records_out=4,
                                           replay_fidelity="full", records=()),
            projection=SimpleNamespace(admitted=[1, 2], excluded=[3]),
            candidate_report="x" * 40,
            candidate_verdict=verdict, final_verdict=verdict, dossier_verdict=verdict,
            evidence_items=[1, 2],
            source_outcome=SimpleNamespace(model_revision="ollama:test-model"),
            repair_actions=(), escalation=None,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def _step(self, trace, stage_fragment):
        return next(step for step in trace if stage_fragment.lower() in step.stage.lower())

    def test_dynamic_planning_is_reported_as_such(self):
        step = self._step(build_trace(self._result()), "Orchestrazione")

        self.assertIn("Il planner ha scelto iterativamente gli strumenti", step.detail)
        self.assertEqual(step.status, "completed")

    def test_safe_fallback_is_never_described_as_dynamic_planning(self):
        result = self._result(planning_mode="safe_fallback", fallback_reason="timeout")

        step = self._step(build_trace(result), "Orchestrazione")

        self.assertIn("non dimostra pianificazione agentica dinamica", step.detail)
        self.assertNotIn("ha scelto iterativamente", step.detail)
        self.assertIn("timeout", step.detail)

    def test_fixed_plan_orchestration_names_the_declared_plan(self):
        result = self._result(orchestration_mode="deterministic",
                              planning_mode="fixed_plan", planner_calls=0)

        step = self._step(build_trace(result), "Orchestrazione")

        self.assertIn("Piano fisso dichiarato prima dell", step.detail)
        self.assertEqual(step.actor, "Controller a piano fisso")

    def test_repair_step_is_not_claimed_when_no_repair_ran(self):
        step = self._step(build_trace(self._result()), "Riparazione")

        self.assertIn("Nessuna riparazione necessaria", step.detail)

    def test_repair_step_reports_the_executed_kind_when_it_ran(self):
        action = SimpleNamespace(kind="rendering", tool_name=None,
                                 triggered_by=("MISSING_CLAIM",))

        step = self._step(build_trace(self._result(repair_actions=(action,))), "Riparazione")

        self.assertIn("rigenerazione del report", step.detail)
        self.assertIn("MISSING_CLAIM", step.detail)

    def test_canonical_view_step_reports_the_deduplication(self):
        step = self._step(build_trace(self._result()), "Vista canonica")

        self.assertIn("5 record osservati ridotti a 4", step.detail)
        self.assertIn("genealogia conservata", step.detail)

    def test_projection_step_reports_admitted_and_excluded(self):
        step = self._step(build_trace(self._result()), "Proiezione")

        self.assertIn("2 record ammessi", step.detail)
        self.assertIn("1 esclusi con motivazione", step.detail)

    def test_both_architectures_produce_the_same_trace_structure(self):
        agentic = build_trace(self._result())
        deterministic = build_trace(
            self._result(orchestration_mode="deterministic",
                         planning_mode="fixed_plan", planner_calls=0)
        )

        self.assertEqual([s.stage for s in agentic], [s.stage for s in deterministic])
        self.assertEqual([s.order for s in agentic], list(range(1, len(agentic) + 1)))


class LimitationsTest(TestCase):
    def _result(self, **overrides):
        collection = SimpleNamespace(
            planning_mode="llm_dynamic", missing_mandatory_tools=[], errors=[],
        )
        for key in ("planning_mode", "missing_mandatory_tools", "errors"):
            if key in overrides:
                setattr(collection, key, overrides.pop(key))
        base = dict(
            collection=collection,
            canonical_view=SimpleNamespace(replay_fidelity="full"),
            escalation=None,
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_ledger_is_described_as_tamper_evident_not_absolutely_immutable(self):
        joined = " ".join(build_limitations(self._result()))

        self.assertIn("append-only e tamper-evident", joined)
        self.assertIn("non immutabile in senso assoluto", joined)

    def test_research_prototype_boundary_is_always_declared(self):
        self.assertTrue(
            any("Prototipo di ricerca" in item for item in build_limitations(self._result()))
        )

    def test_safe_fallback_limitation_never_claims_dynamic_planning(self):
        limitations = build_limitations(self._result(planning_mode="safe_fallback"))

        self.assertTrue(
            any("non dimostra pianificazione agentica dinamica" in item for item in limitations)
        )

    def test_missing_mandatory_tools_are_surfaced(self):
        limitations = build_limitations(
            self._result(missing_mandatory_tools=["check_resistance"])
        )

        self.assertTrue(any("check_resistance" in item for item in limitations))

    def test_sanitized_runtime_errors_are_surfaced_without_raw_exception_text(self):
        limitations = build_limitations(self._result(
            errors=["check_resistance: servizio esterno non disponibile"]
        ))

        errors = [item for item in limitations if item.startswith("Errori durante la raccolta")]
        self.assertEqual(len(errors), 1)
        self.assertIn("servizio esterno non disponibile", errors[0])

    def test_no_error_limitation_when_collection_succeeded(self):
        self.assertFalse(
            any(item.startswith("Errori durante la raccolta")
                for item in build_limitations(self._result()))
        )

    def test_degraded_replay_fidelity_is_declared(self):
        limitations = build_limitations(self._result(
            canonical_view=SimpleNamespace(replay_fidelity="degraded_v1_events")
        ))

        self.assertTrue(any("Fedelt" in item and "replay" in item for item in limitations))


class RenderVerifiedReportTest(TestCase):
    _BANNED_PHRASES = ("terapia raccomandata", "terapia indicata", "paziente eleggibile", "opzione applicabile")

    def _verification(self, **overrides):
        base = dict(
            source_support_status="supported_as_written",
            source_support_reason="La fonte documenta il proprio record.",
            source_population=None,
            source_line=None,
            source_setting=None,
            source_prerequisites=None,
            derived_verified_claim=None,
            applicability_status="indeterminate",
            applicability_reason="Dati clinici insufficienti per decidere.",
        )
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_avoids_recommendation_wording_when_not_compatible(self):
        item = EvidenceItem(
            subject="EGFR T790M",
            relation="Sensitivity/Response",
            object="osimertinib",
            context="NSCLC post-progressione",
            source_id="PMID:27959700",
            provenance="fixture",
        )
        verification = self._verification(
            source_population="NSCLC EGFR T790M",
            source_line="seconda linea",
            source_setting="post-progressione",
            source_prerequisites="progressione a un precedente EGFR-TKI",
            applicability_status="not_compatible",
            applicability_reason="Richiesta first-line esplicita; la fonte riguarda solo pazienti post-progressione.",
        )
        report = _render_verified_report("EGFR T790M · NSCLC · first-line", [item], [verification])

        for phrase in self._BANNED_PHRASES:
            self.assertNotIn(phrase, report.lower())
        self.assertIn("PMID:27959700", report)
        self.assertIn("post-progressione", report)

    def test_avoids_recommendation_wording_when_applicability_indeterminate(self):
        item = EvidenceItem(
            subject="EGFR L858R",
            relation="Sensitivity/Response",
            object="osimertinib",
            context="NSCLC",
            source_id="PMID:29151359",
            provenance="fixture",
        )
        verification = self._verification(applicability_status="indeterminate")
        report = _render_verified_report("EGFR L858R · NSCLC · first-line", [item], [verification])

        for phrase in self._BANNED_PHRASES:
            self.assertNotIn(phrase, report.lower())
        self.assertIn("indeterminata", report)
