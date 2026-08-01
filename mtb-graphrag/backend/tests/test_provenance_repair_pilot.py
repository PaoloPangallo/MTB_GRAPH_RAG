from __future__ import annotations

import unittest

from backend.pipeline.evidence.corpus.provenance_repair_pilot import (
    AMBIGUOUS_PARENT_PROVENANCE,
    CLAIM_PUBLICATION_IDENTIFIER_ONLY,
    CLAIM_VERIFIED_LOCATOR,
    PARENT_PUBLICATION_AVAILABLE,
    apply_decision,
    decide_propagation,
)


def make_claim(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "claim_id": "CLM-pilot",
        "claim_type": "atomic_intervention_claim",
        "source_unit_ids": [],
        "locators": [],
        "provenance": {},
    }
    value.update(overrides)
    return value


def make_parent(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "parent_id": "GEP-pilot",
        "source_ids": ["PUBMED:12345678"],
        "source_record_ids": ["evidence:pilot#row-000"],
    }
    value.update(overrides)
    return value


class ProvenanceRepairPilotTest(unittest.TestCase):
    def test_explicit_mapping_promotes_real_source_unit_and_locator(self) -> None:
        mapping = {
            "claim_id": "CLM-pilot",
            "source_unit_ids": ["SU-12345678-arm-a"],
            "locators": [{"source_id": "PMID:12345678", "text": "abstract, frase 2"}],
        }
        decision = decide_propagation(make_claim(), make_parent(), explicit_mapping=mapping)
        repaired = apply_decision(make_claim(), decision)
        self.assertEqual(decision.status, CLAIM_VERIFIED_LOCATOR)
        self.assertEqual(repaired["source_unit_ids"], ["SU-12345678-arm-a"])
        self.assertEqual(repaired["locators"], mapping["locators"])
        self.assertEqual(repaired["provenance_repair"]["claim_source_ids"], ["PMID:12345678"])

    def test_mapping_without_locator_is_publication_only(self) -> None:
        mapping = {
            "claim_id": "CLM-pilot",
            "source_unit_ids": ["SU-12345678-arm-a"],
            "source_ids": ["PMID:12345678"],
        }
        decision = decide_propagation(make_claim(), make_parent(), explicit_mapping=mapping)
        repaired = apply_decision(make_claim(), decision)
        self.assertEqual(decision.status, CLAIM_PUBLICATION_IDENTIFIER_ONLY)
        self.assertEqual(repaired["source_unit_ids"], ["SU-12345678-arm-a"])
        self.assertEqual(repaired["locators"], [])

    def test_parent_with_multiple_publications_is_ambiguous(self) -> None:
        decision = decide_propagation(
            make_claim(),
            make_parent(source_ids=["PUBMED:12345678", "PUBMED:87654321"]),
        )
        self.assertEqual(decision.status, AMBIGUOUS_PARENT_PROVENANCE)
        self.assertEqual(apply_decision(make_claim(), decision)["source_unit_ids"], [])

    def test_single_parent_publication_is_not_claim_verified(self) -> None:
        decision = decide_propagation(make_claim(), make_parent())
        self.assertEqual(decision.status, PARENT_PUBLICATION_AVAILABLE)
        self.assertEqual(apply_decision(make_claim(), decision)["source_unit_ids"], [])

    def test_aggregate_without_mapping_is_not_attributed(self) -> None:
        decision = decide_propagation(
            make_claim(claim_type="aggregate_intervention_claim"), make_parent()
        )
        self.assertEqual(decision.status, PARENT_PUBLICATION_AVAILABLE)
        self.assertIn("explicit mapping", decision.reason)

    def test_existing_claim_provenance_is_preserved(self) -> None:
        original = make_claim(
            source_unit_ids=["SU-12345678-arm-a"],
            locators=[{"source_id": "PMID:12345678", "text": "abstract, frase 2"}],
            provenance={"source_id": "PMID:12345678"},
        )
        decision = decide_propagation(
            original, make_parent(source_ids=["PUBMED:87654321"])
        )
        repaired = apply_decision(original, decision)
        self.assertEqual(decision.status, CLAIM_VERIFIED_LOCATOR)
        self.assertEqual(repaired["locators"], original["locators"])
        self.assertEqual(repaired["provenance"], original["provenance"])


if __name__ == "__main__":
    unittest.main()
