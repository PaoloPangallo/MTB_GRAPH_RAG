"""Protegge gli invarianti dell'audit pre-promozione del repository 1.3.

I test difendono cinque cose, e ognuna e' un modo di sbagliare che questa fase
rende possibile per la prima volta.

Che l'audit derivi dai file e non dal manifest: un manifest che si autodichiara
coerente non e' una verifica, e un audit che lo rileggesse verificherebbe
soltanto che il manifest e' uguale a se stesso.

Che gli ID si ricalcolino a partire dalle sole righe emesse, ordine di lettura
compreso, perche' un ID scritto una volta e mai piu' verificato non e'
verificabile da chi non lo ha emesso.

Che un termine mai visto non possa diventare exact per sottostringa, prefisso,
distanza di edit o classe, e che un termine registrato continui a funzionare:
senza il controllo negativo, "non fonde niente" sarebbe soddisfatto anche da un
sistema che non fonde nulla mai.

Che nessun punteggio, per quanto alto, riapra un bucket che un gate ha chiuso.

Che la fase non abbia toccato nulla di cio' che dichiara di non toccare, gold
compreso.
"""

from __future__ import annotations

import json
import unittest

from pathlib import Path

from backend.pipeline.evidence.shadow import disease_gate as DISEASE
from backend.pipeline.evidence.shadow import integrated_gates as GATE
from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    MATCH_TYPES,
)
from benchmarks.mtb_evidence.evaluation.disease_hierarchy_policy import (
    EXACT_RELATIONS,
    MISSING_CLAIM_DISEASE,
    MISSING_QUERY_DISEASE,
    UNRESOLVED_DISEASE_RELATION,
    resolve_relation,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import findings as FINDINGS
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import gate_audit as GATES
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    identity_audit as IDENTITY,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import inventory as INVENTORY
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    lineage_audit as LINEAGE,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import novelty as NOVELTY
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import plan_audit as PLANS
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import promotion as PROMOTION
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import (
    provenance_audit as PROVENANCE,
)
from benchmarks.mtb_evidence.evaluation.pre_promotion_audit import scope as SCOPE
from benchmarks.mtb_evidence.evaluation import tree_hash_erratum as TREE_ERRATUM
from benchmarks.mtb_evidence.evaluation.scripts.build_pre_promotion_audit_1_3 import (
    DEFAULT_OUTPUT,
    build,
    build_data_artifacts,
    policy_declaration,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = DEFAULT_OUTPUT

START_SHA = SCOPE.START_SHA

# Estremo di fase: il commit che chiude la fase, mai HEAD. Il perimetro di una
# fase e' una proprieta' storica e chiusa, e misurarlo contro l'albero di lavoro
# lo farebbe crescere con la fase successiva, fallendo per la ragione sbagliata.
PHASE_END_SHA = "61627448e01d277e2aa27ae1c04f90885a68869f"

ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/pre_promotion_audit_1_3/",
    "benchmarks/mtb_evidence/evaluation/pre_promotion_audit/",
    "benchmarks/mtb_evidence/evaluation/pre_promotion_audit_reports.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_pre_promotion_audit_1_3.py",
    "backend/tests/test_pre_promotion_audit_1_3.py",
)

FROZEN_OPERATIONAL_PATHS = tuple(SCOPE.OPERATIONAL_ARTIFACTS)
FROZEN_SHADOW_DIRS = tuple(sorted(SCOPE.FROZEN_SHADOW_DIRS.values()))

REQUIRED_ARTIFACTS = (
    "audit_scope.json",
    "repository_inventory_audit.json",
    "parent_claim_reconciliation.jsonl",
    "claim_id_recomputation.jsonl",
    "lineage_audit.jsonl",
    "provenance_completeness_audit.jsonl",
    "qualification_link_plan_audit.json",
    "qualified_view_plan_audit.json",
    "integrated_gate_audit.jsonl",
    "novelty_handling_cases.jsonl",
    "novelty_handling_summary.json",
    "promotion_diff_simulation.json",
    "backward_compatibility_audit.json",
    "rollback_plan.json",
    "findings.jsonl",
    "readiness_decision.json",
    "audit_manifest.json",
    "PRE_PROMOTION_AUDIT_1_3.md",
    "NOVELTY_HANDLING_DIAGNOSTICS.md",
    "PROMOTION_DIFF_AND_ROLLBACK.md",
    "PRE_PROMOTION_READINESS.md",
)


def _repository():
    return SCOPE.load_repository()


def _artifact(name: str):
    text = (OUTPUT / name).read_text(encoding="utf-8")
    if name.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


class InventoryTests(unittest.TestCase):
    """L'inventario derivato dai file, non riletto dal manifest."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.audit = INVENTORY.audit(cls.repository)

    def test_counts_match_the_declared_inventory(self) -> None:
        self.assertEqual(self.audit["count_mismatches_vs_expected"], {})
        self.assertTrue(self.audit["counts_match_expected"])

    def test_derived_counts_match_the_manifest(self) -> None:
        self.assertEqual(self.audit["count_mismatches_vs_manifest"], {})

    def test_the_full_inventory_is_consistent(self) -> None:
        self.assertTrue(self.audit["inventory_consistent"])

    def test_every_expected_total_is_reproduced(self) -> None:
        derived = self.audit["audit_derived_counts"]
        for key, expected in INVENTORY.EXPECTED_COUNTS.items():
            with self.subTest(count=key):
                self.assertEqual(derived[key], expected)

    def test_no_orphan_claim(self) -> None:
        integrity = self.audit["structural_integrity"]
        self.assertEqual(integrity["orphan_claims"], [])
        self.assertTrue(integrity["no_orphan_claims"])

    def test_no_child_points_at_a_missing_parent(self) -> None:
        self.assertEqual(
            self.audit["structural_integrity"]["dangling_child_references"], []
        )

    def test_every_parent_lists_its_own_claims(self) -> None:
        self.assertEqual(
            self.audit["structural_integrity"]["claims_not_listed_by_their_parent"], []
        )

    def test_deprecated_claims_are_excluded_from_the_active_set(self) -> None:
        integrity = self.audit["structural_integrity"]
        self.assertEqual(integrity["deprecated_claims_present_in_active_set"], [])
        self.assertEqual(integrity["claims_flagged_deprecated_inside_active_set"], [])

    def test_the_three_parents_without_claims_are_the_declared_ones(self) -> None:
        self.assertEqual(
            self.audit["parents_without_claims_observed"],
            sorted(INVENTORY.PARENTS_WITHOUT_CLAIMS),
        )

    def test_domain_files_partition_the_active_claims(self) -> None:
        partition = self.audit["domain_file_partition"]
        self.assertTrue(partition["domain_files_partition_active_claims"])
        self.assertEqual(partition["overlapping_between_domain_files"], [])

    def test_reconciliation_closes_on_the_derived_totals(self) -> None:
        rows = INVENTORY.reconciliation_rows(self.repository)
        totals = INVENTORY.reconciliation_totals(rows)
        derived = self.audit["audit_derived_counts"]
        self.assertEqual(totals["parents"], derived["parents"])
        self.assertEqual(totals["active_claims"], derived["active_claims_total"])
        self.assertEqual(totals["retired_claims"], derived["deprecated_claims"])
        self.assertEqual(
            totals["unsupported_associations"], derived["unsupported_associations"]
        )
        self.assertEqual(
            totals["unresolved_associations"], derived["unresolved_associations"]
        )


class IdentityTests(unittest.TestCase):
    """Ogni ID si ricalcola dalle sole righe emesse."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.audit = IDENTITY.audit(cls.repository)

    def test_every_identity_recomputes(self) -> None:
        self.assertEqual(self.audit["mismatched_ids"], [])
        self.assertTrue(self.audit["claim_ids_recomputable"])

    def test_no_collision_and_no_unexplained_duplication(self) -> None:
        self.assertEqual(self.audit["collisions"], 0)
        self.assertEqual(self.audit["unexplained_duplications"], [])
        self.assertEqual(self.audit["shared_ids_between_active_and_retired"], [])

    def test_recomputation_is_stable(self) -> None:
        self.assertTrue(self.audit["stable_across_recomputation"])

    def test_recomputation_does_not_depend_on_input_order(self) -> None:
        self.assertTrue(self.audit["order_invariance"]["identical"])

    def test_the_formula_is_versioned(self) -> None:
        self.assertEqual(
            self.audit["formula_versions"],
            ["claim_id_formula/1.0", "non_therapeutic_claim_id_formula/1.0"],
        )

    def test_parent_and_claim_id_spaces_are_disjoint(self) -> None:
        self.assertTrue(self.audit["id_prefix_spaces_disjoint"])

    def test_the_named_records_all_recompute(self) -> None:
        named = {row["graph_evidence_id"] for row in self.audit["named_records"]}
        self.assertEqual(named, set(IDENTITY.NAMED_GRAPH_EVIDENCE_IDS))
        self.assertTrue(self.audit["named_records_all_match"])

    def test_a_canonical_payload_is_available_for_every_identity(self) -> None:
        for row in IDENTITY.recomputation_rows(self.repository):
            with self.subTest(identity=row["declared_id"]):
                self.assertTrue(row["canonical_payload"])

    def test_the_canonicalized_literal_leaves_the_identity_and_stays_in_the_record(
        self,
    ) -> None:
        preservation = self.audit["source_literal_preservation"]
        self.assertEqual(preservation["canonicalized_literal"], ["BGJ398"])
        # I due aggregati canonicalizzati tengono `BGJ398` fuori dall'hash e
        # dentro il record. Se il letterale rientrasse nell'identita' l'ID non
        # sarebbe cambiato; se uscisse dal record la fonte sarebbe riscritta.
        self.assertEqual(
            len(preservation["records_keeping_the_literal_out_of_identity"]), 2
        )
        self.assertGreaterEqual(
            len(preservation["records_still_carrying_the_literal"]), 2
        )


class LineageTests(unittest.TestCase):
    """La lineage delle sostituzioni e' completa e reversibile."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.audit = LINEAGE.audit(cls.repository)

    def test_lineage_is_complete(self) -> None:
        self.assertTrue(self.audit["lineage_complete"])
        self.assertEqual(self.audit["replacements_broken"], [])
        self.assertEqual(self.audit["replacements_with_missing_fields"], [])

    def test_every_replacement_is_reversible(self) -> None:
        self.assertEqual(self.audit["replacements_irreversible"], [])

    def test_terminology_changes_representation_not_proposition(self) -> None:
        terminology = self.audit["terminology"]
        self.assertEqual(terminology["observed_records"], ["evidence:1851", "evidence:1853"])
        self.assertTrue(terminology["aggregate_semantics_unchanged"])
        self.assertTrue(terminology["canonical_label_uses_verified_term"])
        self.assertTrue(terminology["source_literal_preserved"])

    def test_disease_narrowing_narrows_and_does_not_broaden(self) -> None:
        narrowing = self.audit["scope_narrowing"]
        self.assertEqual(narrowing["observed_records"], ["evidence:1846", "evidence:1847"])
        self.assertTrue(narrowing["narrowed_not_broadened"])

    def test_the_three_records_without_replacement_keep_their_parent(self) -> None:
        self.assertEqual(
            self.audit["records_without_replacement"],
            list(LINEAGE.RECORDS_WITHOUT_REPLACEMENT),
        )
        self.assertTrue(self.audit["records_without_replacement_all_present"])

    def test_no_retired_claim_is_active(self) -> None:
        status = self.audit["retired_claim_status"]
        self.assertEqual(status["retired_present_in_active_set"], [])
        self.assertTrue(status["all_retired_flagged_deprecated"])

    def test_no_retired_claim_is_primary_or_final_ranking_eligible(self) -> None:
        """La versione comportamentale: il gate li tiene fuori, non solo il flag."""
        rows = [
            row
            for row in GATES.case_rows(self.repository)
            if row["case_id"] == "deprecated-with-everything-exact"
        ]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(mode=row["policy_mode"]):
                self.assertFalse(row["primary_candidate_eligible"])
                self.assertFalse(row["final_ranking_eligible"])


class ProvenanceTests(unittest.TestCase):
    """La provenance minima, classificata invece che conteggiata."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.audit = PROVENANCE.audit(cls.repository)
        cls.rows = PROVENANCE.claim_rows(cls.repository)

    def test_every_active_claim_carries_parent_and_graph_record(self) -> None:
        for row in self.rows:
            with self.subTest(claim=row["claim_id"]):
                self.assertTrue(row["present_fields"]["parent_id"])
                self.assertTrue(row["present_fields"]["graph_evidence_id"])

    def test_every_active_claim_carries_a_source_unit_and_adapter_lineage(self) -> None:
        for row in self.rows:
            with self.subTest(claim=row["claim_id"]):
                self.assertTrue(row["present_fields"]["source_unit"])
                self.assertTrue(row["present_fields"]["adapter_lineage"])

    def test_every_active_claim_has_a_locator_or_an_explicit_limitation(self) -> None:
        for row in self.rows:
            with self.subTest(claim=row["claim_id"]):
                self.assertTrue(row["has_locator"] or row["limitation_form"])

    def test_absences_are_classified_and_none_is_invented(self) -> None:
        allowed = {
            PROVENANCE.PROMOTION_BLOCKING,
            PROVENANCE.WARNING_ONLY,
            PROVENANCE.EXPECTED_LEGACY,
        }
        for row in self.rows:
            for item in row["missing_fields"]:
                with self.subTest(claim=row["claim_id"], field=item["field"]):
                    self.assertIn(item["classification"], allowed)

    def test_the_only_promotion_blocking_absence_is_the_known_one(self) -> None:
        """Il finding e' pinnato: se sparisse senza una correzione, il test cade."""
        self.assertEqual(
            self.audit["promotion_blocking_fields"], ["propagation_policy"]
        )
        self.assertEqual(len(self.audit["claims_with_promotion_blocking_absence"]), 6)

    def test_the_claims_missing_propagation_policy_are_the_non_atomic_ones(self) -> None:
        blocked = set(self.audit["claims_with_promotion_blocking_absence"])
        non_atomic = {
            claim["claim_id"]
            for claim in self.repository["claims"]
            if claim["claim_type"] in ("aggregate_intervention_claim", "regimen_claim")
        }
        self.assertEqual(blocked, non_atomic)


class PlanTests(unittest.TestCase):
    """Link plan e view plan, coerenti e non eseguiti."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.audit = PLANS.audit(cls.repository)

    def test_the_link_plan_is_consistent(self) -> None:
        self.assertTrue(self.audit["links"]["qualification_link_plan_consistent"])

    def test_the_thirty_seven_actions_reconcile(self) -> None:
        reconciliation = self.audit["links"]["reconciliation"]
        self.assertEqual(reconciliation["total_actions"], PLANS.EXPECTED_LINK_ACTIONS)
        self.assertTrue(reconciliation["totals_reconcile"])
        self.assertEqual(reconciliation["terminology_retire"], 2)
        self.assertEqual(reconciliation["terminology_create"], 2)
        self.assertEqual(reconciliation["diagnostic_scope_retire"], 2)
        self.assertEqual(reconciliation["diagnostic_scope_create"], 2)
        self.assertEqual(reconciliation["carried_from_earlier_phases"], 29)

    def test_no_link_points_at_a_retired_or_missing_claim(self) -> None:
        links = self.audit["links"]
        self.assertEqual(links["creates_towards_retired_claim"], [])
        self.assertEqual(links["creates_towards_missing_claim"], [])

    def test_no_duplicate_link_action(self) -> None:
        self.assertEqual(self.audit["links"]["duplicate_plan_ids"], [])

    def test_no_link_action_is_executed(self) -> None:
        self.assertEqual(self.audit["links"]["actions_executed"], [])

    def test_no_action_flattens_a_typed_object(self) -> None:
        self.assertEqual(self.audit["links"]["flattening_flags_set"], [])

    def test_the_records_without_replacement_are_retired_without_creation(self) -> None:
        self.assertEqual(
            self.audit["links"]["reconciliation"]["records_retired_without_creation"],
            list(LINEAGE.RECORDS_WITHOUT_REPLACEMENT),
        )

    def test_the_view_plan_is_consistent(self) -> None:
        self.assertTrue(self.audit["views"]["qualified_view_plan_consistent"])

    def test_there_are_four_view_actions_split_two_and_two(self) -> None:
        views = self.audit["views"]
        self.assertEqual(views["total_actions"], PLANS.EXPECTED_VIEW_ACTIONS)
        self.assertEqual(
            views["action_breakdown"],
            {
                "regenerate_diagnostic_view": 2,
                "verify_no_view_references_replaced_claim": 2,
            },
        )

    def test_the_terminology_claims_do_not_appear_in_the_operational_views(self) -> None:
        """La ragione per cui le azioni sono 4 e non 2, verificata e non assunta."""
        views = self.audit["views"]
        self.assertTrue(views["terminology_claims_absent_from_operational_views"])
        self.assertTrue(views["operational_views_keyed_by_legacy_statement"])

    def test_no_orphan_view_and_no_flattened_domain(self) -> None:
        views = self.audit["views"]
        self.assertEqual(views["orphan_views"], [])
        self.assertEqual(views["flattened_domain_or_score"], [])
        self.assertEqual(views["actions_executed"], [])


class GateCompositionTests(unittest.TestCase):
    """La composizione dei gate e' una congiunzione, e nessun punteggio la apre."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.rows = GATES.case_rows(cls.repository)
        cls.audit = GATES.audit(cls.repository)

    def test_all_gate_invariants_hold(self) -> None:
        self.assertTrue(self.audit["integrated_gate_invariants_hold"])
        self.assertEqual(self.audit["unexpected_bucket"], [])
        self.assertEqual(self.audit["unexpected_blocking_gate"], [])

    def test_no_gate_is_bypassed(self) -> None:
        self.assertEqual(self.audit["gate_bypasses"], 0)
        self.assertEqual(self.audit["gate_bypass_details"], [])

    def test_score_flags_are_cleared_outside_rankable_buckets(self) -> None:
        self.assertEqual(
            self.audit["score_flags_leaked_outside_rankable_buckets"], 0
        )
        for row in self.rows:
            if row["final_bucket"] not in GATES.NON_RANKABLE_BUCKETS:
                continue
            with self.subTest(case=row["case_id"], mode=row["policy_mode"]):
                self.assertFalse(any(row["score_flags"].values()))
                self.assertTrue(row["positive_score_forbidden"])

    def test_primary_is_never_granted_with_a_blocking_gate(self) -> None:
        self.assertEqual(self.audit["primary_with_blocking_gate"], 0)
        for row in self.rows:
            with self.subTest(case=row["case_id"], mode=row["policy_mode"]):
                if row["primary_candidate_eligible"]:
                    self.assertEqual(row["blocking_gates"], [])

    def test_the_primary_bucket_does_not_depend_on_the_mode(self) -> None:
        self.assertTrue(self.audit["primary_bucket_is_mode_invariant"])

    def test_bucket_precedence_is_the_declared_one(self) -> None:
        self.assertEqual(
            self.audit["bucket_precedence"], list(GATE.BUCKET_PRECEDENCE)
        )

    def test_an_arbitrarily_high_score_moves_nothing(self) -> None:
        rows = [row for row in self.rows if row["case_id"] == "arbitrarily-high-score"]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(mode=row["policy_mode"]):
                self.assertEqual(row["final_bucket"], GATE.REJECTED_BUCKET)
                self.assertFalse(row["final_ranking_eligible"])
                self.assertFalse(any(row["score_flags"].values()))

    def test_each_required_case_blocks_on_the_gate_it_is_built_for(self) -> None:
        expected = {
            "exact-disease-biomarker-incompatible": "biomarker",
            "disease-child-biomarker-exact": "disease",
            "disease-exact-regimen-component": "intervention",
            "unsupported-with-everything-exact": "claim_status",
            "deprecated-with-everything-exact": "claim_status",
            "mapping-pending-with-everything-exact": "intervention",
        }
        strict = {
            row["case_id"]: row
            for row in self.rows
            if row["policy_mode"] == DISEASE.DEFAULT_POLICY_MODE
        }
        for case_id, gate in expected.items():
            with self.subTest(case=case_id):
                self.assertIn(gate, strict[case_id]["blocking_gates"])
                self.assertFalse(strict[case_id]["primary_candidate_eligible"])


class StrictDefaultTests(unittest.TestCase):
    """Il default e' strict_verified, e una modalita' sconosciuta non passa."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = policy_declaration(_repository())

    def test_the_default_is_declared_machine_readably(self) -> None:
        self.assertTrue(self.policy["strict_default_explicit"])
        self.assertEqual(self.policy["declared_default_mode"], "strict_verified")

    def test_an_unspecified_mode_resolves_to_strict_verified(self) -> None:
        self.assertEqual(DISEASE.policy_mode({}), "strict_verified")
        self.assertEqual(self.policy["behaviour_default_mode"], "strict_verified")
        self.assertTrue(self.policy["default_matches_behaviour"])

    def test_an_unknown_mode_is_rejected(self) -> None:
        with self.assertRaises(DISEASE.DiseaseGateError):
            DISEASE.policy_mode({"disease_policy_mode": "definitely_not_a_mode"})
        with self.assertRaises(DISEASE.DiseaseGateError):
            DISEASE.evaluate({"disease": "X"}, object(), mode="definitely_not_a_mode")

    def test_an_unknown_mode_never_falls_back_to_a_broader_one(self) -> None:
        for unknown in ("", "STRICT_VERIFIED", "strict", "ontology_aware", "all"):
            with self.subTest(mode=unknown):
                if unknown == "":
                    # Una stringa vuota non e' una modalita' dichiarata: il
                    # gate la tratta come assenza e applica il default, che e'
                    # la modalita' piu' restrittiva e non una piu' larga.
                    self.assertEqual(
                        DISEASE.policy_mode({"disease_policy_mode": unknown}),
                        "strict_verified",
                    )
                    continue
                with self.assertRaises(DISEASE.DiseaseGateError):
                    DISEASE.policy_mode({"disease_policy_mode": unknown})

    def test_the_required_pipeline_behaviour_is_recorded(self) -> None:
        required = self.policy["required_pipeline_behaviour"]
        self.assertTrue(required["use_strict_verified_when_unspecified"])
        self.assertTrue(required["reject_unknown_modes"])
        self.assertFalse(required["silent_fallback_to_ontology_aware_warning"])
        self.assertFalse(required["silent_fallback_to_audit_all"])


class NoveltyHandlingTests(unittest.TestCase):
    """Nessun termine mai visto diventa exact, e i registrati continuano a valere."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = NOVELTY.case_rows()
        cls.summary = NOVELTY.summary(cls.rows)
        cls.by_case = {row["case_id"]: row for row in cls.rows}

    def test_the_diagnostics_are_complete(self) -> None:
        self.assertTrue(self.summary["novelty_diagnostics_complete"])
        self.assertEqual(self.summary["unexpected_outcomes"], [])

    def test_no_false_automatic_merge(self) -> None:
        self.assertEqual(self.summary["false_automatic_merges"], 0)
        self.assertEqual(self.summary["false_automatic_merge_cases"], [])

    def test_no_gate_bypass(self) -> None:
        self.assertEqual(self.summary["gate_bypasses_observed"], 0)

    def test_the_diagnostics_create_no_mapping(self) -> None:
        self.assertEqual(self.summary["mappings_created_by_these_diagnostics"], 0)

    def test_these_are_not_called_generalization_accuracy(self) -> None:
        self.assertEqual(
            self.summary["diagnostics_name"], "conservative novelty-handling diagnostics"
        )
        self.assertIn("generalization accuracy", self.summary["not_a_measure_of"])

    def test_an_unknown_code_never_becomes_exact(self) -> None:
        row = self.by_case["unknown-development-code"]
        self.assertFalse(row["reached_exact_identity"])
        self.assertEqual(row["observed_outcome"], NOVELTY.REJECTED)

    def test_a_near_match_code_never_becomes_exact(self) -> None:
        for case_id in (
            "near-miss-development-code",
            "graphic-variation-of-known-code",
            "unregistered-vendor-prefix",
            "hyphenated-unresolved-code",
        ):
            with self.subTest(case=case_id):
                self.assertFalse(self.by_case[case_id]["reached_exact_identity"])

    def test_a_shared_substring_or_prefix_never_becomes_exact(self) -> None:
        for case_id in (
            "shared-substring-different-concept",
            "shared-prefix-different-concept",
        ):
            with self.subTest(case=case_id):
                row = self.by_case[case_id]
                self.assertFalse(row["reached_exact_identity"])
                self.assertIn(row["merge_mechanism_if_any"], (None, "substring_or_prefix"))

    def test_the_salt_form_is_not_flattened_into_the_moiety(self) -> None:
        row = self.by_case["salt-form-of-canonical-term"]
        self.assertFalse(row["reached_exact_identity"])
        self.assertFalse(row["primary_eligible"])

    def test_the_registered_salt_suffix_merge_is_recorded_as_registered(self) -> None:
        """Non e' una fusione falsa, ma non deve poter passare inosservata."""
        row = self.by_case["salt-form-in-registered-suffix-table"]
        self.assertTrue(row["merge_basis_is_registered"])
        self.assertFalse(row["false_automatic_merge"])
        self.assertEqual(
            self.summary["registered_normalization_merges"],
            ["salt-form-in-registered-suffix-table"],
        )

    def test_a_case_or_whitespace_variation_is_still_the_same_term(self) -> None:
        row = self.by_case["case-and-whitespace-variation"]
        self.assertEqual(row["observed_outcome"], NOVELTY.NORMALIZED_EXACT)

    def test_a_pending_alias_stays_pending(self) -> None:
        row = self.by_case["pending-alias-of-canonical-term"]
        self.assertEqual(row["match_type"], "mapping_pending")
        self.assertFalse(MATCH_TYPES[row["match_type"]]["primary_eligible"])

    def test_an_unknown_disease_is_unresolved_or_rejected_never_exact(self) -> None:
        for case_id in (
            "unknown-disease-entirely",
            "unregistered-abbreviation",
            "near-miss-of-registered-abbreviation",
            "subtype-not-in-hierarchy",
            "unregistered-generic-tumor-phrase",
        ):
            with self.subTest(case=case_id):
                row = self.by_case[case_id]
                self.assertFalse(row["is_exact_relation"])
                self.assertNotIn(row["relation_type"], EXACT_RELATIONS)

    def test_an_unknown_disease_never_becomes_a_verified_alias(self) -> None:
        for query, claim in (
            ("Xanthic Neoplasm of the Falx", "Cholangiocarcinoma"),
            ("NSCLCx", "Non-Small Cell Lung Cancer"),
            ("Squamoid Cholangiocarcinoma", "Cholangiocarcinoma"),
        ):
            with self.subTest(query=query):
                self.assertNotEqual(
                    resolve_relation(query, claim).relation_type,
                    "verified_disease_alias",
                )

    def test_a_missing_disease_is_distinct_from_an_unresolved_one(self) -> None:
        self.assertEqual(
            self.by_case["missing-query-disease"]["relation_type"], MISSING_QUERY_DISEASE
        )
        self.assertEqual(
            self.by_case["missing-claim-disease"]["relation_type"], MISSING_CLAIM_DISEASE
        )
        self.assertEqual(
            self.by_case["both-terms-unregistered"]["relation_type"],
            UNRESOLVED_DISEASE_RELATION,
        )

    def test_a_registered_alias_still_resolves(self) -> None:
        """Controllo negativo: senza, "non fonde niente" sarebbe banalmente vero."""
        row = self.by_case["registered-alias-still-works"]
        self.assertEqual(row["relation_type"], "verified_disease_alias")
        self.assertTrue(row["is_exact_relation"])

    def test_no_novelty_case_reaches_the_primary_bucket(self) -> None:
        for row in self.rows:
            if row["domain"] != "terminology":
                continue
            if row["case_id"] in (
                "case-and-whitespace-variation",
                "salt-form-in-registered-suffix-table",
            ):
                continue
            with self.subTest(case=row["case_id"]):
                self.assertNotEqual(row["bucket"], GATE.PRIMARY_BUCKET)


class PromotionAndRollbackTests(unittest.TestCase):
    """Il diff di promozione e' completo, e il rollback e' eseguibile ma non eseguito."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = _repository()
        cls.audit = PROMOTION.audit(cls.repository)

    def test_the_promotion_diff_is_complete(self) -> None:
        self.assertTrue(self.audit["promotion_diff_complete"])

    def test_the_promotion_diff_is_deterministic(self) -> None:
        first = PROMOTION.diff(self.repository)
        second = PROMOTION.diff(self.repository)
        self.assertEqual(first, second)

    def test_the_promotion_touches_no_operational_file(self) -> None:
        diff = self.audit["promotion_diff"]
        self.assertEqual(diff["operational_files_modified"], [])
        self.assertEqual(diff["files_replaced"], [])

    def test_four_claim_ids_change_and_they_are_the_known_ones(self) -> None:
        diff = self.audit["promotion_diff"]
        self.assertEqual(diff["claim_ids_changed_count"], 4)
        records = {row["graph_evidence_id"] for row in diff["claim_ids_changed"]}
        self.assertEqual(
            records,
            set(LINEAGE.TERMINOLOGY_RECORDS) | set(LINEAGE.SCOPE_NARROWING_RECORDS),
        )

    def test_the_retriever_and_scoring_incompatibilities_are_named(self) -> None:
        diff = self.audit["promotion_diff"]
        self.assertTrue(diff["retriever_incompatibilities"])
        self.assertTrue(diff["scoring_incompatibilities"])
        for row in diff["retriever_incompatibilities"] + diff["scoring_incompatibilities"]:
            with self.subTest(surface=row["surface"]):
                self.assertFalse(row["resolved_by_this_promotion"])

    def test_every_referenced_legacy_statement_exists_in_the_operational_corpus(
        self,
    ) -> None:
        self.assertEqual(
            self.audit["promotion_diff"][
                "referenced_statements_absent_from_operational_corpus"
            ],
            [],
        )

    def test_the_promotion_never_flattens_a_typed_object(self) -> None:
        contract = self.audit["backward_compatibility"]["intervention_contract"]
        self.assertFalse(contract["flattening_permitted_by_promotion"])
        self.assertEqual(len(contract["breaks"]), 3)
        self.assertEqual(contract["affected_claims"], 8)

    def test_every_backward_lookup_is_resolvable(self) -> None:
        compat = self.audit["backward_compatibility"]
        self.assertTrue(compat["legacy_statement_id_lookup"]["resolvable"])
        self.assertTrue(compat["graph_evidence_id_lookup"]["resolvable"])
        self.assertTrue(compat["old_claim_id_redirect"]["resolvable"])
        self.assertEqual(compat["old_claim_id_redirect"]["redirects_declared"], 4)
        self.assertTrue(compat["audit_of_retired_claims"]["queryable"])
        self.assertTrue(compat["parent_provenance"]["parents_survive_replacement"])

    def test_the_operational_statement_stays_distinct_from_the_typed_claim(self) -> None:
        self.assertTrue(
            self.audit["backward_compatibility"][
                "operational_statement_vs_typed_claim"
            ]["distinction_preserved"]
        )

    def test_the_rollback_plan_is_complete_and_not_executed(self) -> None:
        rollback = self.audit["rollback"]
        self.assertTrue(rollback["rollback_plan_complete"])
        self.assertFalse(rollback["executed"])
        self.assertEqual(rollback["steps_total"], 7)
        self.assertEqual([row["step"] for row in rollback["steps"]], list(range(1, 8)))

    def test_the_snapshot_precedes_the_write(self) -> None:
        """Il modo tipico in cui un rollback fallisce, escluso dall'ordine."""
        steps = self.audit["rollback"]["steps"]
        self.assertIn("snapshot", steps[0]["title"])
        self.assertLess(steps[0]["step"], steps[1]["step"])

    def test_the_rollback_loses_no_deprecated_claim(self) -> None:
        self.assertTrue(self.audit["rollback"]["deprecated_claims_preserved"])
        self.assertTrue(self.audit["rollback"]["logs_retained"])


class ReadinessTests(unittest.TestCase):
    """La decisione di readiness deriva dai finding, e non li anticipa."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.decision = _artifact("readiness_decision.json")
        cls.findings = _artifact("findings.jsonl")
        cls.manifest = _artifact("audit_manifest.json")

    def test_there_is_no_critical_finding(self) -> None:
        self.assertEqual(self.decision["counts"][FINDINGS.CRITICAL], 0)

    def test_every_finding_carries_a_known_severity(self) -> None:
        for row in self.findings:
            with self.subTest(finding=row["finding_id"]):
                self.assertIn(row["severity"], FINDINGS.SEVERITIES)

    def test_every_blocking_finding_carries_a_required_fix(self) -> None:
        for row in self.findings:
            if row["severity"] not in (FINDINGS.CRITICAL, FINDINGS.MAJOR):
                continue
            with self.subTest(finding=row["finding_id"]):
                self.assertTrue(row["required_promotion_fix"] or row["accepted"])

    def test_the_decision_is_one_of_the_three(self) -> None:
        self.assertIn(
            self.decision["decision"],
            (FINDINGS.READY, FINDINGS.READY_WITH_FIXES, FINDINGS.NOT_READY),
        )

    def test_unaccepted_major_findings_prevent_an_unconditional_recommendation(
        self,
    ) -> None:
        if self.decision["unaccepted_major_findings"]:
            self.assertEqual(self.decision["decision"], FINDINGS.READY_WITH_FIXES)

    def test_no_clinical_readiness_is_declared(self) -> None:
        self.assertFalse(self.decision["clinical_readiness_declared"])

    def test_corpus_promotion_ready_is_false_while_fixes_are_required(self) -> None:
        readiness = self.decision["readiness"]
        if self.decision["decision"] != FINDINGS.READY:
            self.assertFalse(readiness["corpus_promotion_ready"])

    def test_the_retriever_migration_stays_closed(self) -> None:
        self.assertFalse(
            self.decision["readiness"]["operational_retriever_migration_ready"]
        )

    def test_the_full_exploratory_rerun_stays_closed(self) -> None:
        self.assertFalse(self.decision["readiness"]["full_exploratory_rerun_ready"])

    def test_every_gate_is_green(self) -> None:
        self.assertEqual(self.decision["gates_not_green"], [])


class ArtifactTests(unittest.TestCase):
    """Gli artefatti esistono, sono deterministici e non contengono altro."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.artifacts = build()

    def test_every_required_artifact_is_produced(self) -> None:
        for name in REQUIRED_ARTIFACTS:
            with self.subTest(artifact=name):
                self.assertIn(name, self.artifacts)
                self.assertTrue((OUTPUT / name).exists())

    def test_the_output_contains_nothing_else(self) -> None:
        written = {path.name for path in OUTPUT.iterdir() if path.is_file()}
        self.assertEqual(written, set(self.artifacts))

    # `test_rebuilding_reproduces_the_committed_artifacts` sta in
    # `backend/tests_external/gold/`: rigenerare richiede il bundle gold, che
    # questa suite non apre.

    def test_double_generation_is_identical(self) -> None:
        self.assertEqual(build_data_artifacts(), build_data_artifacts())

    def test_the_manifest_hashes_match_the_artifacts(self) -> None:
        manifest = json.loads(self.artifacts["audit_manifest.json"])
        for name, digest in manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                self.assertEqual(SCOPE.sha256_text(self.artifacts[name]), digest)


class IntegrityTests(unittest.TestCase):
    """La fase non ha toccato nulla di cio' che dichiara di non toccare."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = _artifact("audit_manifest.json")

    def test_the_frozen_artifacts_are_unchanged(self) -> None:
        integrity = self.manifest["integrity"]
        self.assertTrue(integrity["all_frozen_artifacts_unchanged"])
        self.assertEqual(integrity["changed"], [])

    def test_the_current_hashes_still_match_the_recorded_ones(self) -> None:
        observed = SCOPE.frozen_hashes()
        for role, digest in self.manifest["integrity"]["frozen_sha256"].items():
            with self.subTest(role=role):
                self.assertEqual(observed["files"][role]["sha256"], digest)
        for role, digest in self.manifest["integrity"]["frozen_tree_sha256"].items():
            with self.subTest(tree=role):
                TREE_ERRATUM.assert_frozen_tree(
                    role, REPO_ROOT / observed["trees"][role]["path"], digest
                )

    def test_the_shadow_repository_1_3_is_unchanged(self) -> None:
        self.assertEqual(
            SCOPE.sha256_tree(SCOPE.SHADOW_V13),
            self.manifest["integrity"]["frozen_tree_sha256"]["shadow repository 1.3"],
        )

    def test_the_earlier_shadow_repositories_are_unchanged(self) -> None:
        for role in ("shadow repository 1.0", "shadow repository 1.1", "shadow repository 1.2"):
            with self.subTest(repository=role):
                self.assertIn(role, self.manifest["integrity"]["frozen_tree_sha256"])

    def test_the_operational_query_returns_the_same_bytes(self) -> None:
        query = self.manifest["integrity"]["operational_query"]
        self.assertTrue(query["parity"])
        self.assertEqual(query["sha256"], query["baseline_sha256"])

    def test_no_gold_record_was_read(self) -> None:
        gold = self.manifest["gold"]
        self.assertEqual(gold["gold_records_read"], 0)
        self.assertFalse(gold["used_for_any_decision"])
        self.assertTrue(gold["checksum_only_no_deserialization"])

    def test_the_audit_declares_itself_read_only(self) -> None:
        scope_artifact = _artifact("audit_scope.json")
        self.assertTrue(scope_artifact["read_only"])
        self.assertFalse(scope_artifact["promotion_applied"])
        self.assertFalse(scope_artifact["plans_executed"])
        self.assertFalse(scope_artifact["gold_used"])

    def test_the_invariants_recorded_in_the_manifest_hold(self) -> None:
        invariants = self.manifest["invariants"]
        self.assertEqual(invariants["false_automatic_merges"], 0)
        self.assertEqual(invariants["gate_bypasses"], 0)
        self.assertEqual(invariants["gold_artifacts_read"], 0)
        self.assertEqual(
            invariants["score_flags_leaked_outside_rankable_buckets"], 0
        )
        self.assertFalse(invariants["operational_artifacts_modified"])
        self.assertFalse(invariants["plans_executed"])
        self.assertFalse(invariants["promotion_applied"])
        self.assertFalse(invariants["shadow_1_3_modified"])


class PhasePerimeterTests(unittest.TestCase):
    """Il perimetro della fase, misurato su un intervallo chiuso di commit."""

    def test_the_phase_wrote_only_inside_its_own_perimeter(self) -> None:
        if not PHASE_END_SHA:
            self.skipTest("la fase non e' ancora chiusa: nessun estremo da misurare")
        scope_ = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        violations = scope_.violations(scope_.changed_paths())
        self.assertEqual(violations, [])

    def test_the_frozen_paths_are_not_in_the_allowed_write_prefixes(self) -> None:
        """L'elenco dei path scrivibili non deve poter contenere un congelato."""
        for path in FROZEN_OPERATIONAL_PATHS + FROZEN_SHADOW_DIRS:
            with self.subTest(path=path):
                self.assertFalse(path.startswith(ALLOWED_WRITE_PREFIXES))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
