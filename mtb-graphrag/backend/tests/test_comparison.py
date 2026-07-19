from unittest import TestCase

from backend.api.schemas import ArchitectureComparisonRequest
from backend.comparison.service import compare_architectures


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
