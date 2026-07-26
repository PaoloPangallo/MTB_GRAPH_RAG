"""Protegge il narrowing documentale dei due claim diagnostici FGFR2.

La fase e' locale allo shadow 1.2: non introduce una disease hierarchy, non
promuove il repository e non modifica gli artefatti operativi o le versioni
shadow precedenti.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.shadow import domain_gates as GATE
from backend.pipeline.evidence.shadow.identity import (
    NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
    non_therapeutic_claim_id,
)
from backend.pipeline.evidence.shadow.schema import (
    MODEL_SCHEMA_VERSION_V11,
    OUTPUT_CONTRACT_VERSION_V11,
    STRUCTURAL_GATE_VERSION_V11,
)
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.scripts.build_diagnostic_disease_scope_narrowing_shadow import (
    DEFAULT_OUTPUT,
    EXPECTED_NEW_IDS,
    OPERATIONAL_QUERY_BASELINE_SHA256,
    SHADOW_QUERIES,
    build,
    run_update,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
SHADOW_V10 = V3 / "typed_claim_shadow_migration"
SHADOW_V11 = V3 / "non_therapeutic_shadow_update"
SOURCE_CLOSURE = V3 / "non_therapeutic_source_closure"
OUT = DEFAULT_OUTPUT

START_SHA = "6f5d643f48c845ea9b18bf097315e392436414f2"
# La fase termina sull'ultimo commit di contenuto. L'estremo resta fisso anche
# quando fasi successive aggiungono nuovi commit.
PHASE_END_SHA = "1639568cb299b1b8975dce854f1f9e1fdc3181c2"

OLD_IDS = {
    "evidence:1846": "CLM-2175b95ae3113c4f5d97",
    "evidence:1847": "CLM-7056003a9bdef747f514",
}
NEW_IDS = {
    "evidence:1846": "CLM-8941c177da91f66ff93a",
    "evidence:1847": "CLM-a7e1c40b794d2c4d4ca8",
}
ICCA = "Intrahepatic Cholangiocarcinoma"
GENERIC = "Cholangiocarcinoma"

FROZEN_OPERATIONAL_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualification_links.jsonl",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/qualified_evidence_views.jsonl",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256_text(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


class NarrowingCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_update()
        cls.artifacts = build()
        cls.manifest = json.loads(cls.artifacts["repository_v1_2_manifest.json"])
        cls.active = {
            row["graph_evidence_id"]: row
            for row in json.loads(
                "[" + cls.artifacts["diagnostic_claims_v1_2.jsonl"].replace("\n", ",")[:-1] + "]"
            )
        }
        cls.deprecated = {
            row["graph_evidence_id"]: row
            for row in json.loads(
                "["
                + cls.artifacts["deprecated_diagnostic_claims.jsonl"].replace("\n", ",")[:-1]
                + "]"
            )
        }
        cls.replacements = {
            row["parent_id"]: row
            for row in json.loads(
                "["
                + cls.artifacts["diagnostic_claim_replacement_map.jsonl"].replace("\n", ",")[
                    :-1
                ]
                + "]"
            )
        }


class TestCounts(NarrowingCase):
    def test_repository_counts_are_derived_and_unchanged(self) -> None:
        counts = self.manifest["counts"]
        self.assertEqual(counts["parents"], 147)
        self.assertEqual(counts["therapeutic_claims"], 146)
        self.assertEqual(counts["diagnostic_claims_active"], 2)
        self.assertEqual(counts["diagnostic_claims_deprecated"], 2)
        self.assertEqual(counts["prognostic_claims"], 0)
        self.assertEqual(counts["active_claims_total"], 148)
        self.assertEqual(counts["parents_without_claims"], 3)
        self.assertEqual(
            counts["parents_without_claims_ids"],
            ["evidence:347", "evidence:3811", "evidence:4759"],
        )
        self.assertFalse(counts["expected_count_forced"])


class TestNarrowedClaims(NarrowingCase):
    def test_only_the_two_reviewed_diagnostic_claims_are_active(self) -> None:
        self.assertEqual(set(self.active), {"evidence:1846", "evidence:1847"})
        for graph_evidence_id, claim in sorted(self.active.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(claim["disease_scope"], ICCA)
                self.assertEqual(
                    claim["diagnostic_interpretation"],
                    "subtype_defining_alteration",
                )
                self.assertEqual(claim["source_unit_ids"], ["PU-PMID-24122810-cohort-1"])
                self.assertEqual(claim["review_status"], "first_review_complete")
                self.assertEqual(claim["review_independence"], "non_independent")
                self.assertEqual(claim["propagation_policy"], "prototype_only")
                self.assertFalse(claim["hard_filterable"])
                self.assertFalse(claim["final_evaluable"])
                self.assertEqual(claim["access_type"], "abstract_only")
                self.assertFalse(claim["full_text_available"])

    def test_partners_remain_distinct(self) -> None:
        self.assertEqual(self.active["evidence:1846"]["biomarker"], "FGFR2::BICC1 Fusion")
        self.assertEqual(self.active["evidence:1847"]["biomarker"], "FGFR2::AHCYL1 Fusion")
        self.assertNotEqual(
            self.active["evidence:1846"]["claim_id"],
            self.active["evidence:1847"]["claim_id"],
        )

    def test_prevalence_remains_aggregate_only(self) -> None:
        for claim in self.active.values():
            with self.subTest(claim=claim["claim_id"]):
                self.assertFalse(claim["prevalence_attributable_to_subject"])
                self.assertEqual(claim["prevalence"]["value_percent"], 13.6)
                self.assertEqual(claim["prevalence"]["level"], "aggregate_fgfr2_fusions")
                self.assertFalse(claim["prevalence"]["partner_specific"])
                self.assertIn(
                    "PREVALENCE_AGGREGATE_ONLY_NOT_PARTNER_SPECIFIC",
                    claim["limitation_codes"],
                )

    def test_no_clinical_utility_or_therapy_is_invented(self) -> None:
        for claim in self.active.values():
            with self.subTest(claim=claim["claim_id"]):
                self.assertFalse(claim["clinical_validation_asserted"])
                self.assertFalse(claim["diagnostic_utility_asserted"])
                self.assertFalse(claim["validated_clinical_test_asserted"])
                self.assertFalse(claim["intervention_present"])
                self.assertNotIn("intervention", claim["identity_payload_fields"])
                self.assertFalse(claim["receives_therapy_score"])
                self.assertIn("CLINICAL_UTILITY_NOT_ASSERTED", claim["limitation_codes"])

    def test_parent_locator_and_original_provenance_are_preserved(self) -> None:
        old = {
            row["graph_evidence_id"]: row
            for row in load_jsonl(SHADOW_V11 / "diagnostic_claims_v1_1.jsonl")
        }
        for graph_evidence_id, claim in sorted(self.active.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                previous = old[graph_evidence_id]
                self.assertEqual(claim["parent_id"], previous["parent_id"])
                self.assertEqual(claim["locators"], previous["locators"])
                self.assertEqual(claim["source_unit_ids"], previous["source_unit_ids"])
                for key, value in previous["provenance"].items():
                    self.assertEqual(claim["provenance"][key], value)


class TestIdentityAndRetirement(NarrowingCase):
    def test_expected_ids_are_literal_and_different_from_retired_ids(self) -> None:
        self.assertEqual(EXPECTED_NEW_IDS, NEW_IDS)
        for graph_evidence_id, claim in sorted(self.active.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(claim["claim_id"], NEW_IDS[graph_evidence_id])
                self.assertNotEqual(claim["claim_id"], OLD_IDS[graph_evidence_id])

    def test_ids_recompute_with_the_frozen_non_therapeutic_formula(self) -> None:
        for graph_evidence_id, claim in sorted(self.active.items()):
            recomputed = non_therapeutic_claim_id(
                graph_evidence_id=graph_evidence_id,
                claim_type="diagnostic_claim",
                canonical_subject=claim["canonical_subject"],
                biomarker=claim["biomarker"],
                disease_scope=ICCA,
                direction_or_interpretation="subtype_defining_alteration",
                polarity="supports",
                source_unit_id="PU-PMID-24122810-cohort-1",
            )
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(recomputed, NEW_IDS[graph_evidence_id])
        self.assertEqual(
            self.manifest["claim_id_formula"]["version"],
            NON_THERAPEUTIC_CLAIM_ID_FORMULA_VERSION,
        )

    def test_no_collision_exists_across_active_and_deprecated_objects(self) -> None:
        active_ids = [claim.claim_id for claim in self.result.evidence_claims]
        deprecated_ids = [row["claim_id"] for row in self.deprecated.values()]
        self.assertEqual(len(active_ids), len(set(active_ids)))
        self.assertFalse(set(active_ids) & set(deprecated_ids))
        self.assertEqual(self.manifest["claim_id_formula"]["collisions"], 0)

    def test_retired_claims_remain_auditable(self) -> None:
        self.assertEqual(set(self.deprecated), set(OLD_IDS))
        for graph_evidence_id, row in sorted(self.deprecated.items()):
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(row["claim_id"], OLD_IDS[graph_evidence_id])
                self.assertEqual(row["disease_scope"], GENERIC)
                self.assertTrue(row["deprecated"])
                self.assertEqual(
                    row["deprecation_status"],
                    "replaced_by_narrowed_diagnostic_claim",
                )
                self.assertEqual(
                    row["reason_code"],
                    "DISEASE_SCOPE_BROADER_THAN_SOURCE_POPULATION",
                )
                self.assertEqual(row["replacement_claim_id"], NEW_IDS[graph_evidence_id])

    def test_replacement_lineage_is_complete_and_reversible(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["diagnostic_claim_replacement_map.jsonl"].replace("\n", ",")[
                :-1
            ]
            + "]"
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            graph_evidence_id = row["parent_id"]
            with self.subTest(graph_evidence_id=graph_evidence_id):
                self.assertEqual(
                    row["legacy_or_shadow_claim_id"], OLD_IDS[graph_evidence_id]
                )
                self.assertEqual(row["replacement_claim_id"], NEW_IDS[graph_evidence_id])
                self.assertEqual(
                    row["reason_code"],
                    "DISEASE_SCOPE_BROADER_THAN_SOURCE_POPULATION",
                )
                self.assertEqual(
                    row["source_narrowing_reason_code"],
                    "SOURCE_POPULATION_REQUIRES_NARROWER_DISEASE_SCOPE",
                )
                self.assertEqual(
                    row["effective_repository_version"],
                    "qualified_claim_repository/1.2",
                )
                self.assertTrue(row["reversible"])
                self.assertEqual(row["review_status"], "first_review_complete")
                self.assertEqual(row["propagation_policy"], "prototype_only")


class TestPlans(NarrowingCase):
    def test_qualification_plan_retires_two_links_and_creates_two(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["qualification_link_regeneration_plan_v1_2.jsonl"].replace(
                "\n", ","
            )[:-1]
            + "]"
        )
        local = [
            row
            for row in rows
            if row["graph_evidence_id"] in OLD_IDS
            and row["action"] in {"retire_claim_link", "create_claim_link"}
        ]
        self.assertEqual(sum(row["action"] == "retire_claim_link" for row in local), 2)
        self.assertEqual(sum(row["action"] == "create_claim_link" for row in local), 2)
        self.assertEqual(
            self.manifest["counts"]["qualification_plan_actions_total"], len(rows)
        )
        for row in local:
            with self.subTest(plan=row["plan_id"]):
                self.assertFalse(row["executed"])
                self.assertEqual(row["source_unit_id"], "PU-PMID-24122810-cohort-1")
                self.assertEqual(row["propagation_policy"], "prototype_only")
                self.assertFalse(row["therapeutic_qualifiers_created"])
                self.assertTrue(row["locators"])

    def test_view_plan_regenerates_only_the_two_local_diagnostic_views(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["qualified_view_regeneration_plan_v1_2.jsonl"].replace(
                "\n", ","
            )[:-1]
            + "]"
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            with self.subTest(plan=row["plan_id"]):
                self.assertEqual(row["action"], "regenerate_diagnostic_view")
                self.assertEqual(row["claim_domain"], "diagnostic")
                self.assertEqual(row["disease_scope"], ICCA)
                self.assertFalse(row["executed"])
                self.assertFalse(row["therapy_score_present"])
                self.assertIsNone(row["intervention_representation"])
                self.assertFalse(row["cross_domain_ranking"])


class TestStrictDiseaseGate(NarrowingCase):
    def test_icca_queries_return_the_matching_diagnostic_claim_as_primary(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["disease_scope_gate_simulation.jsonl"].replace("\n", ",")[
                :-1
            ]
            + "]"
        )
        primary = {
            (row["query_id"], row["object_id"])
            for row in rows
            if row["primary_candidate_eligible"]
        }
        self.assertIn(("D-ICCA-BICC1", NEW_IDS["evidence:1846"]), primary)
        self.assertIn(("D-ICCA-AHCYL1", NEW_IDS["evidence:1847"]), primary)

    def test_generic_cholangiocarcinoma_is_not_an_exact_or_primary_match(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["disease_scope_gate_simulation.jsonl"].replace("\n", ",")[
                :-1
            ]
            + "]"
        )
        generic = [
            row
            for row in rows
            if row["query_id"] == "D-GENERIC-BICC1"
            and row["object_id"] == NEW_IDS["evidence:1846"]
        ]
        self.assertEqual(len(generic), 1)
        self.assertEqual(
            generic[0]["structural_match"]["disease_match_type"],
            "unresolved_disease_relation",
        )
        self.assertFalse(generic[0]["primary_candidate_eligible"])
        self.assertFalse(generic[0]["disease_hierarchy_applied"])

    def test_therapeutic_query_never_promotes_a_diagnostic_claim(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["disease_scope_gate_simulation.jsonl"].replace("\n", ",")[
                :-1
            ]
            + "]"
        )
        diagnostic = [
            row
            for row in rows
            if row["query_id"] == "T-ICCA-BICC1" and row["claim_domain"] == "diagnostic"
        ]
        self.assertTrue(diagnostic)
        self.assertTrue(all(not row["primary_candidate_eligible"] for row in diagnostic))
        self.assertTrue(all(not row["therapy_score_allowed"] for row in diagnostic))

    def test_untyped_query_keeps_diagnostic_results_in_a_separate_section(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["disease_scope_gate_simulation.jsonl"].replace("\n", ",")[
                :-1
            ]
            + "]"
        )
        diagnostic = [
            row
            for row in rows
            if row["query_id"] == "U-ICCA-FGFR2"
            and row["claim_domain"] == "diagnostic"
        ]
        self.assertEqual({row["section"] for row in diagnostic}, {"diagnostic_results"})
        self.assertTrue(all(not row["cross_domain_ranking_allowed"] for row in diagnostic))

    def test_deprecated_claims_are_never_primary_even_if_scored(self) -> None:
        rows = json.loads(
            "["
            + self.artifacts["disease_scope_gate_simulation.jsonl"].replace("\n", ",")[
                :-1
            ]
            + "]"
        )
        retired = [row for row in rows if row["object_id"] in set(OLD_IDS.values())]
        self.assertTrue(retired)
        self.assertTrue(all(not row["primary_candidate_eligible"] for row in retired))
        self.assertTrue(all(row["score_eligibility"]["positive_score_forbidden"] for row in retired))

    def test_query_set_is_exactly_the_five_requested_simulations(self) -> None:
        self.assertEqual(
            {query["query_id"] for query in SHADOW_QUERIES},
            {
                "D-ICCA-BICC1",
                "D-ICCA-AHCYL1",
                "D-GENERIC-BICC1",
                "T-ICCA-BICC1",
                "U-ICCA-FGFR2",
            },
        )


class TestEvidence347(NarrowingCase):
    def test_evidence_347_is_byte_unchanged_and_has_no_claim(self) -> None:
        previous = SHADOW_V11 / "evidence_347_promotion_audit.json"
        current = json.loads(self.artifacts["evidence_347_audit_v1_2.json"])
        self.assertEqual(current["source_artifact_sha256"], sha256_text(previous))
        self.assertEqual(current["claims_created"], 0)
        self.assertTrue(current["blocks_promotion"])
        self.assertEqual(
            current["legacy_deprecation_state_after"],
            "promotion_blocked_pending_full_text",
        )
        self.assertFalse(current["intervention_invented"])
        self.assertFalse(current["predictive_claim_created"])
        self.assertFalse(current["prognostic_claim_created"])


class TestCompatibilityAndDeterminism(NarrowingCase):
    def test_therapeutic_claims_are_byte_identical_to_1_1(self) -> None:
        self.assertEqual(
            self.artifacts["therapeutic_claims_v1_2.jsonl"],
            (SHADOW_V11 / "therapeutic_claims_v1_1.jsonl").read_text(encoding="utf-8"),
        )

    def test_shadow_1_0_and_1_1_hashes_are_preserved_in_lineage(self) -> None:
        lineage = json.loads(self.artifacts["repository_version_lineage.json"])
        by_version = {row["repository_schema"]: row for row in lineage["versions"]}
        for version, path in (
            ("qualified_claim_repository/1.0", SHADOW_V10),
            ("qualified_claim_repository/1.1", SHADOW_V11),
        ):
            with self.subTest(version=version):
                self.assertFalse(by_version[version]["modified_by_this_phase"])
                for name, digest in by_version[version]["artifact_sha256"].items():
                    self.assertEqual(sha256_text(path / name), digest)

    def test_operational_hashes_and_query_output_match_the_preflight(self) -> None:
        inventory = json.loads(
            self.artifacts["operational_vs_shadow_inventory_v1_2.json"]
        )
        self.assertTrue(inventory["operational_hash_parity"])
        self.assertEqual(
            inventory["operational_query"]["before_sha256"],
            OPERATIONAL_QUERY_BASELINE_SHA256,
        )
        self.assertEqual(
            inventory["operational_query"]["after_sha256"],
            OPERATIONAL_QUERY_BASELINE_SHA256,
        )
        for path, expected in inventory["operational_artifact_sha256_before"].items():
            with self.subTest(path=path):
                self.assertEqual(sha256_text(REPO_ROOT / path), expected)

    def test_two_generations_and_reversed_inputs_are_byte_identical(self) -> None:
        self.assertEqual(build(), self.artifacts)
        self.assertEqual(build(reverse=True), self.artifacts)

    def test_committed_files_match_a_fresh_generation(self) -> None:
        for name, text in sorted(self.artifacts.items()):
            with self.subTest(artifact=name):
                self.assertEqual((OUT / name).read_text(encoding="utf-8"), text)

    def test_manifest_hashes_match_and_no_machine_path_leaks(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                text = self.artifacts[name]
                self.assertEqual(hashlib.sha256(text.encode("utf-8")).hexdigest(), expected)
                lowered = text.lower()
                for fragment in ("c:\\", "/users/", "/home/", "appdata"):
                    self.assertNotIn(fragment, lowered)

    def test_versions_stay_at_1_1_except_repository(self) -> None:
        self.assertEqual(self.manifest["model_schema"], MODEL_SCHEMA_VERSION_V11)
        self.assertEqual(self.manifest["structural_gate"], STRUCTURAL_GATE_VERSION_V11)
        self.assertEqual(self.manifest["output_contract"], OUTPUT_CONTRACT_VERSION_V11)
        self.assertEqual(
            self.manifest["repository_schema"], "qualified_claim_repository/1.2"
        )
        self.assertEqual(self.manifest["migration_status"], "shadow_not_promoted")


class TestReadiness(NarrowingCase):
    def test_readiness_is_positive_only_for_the_shadow_update(self) -> None:
        readiness = self.manifest["readiness"]
        for flag in (
            "diagnostic_scope_narrowing_applied",
            "old_diagnostic_claims_retired",
            "replacement_claims_created",
            "claim_ids_recomputed",
            "repository_v1_2_ready",
            "source_review_status_preserved",
            "evidence_347_unchanged",
            "operational_artifacts_unchanged",
            "terminology_review_required",
            "disease_hierarchy_policy_required",
        ):
            with self.subTest(flag=flag):
                self.assertTrue(readiness[flag])
        for flag in (
            "corpus_promotion_ready",
            "operational_retriever_migration_ready",
            "full_exploratory_rerun_ready",
        ):
            with self.subTest(flag=flag):
                self.assertFalse(readiness[flag])


class TestIsolation(unittest.TestCase):
    def test_generator_never_names_or_loads_gold(self) -> None:
        source = (
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/"
            "build_diagnostic_disease_scope_narrowing_shadow.py"
        ).read_text(encoding="utf-8").lower()
        for fragment in (
            "clinical_gold",
            "snapshot_gold",
            "gold_pilot",
            "mtb_evidence_gold",
            "recall@",
            "precision@",
        ):
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, source)

    def test_no_network_database_or_llm_dependency(self) -> None:
        paths = (
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/scripts/"
            "build_diagnostic_disease_scope_narrowing_shadow.py",
            REPO_ROOT / "backend/pipeline/evidence/shadow/migration_v12.py",
            REPO_ROOT / "backend/pipeline/evidence/shadow/migration_v12_logic.py",
        )
        for path in paths:
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            for forbidden in (
                "requests",
                "httpx",
                "aiohttp",
                "neo4j",
                "openai",
                "anthropic",
                "urllib",
                "socket",
            ):
                with self.subTest(path=path.name, forbidden=forbidden):
                    self.assertFalse(any(forbidden in line for line in imports))

    def test_phase_writes_only_inside_the_shadow_perimeter(self) -> None:
        scope = PhaseScope(
            REPO_ROOT.parent,
            START_SHA,
            PHASE_END_SHA,
            (
                "benchmarks/mtb_evidence/v3/diagnostic_disease_scope_narrowing_shadow/",
                "benchmarks/mtb_evidence/evaluation/scripts/"
                "build_diagnostic_disease_scope_narrowing_shadow.py",
                "backend/pipeline/evidence/shadow/migration_v12.py",
                "backend/pipeline/evidence/shadow/migration_v12_logic.py",
                "backend/tests/test_diagnostic_disease_scope_narrowing_shadow.py",
            ),
        )
        self.assertNotEqual(PHASE_END_SHA, "HEAD")
        changed = scope.changed_paths()
        self.assertEqual(scope.violations(changed), [])
        for path in FROZEN_OPERATIONAL_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, changed)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
