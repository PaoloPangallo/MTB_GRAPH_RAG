import unittest
from pathlib import Path

from benchmarks.mtb_evidence.ontology_shadow_mvp import EntityNormalizer, OntologyRegistry, OntologyShadowEvaluator


ROOT = Path(__file__).resolve().parents[2]


class OntologyRequiredCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = OntologyRegistry.from_local_assets(ROOT)
        cls.evaluator = OntologyShadowEvaluator(cls.registry, EntityNormalizer(cls.registry))

    def assert_match(self, query, claim, entity_type, expected):
        self.assertEqual(self.evaluator.compare(query, claim, entity_type).match_type, expected)

    def test_exact_synonym_descendant_ancestor(self):
        self.assert_match("EGFR", "EGFR", "gene", "EXACT")
        self.assert_match("EGFR L858R", "EGFR p.L858R", "variant", "SYNONYM")
        self.assert_match("Non-Small Cell Lung Cancer", "Lung Adenocarcinoma", "disease", "DESCENDANT")
        self.assert_match("Lung Adenocarcinoma", "Non-Small Cell Lung Cancer", "disease", "ANCESTOR")

    def test_related_incompatible_unknown(self):
        self.assert_match("FGFR2 Fusion", "FGFR2::BICC1 Fusion", "variant", "RELATED")
        self.assert_match("RMI2", "FGFR2::BICC1 Fusion", "variant", "INCOMPATIBLE")
        self.assert_match("melanoma", "melanoma", "disease", "UNKNOWN")

    def test_same_gene_different_variant_and_formulation(self):
        self.assert_match("EGFR L858R", "EGFR Exon 19 Deletion", "variant", "INCOMPATIBLE")
        salt = self.evaluator.compare("alectinib", "alectinib hydrochloride", "intervention")
        self.assertEqual(salt.match_type, "RELATED")
        self.assertFalse(salt.compatible_candidate)

    def test_composition_and_disease_incompatibility(self):
        self.assert_match("ALK Fusion AND ALK G1202R", "ALK G1202R AND v::ALK Fusion", "variant", "SYNONYM")
        self.assert_match("NSCLC", "Intrahepatic Cholangiocarcinoma", "disease", "INCOMPATIBLE")


if __name__ == "__main__":
    unittest.main()
