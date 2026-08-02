from __future__ import annotations

import copy
import unittest

from benchmarks.mtb_evidence.unified_dossier_contract.contract import (
    build_claim_extensions,
    build_dossier,
    core_snapshot_fingerprint,
)
from benchmarks.mtb_evidence.unified_dossier_contract.module_status import build_module_status


def core_fixture() -> dict:
    return {
        "bucket_summary": {"primary": 1, "secondary": 0},
        "abstention": False,
        "claims": [
            {"claim_id": "CLM-1", "rank": 1, "statement": "frozen claim"},
            {"claim_id": "CLM-2", "rank": 2, "statement": "second claim"},
        ],
        "score": {"total": 17, "components": {"evidence": 17}},
        "gate_trace": [{"gate": "qualified", "passed": True}],
        "reason_codes": ["QUALIFIED_MATCH"],
        "evidence": [{"evidence_id": "E-1", "rank": 1}, {"evidence_id": "E-2", "rank": 2}],
        "technical_records": [{"record_id": "TR-1", "kind": "frozen_core_record"}],
    }


class CanonicalContractTests(unittest.TestCase):
    def test_canonical_schema_and_core_snapshot_are_additive(self) -> None:
        core = core_fixture()
        before = copy.deepcopy(core)
        dossier = build_dossier(core, case_context={"case_id": "CASE-1"})
        self.assertEqual(
            set(dossier),
            {
                "dossier_version",
                "run",
                "case_context",
                "core_result",
                "claim_extensions",
                "diagnostic_context",
                "technical_records",
                "module_status",
                "limitations",
                "generated_at",
                "association_diagnostics",
            },
        )
        self.assertEqual(core, before)
        self.assertEqual(dossier["core_result"], before)
        self.assertEqual(dossier["run"]["core_snapshot_integrity"]["before_hash"], core_snapshot_fingerprint(core))
        self.assertEqual(dossier["run"]["core_snapshot_integrity"]["after_hash"], core_snapshot_fingerprint(dossier["core_result"]))
        self.assertTrue(dossier["run"]["core_snapshot_integrity"]["unchanged"])

    def test_claim_extensions_join_only_by_claim_id_and_detect_orphans(self) -> None:
        extensions, diagnostics = build_claim_extensions(
            core_fixture()["claims"],
            provenance_by_claim={"CLM-1": {"claim_level_sources": ["SRC-1"]}, "ORPHAN": {"claim_level_sources": ["SRC-X"]}},
            ontology_by_claim={"CLM-2": {"disease": {"match_type": "EXACT", "query_value": "NSCLC", "claim_value": "NSCLC"}}},
        )
        self.assertEqual(set(extensions), {"CLM-1", "CLM-2"})
        self.assertEqual(extensions["CLM-1"]["provenance"]["claim_level_sources"], ["SRC-1"])
        self.assertEqual(diagnostics["orphan_records"][0]["claim_id"], "ORPHAN")

    def test_parent_publication_is_not_promoted_to_claim_source(self) -> None:
        extensions, _ = build_claim_extensions(
            [{"claim_id": "CLM-1"}],
            provenance_by_claim={
                "CLM-1": {
                    "parent_level_publications": [{"source_id": "PMID:PARENT"}],
                    "source_unit": [{"source_unit_id": "SU-1"}],
                }
            },
        )
        provenance = extensions["CLM-1"]["provenance"]
        self.assertEqual(provenance["claim_level_sources"], [])
        self.assertEqual(provenance["parent_level_publications"], [{"source_id": "PMID:PARENT"}])

    def test_unexecuted_document_support_is_not_assessed(self) -> None:
        extensions, _ = build_claim_extensions(
            [{"claim_id": "CLM-1"}],
            document_support_by_claim={"CLM-1": None},
        )
        support = extensions["CLM-1"]["document_support"]
        self.assertEqual(support["status"], "NOT_ASSESSED")
        self.assertNotEqual(support["status"], "NO_SUPPORT_FOUND")

    def test_ontology_shadow_is_additive_and_keeps_match_types(self) -> None:
        core = core_fixture()
        dossier = build_dossier(
            core,
            ontology_by_claim={"CLM-1": {"disease": {"match_type": "DESCENDANT", "distance": 1}}},
        )
        self.assertEqual(dossier["claim_extensions"]["CLM-1"]["ontology_alignment"]["disease"]["match_type"], "DESCENDANT")
        self.assertTrue(dossier["claim_extensions"]["CLM-1"]["ontology_alignment"]["shadow_only"])
        self.assertEqual(dossier["core_result"]["bucket_summary"], core["bucket_summary"])

    def test_core_order_score_gate_reason_abstention_and_technical_records_are_unchanged(self) -> None:
        core = core_fixture()
        dossier = build_dossier(core, ontology_by_claim={"CLM-1": {"disease": {"match_type": "RELATED"}}})
        for field in ("claims", "score", "gate_trace", "reason_codes", "evidence", "abstention", "technical_records"):
            self.assertEqual(dossier["core_result"][field], core[field])
        self.assertEqual(
            [claim["claim_id"] for claim in dossier["core_result"]["claims"]],
            [claim["claim_id"] for claim in core["claims"]],
        )

    def test_diagnostic_records_are_not_claim_extensions(self) -> None:
        dossier = build_dossier(
            core_fixture(),
            diagnostic_context={
                "records": [{"graph_identifier": "CDX-1", "diagnostic_name": "test CDx"}],
                "status": "STRUCTURAL_DATA_ONLY",
            },
        )
        self.assertEqual(dossier["diagnostic_context"]["records"][0]["graph_identifier"], "CDX-1")
        self.assertNotIn("CDX-1", dossier["claim_extensions"])

    def test_module_maturity_is_explicit(self) -> None:
        modules = build_module_status()
        self.assertEqual(modules["v3_core"]["maturity"], "PRODUCTION")
        self.assertEqual(modules["v3_core"]["execution_mode"], "ACTIVE")
        self.assertEqual(modules["ontology"]["maturity"], "RESEARCH_DRAFT")
        self.assertEqual(modules["ontology"]["execution_mode"], "SHADOW")
        self.assertEqual(modules["companion_diagnostic"]["maturity"], "DISCOVERY_ONLY")
        self.assertEqual(modules["escat"]["status"], "NOT_ASSESSED")


if __name__ == "__main__":
    unittest.main()
