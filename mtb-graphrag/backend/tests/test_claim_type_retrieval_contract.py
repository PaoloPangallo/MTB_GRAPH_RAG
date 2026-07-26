"""Protegge gli invarianti del contratto di retrieval sui claim tipizzati.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano LLM. Il gold non viene letto.

Il test centrale non e' su un conteggio ma su una precedenza: il tipo strutturale
del match decide l'idoneita' prima e indipendentemente da qualunque punteggio.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.claim_type_retrieval_contract import (
    BUCKETS,
    CLAIM_TYPES,
    ContractError,
    MATCH_TYPES,
    PARENT_FORBIDDEN_USES,
    PARENT_KIND,
    POSITIVE_SCORE_FORBIDDEN,
    QUERY_TYPES,
    VERIFIED_CLASS_MEMBERSHIPS,
    WARNING_CODES,
    check_no_numerical_compensation,
    classify_query,
    direction_match_type,
    polarity_match_type,
    score_eligibility,
    structural_match,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_claim_retrieval_contract import build

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
CONTRACT = V3 / "claim_type_retrieval_contract"
ADJ = V3 / "multi_intervention_adjudication"
START_SHA = "6341d12088c4b856320eae3ece90936b9bbdd64b"
# La fase del contratto si chiude qui. Il controllo era rimasto aperto
# sull'albero di lavoro, come annotato allora: convertito in intervallo chiuso
# alla chiusura della fase, cosi' non fallisce quando la fase successiva scrive
# dentro al proprio perimetro.
PHASE_END_SHA = "f7749eaa674042bfd232c4b06f1b019c645e6c99"

FROZEN_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/corpus_manifest.py",
    "backend/pipeline/evidence/corpus_regeneration.py",
    "backend/pipeline/evidence/repository.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
    "benchmarks/mtb_evidence/v3/qualification_corpus_v2/evidence_statements.jsonl",
)

ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/claim_type_retrieval_contract/",
    "benchmarks/mtb_evidence/evaluation/claim_type_retrieval_contract.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_claim_retrieval_contract.py",
    "benchmarks/mtb_evidence/evaluation/data/claim_retrieval_",
    "backend/tests/test_claim_type_retrieval_contract.py",
    # Il test di perimetro dell'adjudication misurava il proprio intervallo
    # contro l'albero di lavoro e sarebbe fallito qui. Corretto in un commit
    # separato; gli artefatti dell'adjudication restano intatti.
    "backend/tests/test_multi_intervention_adjudication.py",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def query(**overrides) -> dict:
    payload = {
        "query_id": "QT",
        "disease": "Lung Non-small Cell Carcinoma",
        "biomarker": "EGFR L858R",
        "direction": "sensitivity",
        "polarity": "supports",
        "interventions": [],
        "intervention_combination": False,
        "intervention_class": None,
    }
    payload.update(overrides)
    return payload


def claim(**overrides) -> dict:
    payload = {
        "claim_id": "CLM-test",
        "graph_evidence_parent": "evidence:1",
        "claim_type": "atomic_intervention_claim",
        "intervention_members": ["erlotinib"],
        "aggregate_kind": None,
        "biomarker": "EGFR L858R",
        "disease_scope": "Lung Non-small Cell Carcinoma",
        "direction": "sensitivity",
        "polarity": "supports",
        "evidence_setting": "clinical",
        "source_id": "PMID:1",
        "source_unit_id": "SU-1",
        "locator": "abstract, braccio A",
        "source_literal_terms": ["erlotinib"],
    }
    payload.update(overrides)
    return payload


class ContractCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.claim_types = json.loads(
            (CONTRACT / "claim_type_definitions.json").read_text(encoding="utf-8")
        )
        cls.query_types = json.loads(
            (CONTRACT / "query_type_definitions.json").read_text(encoding="utf-8")
        )
        cls.structural = json.loads(
            (CONTRACT / "structural_match_contract.json").read_text(encoding="utf-8")
        )
        cls.buckets = json.loads(
            (CONTRACT / "candidate_bucket_contract.json").read_text(encoding="utf-8")
        )
        cls.eligibility = json.loads(
            (CONTRACT / "score_eligibility_contract.json").read_text(encoding="utf-8")
        )
        cls.codes = json.loads(
            (CONTRACT / "warning_reason_codes.json").read_text(encoding="utf-8")
        )
        cls.audit = load_jsonl(CONTRACT / "current_scoring_assumption_audit.jsonl")
        cls.features = load_jsonl(CONTRACT / "proposed_scoring_features.jsonl")
        cls.simulation = load_jsonl(CONTRACT / "adjudicated_claim_query_simulation.jsonl")
        cls.regression = load_jsonl(CONTRACT / "regression_case_simulation.jsonl")
        cls.output = json.loads((CONTRACT / "output_contract.json").read_text(encoding="utf-8"))
        cls.impact = json.loads((CONTRACT / "migration_impact.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads(
            (CONTRACT / "contract_manifest.json").read_text(encoding="utf-8")
        )

    def rows_for(self, query_id: str) -> list[dict]:
        return [row for row in self.simulation if row["query_id"] == query_id]

    def primary(self) -> list[dict]:
        return [row for row in self.simulation if row["bucket"] == "primary_ranked_results"]


# ── parent ────────────────────────────────────────────────────────────────────


class TestParentIsNeverAClaim(ContractCase):
    def test_the_parent_is_declared_not_a_claim(self) -> None:
        self.assertFalse(self.claim_types["parent"]["is_claim"])
        self.assertNotIn(PARENT_KIND, CLAIM_TYPES)
        for use in PARENT_FORBIDDEN_USES:
            with self.subTest(use=use):
                self.assertIn(use, self.claim_types["parent"]["forbidden_uses"])

    def test_no_parent_ever_reaches_a_non_audit_bucket(self) -> None:
        parents = [row for row in self.simulation if row["claim_type"] == PARENT_KIND]
        self.assertTrue(parents)
        for row in parents:
            with self.subTest(row=row["simulation_id"]):
                self.assertEqual(row["bucket"], "audit_only_results")
                self.assertFalse(row["primary_candidate_eligible"])
                self.assertIn(
                    "PARENT_PROVENANCE_CONTAINER_NOT_CLAIM", row["exclusion_reason_codes"]
                )

    def test_the_parent_never_gets_a_therapy_score(self) -> None:
        for row in self.simulation:
            if row["claim_type"] != PARENT_KIND:
                continue
            with self.subTest(row=row["simulation_id"]):
                self.assertFalse(row["score_eligibility"]["structural_score_eligible"])
                self.assertFalse(row["score_eligibility"]["qualified_score_eligible"])
                self.assertFalse(row["score_eligibility"]["final_ranking_eligible"])

    def test_the_summary_counts_zero_parents_in_primary(self) -> None:
        self.assertEqual(self.manifest["simulation_summary"]["parent_in_primary"], 0)


# ── atomic, regimen, classe, aggregato ────────────────────────────────────────


class TestAtomicMatching(ContractCase):
    def test_an_exact_atomic_match_is_primary(self) -> None:
        match = structural_match(query(interventions=["erlotinib"]), claim())
        self.assertEqual(match.intervention_match_type, "exact_atomic_intervention")
        self.assertTrue(match.primary_candidate_eligible)
        self.assertEqual(match.bucket, "primary_ranked_results")

    def test_a_salt_form_normalizes_to_the_same_active_moiety(self) -> None:
        match = structural_match(
            query(interventions=["alectinib"]),
            claim(intervention_members=["alectinib hydrochloride"]),
        )
        self.assertEqual(match.intervention_match_type, "normalized_atomic_intervention")
        self.assertTrue(match.primary_candidate_eligible)

    def test_a_pending_mapping_is_never_an_exact_match(self) -> None:
        match = structural_match(
            query(interventions=["infigratinib"]), claim(intervention_members=["bgj398"])
        )
        self.assertEqual(match.intervention_match_type, "mapping_pending")
        self.assertFalse(match.primary_candidate_eligible)
        self.assertEqual(match.bucket, "audit_only_results")


class TestRegimenMatching(ContractCase):
    def regimen_claim(self, **overrides) -> dict:
        payload = claim(
            claim_type="regimen_claim", intervention_members=["erlotinib", "ramucirumab"]
        )
        payload.update(overrides)
        return payload

    def test_an_exact_regimen_ignores_component_order(self) -> None:
        forward = structural_match(
            query(interventions=["erlotinib", "ramucirumab"], intervention_combination=True),
            self.regimen_claim(),
        )
        backward = structural_match(
            query(interventions=["ramucirumab", "erlotinib"], intervention_combination=True),
            self.regimen_claim(),
        )
        self.assertEqual(forward.intervention_match_type, "exact_regimen")
        self.assertEqual(backward.intervention_match_type, "exact_regimen")
        self.assertTrue(forward.primary_candidate_eligible)
        self.assertTrue(backward.primary_candidate_eligible)

    def test_a_single_component_is_never_an_exact_regimen(self) -> None:
        match = structural_match(query(interventions=["ramucirumab"]), self.regimen_claim())
        self.assertEqual(match.intervention_match_type, "regimen_component_related")
        self.assertFalse(match.primary_candidate_eligible)
        self.assertTrue(match.warning_eligible)
        self.assertIn("RESULT_APPLIES_TO_COMBINATION_NOT_COMPONENT", match.warning_codes)
        self.assertIn("ATOMIC_COMPONENT_NOT_REGIMEN_MATCH", match.explanation_codes)

    def test_a_proper_subset_is_not_exact(self) -> None:
        match = structural_match(
            query(interventions=["erlotinib"], intervention_combination=False),
            self.regimen_claim(intervention_members=["erlotinib", "ramucirumab", "x"]),
        )
        self.assertNotEqual(match.intervention_match_type, "exact_regimen")
        subset = structural_match(
            query(interventions=["erlotinib", "ramucirumab"], intervention_combination=True),
            self.regimen_claim(intervention_members=["erlotinib", "ramucirumab", "x"]),
        )
        self.assertEqual(subset.intervention_match_type, "regimen_subset_mismatch")
        self.assertIn("QUERY_REGIMEN_IS_PROPER_SUBSET", subset.explanation_codes)
        self.assertFalse(subset.primary_candidate_eligible)

    def test_a_proper_superset_is_not_exact(self) -> None:
        match = structural_match(
            query(
                interventions=["erlotinib", "ramucirumab", "osimertinib"],
                intervention_combination=True,
            ),
            self.regimen_claim(),
        )
        self.assertEqual(match.intervention_match_type, "regimen_superset_mismatch")
        self.assertIn("QUERY_REGIMEN_IS_PROPER_SUPERSET", match.explanation_codes)
        self.assertFalse(match.primary_candidate_eligible)

    def test_two_drugs_without_a_structured_indicator_are_not_a_regimen(self) -> None:
        self.assertEqual(
            classify_query(query(interventions=["a", "b"])),
            "unspecified_multi_intervention_query",
        )
        match = structural_match(
            query(interventions=["erlotinib", "ramucirumab"]), self.regimen_claim()
        )
        self.assertNotEqual(match.intervention_match_type, "exact_regimen")


class TestClassAndAggregateMatching(ContractCase):
    def class_claim(self) -> dict:
        return claim(
            claim_type="aggregate_intervention_claim",
            aggregate_kind="drug_class",
            intervention_members=["EGFR tyrosine kinase inhibitor"],
        )

    def test_an_exact_class_match_is_primary(self) -> None:
        match = structural_match(
            query(intervention_class="EGFR tyrosine kinase inhibitor"), self.class_claim()
        )
        self.assertEqual(match.intervention_match_type, "exact_intervention_class")
        self.assertTrue(match.primary_candidate_eligible)

    def test_a_class_member_never_becomes_a_drug_specific_match(self) -> None:
        match = structural_match(query(interventions=["erlotinib"]), self.class_claim())
        self.assertNotEqual(match.intervention_match_type, "exact_atomic_intervention")
        self.assertIn(
            match.intervention_match_type,
            ("class_member_related", "unresolved_class_relation"),
        )
        self.assertFalse(match.primary_candidate_eligible)

    def test_an_unverified_class_relation_is_not_inferred_from_the_string(self) -> None:
        self.assertEqual(VERIFIED_CLASS_MEMBERSHIPS, {})
        match = structural_match(query(interventions=["erlotinib"]), self.class_claim())
        self.assertEqual(match.intervention_match_type, "unresolved_class_relation")
        self.assertTrue(self.claim_types["verified_class_membership_registry"]["empty_by_design"])

    def test_an_aggregate_member_is_not_atomized(self) -> None:
        match = structural_match(
            query(interventions=["pd173074"]),
            claim(
                claim_type="aggregate_intervention_claim",
                aggregate_kind="non_separable_inhibitor_set",
                intervention_members=["bgj398", "pd173074"],
            ),
        )
        self.assertEqual(match.intervention_match_type, "aggregate_member_related")
        self.assertFalse(match.primary_candidate_eligible)
        self.assertIn("AGGREGATE_RESULT_NOT_SEPARABLE_BY_INTERVENTION", match.warning_codes)


# ── associazioni ──────────────────────────────────────────────────────────────


class TestAssociations(ContractCase):
    def test_unsupported_is_never_primary_and_never_scores(self) -> None:
        rows = [row for row in self.simulation if row["claim_type"] == "unsupported_association"]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row["simulation_id"]):
                self.assertNotEqual(row["bucket"], "primary_ranked_results")
                self.assertFalse(row["score_eligibility"]["structural_score_eligible"])
                self.assertFalse(row["score_eligibility"]["qualified_score_eligible"])
                self.assertTrue(row["score_eligibility"]["positive_score_forbidden"])

    def test_unresolved_is_never_positive_support_nor_negative_evidence(self) -> None:
        rows = [row for row in self.simulation if row["claim_type"] == "unresolved_association"]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row["simulation_id"]):
                self.assertNotEqual(row["bucket"], "primary_ranked_results")
                self.assertTrue(row["score_eligibility"]["positive_score_forbidden"])
                self.assertNotIn("NATIVE_POLARITY_MISMATCH", row["exclusion_reason_codes"])

    def test_unsupported_and_unresolved_are_distinct_states(self) -> None:
        self.assertNotEqual(
            MATCH_TYPES["unsupported"]["warning_eligible"],
            MATCH_TYPES["unresolved"]["warning_eligible"],
        )
        self.assertIn(
            "DOCUMENTARY_ATTRIBUTION_UNRESOLVED", self.codes["unresolved_reason_codes"]
        )


# ── nessuna compensazione numerica ────────────────────────────────────────────


class TestNoNumericalCompensation(ContractCase):
    def test_a_related_match_cannot_be_promoted_by_any_score(self) -> None:
        related = (
            "regimen_component_related",
            "class_member_related",
            "aggregate_member_related",
            "unsupported",
            "unresolved",
        )
        for name in related:
            with self.subTest(match=name):
                self.assertFalse(MATCH_TYPES[name]["primary_eligible"])

    def test_the_invariant_raises_when_eligibility_contradicts_the_match_type(self) -> None:
        match = structural_match(
            query(interventions=["ramucirumab"]),
            claim(claim_type="regimen_claim", intervention_members=["erlotinib", "ramucirumab"]),
        )
        self.assertFalse(match.primary_candidate_eligible)
        forged = match.__class__(**{**match.as_dict(), "primary_candidate_eligible": True})
        with self.assertRaises(ContractError):
            check_no_numerical_compensation(forged, hypothetical_score=999.0)

    def test_a_forbidden_type_cannot_carry_a_positive_score(self) -> None:
        match = structural_match(
            query(interventions=["infigratinib"]), claim(intervention_members=["bgj398"])
        )
        with self.assertRaises(ContractError):
            check_no_numerical_compensation(match, hypothetical_score=42.0)

    def test_perfect_biomarker_and_disease_do_not_promote_a_component(self) -> None:
        """Biomarcatore e disease esatti non riportano un componente nel primario."""
        match = structural_match(
            query(interventions=["ramucirumab"]),
            claim(
                claim_type="regimen_claim",
                intervention_members=["erlotinib", "ramucirumab"],
            ),
        )
        self.assertEqual(match.biomarker_match_type, "exact")
        self.assertEqual(match.disease_match_type, "exact")
        self.assertFalse(match.primary_candidate_eligible)
        self.assertEqual(match.bucket, "retained_with_warning")

    def test_every_simulated_row_satisfies_the_invariant(self) -> None:
        for row in self.simulation:
            spec = MATCH_TYPES[row["intervention_match_type"]]
            with self.subTest(row=row["simulation_id"]):
                if row["primary_candidate_eligible"]:
                    self.assertTrue(spec["primary_eligible"])
                if row["intervention_match_type"] in POSITIVE_SCORE_FORBIDDEN:
                    self.assertTrue(row["score_eligibility"]["positive_score_forbidden"])


# ── direzione e polarita' ─────────────────────────────────────────────────────


class TestDirectionAndPolarity(ContractCase):
    def test_reduced_sensitivity_is_not_resistance(self) -> None:
        self.assertEqual(
            direction_match_type("reduced_sensitivity", "resistance"), "related_not_equivalent"
        )
        self.assertEqual(
            direction_match_type("resistance", "reduced_sensitivity"), "related_not_equivalent"
        )
        self.assertEqual(direction_match_type("resistance", "resistance"), "exact")

    def test_a_related_direction_does_not_reach_the_primary_bucket(self) -> None:
        match = structural_match(
            query(
                interventions=["crizotinib"],
                direction="reduced_sensitivity",
                biomarker="B",
            ),
            claim(intervention_members=["crizotinib"], direction="resistance", biomarker="B"),
        )
        self.assertFalse(match.primary_candidate_eligible)
        self.assertEqual(match.bucket, "retained_with_warning")
        self.assertIn("REDUCED_SENSITIVITY_IS_NOT_RESISTANCE", match.warning_codes)

    def test_negative_evidence_is_preserved_not_flipped(self) -> None:
        match = structural_match(
            query(interventions=["crizotinib"], direction="resistance", biomarker="B"),
            claim(intervention_members=["crizotinib"], direction="resistance", biomarker="B"),
        )
        self.assertEqual(match.direction_match_type, "exact")
        self.assertTrue(match.primary_candidate_eligible)
        self.assertEqual(match.polarity_match_type, "exact")

    def test_does_not_support_never_becomes_positive(self) -> None:
        self.assertEqual(polarity_match_type("supports", "does_not_support"), "opposed")
        match = structural_match(
            query(interventions=["erlotinib"], polarity="supports"),
            claim(polarity="does_not_support"),
        )
        self.assertFalse(match.primary_candidate_eligible)
        self.assertIn("NATIVE_POLARITY_MISMATCH", match.exclusion_reason_codes)

    def test_conflicting_is_preserved_with_a_warning(self) -> None:
        match = structural_match(
            query(interventions=["erlotinib"]), claim(polarity="conflicting")
        )
        self.assertEqual(match.polarity_match_type, "conflicting")
        self.assertIn("CONFLICTING_RESULT_PRESERVED", match.warning_codes)

    def test_unknown_is_not_assumed_compatible(self) -> None:
        match = structural_match(
            query(interventions=["erlotinib"], direction="sensitivity"),
            claim(direction="unknown"),
        )
        self.assertEqual(match.direction_match_type, "unknown_claim_direction")
        self.assertIn("DIRECTION_UNKNOWN_NOT_ASSUMED_COMPATIBLE", match.warning_codes)


# ── casi di regressione ───────────────────────────────────────────────────────


class TestRegressionCases(ContractCase):
    def case(self, group: str) -> dict:
        return next(row for row in self.regression if row["graph_evidence_id"] == group)

    def test_evidence_275_never_attributes_the_class_result_to_a_drug(self) -> None:
        case = self.case("evidence:275")
        self.assertFalse(case["parent_ever_primary"])
        self.assertFalse(case["unsupported_ever_primary"])
        self.assertIn("exact_intervention_class", case["match_types_observed"])
        self.assertNotIn("exact_atomic_intervention", case["match_types_observed"])
        rows = [
            row
            for row in self.simulation
            if row["parent_graph_evidence_id"] == "evidence:275"
            and row["bucket"] == "primary_ranked_results"
        ]
        for row in rows:
            with self.subTest(row=row["simulation_id"]):
                self.assertIn(
                    row["intervention_match_type"],
                    ("exact_intervention_class", "no_intervention_constraint"),
                )

    def test_evidence_275_class_query_reaches_the_aggregate(self) -> None:
        rows = [
            row
            for row in self.rows_for("Q07")
            if row["intervention_match_type"] == "exact_intervention_class"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["parent_graph_evidence_id"], "evidence:275")
        self.assertEqual(rows[0]["bucket"], "primary_ranked_results")

    def test_evidence_4759_produces_no_claim_and_no_support(self) -> None:
        case = self.case("evidence:4759")
        self.assertEqual(case["primary_results"], 0)
        self.assertEqual(case["primary_claim_ids"], [])
        self.assertFalse(case["unsupported_ever_primary"])
        self.assertIn("unsupported", case["match_types_observed"])

    def test_evidence_3811_stays_unresolved_and_audit(self) -> None:
        case = self.case("evidence:3811")
        self.assertEqual(case["primary_results"], 0)
        self.assertFalse(case["unresolved_ever_primary"])
        self.assertIn("unresolved", case["match_types_observed"])
        self.assertNotIn("exact_atomic_intervention", case["match_types_observed"])

    def test_evidence_11240_keeps_the_regimen_and_the_atomic_claim_apart(self) -> None:
        case = self.case("evidence:11240")
        self.assertIn("exact_regimen", case["match_types_observed"])
        self.assertIn("exact_atomic_intervention", case["match_types_observed"])
        self.assertIn("regimen_component_related", case["match_types_observed"])
        self.assertEqual(len(case["primary_claim_ids"]), 2)

    def test_evidence_11240_regimen_query_does_not_promote_the_atomic_claim(self) -> None:
        rows = [
            row
            for row in self.rows_for("Q04")
            if row["parent_graph_evidence_id"] == "evidence:11240"
            and row["claim_type"] == "atomic_intervention_claim"
        ]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(row=row["simulation_id"]):
                self.assertNotEqual(row["intervention_match_type"], "exact_regimen")

    def test_evidence_11240_drug_query_gives_atomic_exact_and_regimen_warning(self) -> None:
        rows = {
            row["claim_type"]: row
            for row in self.rows_for("Q11")
            if row["parent_graph_evidence_id"] == "evidence:11240"
            and row["claim_type"] in ("atomic_intervention_claim", "regimen_claim")
        }
        self.assertEqual(
            rows["atomic_intervention_claim"]["intervention_match_type"],
            "exact_atomic_intervention",
        )
        self.assertEqual(rows["atomic_intervention_claim"]["bucket"], "primary_ranked_results")
        self.assertEqual(
            rows["regimen_claim"]["intervention_match_type"], "regimen_component_related"
        )
        self.assertEqual(rows["regimen_claim"]["bucket"], "retained_with_warning")

    def test_evidence_12131_regimen_does_not_propagate_to_components(self) -> None:
        case = self.case("evidence:12131")
        self.assertIn("exact_regimen", case["match_types_observed"])
        component_rows = [
            row
            for row in self.simulation
            if row["parent_graph_evidence_id"] == "evidence:12131"
            and row["intervention_match_type"] == "regimen_component_related"
        ]
        for row in component_rows:
            with self.subTest(row=row["simulation_id"]):
                self.assertNotEqual(row["bucket"], "primary_ranked_results")


# ── contratto, audit, output ──────────────────────────────────────────────────


class TestContractCompleteness(ContractCase):
    def test_every_match_type_declares_all_its_eligibilities(self) -> None:
        for name, spec in MATCH_TYPES.items():
            with self.subTest(match=name):
                for field in (
                    "definition",
                    "primary_eligible",
                    "warning_eligible",
                    "audit_eligible",
                    "structural_score_eligible",
                    "qualified_score_eligible",
                    "reason_code",
                    "explanation_template",
                ):
                    self.assertIn(field, spec)
                self.assertTrue(spec["definition"])
                self.assertTrue(spec["explanation_template"])

    def test_the_required_match_types_are_all_defined(self) -> None:
        for name in (
            "exact_atomic_intervention",
            "normalized_atomic_intervention",
            "verified_atomic_alias",
            "exact_regimen",
            "regimen_component_related",
            "regimen_subset_mismatch",
            "regimen_superset_mismatch",
            "exact_intervention_class",
            "class_member_related",
            "aggregate_member_related",
            "aggregate_not_separable",
            "mapping_pending",
            "unsupported",
            "unresolved",
            "no_intervention_constraint",
            "incompatible",
        ):
            with self.subTest(match=name):
                self.assertIn(name, MATCH_TYPES)

    def test_the_query_types_are_frozen(self) -> None:
        self.assertEqual(set(self.query_types["query_types"]), set(QUERY_TYPES))
        self.assertTrue(self.query_types["regimen_requires_structured_indicator"])

    def test_the_buckets_are_the_four_declared_ones(self) -> None:
        self.assertEqual(set(self.buckets["buckets"]), set(BUCKETS))
        self.assertTrue(self.buckets["audit_objects_are_never_deleted"])
        for row in self.simulation:
            with self.subTest(row=row["simulation_id"]):
                self.assertIn(row["bucket"], BUCKETS)

    def test_the_hierarchy_policy_is_declared_but_inactive(self) -> None:
        self.assertFalse(self.structural["hierarchy_policy_active"])
        relations = self.structural["disease_relations"]
        for name in ("explicit_parent", "explicit_child", "explicit_sibling"):
            with self.subTest(relation=name):
                self.assertFalse(relations[name]["active"])
        for name in ("exact", "normalized_exact", "verified_alias"):
            with self.subTest(relation=name):
                self.assertTrue(relations[name]["primary_hard_match"])

    def test_no_weight_was_defined(self) -> None:
        self.assertFalse(self.eligibility["weights_defined_in_this_phase"])
        self.assertFalse(self.manifest["weights_defined"])
        blob = json.dumps(self.features)
        self.assertNotIn("weight", blob.lower())

    def test_the_scoring_audit_classifies_every_component(self) -> None:
        allowed = {
            "reusable_unchanged",
            "reusable_with_typed_input",
            "requires_claim_type_branch",
            "requires_new_feature",
            "should_be_removed",
            "incompatible_with_new_schema",
        }
        self.assertGreaterEqual(len(self.audit), 20)
        for row in self.audit:
            with self.subTest(component=row["component_id"]):
                self.assertIn(row["classification"], allowed)
                self.assertTrue(row["assumption"])
                self.assertTrue(row["note"])

    def test_the_compensable_penalties_are_marked_for_removal(self) -> None:
        removals = {
            row["component"]
            for row in self.audit
            if row["classification"] == "should_be_removed"
        }
        for penalty in (
            "weights.penalty_pending_terminology",
            "weights.penalty_not_separable",
            "weights.penalty_unresolved",
        ):
            with self.subTest(penalty=penalty):
                self.assertIn(penalty, removals)

    def test_every_feature_declares_its_role(self) -> None:
        self.assertGreaterEqual(len(self.features), 11)
        for row in self.features:
            with self.subTest(feature=row["feature_id"]):
                for field in (
                    "domain",
                    "meaning",
                    "allowed_values",
                    "can_increase_score",
                    "penalty_only",
                    "is_gate",
                    "provenance_required",
                ):
                    self.assertIn(field, row)
                self.assertTrue(row["provenance_required"])

    def test_the_guard_features_can_never_increase_the_score(self) -> None:
        for row in self.features:
            if row["feature"].endswith("_guard") or row["feature"].endswith("_relation"):
                with self.subTest(feature=row["feature"]):
                    self.assertFalse(row["can_increase_score"])
                    self.assertTrue(row["is_gate"])

    def test_the_output_contract_is_typed(self) -> None:
        fields = self.output["fields"]
        for name in (
            "claim_id",
            "parent_graph_evidence_id",
            "claim_type",
            "intervention_representation",
            "structural_match",
            "score_eligibility",
            "warnings",
            "provenance",
            "review_status",
            "deprecated",
            "audit_status",
        ):
            with self.subTest(field=name):
                self.assertIn(name, fields)
        self.assertIn("atomic", fields["intervention_representation"])
        self.assertIn("regimen", fields["intervention_representation"])
        self.assertIn("class", fields["intervention_representation"])
        self.assertTrue(self.output["intervention_representation_contract"]["typed"])
        self.assertTrue(
            self.output["intervention_representation_contract"][
                "flattening_to_single_string_forbidden"
            ]
        )

    def test_the_warning_codes_are_frozen(self) -> None:
        self.assertEqual(set(self.codes["warning_codes"]), set(WARNING_CODES))
        for row in self.simulation:
            for code in row["warning_codes"]:
                with self.subTest(code=code):
                    self.assertIn(code, WARNING_CODES)

    def test_the_migration_impact_covers_every_required_area(self) -> None:
        areas = self.impact["areas"]
        for name in (
            "adapter_output",
            "repository",
            "corpus",
            "qualification_links",
            "qualified_evidence_view",
            "retrieval_indices",
            "candidate_generation",
            "scoring",
            "ranking",
            "warnings",
            "metrics",
            "benchmark",
            "report_renderer",
            "backward_compatibility",
            "audit_log",
        ):
            with self.subTest(area=name):
                self.assertIn(name, areas)
                self.assertTrue(areas[name]["change"])
        self.assertEqual(self.impact["status"], "described_not_applied")

    def test_readiness_keeps_corpus_and_rerun_closed(self) -> None:
        readiness = self.manifest["readiness"]
        for key in (
            "claim_types_frozen",
            "query_types_frozen",
            "structural_match_rules_frozen",
            "candidate_bucket_rules_frozen",
            "score_eligibility_rules_frozen",
            "warning_codes_frozen",
            "current_scoring_audited",
            "new_weights_required",
            "adapter_migration_ready",
        ):
            with self.subTest(key=key):
                self.assertTrue(readiness[key])
        self.assertFalse(readiness["corpus_regeneration_ready"])
        self.assertFalse(readiness["hierarchy_policy_ready"])
        self.assertFalse(readiness["full_exploratory_rerun_ready"])


# ── determinismo e integrita' ─────────────────────────────────────────────────


class TestDeterminism(ContractCase):
    def test_rebuilding_reproduces_the_committed_artifacts(self) -> None:
        for name, content in build().items():
            with self.subTest(artifact=name):
                self.assertEqual(content, (CONTRACT / name).read_text(encoding="utf-8"))

    def test_the_build_is_identical_twice(self) -> None:
        self.assertEqual(build(), build())

    def test_reversing_the_query_order_changes_nothing(self) -> None:
        self.assertEqual(build(reverse=False), build(reverse=True))

    def test_the_manifest_hashes_match_the_files_on_disk(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                content = (CONTRACT / name).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(content.encode("utf-8")).hexdigest(), expected)

    def test_the_adjudication_is_unchanged(self) -> None:
        recorded = self.manifest["input_hashes"]["adjudication"]
        files = sorted(p for p in ADJ.rglob("*") if p.is_file())
        self.assertEqual(recorded["file_count"], len(files))

    def test_the_frozen_components_are_unchanged(self) -> None:
        for path, expected in self.manifest["input_hashes"]["frozen_artifacts"].items():
            with self.subTest(path=path):
                self.assertIsNotNone(expected, f"artefatto mancante: {path}")
                self.assertEqual(
                    hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest(), expected
                )

    def test_the_gold_did_not_drive_any_rule_or_weight(self) -> None:
        self.assertFalse(self.manifest["gold_used_for_rules_or_weights"])
        for path in sorted(CONTRACT.iterdir()):
            if not path.is_file() or path.name == "contract_manifest.json":
                continue
            blob = path.read_text(encoding="utf-8").lower()
            with self.subTest(artifact=path.name):
                for fragment in ("clinical_gold", "provisional_gold", "expected_claims", "recall@"):
                    self.assertNotIn(fragment, blob)


class TestUntouchedArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scope = PhaseScope(
            REPO_ROOT.parent, START_SHA, PHASE_END_SHA, ALLOWED_WRITE_PREFIXES
        )
        cls.changed = cls.scope.changed_paths()

    def test_adapter_corpus_retriever_and_scoring_are_unchanged(self) -> None:
        for path in FROZEN_PATHS:
            with self.subTest(path=path):
                self.assertNotIn(path, self.changed)

    def test_no_upstream_review_artifact_was_modified(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                for prefix in (
                    "multi_intervention_source_review/",
                    "multi_intervention_second_review/",
                    "multi_intervention_review_comparison/",
                    "multi_intervention_adjudication/",
                ):
                    self.assertNotIn(prefix, path)

    def test_no_qualified_evidence_view_was_regenerated(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                self.assertNotIn("qualified_retriever_prototype", path)
                self.assertNotIn("qualification_corpus", path)

    def test_the_branch_only_wrote_inside_the_contract_perimeter(self) -> None:
        self.assertEqual(
            self.scope.violations(self.changed),
            [],
            "modifica fuori dal perimetro del contratto",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
