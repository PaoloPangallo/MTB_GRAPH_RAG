"""Approvazione dell'autore su PMID 23344087: abstract-only, pannello non risolto.

Tutti offline. La fonte esiste soltanto come abstract, e questo cambia che cosa i
test devono proteggere. Le due fasi precedenti difendevano decisioni; qui la cosa
piu' facile da perdere e' un **limite**: un record che dimentica di dire quanto
poco documento ha visto sembra identico a uno scritto sul full text.

Gli errori che il file cerca:

- una unita' che dichiari `full_text_verified` su una fonte abstract-only;
- `unknown` scritto dove serve `not_separable`, che sposterebbe la colpa
  dell'assenza dalla fonte al lettore;
- una relazione fra cloni e linee cellulari che l'abstract non afferma;
- «less sensitive» promosso a resistenza completa;
- `ambiguous` letto come `conflicting`, cioe' un limite letto come smentita;
- un numero di paziente inventato per far sembrare tracciabile un caso che non lo e';
- e i soliti: gold che smette di essere provvisorio, packet ciechi che parlano,
  fasi gia' approvate che cambiano.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest

from backend.tests import erratum_support as ERRATUM_SUPPORT
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.pipeline.evidence.corpus_manifest import content_hash
from backend.pipeline.evidence.evidence_granularity import (
    GRANULARITY_CASE,
    is_non_generalizable,
)
from backend.pipeline.evidence.profile_unit import (
    COHORT_REVIEWED_PENDING_INDEPENDENT,
    COHORT_SUPERSEDED_BY_RESTRUCTURE,
    FIRST_REVIEW_COMPLETE,
    HUMAN_ONLY_STATUSES,
    UNIT_TYPES,
)
from backend.pipeline.evidence.propagation_guards import GUARD_V12_RULE_IDS, run_guards
from backend.pipeline.evidence.propagation_policy import PROTOTYPE_ONLY, validate_units
from backend.pipeline.evidence.source_basis import (
    ABSTRACT_ONLY,
    CONFIDENCE_PARTIAL,
    NOT_SEPARABLE,
)
from benchmarks.mtb_evidence.evaluation.author_approval_23344087 import (
    APPROVE_WITH_CORRECTIONS,
    APPROVED_UNIT_IDS,
    AUDIT_PROPOSED_UNITS,
    AUTHOR_APPROVED_ACTIVE_UNITS,
    CLINICAL_COHORT_ID,
    DETECTOR_PRINCIPLE,
    DOCUMENT_HASH,
    ENGINEERED_CLONES_PROPOSAL_ID,
    FORBIDDEN_STATUSES,
    LOCATOR_COUNT,
    PARENT_UNIT_ID,
    PATIENT_DERIVED_PROPOSAL_ID,
    PRECLINICAL_PANEL_ID,
    REJECTED_PROPOSALS,
    REJECTION_STATUS,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_REVIEW_PROPOSED_UNITS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVAL = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval_23344087"
PREVIOUS = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval_22235099"
FIRST_APPROVAL = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval"
FIRST_REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/first_review"
BATCH = REPO_ROOT / "benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"

STATEMENT_PARTIAL = "ES-V2-evidence-765"
STATEMENT_AMBIGUOUS = "ES-V2-evidence-767"

FIXED_TIMESTAMP = "2026-07-24T12:00:00+00:00"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def by_id(rows: list[dict], key: str = "profile_unit_id") -> dict[str, dict]:
    return {str(row[key]): row for row in rows}


# ── base documentale ──────────────────────────────────────────────────────────


class TestAbstractOnlyBasis(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = load_jsonl(APPROVAL / "author_approval_records.jsonl")[0]
        cls.units = load_jsonl(APPROVAL / "approved_profile_units.jsonl")

    # 23. source basis abstract-only
    def test_the_source_basis_is_abstract_only(self) -> None:
        self.assertEqual(self.record["source_basis"], ABSTRACT_ONLY)
        self.assertEqual(self.record["availability"], ABSTRACT_ONLY)
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["source_basis"], ABSTRACT_ONLY)

    # 24. structural confidence partial
    def test_the_structural_confidence_is_partial(self) -> None:
        self.assertEqual(self.record["structural_confidence"], CONFIDENCE_PARTIAL)
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["structural_confidence"], CONFIDENCE_PARTIAL)
                self.assertTrue(row["requires_full_text_or_independent_review"])

    def test_nothing_claims_the_full_text_was_verified(self) -> None:
        for payload in [self.record, *self.units]:
            with self.subTest(subject=payload.get("profile_unit_id") or "record"):
                self.assertFalse(payload["full_text_verified"])
                self.assertFalse(payload["full_text_stored"])

    def test_the_unavailability_declaration_is_preserved(self) -> None:
        access = self.record["full_text_access"]
        self.assertFalse(access["full_text_publicly_available"])
        self.assertEqual(access["europe_pmc_status"], "subscription required")
        self.assertFalse(access["in_pmc"])
        self.assertFalse(access["open_access"])
        self.assertEqual(access["public_access_route"], "none")
        self.assertIn("Subscription required", access["declaration"])

    def test_the_abstract_hash_and_locators_match_the_batch(self) -> None:
        access = next(
            row
            for row in load_jsonl(BATCH / "source_access_verification.jsonl")
            if row["profile_unit_id"] == PARENT_UNIT_ID
        )
        self.assertEqual(access["document_hash"], DOCUMENT_HASH)
        self.assertEqual(access["stored_abstract_hash"], DOCUMENT_HASH)
        self.assertTrue(access["abstract_hash_matches"])
        self.assertEqual(access["locators_verified"], LOCATOR_COUNT)
        self.assertEqual(access["match_type_counts"], {"exact": 6})
        self.assertEqual(access["availability"], ABSTRACT_ONLY)
        self.assertEqual(access["pmc_id"], "")

    def test_the_source_check_is_recorded_on_the_approval(self) -> None:
        check = self.record["source_check"]
        self.assertEqual(check["abstract_hash"], DOCUMENT_HASH)
        self.assertEqual(check["locators_verified"], LOCATOR_COUNT)
        self.assertEqual(check["locators_not_verified"], 0)
        self.assertEqual(check["availability"], ABSTRACT_ONLY)
        self.assertFalse(check["full_text_stored"])
        self.assertTrue(
            any("Subscription required" in item for item in check["source_declarations"])
        )


# ── unita' attive e storico ───────────────────────────────────────────────────


class TestApprovedUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(APPROVAL / "approved_profile_units.jsonl")
        cls.by_unit = by_id(cls.units)
        cls.history = load_jsonl(APPROVAL / "parent_unit_history.jsonl")
        cls.by_history = by_id(cls.history)

    # 2. esattamente due unita' attive
    def test_exactly_two_active_units(self) -> None:
        active = [row for row in self.units if row["is_active"]]
        self.assertEqual(len(active), AUTHOR_APPROVED_ACTIVE_UNITS)
        self.assertEqual(sorted(by_id(active)), sorted(APPROVED_UNIT_IDS))

    # 4/5. una clinica, una preclinica unresolved
    def test_one_clinical_and_one_preclinical(self) -> None:
        self.assertEqual(sum(1 for row in self.units if row["is_clinical"]), 1)
        self.assertEqual(sum(1 for row in self.units if row["is_preclinical"]), 1)
        self.assertTrue(self.by_unit[CLINICAL_COHORT_ID]["is_clinical"])
        self.assertTrue(self.by_unit[PRECLINICAL_PANEL_ID]["is_preclinical"])

    def test_the_unit_types_come_from_the_existing_vocabulary(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertIn(row["unit_type"], UNIT_TYPES)
        # Il tipo generico e' deliberato: `engineered` o `patient_derived`
        # direbbero di che cosa e' fatto il pannello, che e' cio' che l'abstract
        # non dice.
        self.assertEqual(self.by_unit[PRECLINICAL_PANEL_ID]["unit_type"], "preclinical_in_vitro")

    # 1. parent unit conservata
    def test_the_parent_unit_is_preserved(self) -> None:
        parent = self.by_history[PARENT_UNIT_ID]
        self.assertEqual(parent["role"], "parent_unit")
        self.assertEqual(parent["cohort_state"], COHORT_SUPERSEDED_BY_RESTRUCTURE)
        self.assertFalse(parent["is_active"])
        self.assertFalse(parent["is_propagatable"])
        self.assertEqual(sorted(parent["superseded_by"]), sorted(APPROVED_UNIT_IDS))

    def test_the_parent_keeps_references_and_statement_candidates(self) -> None:
        parent = self.by_history[PARENT_UNIT_ID]
        self.assertEqual(
            sorted(parent["statement_candidates_preserved"]),
            sorted([STATEMENT_PARTIAL, STATEMENT_AMBIGUOUS]),
        )
        for reference in parent["historical_references_preserved"]:
            with self.subTest(reference=reference):
                self.assertTrue((REPO_ROOT / "benchmarks/mtb_evidence/v3" / reference).is_file())

    # 3. tre proposte conservate nello storico
    def test_all_three_proposals_are_retained(self) -> None:
        proposals = [row for row in self.history if row["role"] != "parent_unit"]
        self.assertEqual(len(proposals), SOURCE_REVIEW_PROPOSED_UNITS)
        source_ids = {
            str(row["proposed_profile_unit_id"])
            for row in load_jsonl(BATCH / "proposed_profile_units.jsonl")
            if row["canonical_source_id"] == "PMID:23344087"
        }
        self.assertEqual(source_ids, {row["profile_unit_id"] for row in proposals})

    # 6/7. engineered-clones e patient-derived non attive
    def test_neither_preclinical_proposal_is_active(self) -> None:
        for unit_id in (ENGINEERED_CLONES_PROPOSAL_ID, PATIENT_DERIVED_PROPOSAL_ID):
            with self.subTest(unit=unit_id):
                self.assertNotIn(unit_id, self.by_unit)
                row = self.by_history[unit_id]
                self.assertFalse(row["is_active"])
                self.assertFalse(row["is_propagatable"])
                self.assertEqual(row["review_status"], REJECTION_STATUS)
                self.assertEqual(row["replacement_unit"], PRECLINICAL_PANEL_ID)

    def test_the_rejected_proposals_are_not_declared_false(self) -> None:
        # Non sono sbagliate: sono non verificabili. Il full text potrebbe
        # riattivarle, e un record che le dicesse false lo impedirebbe.
        for unit_id in REJECTED_PROPOSALS:
            row = self.by_history[unit_id]
            with self.subTest(unit=unit_id):
                self.assertTrue(row["rejected_for_lack_of_source_resolution"])
                self.assertFalse(row["rejected_as_false"])
                self.assertEqual(row["role"], "unapproved_structural_hypothesis")

    def test_no_historical_row_is_active_or_propagatable(self) -> None:
        for row in self.history:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["is_active"])
                self.assertFalse(row["is_propagatable"])

    # 21/22. prototype_only, mai hard-filterable
    def test_every_unit_is_prototype_only(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["propagation_eligibility"], PROTOTYPE_ONLY)
                self.assertTrue(row["may_display_qualifiers"])

    def test_no_unit_is_propagatable_or_hard_filterable(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["is_propagatable"])
                self.assertFalse(row["is_hard_filterable"])
                self.assertFalse(row["used_as_hard_filter"])
        self.assertEqual(validate_units(self.units), [])

    def test_the_pending_state_is_what_blocks_propagation(self) -> None:
        for row in self.units:
            self.assertEqual(row["cohort_state"], COHORT_REVIEWED_PENDING_INDEPENDENT)

    # 25. prima revisione completa e non indipendente
    def test_the_review_is_first_complete_and_not_independent(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["review_status"], FIRST_REVIEW_COMPLETE)
                self.assertIn(row["review_status"], HUMAN_ONLY_STATUSES)
                self.assertTrue(row["human_reviewed"])
                self.assertFalse(row["independent_review"])
                self.assertFalse(row["clinical_reviewed"])
                self.assertFalse(row["clinical_reviewer"])
                self.assertFalse(row["second_review_complete"])
                self.assertTrue(row["requires_second_independent_review"])

    # 27. is_evaluable false
    def test_no_unit_is_evaluable(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["is_evaluable"])

    # 34. provenance completeness
    def test_every_known_dimension_carries_provenance(self) -> None:
        for row in self.units:
            fields = {item["field_name"] for item in row["provenance"]}
            for dimension in row["known_dimensions"]:
                with self.subTest(unit=row["profile_unit_id"], dimension=dimension):
                    self.assertIn(dimension, fields)

    def test_every_provenance_entry_names_the_basis_and_the_reviewer(self) -> None:
        for row in self.units:
            for item in row["provenance"]:
                with self.subTest(unit=row["profile_unit_id"], field=item["field_name"]):
                    self.assertEqual(item["document_hash"], DOCUMENT_HASH)
                    self.assertEqual(item["reviewer"], REVIEWER_ID)
                    self.assertEqual(item["reviewer_role"], REVIEWER_ROLE)
                    self.assertEqual(item["review_method"], REVIEW_METHOD)
                    # La base documentale viaggia con il campo, non solo con
                    # l'unita': un valore estratto da un abstract e uno estratto
                    # da un full text non sono la stessa asserzione.
                    self.assertEqual(item["source_basis"], ABSTRACT_ONLY)
                    self.assertTrue(item["source_locator"])

    def test_the_guards_pass_on_the_approved_units(self) -> None:
        self.assertEqual(run_guards(units=self.units), [])


# ── la coorte clinica ─────────────────────────────────────────────────────────


class TestClinicalCohort(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.unit = by_id(load_jsonl(APPROVAL / "approved_profile_units.jsonl"))[
            CLINICAL_COHORT_ID
        ]

    def test_the_cohort_is_the_seven_patients(self) -> None:
        self.assertEqual(self.unit["n_subjects"], "7")
        self.assertIn("resistenza acquisita", self.unit["population"])
        self.assertEqual(self.unit["disease"], "Lung Non-small Cell Carcinoma")

    def test_the_enrolment_biomarker_precedes_the_treatment(self) -> None:
        self.assertEqual(self.unit["biomarker_role"], "enrolment_criterion")
        self.assertEqual(self.unit["enrollment_biomarker"], ["ALK rearrangement"])
        self.assertTrue(self.unit["enrollment_biomarker_precedes_treatment"])

    def test_resistance_alterations_are_not_enrolment_requirements(self) -> None:
        self.assertEqual(self.unit["biomarker_requirements"], ["ALK gene rearrangement"])
        self.assertFalse(self.unit["acquired_findings_are_enrolment_criteria"])
        for finding in ("ALK L1196M", "ALK G1269A", "EGFR L858R"):
            with self.subTest(finding=finding):
                self.assertIn(finding, self.unit["acquired_findings"])
                self.assertNotIn(finding, self.unit["biomarker_requirements"])

    def test_crizotinib_carries_an_explicit_role(self) -> None:
        self.assertEqual(self.unit["intervention"], ["crizotinib"])
        self.assertEqual(
            self.unit["intervention_role"],
            "prior_or_reference_therapy_not_study_intervention",
        )

    def test_prior_therapies_are_not_inferred(self) -> None:
        self.assertEqual(self.unit["prior_therapies"], [])
        self.assertEqual(
            self.unit["prior_therapy_decision"], "not_recorded_without_further_inference"
        )

    def test_unsupported_dimensions_stay_unknown(self) -> None:
        for dimension in (
            "comparator",
            "exclusion_criteria",
            "inclusion_criteria",
            "regimen",
            "resection_status",
            "stage",
            "setting",
            "therapy_line",
        ):
            with self.subTest(dimension=dimension):
                self.assertEqual(self.unit[dimension], "unknown")


# ── il pannello preclinico non risolto ────────────────────────────────────────


class TestUnresolvedPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.unit = by_id(load_jsonl(APPROVAL / "approved_profile_units.jsonl"))[
            PRECLINICAL_PANEL_ID
        ]
        cls.records = load_jsonl(APPROVAL / "unresolved_structure_records.jsonl")
        cls.record = cls.records[0]

    def test_the_panel_is_an_active_unit(self) -> None:
        self.assertTrue(self.unit["is_active"])
        self.assertEqual(self.unit["experiment_role"], "unresolved_in_vitro_resistance_panel")

    # 8. composizione not_separable
    def test_the_composition_is_not_separable_not_unknown(self) -> None:
        # La differenza porta informazione: `unknown` direbbe che il valore va
        # cercato meglio, `not_separable` che il documento non lo contiene.
        self.assertEqual(self.unit["preclinical_model_composition"], NOT_SEPARABLE)
        self.assertNotEqual(self.unit["preclinical_model_composition"], "unknown")
        self.assertEqual(self.unit["component_to_statement_mapping"], NOT_SEPARABLE)
        self.assertEqual(self.record["resolution_state"], NOT_SEPARABLE)

    # 9. background dei cloni unknown
    def test_the_clone_background_is_unknown(self) -> None:
        # Qui `unknown` e' corretto: l'abstract non nomina affatto il fondo
        # cellulare, quindi non c'e' una relazione confermata da non separare.
        self.assertEqual(self.unit["cellular_background_of_mutant_clones"], "unknown")
        self.assertEqual(self.record["cellular_background_of_mutant_clones"], "unknown")

    def test_the_components_are_the_three_named_by_the_abstract(self) -> None:
        self.assertEqual(
            self.unit["model_components"], ["SNU-2535", "H3122 CR1", "mutant clones"]
        )
        self.assertFalse(self.unit["model_component_count_known"])
        self.assertEqual(self.unit["distinct_preclinical_system_count"], "unknown")

    # 10. nessuna relazione inventata
    def test_no_relation_between_clones_and_lines_is_asserted(self) -> None:
        self.assertEqual(self.unit["clones_derived_from_snu2535"], "not_asserted_by_source")
        self.assertEqual(self.unit["clones_derived_from_h3122_cr1"], "not_asserted_by_source")
        self.assertEqual(
            self.unit["snu2535_and_clones_same_experimental_unit"], "not_asserted_by_source"
        )
        self.assertEqual(len(self.unit["not_asserted"]), 4)

    def test_the_two_intensities_stay_apart(self) -> None:
        # SNU-2535 «resistant», i cloni «less sensitive»: l'abstract li distingue
        # nella stessa frase, e il pannello non li fonde.
        by_component = {
            item["component"]: item for item in self.unit["component_observations"]
        }
        self.assertEqual(by_component["SNU-2535"]["intensity"], "resistant")
        self.assertEqual(
            by_component["L1196M and G1269A mutant clones"]["intensity"],
            "relative_reduced_sensitivity",
        )

    def test_the_panel_does_not_inherit_the_patients(self) -> None:
        self.assertFalse(self.unit["clinical_population_inherited"])
        self.assertFalse(self.unit["clinical_response_observed"])
        for dimension in (
            "population",
            "stage",
            "setting",
            "therapy_line",
            "resection_status",
            "inclusion_criteria",
            "exclusion_criteria",
            "disease",
        ):
            with self.subTest(dimension=dimension):
                self.assertEqual(self.unit[dimension], "not_applicable")
        self.assertEqual(self.unit["prior_therapies"], [])

    def test_the_panel_stays_blocked_past_a_second_review(self) -> None:
        self.assertTrue(self.unit["propagation_blocked_beyond_second_review"])
        self.assertTrue(self.record["propagation_blocked_beyond_second_review"])
        self.assertFalse(self.record["is_propagatable"])
        self.assertEqual(self.record["blocked_by"], "source_basis=abstract_only")
        self.assertEqual(len(self.record["unblock_conditions"]), 2)

    def test_the_unresolved_record_names_the_rejected_hypotheses(self) -> None:
        self.assertEqual(sorted(self.record["rejected_hypotheses"]), sorted(REJECTED_PROPOSALS))
        self.assertEqual(self.record["unresolved_dimension"], "preclinical_model_composition")


# ── decisioni sugli statement ─────────────────────────────────────────────────


class TestStatementDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(APPROVAL / "statement_first_review_decisions.jsonl")
        cls.by_statement = by_id(cls.rows, "statement_id")

    def test_two_statements_are_reviewed(self) -> None:
        self.assertEqual(len(self.rows), 2)
        self.assertEqual(
            sorted(self.by_statement), sorted([STATEMENT_PARTIAL, STATEMENT_AMBIGUOUS])
        )

    # 11. ES-V2-evidence-765 candidate_partial
    def test_765_is_candidate_partial(self) -> None:
        row = self.by_statement[STATEMENT_PARTIAL]
        self.assertEqual(row["first_review_candidate_status"], "candidate_partial")
        self.assertEqual(row["first_review_link_status"], "partial_link")
        self.assertEqual(
            row["support_type"], "clinical_observation_with_preclinical_validation"
        )

    # 12. supporto clinico e preclinico distinti
    def test_765_keeps_the_two_supports_apart(self) -> None:
        row = self.by_statement[STATEMENT_PARTIAL]
        self.assertNotEqual(row["clinical_support"], row["preclinical_support"])
        self.assertEqual(row["clinical_support"]["profile_unit_id"], CLINICAL_COHORT_ID)
        self.assertEqual(row["preclinical_support"]["profile_unit_id"], PRECLINICAL_PANEL_ID)
        self.assertFalse(row["preclinical_validation_is_clinical_response"])

    def test_765_points_at_the_two_active_units(self) -> None:
        row = self.by_statement[STATEMENT_PARTIAL]
        self.assertEqual(sorted(row["profile_unit_ids"]), sorted(APPROVED_UNIT_IDS))
        for unit_id in REJECTED_PROPOSALS:
            self.assertIn(unit_id, row["previous_profile_unit_ids"])

    # 13/14. relative reduced sensitivity, non resistenza completa
    def test_765_records_the_relative_qualifier(self) -> None:
        row = self.by_statement[STATEMENT_PARTIAL]
        self.assertEqual(row["resistance_qualifier"], "relative_reduced_sensitivity")
        self.assertFalse(row["complete_resistance"])
        self.assertEqual(row["claim_strength_alignment"], "partial")

    # 15. non un sinonimo esatto, e non un conflitto
    def test_765_is_a_strength_difference_not_a_conflict(self) -> None:
        row = self.by_statement[STATEMENT_PARTIAL]
        self.assertEqual(row["source_term"], "less sensitive to crizotinib")
        self.assertEqual(row["statement_term"], "resistance")
        self.assertEqual(row["mapping_status"], "requires_terminology_verification")
        self.assertFalse(row["assertion_conflict"])
        self.assertEqual(row["conflict_dimensions"], [])

    def test_765_keeps_the_panel_composition_unresolved(self) -> None:
        row = self.by_statement[STATEMENT_PARTIAL]
        self.assertEqual(row["preclinical_model_composition"], NOT_SEPARABLE)
        self.assertEqual(row["component_to_statement_mapping"], NOT_SEPARABLE)

    # 16. ES-V2-evidence-767 candidate_ambiguous
    def test_767_is_candidate_ambiguous(self) -> None:
        row = self.by_statement[STATEMENT_AMBIGUOUS]
        self.assertEqual(row["first_review_candidate_status"], "candidate_ambiguous")
        self.assertEqual(row["first_review_link_status"], "ambiguous_link")
        self.assertEqual(
            row["support_type"],
            "direct_clinical_support_with_confounded_causal_attribution",
        )

    def test_767_is_not_conflicting(self) -> None:
        # `conflicting` direbbe che la fonte nega lo statement. La fonte dice meno,
        # non il contrario.
        row = self.by_statement[STATEMENT_AMBIGUOUS]
        self.assertNotEqual(row["first_review_candidate_status"], "candidate_conflicting")
        self.assertFalse(row["assertion_conflict"])
        self.assertFalse(row["source_contradicts_statement"])
        self.assertTrue(row["why_not_conflicting"])

    # 17. case-level
    def test_767_is_case_level_on_a_single_patient(self) -> None:
        row = self.by_statement[STATEMENT_AMBIGUOUS]
        self.assertEqual(row["evidence_granularity"], GRANULARITY_CASE)
        self.assertEqual(row["population_scope"], "single_patient")
        self.assertEqual(row["subset_size"], 1)
        self.assertEqual(row["cohort_size"], 7)
        self.assertFalse(row["cohort_generalizable"])
        self.assertEqual(row["frequency_inference"], "forbidden")

    def test_767_does_not_invent_a_patient_number(self) -> None:
        row = self.by_statement[STATEMENT_AMBIGUOUS]
        self.assertEqual(row["case_identifier"], "unknown")
        self.assertFalse(row["case_identifier_verified"])
        self.assertIn("one patient", row["case_identifier_reason"])

    def test_the_abstract_really_does_not_number_the_patient(self) -> None:
        access = next(
            row
            for row in load_jsonl(BATCH / "source_access_verification.jsonl")
            if row["profile_unit_id"] == PARENT_UNIT_ID
        )
        locator = next(
            item for item in access["locators"] if item["locator_id"] == "B-clin-cng"
        )
        self.assertEqual(locator["match_type"], "exact")
        self.assertIn("one patient displayed ALK gene copy number gain", locator["excerpt"])
        self.assertNotIn("#", locator["excerpt"])

    # 18/19. co-occorrenza e attribuzione causale
    def test_767_records_the_cooccurring_alteration(self) -> None:
        row = self.by_statement[STATEMENT_AMBIGUOUS]
        self.assertEqual(row["cooccurring_alterations"], ["EGFR L858R"])
        self.assertIn("high polysomy", row["cooccurrence_detail"])
        self.assertEqual(row["confounding_status"], "molecular_cooccurrence")

    def test_767_does_not_isolate_the_mechanism(self) -> None:
        row = self.by_statement[STATEMENT_AMBIGUOUS]
        self.assertEqual(row["causal_attribution"], NOT_SEPARABLE)
        self.assertFalse(row["isolated_mechanism_support"])

    def test_the_guards_pass_on_the_decisions(self) -> None:
        self.assertEqual(run_guards(decisions=self.rows), [])

    def test_no_decision_is_evaluable(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_evaluable_for_final_metrics"])
                self.assertFalse(row["independent_review"])
                self.assertFalse(row["clinical_reviewer"])
                self.assertEqual(row["source_basis"], ABSTRACT_ONLY)


class TestReusedCaseLevelPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(APPROVAL / "case_level_annotations.jsonl")
        cls.confounding = load_jsonl(APPROVAL / "confounding_annotations.jsonl")

    def test_the_case_level_statement_is_protected(self) -> None:
        self.assertEqual(len(self.rows), 1)
        row = self.rows[0]
        self.assertEqual(row["statement_id"], STATEMENT_AMBIGUOUS)
        self.assertTrue(is_non_generalizable(row["evidence_granularity"]))
        self.assertFalse(row["cohort_generalizable"])
        self.assertEqual(row["population_level_propagation"], "forbidden")
        self.assertEqual(row["frequency_inference"], "forbidden")
        self.assertEqual(row["enrolment_requirement_promotion"], "forbidden")

    def test_the_policy_is_reused_and_not_rewritten(self) -> None:
        # Nessuna regola nuova: gli id sono quelli introdotti dalla fase
        # precedente, e il record dice da dove vengono.
        row = self.rows[0]
        self.assertEqual(row["guard_rule_ids"], list(GUARD_V12_RULE_IDS))
        self.assertIn("22235099", row["policy_reused_from"])

    def test_confounding_is_recorded_separately_from_granularity(self) -> None:
        # Un caso singolo ha un denominatore troppo piccolo; un caso confuso ha
        # due spiegazioni. Sommarli perderebbe il motivo del limite.
        self.assertEqual(len(self.confounding), 1)
        row = self.confounding[0]
        self.assertEqual(row["statement_id"], STATEMENT_AMBIGUOUS)
        self.assertEqual(row["causal_attribution"], NOT_SEPARABLE)
        self.assertEqual(row["cooccurring_alterations"], ["EGFR L858R"])
        self.assertFalse(row["assertion_conflict"])


# ── terminologia ──────────────────────────────────────────────────────────────


class TestTerminologyMappings(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(APPROVAL / "terminology_mappings.jsonl")
        cls.by_mapping = by_id(cls.rows, "mapping_id")

    def test_both_mappings_are_recorded(self) -> None:
        self.assertEqual(len(self.rows), 2)
        self.assertEqual(
            sorted(self.by_mapping),
            sorted(["TM-PMID-23344087-cng", "TM-PMID-23344087-sensitivity"]),
        )

    # 20. copy-number gain non e' amplification esatta
    def test_the_copy_number_mapping_stays_unverified(self) -> None:
        row = self.by_mapping["TM-PMID-23344087-cng"]
        self.assertEqual(row["source_term"], "ALK gene copy number gain")
        self.assertEqual(row["statement_term"], "ALK Amplification")
        self.assertEqual(row["mapping_type"], "biomarker_strength_normalization")
        self.assertEqual(row["mapping_status"], "requires_terminology_verification")
        self.assertFalse(row["literal_equivalence"])
        self.assertTrue(row["source_supports_broader_concept"])
        self.assertEqual(row["source_supports_exact_normalized_term"], "not_verified")
        self.assertFalse(row["kg_used_as_sole_authority"])
        self.assertFalse(row["promoted_to_verified_synonym"])

    def test_amplification_is_not_used_as_a_source_native_value(self) -> None:
        row = self.by_mapping["TM-PMID-23344087-cng"]
        self.assertEqual(row["source_native_term"], "ALK gene copy number gain")
        self.assertFalse(row["amplification_used_as_source_native"])

    # 15. less sensitive non e' resistance
    def test_the_sensitivity_mapping_is_a_strength_difference(self) -> None:
        row = self.by_mapping["TM-PMID-23344087-sensitivity"]
        self.assertEqual(row["source_term"], "less sensitive to crizotinib")
        self.assertEqual(row["statement_term"], "resistance")
        self.assertEqual(row["mapping_type"], "evidence_strength_normalization")
        self.assertEqual(row["mapping_status"], "requires_terminology_verification")
        self.assertEqual(row["resistance_qualifier"], "relative_reduced_sensitivity")
        self.assertFalse(row["complete_resistance"])
        self.assertFalse(row["assertion_conflict"])
        self.assertEqual(row["uncertain_dimension"], "claim_strength")

    def test_the_batch_mappings_are_unchanged(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "terminology_mappings.jsonl")
            if row["canonical_source_id"] == "PMID:23344087"
        ]
        self.assertEqual(len(rows), 2)
        for row in rows:
            with self.subTest(term=row["source_term"]):
                self.assertEqual(row["mapping_status"], "requires_terminology_verification")


# ── gold provvisorio ──────────────────────────────────────────────────────────


class TestProvisionalGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gold = load_jsonl(APPROVAL / "provisional_gold.jsonl")
        cls.previous = load_jsonl(PREVIOUS / "provisional_gold.jsonl")
        cls.annotated = [
            row
            for row in cls.gold
            if row["profile_unit_id"] == PARENT_UNIT_ID
            and row.get("first_annotator") == REVIEWER_ID
        ]

    def test_two_links_are_annotated(self) -> None:
        self.assertEqual(len(self.annotated), 2)
        self.assertEqual(
            sorted(row["statement_id"] for row in self.annotated),
            sorted([STATEMENT_PARTIAL, STATEMENT_AMBIGUOUS]),
        )

    # 26. gold provisional
    def test_the_gold_is_still_provisional(self) -> None:
        for row in self.annotated:
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_first_review")
                self.assertEqual(row["review_stage"], "first_review_complete")
                self.assertTrue(row["requires_second_review"])

    # 27. is_evaluable false
    def test_no_gold_row_is_evaluable(self) -> None:
        for row in self.gold:
            with self.subTest(link=row.get("gold_link_id")):
                self.assertFalse(row.get("is_evaluable"))

    # 28/29. second reviewer e agreement null
    def test_the_second_annotator_and_agreement_are_null(self) -> None:
        for row in self.annotated:
            with self.subTest(link=row["gold_link_id"]):
                self.assertIsNone(row["second_annotator"])
                self.assertIsNone(row["second_annotation"])
                self.assertIsNone(row["agreement"])
                self.assertIsNone(row["adjudication"])
                self.assertIsNone(row["adjudicator"])

    def test_the_decision_lives_in_the_annotation_not_in_final_status(self) -> None:
        for row in self.annotated:
            annotation = row["first_review_annotation"]
            with self.subTest(link=row["gold_link_id"]):
                self.assertIn(
                    annotation["candidate_status"],
                    ("candidate_partial", "candidate_ambiguous"),
                )
                self.assertNotEqual(row["final_status"], annotation["candidate_status"])
                self.assertNotIn(row["final_status"], ("final", "frozen", "adjudicated"))

    def test_the_annotation_carries_the_basis_and_the_confidence(self) -> None:
        for row in self.annotated:
            annotation = row["first_review_annotation"]
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(annotation["source_basis"], ABSTRACT_ONLY)
                self.assertEqual(annotation["structural_confidence"], CONFIDENCE_PARTIAL)
                self.assertFalse(annotation["independent_review"])
                self.assertFalse(annotation["clinical_reviewer"])

    def test_no_previous_gold_row_is_lost(self) -> None:
        self.assertEqual(len(self.gold), len(self.previous))
        self.assertEqual(
            {row["gold_link_id"] for row in self.gold},
            {row["gold_link_id"] for row in self.previous},
        )

    def test_the_untouched_rows_are_identical(self) -> None:
        previous = {row["gold_link_id"]: row for row in self.previous}
        annotated_ids = {row["gold_link_id"] for row in self.annotated}
        for row in self.gold:
            if row["gold_link_id"] in annotated_ids:
                continue
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row, previous[row["gold_link_id"]])

    def test_the_previous_annotations_survive(self) -> None:
        # Le tre annotazioni della fase precedente su PMID 22235099 restano nel
        # gold: una fase nuova aggiunge, non riscrive.
        earlier = [
            row
            for row in self.gold
            if row["profile_unit_id"] == "PU-PMID-22235099-cohort-1"
            and row.get("first_annotator") == REVIEWER_ID
        ]
        self.assertEqual(len(earlier), 3)


# ── identita' del revisore ────────────────────────────────────────────────────


class TestReviewerIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = load_jsonl(APPROVAL / "author_approval_records.jsonl")[0]
        cls.trail = load_jsonl(APPROVAL / "audit_trail.jsonl")

    def test_the_approval_is_with_corrections(self) -> None:
        self.assertEqual(self.record["author_decision"], APPROVE_WITH_CORRECTIONS)

    def test_the_reviewer_is_recorded_as_non_clinical(self) -> None:
        self.assertEqual(self.record["reviewer_id"], REVIEWER_ID)
        self.assertEqual(self.record["reviewer_role"], REVIEWER_ROLE)
        self.assertFalse(self.record["clinical_reviewer"])
        self.assertFalse(self.record["clinical_reviewed"])

    def test_the_llm_assisted_method_is_declared(self) -> None:
        self.assertEqual(self.record["review_method"], REVIEW_METHOD)
        self.assertIn("llm_assisted", REVIEW_METHOD)

    def test_the_review_is_not_independent(self) -> None:
        self.assertFalse(self.record["independent_review"])
        self.assertTrue(self.record["requires_second_independent_review"])
        self.assertFalse(self.record["is_evaluable_for_final_metrics"])

    def test_the_split_is_confirmed_and_the_count_corrected(self) -> None:
        self.assertEqual(self.record["clinical_preclinical_split"], "confirmed")
        self.assertEqual(
            self.record["structural_decision"], "audit_split_partially_supported"
        )
        self.assertEqual(self.record["audit_proposed_units"], AUDIT_PROPOSED_UNITS)
        self.assertEqual(
            self.record["source_review_proposed_units"], SOURCE_REVIEW_PROPOSED_UNITS
        )
        self.assertEqual(
            self.record["author_approved_active_units"], AUTHOR_APPROVED_ACTIVE_UNITS
        )

    def test_no_forbidden_status_is_declared(self) -> None:
        text = json.dumps(self.record, ensure_ascii=False)
        for status in FORBIDDEN_STATUSES:
            with self.subTest(status=status):
                self.assertNotIn(f'"{status}": true', text)
                self.assertNotIn(f'"review_status": "{status}"', text)

    def test_the_audit_trail_names_who_decided(self) -> None:
        self.assertEqual(len(self.trail), 4)
        human = [row for row in self.trail if row["is_human_decision"]]
        self.assertEqual(len(human), 1)
        self.assertEqual(human[0]["decided_by"], REVIEWER_ID)
        self.assertEqual(human[0]["phase"], "author_approval")
        self.assertEqual([row["sequence"] for row in self.trail], [1, 2, 3, 4])
        for row in self.trail:
            self.assertEqual(row["source_basis"], ABSTRACT_ONLY)


# ── rilevatore ────────────────────────────────────────────────────────────────


class TestDetectorReferenceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_jsonl(APPROVAL / "detector_reference_cases.jsonl")[0]

    # 30. positivo parziale
    def test_it_is_a_partially_confirmed_positive(self) -> None:
        self.assertTrue(self.case["detector_reference_case"])
        self.assertEqual(
            self.case["reference_case_type"],
            "partially_confirmed_clinical_preclinical_mixture",
        )
        self.assertEqual(self.case["detector_original_verdict"], "split_required")
        self.assertEqual(self.case["reviewed_verdict"], "split_partially_supported")
        self.assertTrue(self.case["detector_presence_signal_correct"])
        self.assertFalse(self.case["detector_granularity_prediction_correct"])

    # 31. detector non promosso
    def test_the_detector_is_not_promoted(self) -> None:
        self.assertFalse(self.case["detector_promoted"])
        self.assertFalse(self.case["use_for_detector_performance_estimation"])
        self.assertTrue(self.case["use_as_regression_case"])

    def test_there_is_no_ground_truth_to_measure_against(self) -> None:
        # Il punto che distingue questo caso dai due precedenti: non e' il
        # rilevatore ad avere torto, e' il documento a non bastare.
        self.assertFalse(self.case["ground_truth_available"])
        self.assertIn("full text", self.case["ground_truth_unavailable_reason"])
        self.assertEqual(self.case["source_basis"], ABSTRACT_ONLY)

    def test_the_principle_is_stated(self) -> None:
        self.assertEqual(self.case["principle"], DETECTOR_PRINCIPLE)

    def test_the_batch_verdict_is_unchanged(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "detector_case_review.jsonl")
            if row["canonical_source_id"] == "PMID:23344087"
        ]
        self.assertEqual(rows[0]["concordance"], "partially_confirmed")
        self.assertFalse(rows[0]["unit_count_correct"])


# ── metriche e readiness ──────────────────────────────────────────────────────


class TestMetricsAndReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = load_json(APPROVAL / "review_metrics.json")
        cls.readiness = load_json(APPROVAL / "readiness.json")
        cls.previous_metrics = load_json(PREVIOUS / "review_metrics.json")
        cls.previous_readiness = load_json(PREVIOUS / "readiness.json")

    def test_descriptive_counters_are_updated(self) -> None:
        self.assertEqual(self.metrics["author_approval_packets_completed"], 1)
        self.assertEqual(self.metrics["first_review_sources_completed"], 1)
        self.assertEqual(self.metrics["first_review_statements_reviewed"], 2)
        self.assertEqual(self.metrics["first_review_profile_units_approved"], 2)
        self.assertEqual(self.metrics["first_review_clinical_units"], 1)
        self.assertEqual(self.metrics["first_review_preclinical_units"], 1)
        self.assertEqual(self.metrics["first_review_candidate_partial"], 1)
        self.assertEqual(self.metrics["first_review_candidate_ambiguous"], 1)
        self.assertEqual(self.metrics["first_review_case_level_statements"], 1)
        self.assertEqual(self.metrics["first_review_abstract_only_sources"], 1)
        self.assertEqual(self.metrics["detector_reference_partial_positives"], 1)
        self.assertEqual(self.metrics["unresolved_preclinical_panels"], 1)

    def test_the_cumulative_counters_advance(self) -> None:
        cumulative = self.metrics["cumulative"]
        previous = self.previous_metrics["cumulative"]
        self.assertEqual(
            cumulative["first_review_statements_reviewed"],
            previous["first_review_statements_reviewed"] + 2,
        )
        self.assertEqual(
            cumulative["first_review_profile_units_created"],
            previous["first_review_profile_units_created"] + 2,
        )
        self.assertEqual(
            cumulative["author_approval_packets_completed"],
            previous["author_approval_packets_completed"] + 1,
        )

    def test_coverage_separates_the_review_stages(self) -> None:
        coverage = self.metrics["coverage_by_review_stage"]
        self.assertEqual(coverage["source_checked_proposal"], SOURCE_REVIEW_PROPOSED_UNITS)
        self.assertEqual(
            coverage["first_review_confirmed"],
            self.previous_metrics["coverage_by_review_stage"]["first_review_confirmed"] + 2,
        )
        self.assertEqual(coverage["second_review_confirmed"], 0)
        self.assertEqual(coverage["final_adjudicated"], 0)

    # 34. provenance completeness
    def test_provenance_completeness_is_one(self) -> None:
        self.assertEqual(self.metrics["qualifier_provenance_completeness"], 1.0)

    # 35. nessuna metrica finale
    def test_no_final_metric_is_calculated(self) -> None:
        for key, value in self.metrics["not_calculated"].items():
            with self.subTest(metric=key):
                self.assertEqual(value, "not_calculated")
        for forbidden in ("precision", "recall", "f1", "accuracy", "agreement"):
            with self.subTest(metric=forbidden):
                self.assertNotIn(forbidden, self.metrics)

    def test_hashes_match_the_artifacts(self) -> None:
        pairs = {
            "statement_decisions": "statement_first_review_decisions.jsonl",
            "case_level_annotations": "case_level_annotations.jsonl",
            "confounding_annotations": "confounding_annotations.jsonl",
            "terminology_mappings": "terminology_mappings.jsonl",
            "provisional_gold": "provisional_gold.jsonl",
            "detector_reference_cases": "detector_reference_cases.jsonl",
        }
        for key, name in pairs.items():
            with self.subTest(artifact=name):
                self.assertEqual(
                    self.metrics["hashes"][key], content_hash(load_jsonl(APPROVAL / name))
                )

    def test_the_batch_is_complete(self) -> None:
        self.assertTrue(self.readiness["clinical_preclinical_author_approval_batch_complete"])
        self.assertEqual(
            self.readiness["author_approvals_completed"],
            self.previous_readiness["author_approvals_completed"] + 1,
        )
        self.assertEqual(self.readiness["author_approvals_pending"], 0)
        self.assertEqual(self.readiness["clinical_preclinical_partial_positives_confirmed"], 1)
        self.assertEqual(self.readiness["abstract_only_first_reviews"], 1)
        self.assertEqual(self.readiness["unresolved_preclinical_composition_count"], 1)

    # 36. readiness per corpus regeneration
    def test_the_corpus_regeneration_is_the_next_step(self) -> None:
        self.assertTrue(self.readiness["ready_for_versioned_corpus_regeneration"])
        self.assertEqual(
            self.readiness["next_step"], "versioned_qualification_corpus_regeneration"
        )
        self.assertIsNone(self.readiness["next_report_to_approve"])
        self.assertFalse(self.readiness["standard_queue_resumed"])

    def test_readiness_keeps_every_other_gate_closed(self) -> None:
        for key in (
            "detector_promotion_ready",
            "hard_filtering_available",
            "ready_for_final_evaluation",
            "gold_evaluable",
        ):
            with self.subTest(gate=key):
                self.assertFalse(self.readiness[key])
        self.assertTrue(self.readiness["second_review_required"])

    def test_no_forbidden_status_is_declared(self) -> None:
        self.assertEqual(self.readiness["forbidden_statuses_declared"], [])
        self.assertEqual(
            sorted(self.readiness["forbidden_statuses_checked"]), sorted(FORBIDDEN_STATUSES)
        )


# ── blinding, fasi protette, determinismo ─────────────────────────────────────


class TestBlinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = load_json(APPROVAL / "second_review_blinding_check.json")
        cls.directory = CURATION / "annotation_packets/second_review"

    # 32. packet byte-identical
    def test_the_seventy_packets_are_byte_identical(self) -> None:
        self.assertTrue(self.check["byte_identical"])
        self.assertEqual(self.check["changed_files"], [])
        self.assertEqual(self.check["file_count_after"], 70)
        self.assertEqual(self.check["expected_file_count"], 70)

    def test_the_recorded_hashes_still_match_the_files(self) -> None:
        recomputed = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.directory.iterdir())
            if path.is_file()
        }
        self.assertEqual(recomputed, self.check["hashes_after"])

    # 33. precedenti author approval invariati
    def test_the_previous_phases_are_untouched(self) -> None:
        self.assertTrue(self.check["protected_phases_byte_identical"])
        self.assertEqual(self.check["protected_phases_changed_files"], {})
        for phase, hashes in self.check["protected_phase_hashes"].items():
            directory = REPO_ROOT / phase
            present = {
                path.name for path in sorted(directory.iterdir()) if path.is_file()
            }
            with self.subTest(phase=phase):
                # Prima il perimetro: nessun file aggiunto, nessuno sparito.
                # Confrontare solo le impronte lascerebbe passare un file nuovo.
                self.assertEqual(present, set(hashes))
            for name, declared in sorted(hashes.items()):
                with self.subTest(phase=phase, artifact=name):
                    # Due file di `v3/first_review/` portano un'impronta presa
                    # nella forma CRLF di allora. La divergenza e' registrata in
                    # `artifact_hash_erratum`, e l'helper la accetta solo se il
                    # file ha ancora la forma canonica che l'erratum gli
                    # attribuisce: se cambiasse davvero, qui fallirebbe.
                    ERRATUM_SUPPORT.assert_frozen_digest(
                        self, directory / name, declared, context=phase
                    )

    def test_all_three_earlier_phases_are_protected(self) -> None:
        protected = set(self.check["protected_phases"])
        for phase in (FIRST_APPROVAL, PREVIOUS, FIRST_REVIEW):
            with self.subTest(phase=phase.name):
                self.assertIn(
                    str(phase.relative_to(REPO_ROOT)).replace("\\", "/"), protected
                )

    def test_nothing_from_this_review_leaks_into_the_blind_packets(self) -> None:
        # I termini che compaiono nei packet come vocabolario ammesso non sono
        # decisioni: il test cerca cio' che questa fase ha deciso.
        leaks = (
            REVIEWER_ID,
            "approve_with_corrections",
            "audit_split_partially_supported",
            PRECLINICAL_PANEL_ID,
            "preclinical-unresolved-panel",
            "unresolved_in_vitro_resistance_panel",
            "relative_reduced_sensitivity",
            "molecular_cooccurrence",
            "EGFR L858R",
            "biomarker_strength_normalization",
            "evidence_strength_normalization",
            "first_review_complete",
            "human_approved_llm_assisted_source_review",
            "abstract_only",
        )
        for path in sorted(self.directory.iterdir()):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for token in leaks:
                with self.subTest(packet=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_no_blind_packet_carries_a_first_review_decision(self) -> None:
        for path in sorted(self.directory.iterdir()):
            if path.suffix != ".json":
                continue
            text = path.read_text(encoding="utf-8")
            with self.subTest(packet=path.name):
                self.assertNotIn('"candidate_status"', text)
                self.assertNotIn('"first_review_annotation"', text)


class TestDeterminism(unittest.TestCase):
    """Due esecuzioni con lo stesso timestamp producono gli stessi byte."""

    @staticmethod
    def _run_phase(output: Path) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts import (
            build_approved_units_23344087,
            record_author_approval_23344087,
            revise_statement_decisions_23344087,
        )

        arguments = ["--output", str(output), "--timestamp", FIXED_TIMESTAMP]
        with contextlib.redirect_stdout(io.StringIO()):
            for module in (
                record_author_approval_23344087,
                build_approved_units_23344087,
                revise_statement_decisions_23344087,
            ):
                if module.main(arguments) != 0:
                    raise AssertionError(f"{module.__name__} non e' uscito con 0")

    # 39. artefatti deterministici su due esecuzioni
    def test_two_runs_produce_identical_artifacts(self) -> None:
        digests: list[dict[str, str]] = []
        for _ in range(2):
            with TemporaryDirectory() as temporary:
                output = Path(temporary) / "phase"
                self._run_phase(output)
                digests.append(
                    {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in sorted(output.iterdir())
                        if path.is_file()
                    }
                )
        self.assertEqual(digests[0], digests[1])
        self.assertTrue(digests[0])

    def test_the_committed_artifacts_match_a_fresh_run(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "phase"
            self._run_phase(output)
            for path in sorted(output.iterdir()):
                with self.subTest(artifact=path.name):
                    self.assertEqual(path.read_bytes(), (APPROVAL / path.name).read_bytes())


# ── regressione ───────────────────────────────────────────────────────────────


class TestRegression(unittest.TestCase):
    def test_the_source_review_report_is_untouched(self) -> None:
        text = (BATCH / "SOURCE_REVIEW_PMID-23344087.md").read_text(encoding="utf-8")
        self.assertIn("audit_split_partially_supported", text)
        self.assertIn("source_checked_review_proposal", text)
        self.assertIn("first_review_complete              = false", text)

    def test_the_original_approval_packet_is_untouched(self) -> None:
        packet = load_json(BATCH / "annotation_packets/author_approval/AA-PMID-23344087.json")
        self.assertIsNone(packet["decision"])
        self.assertIsNone(packet["decided_by"])
        self.assertIsNone(packet["decided_at"])
        self.assertEqual(packet["reviewed_unit_count"], SOURCE_REVIEW_PROPOSED_UNITS)

    def test_the_source_checked_proposals_are_untouched(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "proposed_profile_units.jsonl")
            if row["canonical_source_id"] == "PMID:23344087"
        ]
        self.assertEqual(len(rows), SOURCE_REVIEW_PROPOSED_UNITS)
        for row in rows:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertEqual(row["review_status"], "source_checked_review_proposal")
                self.assertFalse(row["human_reviewed"])
                self.assertFalse(row["is_propagatable"])

    def test_the_statement_repository_still_has_147_statements(self) -> None:
        rows = load_jsonl(
            REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl"
        )
        self.assertEqual(len(rows), 147)

    # 38. nessuna rete
    def test_no_network_is_needed(self) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts.build_approved_units_23344087 import (
            parse_args,
        )

        args = parse_args([])
        self.assertFalse(hasattr(args, "allow_network"))
        for name in ("requests", "urllib.request", "httpx"):
            with self.subTest(module=name):
                for path in sorted(APPROVAL.glob("*")):
                    self.assertNotIn(name, path.read_text(encoding="utf-8"))

    def test_the_retriever_is_not_implemented(self) -> None:
        self.assertEqual(list(REPO_ROOT.rglob("*QualifiedEvidenceRetriever*")), [])


if __name__ == "__main__":
    unittest.main()
