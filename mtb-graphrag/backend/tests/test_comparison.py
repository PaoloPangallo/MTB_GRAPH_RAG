from types import SimpleNamespace
from unittest import TestCase

from backend.api.schemas import ArchitectureComparisonRequest, EvidenceItem
from backend.comparison.service import (
    _agentic_guarantees,
    _agentic_trace,
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
        supported = [item for item in dossier.evidence if item.source_support_status == "supported"]
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


class AgenticTraceTest(TestCase):
    def _collection(self, **overrides):
        base = {
            "planning_mode": "llm_dynamic",
            "tool_path": ["interpret_variant"],
            "fallback_reason": None,
            "run_id": "run-fixture",
            "planner_attempts": 0,
            "planner_elapsed_ms": 0,
            "errors": [],
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_trace_reflects_llm_dynamic_planning(self):
        collection = self._collection(tool_path=["interpret_variant", "assess_complexity"])
        trace = _agentic_trace(collection, evidence=[], events=[], ledger_valid=True, supported=1, blocked=0, uncertain=0)
        planning_step, collection_step = trace[1], trace[2]

        self.assertEqual(planning_step.detail, "Il planner ha scelto iterativamente gli strumenti.")
        self.assertEqual(planning_step.status, "completed")
        self.assertIn("ha alimentato la decisione successiva", collection_step.detail)
        self.assertEqual(collection_step.status, "completed")

    def test_trace_reflects_safe_fallback_planning(self):
        collection = self._collection(planning_mode="safe_fallback", fallback_reason="timeout")
        trace = _agentic_trace(collection, evidence=[], events=[], ledger_valid=True, supported=0, blocked=0, uncertain=0)
        planning_step, collection_step = trace[1], trace[2]

        self.assertEqual(
            planning_step.detail,
            "È stato eseguito un piano tipizzato predefinito; questa esecuzione non "
            "dimostra pianificazione agentica dinamica.",
        )
        self.assertEqual(planning_step.status, "warning")
        self.assertNotIn("ha alimentato la decisione successiva", collection_step.detail)
        self.assertEqual(collection_step.status, "warning")
        self.assertIn("timeout", collection_step.detail)

    def test_verification_step_reports_both_independent_axes(self):
        collection = self._collection()
        trace = _agentic_trace(
            collection, evidence=[], events=[], ledger_valid=True,
            supported=2, blocked=1, uncertain=1,
            compatible=1, indeterminate_applicability=2, not_compatible=1,
        )
        verification_step = trace[7]
        self.assertEqual(verification_step.order, 8)
        self.assertIn("due assi indipendenti", verification_step.detail)
        self.assertIn("2 supportate, 1 bloccate, 1 inviate a revisione", verification_step.detail)
        self.assertIn("1 compatibili, 2 indeterminate, 1 non compatibili", verification_step.detail)

    def test_repair_step_distinguishes_excluded_from_visible_context(self):
        collection = self._collection()
        trace = _agentic_trace(collection, evidence=[], events=[], ledger_valid=True, supported=0, blocked=0, uncertain=0)
        repair_step = trace[8]
        self.assertEqual(repair_step.order, 9)
        self.assertIn("escluse dal report", repair_step.detail)
        self.assertIn("non come opzioni per il caso", repair_step.detail)

    def test_verified_report_step_clarifies_documentary_not_clinical_meaning(self):
        collection = self._collection()
        trace = _agentic_trace(collection, evidence=[], events=[], ledger_valid=True, supported=0, blocked=0, uncertain=0)
        verified_report_step = trace[9]
        self.assertEqual(verified_report_step.order, 10)
        self.assertIn("non clinicamente raccomandato", verified_report_step.detail)


class AgenticGuaranteesTest(TestCase):
    def _collection(self, **overrides):
        base = {
            "planning_mode": "llm_dynamic",
            "run_id": "run-fixture",
            "fallback_reason": None,
            "planner_attempts": 0,
            "planner_elapsed_ms": 0,
            "errors": [],
        }
        base.update(overrides)
        return SimpleNamespace(**base)

    def test_llm_dynamic_guarantee_does_not_mention_safe_fallback(self):
        guarantees = _agentic_guarantees(self._collection())
        self.assertEqual(guarantees[0], "Il planner ha scelto iterativamente gli strumenti.")
        self.assertFalse(any("piano sicuro predefinito" in guarantee and "motivo" in guarantee for guarantee in guarantees))

    def test_safe_fallback_guarantee_never_claims_dynamic_planning(self):
        collection = self._collection(
            planning_mode="safe_fallback", fallback_reason="timeout", planner_attempts=2, planner_elapsed_ms=500,
        )
        guarantees = _agentic_guarantees(collection)
        self.assertEqual(
            guarantees[0],
            "È stato eseguito il piano sicuro predefinito; questa esecuzione non "
            "dimostra pianificazione agentica dinamica.",
        )
        self.assertTrue(any("motivo: timeout" in guarantee for guarantee in guarantees))
        self.assertFalse(any(guarantee == "Il planner ha scelto iterativamente gli strumenti." for guarantee in guarantees))

    def test_sanitized_runtime_errors_are_surfaced_without_raw_exception_text(self):
        collection = self._collection(errors=["check_resistance: servizio esterno non disponibile durante l'esecuzione dello strumento"])
        guarantees = _agentic_guarantees(collection)
        escalation = [g for g in guarantees if g.startswith("Escalation runtime")]
        self.assertEqual(len(escalation), 1)
        self.assertIn("servizio esterno non disponibile", escalation[0])

    def test_no_escalation_guarantee_when_no_errors(self):
        guarantees = _agentic_guarantees(self._collection())
        self.assertFalse(any(g.startswith("Escalation runtime") for g in guarantees))


class RenderVerifiedReportTest(TestCase):
    _BANNED_PHRASES = ("terapia raccomandata", "terapia indicata", "paziente eleggibile", "opzione applicabile")

    def _verification(self, **overrides):
        base = dict(
            source_support_status="supported",
            source_support_reason="La fonte documenta il proprio record.",
            source_population=None,
            source_line=None,
            source_setting=None,
            source_prerequisites=None,
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
