from unittest import TestCase

from backend.api.schemas import ArchitectureComparisonRequest, EvidenceItem
from backend.comparison.service import _canonical_evidence, compare_architectures


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

        self.assertEqual(
            result.deterministic.dossier.review_evidence[0].support_status,
            "not_checked",
        )
        self.assertEqual(
            result.agentic.dossier.supported_evidence[0].source_id,
            "PMID:29151359",
        )
        self.assertEqual(
            result.agentic.dossier.supported_evidence[0].applicability_status,
            "indeterminate",
        )
        self.assertEqual(
            result.agentic.dossier.excluded_evidence[0].claim,
            "Il caso presenta amplificazione di MET.",
        )
        self.assertEqual(
            result.agentic.dossier.excluded_evidence[0].applicability_status,
            "indeterminate",
        )
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
        self.assertEqual(
            dossier.supported_evidence[0].applicability_status,
            "compatible",
        )

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
