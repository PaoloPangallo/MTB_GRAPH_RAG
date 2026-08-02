import json
import unittest
from pathlib import Path

from benchmarks.mtb_evidence.ontology_shadow_mvp import (
    EntityNormalizer,
    OntologyConcept,
    OntologyRegistry,
    OntologyShadowEvaluator,
)


ROOT = Path(__file__).resolve().parents[2]


class OntologyShadowMvpTests(unittest.TestCase):
    def setUp(self):
        registry = OntologyRegistry.from_local_assets(ROOT)
        self.evaluator = OntologyShadowEvaluator(registry, EntityNormalizer(registry))

    def test_class_match_is_only_available_from_an_explicit_local_fixture(self):
        registry = OntologyRegistry()
        parent = OntologyConcept("intervention:class", "LOCAL:CLASS", "local class", "intervention")
        child = OntologyConcept("intervention:member", "LOCAL:MEMBER", "local member", "intervention")
        registry.add_concept(parent)
        registry.add_concept(child)
        registry.add_relation(parent.registry_key, child.registry_key, "test fixture", "test/1")
        child.relation_kinds[parent.registry_key] = "class_of"
        evaluator = OntologyShadowEvaluator(registry, EntityNormalizer(registry))
        self.assertEqual(evaluator.compare("local class", "local member", "intervention").match_type, "CLASS_MATCH")

    def test_runtime_fields_are_not_touched(self):
        claim = {"claim_id": "x", "bucket": "primary", "score": 1.25, "rank": 3}
        before = json.loads(json.dumps(claim))
        self.evaluator.evaluate_claim(claim, {"disease_context": "NSCLC", "biomarker_context": "EGFR L858R"})
        self.assertEqual(claim, before)


if __name__ == "__main__":
    unittest.main()
