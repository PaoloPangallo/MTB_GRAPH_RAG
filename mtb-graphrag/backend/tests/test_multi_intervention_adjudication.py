"""Protegge le decisioni dell'adjudication e gli invarianti del modello dei claim.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano LLM. Il gold non guida nessuna decisione e i test lo
verificano invece di assumerlo.
"""

from __future__ import annotations

import hashlib
import json
import unittest

from benchmarks.mtb_evidence.evaluation import external_inputs as EXTERNAL
from pathlib import Path

from backend.tests.phase_scope import PhaseScope
from benchmarks.mtb_evidence.evaluation.multi_intervention_adjudication import (
    ADJUDICATOR_LABELS,
    ASSOCIATION_OUTCOMES,
    CLAIM_TYPES,
    GROUP_ADJUDICATIONS,
    PARENT_NO_LONGER,
    PARENT_SEMANTICS_DECISION,
    PARENT_SEMANTICS_OPTIONS,
    PENDING_ALIASES,
    REASON_CODES,
    ProhibitedInference,
    ScopeMismatch,
    canonical_regimen,
    check_claim_ids,
    check_claim_is_materializable,
    check_group_adjudication,
    check_no_regimen_split,
    claim_id,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_adjudication_artifacts import build

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
ADJ = V3 / "multi_intervention_adjudication"
FIRST = V3 / "multi_intervention_source_review"
REPLICATE = V3 / "multi_intervention_second_review"
COMPARISON = V3 / "multi_intervention_review_comparison"
START_SHA = "3ef3e99a9ec0491aab37384f336e857ea08aa8a2"
# La fase di adjudication si chiude qui. Come per le due fasi precedenti, il
# perimetro va misurato su un intervallo chiuso: confrontarlo con l'albero di
# lavoro lo farebbe fallire a ogni fase successiva invece che quando questa fase
# ha scritto dove non doveva.
PHASE_END_SHA = "6341d12088c4b856320eae3ece90936b9bbdd64b"

MANDATORY_GROUPS = (
    "evidence:275",
    "evidence:4759",
    "evidence:3811",
    "evidence:11240",
    "evidence:12131",
)

FROZEN_PATHS = (
    "backend/pipeline/evidence/v2_adapter.py",
    "backend/pipeline/evidence/corpus_manifest.py",
    "backend/pipeline/evidence/corpus_regeneration.py",
    "backend/pipeline/evidence/qualified_retriever.py",
    "backend/pipeline/evidence/qualified_retrieval_scoring.py",
    "backend/pipeline/evidence/qualified_retriever_scoring_config.json",
)

ALLOWED_WRITE_PREFIXES = (
    "benchmarks/mtb_evidence/v3/multi_intervention_adjudication/",
    "benchmarks/mtb_evidence/evaluation/multi_intervention_adjudication.py",
    "benchmarks/mtb_evidence/evaluation/scripts/build_adjudication_artifacts.py",
    "benchmarks/mtb_evidence/evaluation/data/adjudication_",
    "backend/tests/test_multi_intervention_adjudication.py",
    # Il test di perimetro del confronto misurava il proprio intervallo contro
    # l'albero di lavoro invece che contro la fine della propria fase, e sarebbe
    # fallito qui. Corretto dove il difetto e' emerso, in un commit separato; gli
    # artefatti del confronto restano intatti.
    "backend/tests/test_multi_intervention_review_comparison.py",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sample_claim(**overrides) -> dict:
    payload = {
        "claim_id": "CLM-test",
        "claim_type": "atomic_intervention_claim",
        "graph_evidence_parent": "evidence:1",
        "source_id": "PMID:1",
        "source_unit_id": "SU-1",
        "locator": "abstract, braccio A",
        "locator_sufficient": True,
        "biomarker": "EGFR L858R",
        "disease_scope": "Cancer",
        "canonical_intervention_or_regimen": "erlotinib",
        "direction": "sensitivity",
        "polarity": "supports",
        "result_attributable_to_intervention": True,
        "aggregate_to_specific_used": False,
        "pending_alias_used_as_equivalence": False,
        "source_literal_terms": ["erlotinib"],
    }
    payload.update(overrides)
    return payload


class AdjudicationCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metadata = json.loads((ADJ / "adjudicator_metadata.json").read_text(encoding="utf-8"))
        cls.scope = json.loads((ADJ / "adjudication_scope.json").read_text(encoding="utf-8"))
        cls.semantics = json.loads(
            (ADJ / "schema_semantics_decision.json").read_text(encoding="utf-8")
        )
        cls.groups = load_jsonl(ADJ / "packet_adjudications.jsonl")
        cls.interventions = load_jsonl(ADJ / "intervention_adjudications.jsonl")
        cls.children = load_jsonl(ADJ / "child_claim_adjudications.jsonl")
        cls.priority = load_jsonl(ADJ / "priority_concordant_case_adjudications.jsonl")
        cls.regimens = load_jsonl(ADJ / "regimen_adjudications.jsonl")
        cls.aggregates = load_jsonl(ADJ / "aggregate_adjudications.jsonl")
        cls.unsupported = load_jsonl(ADJ / "unsupported_associations.jsonl")
        cls.unresolved = load_jsonl(ADJ / "unresolved_associations.jsonl")
        cls.terminology = load_jsonl(ADJ / "terminology_review_queue.jsonl")
        cls.claims = load_jsonl(ADJ / "approved_claim_simulation.jsonl")
        cls.claim_ids = load_jsonl(ADJ / "claim_id_simulation.jsonl")
        cls.simulation = json.loads(
            (ADJ / "post_adjudication_schema_simulation.json").read_text(encoding="utf-8")
        )
        cls.migration = json.loads(
            (ADJ / "migration_specification.json").read_text(encoding="utf-8")
        )
        cls.manifest = json.loads(
            (ADJ / "adjudication_manifest.json").read_text(encoding="utf-8")
        )


# ── perimetro ─────────────────────────────────────────────────────────────────


class TestScope(AdjudicationCase):
    def test_twelve_packets_were_adjudicated(self) -> None:
        required = {
            row["graph_evidence_id"]
            for row in load_jsonl(COMPARISON / "adjudication_required_groups.jsonl")
        }
        self.assertEqual(len(required), 12)
        adjudicated = {row["graph_evidence_id"] for row in self.groups}
        self.assertTrue(required.issubset(adjudicated))
        self.assertEqual(len(self.groups), 13)

    def test_every_mandatory_group_is_adjudicated(self) -> None:
        adjudicated = {row["graph_evidence_id"] for row in self.groups}
        for group in MANDATORY_GROUPS:
            with self.subTest(group=group):
                self.assertIn(group, adjudicated)

    def test_every_association_has_a_decision(self) -> None:
        self.assertEqual(len(self.interventions), 28)
        for row in self.interventions:
            with self.subTest(row=row["adjudication_id"]):
                self.assertIn(row["association_outcome"], ASSOCIATION_OUTCOMES)
                self.assertTrue(row["reason_codes"])
                self.assertTrue(row["rationale"])
                for code in row["reason_codes"]:
                    self.assertIn(code, REASON_CODES)

    def test_every_group_decision_is_in_the_vocabulary(self) -> None:
        for row in self.groups:
            with self.subTest(group=row["graph_evidence_id"]):
                self.assertIn(row["adjudication"], GROUP_ADJUDICATIONS)

    def test_the_group_guard_still_accepts_every_recorded_decision(self) -> None:
        by_group: dict[str, list[dict]] = {}
        for row in self.interventions:
            by_group.setdefault(row["graph_evidence_id"], []).append(row)
        for row in self.groups:
            with self.subTest(group=row["graph_evidence_id"]):
                check_group_adjudication(row["adjudication"], by_group[row["graph_evidence_id"]])

    def test_the_provisional_consensus_group_was_verified(self) -> None:
        row = next(item for item in self.groups if item["graph_evidence_id"] == "evidence:12131")
        self.assertEqual(row["adjudication_action"], "confirm_provisional_consensus")
        self.assertTrue(row["approved_claims"])
        case = next(
            item for item in self.priority if item["graph_evidence_id"] == "evidence:12131"
        )
        for field in (
            "consensus_integrity_confirmed",
            "pending_mapping_absent",
            "locators_sufficient",
            "aggregate_to_specific_absent",
            "biomarker_scope_mismatch_absent",
        ):
            with self.subTest(field=field):
                self.assertTrue(case[field])


# ── semantica del parent ──────────────────────────────────────────────────────


class TestParentSemantics(AdjudicationCase):
    def test_the_decision_is_single_and_unambiguous(self) -> None:
        self.assertIn(self.semantics["parent_semantics"], PARENT_SEMANTICS_OPTIONS)
        self.assertEqual(self.semantics["parent_semantics"], PARENT_SEMANTICS_DECISION)
        self.assertEqual(self.semantics["decision"], self.semantics["parent_semantics"])

    def test_the_recommendation_was_not_approved_automatically(self) -> None:
        self.assertFalse(self.semantics["automatically_approved"])
        self.assertGreaterEqual(len(self.semantics["decision_rationale"]), 2)
        self.assertEqual(len(self.semantics["alternatives_considered"]), 2)
        for alternative in self.semantics["alternatives_considered"]:
            with self.subTest(option=alternative["option"]):
                self.assertTrue(alternative["arguments_in_favour"])
                self.assertTrue(alternative["reasons_rejected"])

    def test_the_parent_stops_being_a_claim(self) -> None:
        for item in PARENT_NO_LONGER:
            with self.subTest(item=item):
                self.assertIn(item, self.semantics["parent_no_longer"])
        self.assertIn("counted_as_therapy_claim", self.semantics["parent_no_longer"])
        self.assertIn(
            "used_as_automatic_substitute_for_the_first_child", self.semantics["parent_no_longer"]
        )

    def test_no_claim_is_privileged_because_the_parent_carried_it(self) -> None:
        """Gli interventi del parent passano dagli stessi controlli degli altri."""
        parents = [row for row in self.interventions if row["is_parent_intervention"]]
        self.assertEqual(len(parents), 13)
        approved = [row for row in parents if row["claim_id"]]
        rejected = [row for row in parents if not row["claim_id"]]
        self.assertTrue(approved, "almeno un intervento del parent deve produrre un claim")
        self.assertTrue(
            rejected,
            "almeno un intervento del parent deve essere rifiutato: nessuna corsia preferenziale",
        )

    def test_every_parent_is_preserved(self) -> None:
        self.assertEqual(self.simulation["parents_preserved"], 13)
        self.assertEqual(self.simulation["parents_total"], 13)


# ── claim ─────────────────────────────────────────────────────────────────────


class TestClaims(AdjudicationCase):
    def test_every_approved_claim_passes_its_own_guard(self) -> None:
        self.assertTrue(self.claims)
        for claim in self.claims:
            with self.subTest(claim=claim["claim_id"]):
                check_claim_is_materializable(claim)

    def test_every_approved_claim_has_a_locator_and_a_source_unit(self) -> None:
        for claim in self.claims:
            with self.subTest(claim=claim["claim_id"]):
                self.assertTrue(str(claim["locator"]).strip())
                self.assertTrue(claim["source_unit_id"])
                self.assertTrue(claim["locator_sufficient"])

    def test_every_claim_declares_an_explicit_disease_scope(self) -> None:
        for claim in self.claims:
            with self.subTest(claim=claim["claim_id"]):
                self.assertTrue(str(claim["disease_scope"]).strip())

    def test_the_three_claim_types_are_all_present_and_distinct(self) -> None:
        types = {claim["claim_type"] for claim in self.claims}
        self.assertEqual(types, set(CLAIM_TYPES))

    def test_no_aggregate_claim_authorizes_member_specific_claims(self) -> None:
        self.assertTrue(self.aggregates)
        for row in self.aggregates:
            with self.subTest(claim=row["claim_id"]):
                self.assertFalse(row["permits_member_specific_claims"])

    def test_no_aggregate_result_produced_a_member_specific_claim(self) -> None:
        aggregate_parents = {row["graph_evidence_parent"] for row in self.aggregates}
        for claim in self.claims:
            if claim["claim_type"] != "atomic_intervention_claim":
                continue
            with self.subTest(claim=claim["claim_id"]):
                self.assertNotIn(
                    claim["graph_evidence_parent"],
                    aggregate_parents,
                    "un claim atomico non puo' nascere dallo stesso parent di un aggregato",
                )

    def test_no_regimen_was_split_into_its_components(self) -> None:
        check_no_regimen_split(self.claims, self.interventions)
        regimen_units = {(row["graph_evidence_parent"], row["source_unit_id"]) for row in self.regimens}
        for claim in self.claims:
            if claim["claim_type"] != "atomic_intervention_claim":
                continue
            with self.subTest(claim=claim["claim_id"]):
                self.assertNotIn(
                    (claim["graph_evidence_parent"], claim["source_unit_id"]), regimen_units
                )

    def test_regimen_results_are_never_propagated_to_components(self) -> None:
        for row in self.regimens:
            with self.subTest(claim=row["claim_id"]):
                self.assertFalse(row["components_propagated"])
                self.assertGreaterEqual(len(row["regimen_components"]), 2)
                self.assertEqual(row["canonical_regimen"], canonical_regimen(row["regimen_components"]))

    def test_the_guard_rejects_a_claim_without_a_locator(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_claim_is_materializable(sample_claim(locator_sufficient=False))

    def test_the_guard_rejects_an_aggregate_to_specific_claim(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_claim_is_materializable(sample_claim(aggregate_to_specific_used=True))

    def test_the_guard_rejects_a_result_not_attributable(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_claim_is_materializable(
                sample_claim(result_attributable_to_intervention=False)
            )

    def test_the_guard_rejects_an_implicit_disease_scope(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_claim_is_materializable(sample_claim(disease_scope=""))

    def test_the_guard_rejects_a_one_component_regimen(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_claim_is_materializable(
                sample_claim(
                    claim_type="regimen_claim",
                    regimen_components=["erlotinib"],
                    canonical_intervention_or_regimen="erlotinib",
                )
            )

    def test_the_guard_rejects_an_aggregate_that_permits_member_claims(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_claim_is_materializable(
                sample_claim(
                    claim_type="aggregate_intervention_claim",
                    aggregate_members=["a", "b"],
                    permits_member_specific_claims=True,
                )
            )


# ── mapping pending ───────────────────────────────────────────────────────────


class TestPendingMappings(AdjudicationCase):
    def test_no_pending_generic_name_appears_in_an_approved_claim(self) -> None:
        for claim in self.claims:
            canonical = claim["canonical_intervention_or_regimen"].lower()
            for code, generic in PENDING_ALIASES:
                with self.subTest(claim=claim["claim_id"], alias=generic):
                    if code.lower() in canonical:
                        self.assertNotIn(
                            generic.lower(),
                            canonical,
                            "codice e nome generico canonicalizzati insieme",
                        )

    def test_the_guard_rejects_a_promoted_development_code(self) -> None:
        with self.assertRaises(ProhibitedInference):
            check_claim_is_materializable(
                sample_claim(
                    canonical_intervention_or_regimen="infigratinib",
                    source_literal_terms=["BGJ398"],
                )
            )

    def test_pending_interventions_stay_unresolved(self) -> None:
        pending = {"infigratinib", "luminespib"}
        for row in self.interventions:
            if row["intervention"].lower() in pending:
                with self.subTest(row=row["adjudication_id"]):
                    self.assertEqual(row["association_outcome"], "unresolved_association")
                    self.assertIsNone(row["claim_id"])
                    self.assertIn("PENDING_ALIAS_BLOCKS_MATERIALIZATION", row["reason_codes"])

    def test_the_terminology_queue_never_merges(self) -> None:
        self.assertTrue(self.terminology)
        for row in self.terminology:
            with self.subTest(entry=row["queue_id"]):
                self.assertFalse(row["merged"])
                self.assertEqual(row["action"], "terminology_review_required")
                self.assertTrue(row["affected_groups"])

    def test_the_fgfr_aggregate_keeps_the_literal_source_terms(self) -> None:
        rows = [row for row in self.aggregates if "BGJ398" in row["aggregate_members"]]
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(claim=row["claim_id"]):
                self.assertNotIn("infigratinib", row["canonical_aggregate"].lower())


# ── casi obbligatori ──────────────────────────────────────────────────────────


class TestMandatoryCases(AdjudicationCase):
    def case(self, group: str) -> dict:
        return next(row for row in self.priority if row["graph_evidence_id"] == group)

    def test_evidence_275_rejects_the_specific_attribution(self) -> None:
        case = self.case("evidence:275")
        self.assertFalse(case["parent_intervention_present_in_source"])
        self.assertTrue(case["result_is_class_level"])
        self.assertEqual(case["current_specific_claim_disposition"], "rejected")
        for code in (
            "PARENT_INTERVENTION_NOT_PRESENT_IN_SOURCE",
            "CLASS_LEVEL_RESULT_ONLY",
            "SPECIFIC_DRUG_ATTRIBUTION_UNSUPPORTED",
            "AGGREGATE_CLAIM_SUPPORTED",
        ):
            self.assertIn(code, case["reason_codes"])
        rows = [row for row in self.interventions if row["graph_evidence_id"] == "evidence:275"]
        for row in rows:
            with self.subTest(drug=row["intervention"]):
                self.assertEqual(row["association_outcome"], "unsupported_association")
        aggregate = [row for row in self.aggregates if row["graph_evidence_parent"] == "evidence:275"]
        self.assertEqual(len(aggregate), 1)
        self.assertEqual(aggregate[0]["aggregate_kind"], "drug_class")

    def test_evidence_275_never_attributes_the_class_result_to_a_specific_drug(self) -> None:
        aggregate = next(
            row for row in self.aggregates if row["graph_evidence_parent"] == "evidence:275"
        )
        members = " ".join(aggregate["aggregate_members"]).lower()
        self.assertNotIn("erlotinib", members)
        self.assertNotIn("gefitinib", members)

    def test_evidence_4759_is_rejected_for_biomarker_scope(self) -> None:
        case = self.case("evidence:4759")
        self.assertTrue(case["biomarker_scope_mismatch"])
        self.assertTrue(case["result_concerns_uncommon_mutations"])
        self.assertFalse(case["common_mutations_explicitly_included_in_result"])
        self.assertEqual(case["current_claim_disposition"], "rejected")
        for code in (
            "BIOMARKER_SCOPE_MISMATCH",
            "RESULT_ONLY_FOR_UNCOMMON_MUTATIONS",
            "CLAIM_BIOMARKER_NOT_SUPPORTED",
        ):
            self.assertIn(code, case["reason_codes"])
        group = next(row for row in self.groups if row["graph_evidence_id"] == "evidence:4759")
        self.assertEqual(group["adjudication"], "unsupported_associations_rejected")
        self.assertEqual(group["approved_claims"], [])

    def test_evidence_3811_stays_unresolved_without_invented_values(self) -> None:
        case = self.case("evidence:3811")
        self.assertFalse(case["ic50_values_available"])
        self.assertFalse(case["results_specific_to_l858r"])
        self.assertFalse(case["locators_sufficient"])
        group = next(row for row in self.groups if row["graph_evidence_id"] == "evidence:3811")
        self.assertEqual(group["adjudication"], "unresolved_deferred")
        self.assertEqual(group["approved_claims"], [])
        self.assertEqual(len(group["unresolved_associations"]), 3)

    def test_evidence_11240_approves_a_regimen_and_an_atomic_claim(self) -> None:
        group = next(row for row in self.groups if row["graph_evidence_id"] == "evidence:11240")
        self.assertEqual(group["adjudication"], "mixed_claim_structure_approved")
        self.assertEqual(
            set(group["approved_claim_types"]),
            {"atomic_intervention_claim", "regimen_claim"},
        )
        claims = [row for row in self.claims if row["graph_evidence_parent"] == "evidence:11240"]
        units = {claim["source_unit_id"] for claim in claims}
        self.assertEqual(len(units), 2, "i due claim devono poggiare su unita' documentali diverse")

    def test_the_mandatory_cases_all_carry_a_decision_and_a_note(self) -> None:
        for group in MANDATORY_GROUPS:
            with self.subTest(group=group):
                case = self.case(group)
                self.assertTrue(case["decision"])
                self.assertTrue(case["adjudicator_note"])


# ── child claim ───────────────────────────────────────────────────────────────


class TestChildClaims(AdjudicationCase):
    def test_all_three_comparison_sets_are_adjudicated(self) -> None:
        statuses: dict[str, int] = {}
        for row in self.children:
            statuses[row["child_status_in_comparison"]] = (
                statuses.get(row["child_status_in_comparison"], 0) + 1
            )
        self.assertEqual(statuses.get("proposed_by_both"), 3)
        self.assertEqual(statuses.get("proposed_by_first_only"), 5)
        self.assertEqual(statuses.get("proposed_by_replicate_only", 0), 0)

    def test_the_children_agreed_by_both_are_approved(self) -> None:
        rows = [row for row in self.children if row["child_status_in_comparison"] == "proposed_by_both"]
        for row in rows:
            with self.subTest(child=row["child_comparison_id"]):
                self.assertEqual(row["adjudicated_outcome"], "atomic_intervention_claim")
                self.assertTrue(row["materialization_eligible"])
                self.assertTrue(row["adjudicated_claim_id"])

    def test_the_five_first_only_children_answer_all_five_questions(self) -> None:
        rows = [
            row for row in self.children if row["child_status_in_comparison"] == "proposed_by_first_only"
        ]
        self.assertEqual(len(rows), 5)
        for row in rows:
            with self.subTest(child=row["child_comparison_id"]):
                self.assertTrue(row["result_is_intervention_specific"])
                self.assertTrue(row["replicate_declined_only_because_parent_carried_it"])
                self.assertTrue(row["child_needed_under_container_semantics"])
                self.assertTrue(row["locator_sufficient"])
                self.assertTrue(row["semantic_duplication_risk"])
                self.assertTrue(row["is_parent_intervention"])
                self.assertEqual(row["adjudicated_outcome"], "atomic_intervention_claim")

    def test_every_child_record_carries_the_required_fields(self) -> None:
        for row in self.children:
            with self.subTest(child=row["child_comparison_id"]):
                for field in (
                    "graph_evidence_id",
                    "intervention",
                    "source_unit_id",
                    "locator",
                    "biomarker",
                    "direction",
                    "polarity",
                    "first_review_decision",
                    "replicate_decision",
                    "adjudicated_outcome",
                    "rationale",
                ):
                    self.assertTrue(row[field], f"{field} vuoto")


# ── identita' e simulazione ───────────────────────────────────────────────────


class TestClaimIdentity(AdjudicationCase):
    def test_the_simulated_ids_have_no_collisions(self) -> None:
        result = check_claim_ids(self.claims)
        self.assertEqual(result["collision_count"], 0)
        self.assertEqual(result["distinct_ids"], len(self.claims))
        self.assertTrue(result["order_independent"])
        self.assertTrue(result["stable_on_recomputation"])

    def test_the_recorded_ids_match_the_formula(self) -> None:
        for claim in self.claims:
            with self.subTest(claim=claim["claim_id"]):
                self.assertEqual(claim_id(claim), claim["claim_id"])

    def test_a_regimen_id_does_not_depend_on_component_order(self) -> None:
        forward = canonical_regimen(["ramucirumab", "erlotinib"])
        backward = canonical_regimen(["erlotinib", "ramucirumab"])
        self.assertEqual(forward, backward)

    def test_two_claims_differing_only_by_biomarker_get_different_ids(self) -> None:
        first = sample_claim(biomarker="FGFR2::BICC1 Fusion")
        second = sample_claim(biomarker="FGFR2::AHCYL1 Fusion")
        self.assertNotEqual(claim_id(first), claim_id(second))

    def test_the_ids_are_not_implemented_in_the_operational_corpus(self) -> None:
        for row in self.claim_ids:
            with self.subTest(claim=row["claim_id"]):
                self.assertFalse(row["implemented_in_operational_corpus"])
                self.assertTrue(row["parent_lineage_preserved"])


class TestSimulation(AdjudicationCase):
    def test_the_counts_are_internally_consistent(self) -> None:
        self.assertEqual(
            self.simulation["new_claims_total"],
            self.simulation["atomic_claims_approved"]
            + self.simulation["aggregate_claims_approved"]
            + self.simulation["regimen_claims_approved"],
        )
        self.assertEqual(len(self.claims), self.simulation["new_claims_total"])
        self.assertEqual(
            self.simulation["resulting_claim_count"],
            self.simulation["current_operational_statement_count"]
            - self.simulation["current_statements_to_replace"]
            + self.simulation["new_claims_total"],
        )

    def test_every_association_is_accounted_for(self) -> None:
        outcomes = {row["association_outcome"] for row in self.interventions}
        self.assertTrue(outcomes.issubset(set(ASSOCIATION_OUTCOMES)))
        self.assertEqual(
            self.simulation["unsupported_associations"] + self.simulation["unresolved_associations"],
            sum(1 for row in self.interventions if row["claim_id"] is None),
        )

    def test_nothing_operational_was_regenerated(self) -> None:
        for field in (
            "operational_corpus_modified",
            "adapter_modified",
            "retriever_modified",
            "scoring_modified",
            "new_retrieval_metrics_computed",
        ):
            with self.subTest(field=field):
                self.assertFalse(self.simulation[field])

    def test_the_migration_specification_has_all_twenty_sections(self) -> None:
        self.assertEqual(len(self.migration["sections"]), 20)
        self.assertEqual(self.migration["status"], "specified_not_applied")
        for key, section in self.migration["sections"].items():
            with self.subTest(section=key):
                self.assertTrue(section["title"])
                self.assertTrue(section["content"])

    def test_readiness_keeps_corpus_and_rerun_closed(self) -> None:
        readiness = self.manifest["readiness"]
        self.assertTrue(readiness["parent_semantics_decided"])
        self.assertTrue(readiness["all_packets_adjudicated"])
        self.assertTrue(readiness["priority_concordant_cases_adjudicated"])
        self.assertTrue(readiness["migration_specification_complete"])
        self.assertTrue(readiness["adapter_schema_revision_ready"])
        self.assertFalse(readiness["corpus_regeneration_ready"])
        self.assertFalse(readiness["hierarchy_policy_ready"])
        self.assertFalse(readiness["full_exploratory_rerun_ready"])


# ── indipendenza, gold, integrita' ────────────────────────────────────────────


class TestLabelsAndGold(AdjudicationCase):
    def test_the_adjudication_is_not_declared_independent(self) -> None:
        self.assertEqual(self.metadata["adjudicator_role"], "author_adjudicator")
        self.assertEqual(self.metadata["adjudication_independence"], "non_independent")
        self.assertNotEqual(
            self.metadata["adjudicator_role"], "independent_domain_adjudicator"
        )

    def test_nothing_becomes_final_gold(self) -> None:
        self.assertEqual(self.metadata["adjudication_status"], "completed")
        self.assertEqual(self.metadata["propagation_policy"], "prototype_only")
        self.assertFalse(self.metadata["hard_filterable"])
        self.assertFalse(self.metadata["final_clinical_gold"])

    def test_every_structured_artifact_carries_the_labels(self) -> None:
        for path in sorted(ADJ.glob("*.json*")):
            rows = (
                load_jsonl(path)
                if path.suffix == ".jsonl"
                else [json.loads(path.read_text(encoding="utf-8"))]
            )
            for row in rows:
                with self.subTest(artifact=path.name):
                    self.assertEqual(row.get("propagation_policy"), "prototype_only")
                    self.assertFalse(row.get("final_clinical_gold"))
                    self.assertFalse(row.get("gold_used_for_decisions"))

    def test_the_gold_did_not_drive_any_decision(self) -> None:
        self.assertFalse(self.scope["gold_used_for_decisions"])
        inventory = self.simulation["gold_records_inventory"]
        self.assertFalse(inventory["gold_used_for_decisions"])
        self.assertTrue(inventory["gold_read_after_decisions_frozen"])
        self.assertTrue(ADJUDICATOR_LABELS["gold_used_for_decisions"] is False)

    def test_no_artifact_carries_gold_content_or_retrieval_metrics(self) -> None:
        for path in sorted(ADJ.iterdir()):
            if not path.is_file() or path.name == "adjudication_scope.json":
                continue
            blob = path.read_text(encoding="utf-8").lower()
            with self.subTest(artifact=path.name):
                for fragment in ("expected_claims", "recall@", "ndcg", "provisional_gold"):
                    self.assertNotIn(fragment, blob)

    def test_the_upstream_annotations_are_unchanged(self) -> None:
        for label, directory in (
            ("first_review", FIRST),
            ("blinded_replicate", REPLICATE),
            ("review_comparison", COMPARISON),
        ):
            recorded = self.scope["input_hashes"][label]["files"]
            for name, expected in recorded.items():
                with self.subTest(review=label, artifact=name):
                    payload = (directory / name).read_bytes()
                    self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)

    def test_the_frozen_artifacts_are_unchanged(self) -> None:
        for path, expected in self.scope["input_hashes"]["frozen_artifacts"].items():
            with self.subTest(path=path):
                self.assertIsNotNone(expected)
                self.assertEqual(
                    hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest(), expected
                )


class TestDeterminism(AdjudicationCase):
    def test_rebuilding_reproduces_the_committed_artifacts(self) -> None:
        # Il manifest rigenerato incorpora il checksum dell'albero del bundle
        # gold (`bundle_present`, `sha256`). Senza il bundle la rigenerazione
        # produce `bundle_present: false` e non puo' riprodurre l'artefatto
        # committato: non e' un difetto del builder, e' un confronto che senza
        # l'ingresso esterno non ha soggetto.
        EXTERNAL.require_or_skip(EXTERNAL.GOLD_BUNDLE)
        for name, content in build().items():
            with self.subTest(artifact=name):
                self.assertEqual(content, (ADJ / name).read_text(encoding="utf-8"))

    def test_the_build_is_identical_twice(self) -> None:
        self.assertEqual(build(), build())

    def test_reversing_the_packet_order_changes_nothing(self) -> None:
        self.assertEqual(build(reverse=False), build(reverse=True))

    def test_the_manifest_hashes_match_the_files_on_disk(self) -> None:
        for name, expected in self.manifest["artifact_sha256"].items():
            with self.subTest(artifact=name):
                content = (ADJ / name).read_text(encoding="utf-8")
                self.assertEqual(hashlib.sha256(content.encode("utf-8")).hexdigest(), expected)


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
                ):
                    self.assertNotIn(prefix, path)

    def test_no_operational_statement_was_regenerated(self) -> None:
        for path in sorted(self.changed):
            with self.subTest(path=path):
                self.assertNotIn("qualification_corpus", path)
                self.assertNotIn("evidence_statements", path)

    def test_the_branch_only_wrote_inside_the_adjudication_perimeter(self) -> None:
        self.assertEqual(
            self.scope.violations(self.changed),
            [],
            "modifica fuori dal perimetro dell'adjudication",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
