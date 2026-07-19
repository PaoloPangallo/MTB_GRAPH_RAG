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
        self.assertEqual(result.agentic.metrics.blocked_claims, 1)
        self.assertNotEqual(result.deterministic.llm_roles, result.agentic.llm_roles)

    def test_demo_does_not_invent_evidence_for_unknown_case(self):
        result = compare_architectures(self._request("BRAF", "V600E", "Melanoma"))
        self.assertEqual(result.deterministic.evidence, [])
        self.assertEqual(result.agentic.evidence, [])
        self.assertEqual(result.summary.shared_sources, [])
