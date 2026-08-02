from __future__ import annotations

import unittest

from benchmarks.mtb_evidence.unified_dossier_contract.preview import build_preview


class UnifiedDossierPreviewTests(unittest.TestCase):
    def test_four_preview_cases_have_expected_escat_and_abstention(self) -> None:
        preview = build_preview()
        self.assertEqual(
            set(preview["cases"]),
            {"FGFR2_iCCA_derazantinib", "ALK_G1202R_NSCLC_alectinib", "EGFR_L858R_NSCLC_osimertinib", "RMI2_NSCLC"},
        )
        self.assertEqual(preview["cases"]["FGFR2_iCCA_derazantinib"]["claim_extensions"]["CLM-1d3ba8b6ae49232969c7"]["clinical_actionability"]["status"], "INCOMPLETE")
        self.assertEqual(preview["cases"]["ALK_G1202R_NSCLC_alectinib"]["claim_extensions"]["CLM-0f234bc9c53847910521"]["clinical_actionability"]["status"], "NOT_ASSESSED")
        self.assertEqual(preview["cases"]["EGFR_L858R_NSCLC_osimertinib"]["claim_extensions"]["CLM-1ee5f9a16a678cebf993"]["clinical_actionability"]["status"], "NOT_ASSESSED")
        self.assertEqual(preview["cases"]["RMI2_NSCLC"]["core_result"]["abstention"], True)
        self.assertEqual(preview["cases"]["RMI2_NSCLC"]["claim_extensions"], {})

    def test_preview_separates_diagnostic_records_and_has_no_fixture_escat(self) -> None:
        preview = build_preview()
        for dossier in preview["cases"].values():
            self.assertNotIn("TEST_FIXTURE_ONLY", str(dossier))
            self.assertEqual(dossier["module_status"]["escat"]["maturity"], "RESEARCH_DRAFT")
            self.assertFalse(dossier["module_status"]["escat"]["available"])
        diagnostic = preview["cases"]["FGFR2_iCCA_derazantinib"]["diagnostic_context"]
        self.assertTrue(diagnostic["limitations"])
        self.assertIn("disease context missing", " ".join(diagnostic["limitations"]).lower())


if __name__ == "__main__":
    unittest.main()
