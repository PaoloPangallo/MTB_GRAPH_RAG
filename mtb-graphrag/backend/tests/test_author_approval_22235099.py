"""Approvazione dell'autore su PMID 22235099: unita', granularita', gold, blinding.

Tutti offline. Il file protegge i modi in cui questa fase potrebbe sbagliare, e
la maggior parte di essi non produce un errore: produce un record valido che dice
una cosa falsa.

- quattro unita' attive, e cinque proposte che restano leggibili. Se le due
  proposte consolidate sparissero, la decisione — passare da cinque a quattro —
  diventerebbe invisibile;
- un esperimento negativo che resta negativo. `assertion_polarity` e' l'unico
  campo che lo impedisce a chi non legge la nota;
- un modello derivato da paziente che non eredita il paziente;
- due statement senza denominatore, che non lo acquistano;
- una normalizzazione terminologica che non diventa un sinonimo;
- un gold che resta provvisorio e packet ciechi che restano ciechi.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.pipeline.evidence.corpus_manifest import content_hash
from backend.pipeline.evidence.evidence_granularity import (
    GRANULARITY_CASE,
    GRANULARITY_NAMED_PATIENT_SUBSET,
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
from benchmarks.mtb_evidence.evaluation.author_approval_22235099 import (
    APPROVE_WITH_CORRECTIONS,
    APPROVED_UNIT_IDS,
    AUDIT_PROPOSED_UNITS,
    AUTHOR_APPROVED_UNITS,
    CLINICAL_COHORT_ID,
    CUTO1_ID,
    DETECTOR_PRINCIPLE,
    DOCUMENT_HASH,
    ENGINEERED_MODELS_ID,
    FORBIDDEN_STATUSES,
    H3122_KRAS_ID,
    LOCATOR_COUNT,
    PARENT_UNIT_ID,
    REPLACED_PROPOSALS,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
    SOURCE_REVIEW_PROPOSED_UNITS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVAL = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval_22235099"
PREVIOUS = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval"
BATCH = REPO_ROOT / "benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"
AUDIT = REPO_ROOT / "benchmarks/mtb_evidence/v3/cohort_split_audit"

STATEMENT_VALID = "ES-V2-evidence-764"
STATEMENT_CASE = "ES-V2-evidence-4288"
STATEMENT_SUBSET = "ES-V2-evidence-766"

FIXED_TIMESTAMP = "2026-07-24T00:00:00+00:00"


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


# ── unita' attive e storico ───────────────────────────────────────────────────


class TestApprovedUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(APPROVAL / "approved_profile_units.jsonl")
        cls.by_unit = by_id(cls.units)
        cls.history = load_jsonl(APPROVAL / "parent_unit_history.jsonl")
        cls.by_history = by_id(cls.history)

    # 2. quattro unita' attive
    def test_exactly_four_active_units(self) -> None:
        active = [row for row in self.units if row["is_active"]]
        self.assertEqual(len(active), AUTHOR_APPROVED_UNITS)
        self.assertEqual(sorted(by_id(active)), sorted(APPROVED_UNIT_IDS))

    def test_one_clinical_and_three_preclinical(self) -> None:
        self.assertEqual(sum(1 for row in self.units if row["is_clinical"]), 1)
        self.assertEqual(sum(1 for row in self.units if row["is_preclinical"]), 3)

    def test_five_units_are_not_kept_active(self) -> None:
        self.assertLess(len(self.units), SOURCE_REVIEW_PROPOSED_UNITS)

    def test_every_unit_type_is_in_the_schema_vocabulary(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertIn(row["unit_type"], UNIT_TYPES)

    # 1. parent unit conservata
    def test_the_parent_unit_is_preserved(self) -> None:
        parent = self.by_history[PARENT_UNIT_ID]
        self.assertEqual(parent["role"], "parent_unit")
        self.assertEqual(parent["cohort_state"], COHORT_SUPERSEDED_BY_RESTRUCTURE)
        self.assertFalse(parent["is_active"])
        self.assertFalse(parent["is_propagatable"])
        self.assertEqual(sorted(parent["superseded_by"]), sorted(APPROVED_UNIT_IDS))

    def test_the_parent_keeps_its_historical_references(self) -> None:
        parent = self.by_history[PARENT_UNIT_ID]
        self.assertTrue(parent["historical_references_preserved"])
        for reference in parent["historical_references_preserved"]:
            with self.subTest(reference=reference):
                self.assertTrue((REPO_ROOT / "benchmarks/mtb_evidence/v3" / reference).is_file())

    def test_every_active_unit_supersedes_the_parent(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["supersedes"], PARENT_UNIT_ID)
                self.assertEqual(row["parent_profile_unit_id"], PARENT_UNIT_ID)

    # 3. cinque proposte originarie conservate nello storico
    def test_all_five_source_checked_proposals_are_retained(self) -> None:
        proposals = [row for row in self.history if row["role"] != "parent_unit"]
        self.assertEqual(len(proposals), SOURCE_REVIEW_PROPOSED_UNITS)
        source_ids = {
            str(row["proposed_profile_unit_id"])
            for row in load_jsonl(BATCH / "proposed_profile_units.jsonl")
            if row["canonical_source_id"] == "PMID:22235099"
        }
        self.assertEqual(source_ids, {row["profile_unit_id"] for row in proposals})

    def test_no_historical_row_is_active_or_propagatable(self) -> None:
        for row in self.history:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["is_active"])
                self.assertFalse(row["is_propagatable"])

    # 20/21. prototype_only, mai hard-filterable
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

    def test_the_pending_state_can_never_propagate(self) -> None:
        # Il blocco viene dalla politica, non da una riga che qualcuno potrebbe
        # dimenticare: lo stato semplicemente non compare fra quelli propagabili.
        for row in self.units:
            self.assertEqual(row["cohort_state"], COHORT_REVIEWED_PENDING_INDEPENDENT)
        self.assertEqual(validate_units(self.units), [])

    # 22. prima revisione completa e non indipendente
    def test_the_review_is_first_complete_and_not_independent(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["review_status"], FIRST_REVIEW_COMPLETE)
                self.assertTrue(row["human_reviewed"])
                self.assertTrue(row["first_review_complete"])
                self.assertFalse(row["independent_review"])
                self.assertFalse(row["clinical_reviewed"])
                self.assertFalse(row["clinical_reviewer"])
                self.assertFalse(row["second_review_complete"])
                self.assertTrue(row["requires_second_independent_review"])

    def test_the_human_state_sits_on_source_checked_extraction(self) -> None:
        for row in self.units:
            self.assertIn(row["review_status"], HUMAN_ONLY_STATUSES)
            self.assertEqual(row["extraction_status"], "source_checked")

    # 24. is_evaluable false
    def test_no_unit_is_evaluable(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["is_evaluable"])

    # 31. provenance completeness
    def test_every_known_dimension_carries_provenance(self) -> None:
        for row in self.units:
            fields = {item["field_name"] for item in row["provenance"]}
            for dimension in row["known_dimensions"]:
                with self.subTest(unit=row["profile_unit_id"], dimension=dimension):
                    self.assertIn(dimension, fields)

    def test_every_provenance_entry_names_the_document_and_the_reviewer(self) -> None:
        for row in self.units:
            for item in row["provenance"]:
                with self.subTest(unit=row["profile_unit_id"], field=item["field_name"]):
                    self.assertEqual(item["document_hash"], DOCUMENT_HASH)
                    self.assertEqual(item["reviewer"], REVIEWER_ID)
                    self.assertEqual(item["reviewer_role"], REVIEWER_ROLE)
                    self.assertEqual(item["review_method"], REVIEW_METHOD)
                    self.assertTrue(item["source_locator"])

    def test_the_guards_pass_on_the_approved_units(self) -> None:
        self.assertEqual(run_guards(units=self.units), [])


# ── consolidazione Ba/F3 + NIH3T3 ─────────────────────────────────────────────


class TestConsolidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = by_id(load_jsonl(APPROVAL / "approved_profile_units.jsonl"))
        cls.history = by_id(load_jsonl(APPROVAL / "parent_unit_history.jsonl"))
        cls.records = load_jsonl(APPROVAL / "consolidation_records.jsonl")
        cls.unit = cls.units[ENGINEERED_MODELS_ID]

    # 4. Ba/F3 e NIH3T3 consolidate
    def test_neither_engineered_proposal_is_still_a_unit(self) -> None:
        for unit_id in REPLACED_PROPOSALS:
            with self.subTest(unit=unit_id):
                self.assertNotIn(unit_id, self.units)

    def test_both_proposals_point_at_the_replacement(self) -> None:
        for unit_id in REPLACED_PROPOSALS:
            row = self.history[unit_id]
            with self.subTest(unit=unit_id):
                self.assertEqual(
                    row["review_status"], "replaced_by_author_approved_consolidation"
                )
                self.assertEqual(row["replacement_unit"], ENGINEERED_MODELS_ID)
                self.assertEqual(row["superseded_by"], [ENGINEERED_MODELS_ID])

    # 5. due model instances
    def test_the_consolidated_unit_holds_two_model_instances(self) -> None:
        self.assertEqual(self.unit["model_instance_count"], 2)
        self.assertEqual(len(self.unit["model_instances"]), 2)
        names = {item["model_name"] for item in self.unit["model_instances"]}
        self.assertEqual(names, {"Ba/F3", "NIH3T3"})

    def test_each_instance_keeps_its_own_assay_and_locators(self) -> None:
        assays = {item["model_name"]: item["assay"] for item in self.unit["model_instances"]}
        self.assertNotEqual(assays["Ba/F3"], assays["NIH3T3"])
        for item in self.unit["model_instances"]:
            with self.subTest(model=item["model_name"]):
                self.assertTrue(item["source_locators"])
                self.assertIn(item["source_proposal_id"], REPLACED_PROPOSALS)

    def test_the_consolidated_value_declares_that_it_is_consolidated(self) -> None:
        # Il design fonde due saggi: la provenienza non puo' far sembrare che una
        # frase della fonte lo contenga gia'.
        entry = next(
            item for item in self.unit["provenance"] if item["field_name"] == "evidence_design"
        )
        self.assertEqual(entry["value_origin"], "author_approved_consolidation")
        self.assertIn(REVIEWER_ID, entry["asserted_by"])

    def test_the_consolidation_record_states_why(self) -> None:
        record = self.records[0]
        self.assertEqual(record["replaced_count"], 2)
        self.assertEqual(record["resulting_count"], 1)
        self.assertEqual(record["source_review_proposed_units"], SOURCE_REVIEW_PROPOSED_UNITS)
        self.assertEqual(record["author_approved_units"], AUTHOR_APPROVED_UNITS)
        self.assertTrue(record["history_preserved"])
        self.assertIn("stessa proposizione", record["rationale"])

    # 13. supporto clinico e preclinico distinti sulla unita'
    def test_the_model_does_not_inherit_the_patients(self) -> None:
        self.assertEqual(self.unit["population"], "not_applicable")
        self.assertFalse(self.unit["clinical_population_inherited"])
        self.assertFalse(self.unit["clinical_response_observed"])
        for dimension in ("stage", "setting", "therapy_line", "resection_status"):
            with self.subTest(dimension=dimension):
                self.assertEqual(self.unit[dimension], "not_applicable")

    def test_the_construct_is_not_an_enrolment_requirement(self) -> None:
        self.assertEqual(self.unit["biomarker_requirements"], [])
        self.assertEqual(self.unit["model_biomarker_role"], "engineered_construct")


# ── CUTO-1 ────────────────────────────────────────────────────────────────────


class TestPatientDerivedModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = by_id(load_jsonl(APPROVAL / "approved_profile_units.jsonl"))
        cls.unit = cls.units[CUTO1_ID]

    # 6. unita' autonoma
    def test_cuto1_is_its_own_unit(self) -> None:
        self.assertTrue(self.unit["is_active"])
        self.assertTrue(self.unit["is_preclinical"])
        self.assertFalse(self.unit["is_clinical"])
        self.assertEqual(self.unit["unit_type"], "preclinical_patient_derived_model")

    # 7. relazione con il paziente 10 conservata
    def test_the_link_to_patient_ten_is_kept(self) -> None:
        self.assertEqual(self.unit["derived_from_clinical_case"], "patient_10")
        self.assertEqual(self.unit["derivation_relation"], "clinical_case -> derived_model")
        self.assertFalse(self.unit["derivation_is_identity"])

    # 8. biomarcatore clinico non propagato
    def test_the_clinical_biomarker_does_not_cross_the_boundary(self) -> None:
        self.assertEqual(self.unit["biomarker_requirements"], [])
        self.assertEqual(self.unit["cross_context_biomarker_propagation"], "forbidden")
        self.assertEqual(self.unit["inherited_from_clinical_case"], [])
        self.assertIn("biomarker", self.unit["not_inherited_from_clinical_case"])

    def test_the_model_lost_what_the_patient_had(self) -> None:
        self.assertEqual(self.unit["ALK_rearrangement_in_clinical_sample"], "present")
        self.assertEqual(
            self.unit["ALK_rearrangement_in_CUTO1_model"], "lost_or_not_detected"
        )

    def test_the_unanchored_assertion_says_that_it_is_unanchored(self) -> None:
        # La perdita del riarrangiamento non ha un locator proprio. Registrarla
        # senza dirlo la farebbe sembrare verificata quanto il resto.
        self.assertTrue(self.unit["ALK_loss_requires_locator_verification"])
        self.assertIn("without_dedicated_locator", self.unit["ALK_loss_locator_status"])

    def test_the_comparators_are_the_verified_ones(self) -> None:
        self.assertEqual(self.unit["comparator_models"], ["H3122", "H2228"])
        self.assertIn("A-pre-cuto1", self.unit["source_locators"])

    def test_clinical_dimensions_are_not_applicable(self) -> None:
        for dimension in ("population", "stage", "setting", "therapy_line", "disease"):
            with self.subTest(dimension=dimension):
                self.assertEqual(self.unit[dimension], "not_applicable")


# ── esperimento negativo ──────────────────────────────────────────────────────


class TestNegativeExperiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = by_id(load_jsonl(APPROVAL / "approved_profile_units.jsonl"))
        cls.unit = cls.units[H3122_KRAS_ID]
        cls.records = load_jsonl(APPROVAL / "negative_experiment_records.jsonl")
        cls.record = cls.records[0]

    # 9. unita' autonoma
    def test_the_negative_experiment_is_its_own_unit(self) -> None:
        self.assertTrue(self.unit["is_active"])
        self.assertEqual(self.unit["experiment_role"], "negative_experiment")

    # 10. assertion polarity
    def test_the_polarity_is_does_not_support(self) -> None:
        self.assertEqual(self.unit["assertion_polarity"], "does_not_support")
        self.assertEqual(self.record["assertion_polarity"], "does_not_support")

    def test_no_other_unit_shares_that_polarity(self) -> None:
        others = [
            row
            for row in self.units.values()
            if row["profile_unit_id"] != H3122_KRAS_ID
        ]
        for row in others:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["assertion_polarity"], "supports")

    # 11. il risultato negativo non diventa resistenza
    def test_the_result_is_not_turned_into_resistance(self) -> None:
        self.assertEqual(self.record["result_direction"], "no_significant_difference")
        self.assertIn("does not support", self.record["result_interpretation"])
        self.assertEqual(
            self.record["must_not_be_read_as"], "KRAS G12V -> resistance to crizotinib"
        )

    def test_the_negative_result_is_kept_and_visible(self) -> None:
        self.assertFalse(self.record["removed_from_corpus"])
        self.assertTrue(self.record["visible_in_prototype"])
        self.assertEqual(self.record["propagation_eligibility"], PROTOTYPE_ONLY)
        self.assertFalse(self.record["is_propagatable"])

    def test_the_quote_is_the_verified_one(self) -> None:
        self.assertIn("not significantly different", self.record["quote"])
        self.assertIn("A-pre-kras-negative", self.record["source_locators"])

    def test_it_does_not_generalize_to_the_cohort(self) -> None:
        self.assertFalse(self.record["cohort_generalizable"])
        self.assertFalse(self.record["clinical_response_observed"])
        self.assertEqual(self.record["statement_ids"], [])


# ── decisioni sugli statement ─────────────────────────────────────────────────


class TestStatementDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(APPROVAL / "statement_first_review_decisions.jsonl")
        cls.by_statement = by_id(cls.rows, "statement_id")

    def test_three_statements_are_reviewed(self) -> None:
        self.assertEqual(len(self.rows), 3)
        self.assertEqual(
            sorted(self.by_statement),
            sorted([STATEMENT_CASE, STATEMENT_VALID, STATEMENT_SUBSET]),
        )

    # 12. ES-V2-evidence-764 candidate_valid
    def test_764_is_candidate_valid(self) -> None:
        row = self.by_statement[STATEMENT_VALID]
        self.assertEqual(row["first_review_candidate_status"], "candidate_valid")
        self.assertEqual(row["first_review_link_status"], "valid_link")
        self.assertEqual(
            row["support_type"], "clinical_observation_with_preclinical_validation"
        )

    # 13. supporto clinico e preclinico distinti
    def test_764_keeps_the_two_supports_apart(self) -> None:
        row = self.by_statement[STATEMENT_VALID]
        self.assertIn("clinical_support", row)
        self.assertIn("preclinical_support", row)
        self.assertNotEqual(row["clinical_support"], row["preclinical_support"])
        self.assertEqual(
            row["clinical_support"]["profile_unit_id"], CLINICAL_COHORT_ID
        )
        self.assertEqual(
            row["preclinical_support"]["profile_unit_id"], ENGINEERED_MODELS_ID
        )

    def test_764_does_not_turn_validation_into_clinical_response(self) -> None:
        row = self.by_statement[STATEMENT_VALID]
        self.assertFalse(row["preclinical_validation_is_clinical_response"])
        self.assertEqual(row["resistance_qualifier"], "relative_resistance")

    def test_764_points_at_the_consolidated_unit(self) -> None:
        row = self.by_statement[STATEMENT_VALID]
        self.assertEqual(
            sorted(row["profile_unit_ids"]),
            sorted([CLINICAL_COHORT_ID, ENGINEERED_MODELS_ID]),
        )
        # Lo storico conserva a quali proposte puntava prima: senza, la
        # consolidazione sembrerebbe non avere toccato nulla.
        for unit_id in REPLACED_PROPOSALS:
            self.assertIn(unit_id, row["previous_profile_unit_ids"])

    # 14/15. ES-V2-evidence-4288 candidate_partial e case-level
    def test_4288_is_candidate_partial(self) -> None:
        row = self.by_statement[STATEMENT_CASE]
        self.assertEqual(row["first_review_candidate_status"], "candidate_partial")
        self.assertEqual(row["first_review_link_status"], "partial_link")

    def test_4288_is_case_level_on_a_verified_patient(self) -> None:
        row = self.by_statement[STATEMENT_CASE]
        self.assertEqual(row["evidence_granularity"], GRANULARITY_CASE)
        self.assertEqual(row["population_scope"], "single_patient")
        self.assertEqual(row["case_identifier"], "patient_9")
        self.assertTrue(row["case_identifier_verified"])
        self.assertEqual(row["case_identifier_locators"], ["A-clin-egfr"])

    # 17. ES-V2-evidence-766 verificato prima dell'attribuzione
    def test_766_is_not_attributed_to_patient_8_alone(self) -> None:
        row = self.by_statement[STATEMENT_SUBSET]
        self.assertEqual(row["evidence_granularity"], GRANULARITY_NAMED_PATIENT_SUBSET)
        self.assertEqual(row["population_scope"], "named_patients_subset")
        self.assertEqual(row["case_identifiers"], ["patient_7", "patient_8"])
        self.assertEqual(row["subset_size"], 2)
        self.assertEqual(row["cohort_size"], 14)
        self.assertNotIn("case_identifier", row)

    def test_766_records_the_narrowest_case_separately(self) -> None:
        row = self.by_statement[STATEMENT_SUBSET]
        self.assertEqual(row["isolated_cng_case_identifier"], "patient_8")
        self.assertEqual(row["narrowest_case_identifier"], "patient_8")

    def test_766_records_the_discrepancy_with_the_brief(self) -> None:
        row = self.by_statement[STATEMENT_SUBSET]
        discrepancy = row["brief_discrepancy"]
        self.assertEqual(discrepancy["expected_by_brief"]["case_identifier"], "patient_8")
        self.assertEqual(
            discrepancy["found_in_source"]["patients_named"], ["patient_7", "patient_8"]
        )
        self.assertFalse(discrepancy["case_identifier_invented"])
        self.assertTrue(discrepancy["author_approved"])

    def test_the_case_identifiers_appear_in_the_verified_locator(self) -> None:
        # L'identificatore non e' inventato: viene da una frase che il batch
        # source-checked ha verificato come `exact`.
        access = next(
            row
            for row in load_jsonl(BATCH / "source_access_verification.jsonl")
            if row["profile_unit_id"] == PARENT_UNIT_ID
        )
        locator = next(
            item for item in access["locators"] if item["locator_id"] == "A-clin-cng"
        )
        self.assertEqual(locator["match_type"], "exact")
        self.assertIn("#7", locator["excerpt"])
        self.assertIn("#8", locator["excerpt"])

    # 16. case-level non propagabile alla coorte
    def test_no_non_generalizable_statement_reaches_the_cohort(self) -> None:
        for row in self.rows:
            if not is_non_generalizable(row.get("evidence_granularity")):
                continue
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["cohort_generalizable"])
                self.assertEqual(row["population_level_propagation"], "forbidden")
                self.assertEqual(row["frequency_inference"], "forbidden")
                self.assertEqual(row["enrolment_requirement_promotion"], "forbidden")

    def test_the_guards_pass_on_the_decisions(self) -> None:
        self.assertEqual(run_guards(decisions=self.rows), [])

    def test_no_decision_is_evaluable(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_evaluable_for_final_metrics"])
                self.assertFalse(row["independent_review"])
                self.assertFalse(row["clinical_reviewer"])


class TestCaseLevelAnnotations(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(APPROVAL / "case_level_annotations.jsonl")
        cls.by_statement = by_id(cls.rows, "statement_id")

    def test_only_the_two_non_generalizable_statements_are_annotated(self) -> None:
        self.assertEqual(len(self.rows), 2)
        self.assertNotIn(STATEMENT_VALID, self.by_statement)

    def test_the_two_levels_are_not_collapsed(self) -> None:
        levels = {row["statement_id"]: row["evidence_granularity"] for row in self.rows}
        self.assertEqual(levels[STATEMENT_CASE], GRANULARITY_CASE)
        self.assertEqual(levels[STATEMENT_SUBSET], GRANULARITY_NAMED_PATIENT_SUBSET)

    def test_each_annotation_names_the_rules_that_protect_it(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertEqual(row["guard_rule_ids"], list(GUARD_V12_RULE_IDS))


# ── terminologia ──────────────────────────────────────────────────────────────


class TestTerminologyMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mapping = load_jsonl(APPROVAL / "terminology_mappings.jsonl")[0]

    # 18/19. non un sinonimo esatto, e resta da verificare
    def test_the_mapping_is_not_a_verified_synonym(self) -> None:
        self.assertFalse(self.mapping["literal_equivalence"])
        self.assertFalse(self.mapping["promoted_to_verified_synonym"])
        self.assertFalse(self.mapping["literal_string_present_for_exact_statement_term"])

    def test_the_mapping_stays_unverified(self) -> None:
        self.assertEqual(self.mapping["mapping_status"], "requires_terminology_verification")
        self.assertEqual(self.mapping["source_supports_exact_normalized_term"], "not_verified")
        self.assertTrue(self.mapping["source_supports_broader_concept"])
        self.assertTrue(self.mapping["review_required"])

    def test_the_uncertainty_is_named(self) -> None:
        self.assertEqual(self.mapping["uncertain_dimension"], "biomarker_specificity")
        self.assertEqual(self.mapping["mapping_type"], "biomarker_strength_normalization")

    def test_the_graph_is_not_its_own_authority(self) -> None:
        self.assertFalse(self.mapping["kg_used_as_sole_authority"])

    def test_the_batch_mapping_is_unchanged(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "terminology_mappings.jsonl")
            if row["canonical_source_id"] == "PMID:22235099"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mapping_status"], "requires_terminology_verification")


# ── gold provvisorio ──────────────────────────────────────────────────────────


class TestProvisionalGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gold = load_jsonl(APPROVAL / "provisional_gold.jsonl")
        cls.previous = load_jsonl(PREVIOUS / "provisional_gold.jsonl")
        cls.annotated = [
            row
            for row in cls.gold
            if row.get("first_annotator") == REVIEWER_ID
            and row["profile_unit_id"] == PARENT_UNIT_ID
        ]

    def test_three_links_are_annotated(self) -> None:
        self.assertEqual(len(self.annotated), 3)
        self.assertEqual(
            sorted(row["statement_id"] for row in self.annotated),
            sorted([STATEMENT_CASE, STATEMENT_VALID, STATEMENT_SUBSET]),
        )

    # 23. gold ancora provisional
    def test_the_gold_is_still_provisional(self) -> None:
        for row in self.annotated:
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_first_review")
                self.assertEqual(row["review_stage"], "first_review_complete")
                self.assertTrue(row["requires_second_review"])

    # 24. is_evaluable false
    def test_no_gold_row_is_evaluable(self) -> None:
        for row in self.gold:
            with self.subTest(link=row.get("gold_link_id")):
                self.assertFalse(row.get("is_evaluable"))

    # 25/26. secondo annotatore e agreement nulli
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
                    annotation["candidate_status"], ("candidate_valid", "candidate_partial")
                )
                self.assertNotEqual(row["final_status"], annotation["candidate_status"])
                self.assertNotIn(row["final_status"], ("final", "frozen", "adjudicated"))

    def test_the_annotation_carries_the_granularity(self) -> None:
        by_statement = {row["statement_id"]: row for row in self.annotated}
        self.assertEqual(
            by_statement[STATEMENT_SUBSET]["first_review_annotation"]["evidence_granularity"],
            GRANULARITY_NAMED_PATIENT_SUBSET,
        )
        self.assertFalse(
            by_statement[STATEMENT_CASE]["first_review_annotation"]["cohort_generalizable"]
        )

    def test_the_annotation_records_method_and_role(self) -> None:
        for row in self.annotated:
            annotation = row["first_review_annotation"]
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(annotation["reviewer_role"], REVIEWER_ROLE)
                self.assertEqual(annotation["review_method"], REVIEW_METHOD)
                self.assertFalse(annotation["independent_review"])
                self.assertFalse(annotation["clinical_reviewer"])

    def test_no_previous_gold_row_is_lost(self) -> None:
        self.assertEqual(len(self.gold), len(self.previous))
        self.assertEqual(
            {row["gold_link_id"] for row in self.gold},
            {row["gold_link_id"] for row in self.previous},
        )

    def test_the_previous_gold_file_is_unchanged(self) -> None:
        annotated_ids = {row["gold_link_id"] for row in self.annotated}
        for row in self.previous:
            if row["gold_link_id"] not in annotated_ids:
                continue
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_unreviewed")
                self.assertIsNone(row["first_annotator"])

    def test_the_untouched_rows_are_identical(self) -> None:
        previous = {row["gold_link_id"]: row for row in self.previous}
        annotated_ids = {row["gold_link_id"] for row in self.annotated}
        for row in self.gold:
            if row["gold_link_id"] in annotated_ids:
                continue
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row, previous[row["gold_link_id"]])


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

    def test_human_reviewed_does_not_imply_clinical_review(self) -> None:
        self.assertTrue(self.record["human_reviewed"])
        self.assertFalse(self.record["clinical_reviewed"])

    # 4 (criteri). lo split e' confermato
    def test_the_split_is_confirmed_and_the_count_corrected(self) -> None:
        self.assertEqual(self.record["clinical_preclinical_split"], "confirmed")
        self.assertEqual(
            self.record["structural_decision"], "audit_split_confirmed_with_more_units"
        )
        self.assertEqual(self.record["audit_proposed_units"], AUDIT_PROPOSED_UNITS)
        self.assertEqual(
            self.record["source_review_proposed_units"], SOURCE_REVIEW_PROPOSED_UNITS
        )
        self.assertEqual(self.record["author_approved_units"], AUTHOR_APPROVED_UNITS)

    def test_no_forbidden_status_is_declared(self) -> None:
        text = json.dumps(self.record, ensure_ascii=False)
        for status in FORBIDDEN_STATUSES:
            with self.subTest(status=status):
                self.assertNotIn(f'"{status}": true', text)
                self.assertNotIn(f'"review_status": "{status}"', text)

    def test_the_source_check_is_recorded(self) -> None:
        check = self.record["source_check"]
        self.assertEqual(check["document_hash"], DOCUMENT_HASH)
        self.assertEqual(check["locators_verified"], LOCATOR_COUNT)
        self.assertEqual(check["locators_not_verified"], 0)
        self.assertEqual(check["locator_match_type_counts"], {"exact": 12})

    def test_the_audit_trail_names_who_decided(self) -> None:
        self.assertEqual(len(self.trail), 4)
        human = [row for row in self.trail if row["is_human_decision"]]
        self.assertEqual(len(human), 1)
        self.assertEqual(human[0]["decided_by"], REVIEWER_ID)
        self.assertEqual(human[0]["phase"], "author_approval")
        self.assertEqual([row["sequence"] for row in self.trail], [1, 2, 3, 4])


# ── rilevatore ────────────────────────────────────────────────────────────────


class TestDetectorReferenceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_jsonl(APPROVAL / "detector_reference_cases.jsonl")[0]

    # 27. vero positivo strutturale
    def test_it_is_a_confirmed_structural_positive(self) -> None:
        self.assertTrue(self.case["detector_reference_case"])
        self.assertEqual(
            self.case["reference_case_type"], "confirmed_clinical_preclinical_mixture"
        )
        self.assertEqual(self.case["detector_original_verdict"], "split_required")
        self.assertEqual(self.case["reviewed_verdict"], "split_required_with_more_units")
        self.assertTrue(self.case["detector_presence_signal_correct"])

    # 28. granularita' sbagliata
    def test_the_granularity_prediction_is_marked_wrong(self) -> None:
        self.assertFalse(self.case["detector_granularity_prediction_correct"])
        self.assertEqual(self.case["detector_predicted_unit_count"], AUDIT_PROPOSED_UNITS)
        self.assertEqual(self.case["author_approved_unit_count"], AUTHOR_APPROVED_UNITS)
        self.assertNotEqual(
            self.case["detector_predicted_unit_count"], self.case["author_approved_unit_count"]
        )

    # 29. detector non promosso
    def test_the_detector_is_not_promoted(self) -> None:
        self.assertFalse(self.case["detector_promoted"])
        self.assertFalse(self.case["use_for_detector_performance_estimation"])
        self.assertTrue(self.case["use_as_regression_case"])

    def test_the_principle_is_stated(self) -> None:
        self.assertEqual(self.case["principle"], DETECTOR_PRINCIPLE)
        self.assertIn("!=", DETECTOR_PRINCIPLE)

    def test_the_batch_verdict_is_unchanged(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "detector_case_review.jsonl")
            if row["canonical_source_id"] == "PMID:22235099"
        ]
        self.assertEqual(rows[0]["concordance"], "confirmed_positive")
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
        self.assertEqual(self.metrics["first_review_statements_reviewed"], 3)
        self.assertEqual(self.metrics["first_review_profile_units_approved"], 4)
        self.assertEqual(self.metrics["first_review_clinical_units"], 1)
        self.assertEqual(self.metrics["first_review_preclinical_units"], 3)
        self.assertEqual(self.metrics["first_review_candidate_valid"], 1)
        self.assertEqual(self.metrics["first_review_candidate_partial"], 2)
        self.assertEqual(self.metrics["first_review_negative_experiments"], 1)
        self.assertEqual(self.metrics["detector_reference_confirmed_positives"], 1)

    def test_the_two_granularity_counters_stay_separate(self) -> None:
        # Sommarli direbbe «tre statement su un paziente», che e' falso per due
        # di essi in modo diverso.
        self.assertEqual(self.metrics["first_review_case_level_statements"], 1)
        self.assertEqual(self.metrics["first_review_named_patient_subset_statements"], 1)
        self.assertEqual(self.metrics["first_review_non_generalizable_statements"], 2)

    def test_the_consolidation_is_counted(self) -> None:
        self.assertEqual(self.metrics["first_review_units_consolidated_from"], 2)
        self.assertEqual(self.metrics["first_review_units_consolidated_to"], 1)

    def test_coverage_separates_the_review_stages(self) -> None:
        coverage = self.metrics["coverage_by_review_stage"]
        self.assertEqual(coverage["source_checked_proposal"], SOURCE_REVIEW_PROPOSED_UNITS)
        self.assertEqual(
            coverage["first_review_confirmed"],
            self.previous_metrics["coverage_by_review_stage"]["first_review_confirmed"] + 3,
        )
        self.assertEqual(coverage["second_review_confirmed"], 0)
        self.assertEqual(coverage["final_adjudicated"], 0)

    # 31. provenance completeness
    def test_provenance_completeness_is_one(self) -> None:
        self.assertEqual(self.metrics["qualifier_provenance_completeness"], 1.0)

    # 32. nessuna metrica finale
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
            "negative_experiment_records": "negative_experiment_records.jsonl",
            "terminology_mappings": "terminology_mappings.jsonl",
            "provisional_gold": "provisional_gold.jsonl",
            "detector_reference_cases": "detector_reference_cases.jsonl",
        }
        for key, name in pairs.items():
            with self.subTest(artifact=name):
                self.assertEqual(
                    self.metrics["hashes"][key], content_hash(load_jsonl(APPROVAL / name))
                )

    def test_readiness_advances_only_the_descriptive_counters(self) -> None:
        self.assertEqual(
            self.readiness["author_approvals_completed"],
            self.previous_readiness["author_approvals_completed"] + 1,
        )
        self.assertEqual(
            self.readiness["author_approvals_pending"],
            self.previous_readiness["author_approvals_pending"] - 1,
        )
        self.assertEqual(self.readiness["clinical_preclinical_true_positives_confirmed"], 1)
        self.assertEqual(self.readiness["negative_experiments_preserved"], 1)
        self.assertTrue(self.readiness["case_level_evidence_guard_ready"])

    def test_readiness_keeps_every_gate_closed(self) -> None:
        for key in (
            "detector_promotion_ready",
            "hard_filtering_available",
            "ready_for_final_evaluation",
            "gold_evaluable",
            "standard_queue_resumed",
        ):
            with self.subTest(gate=key):
                self.assertFalse(self.readiness[key])
        self.assertTrue(self.readiness["second_review_required"])

    def test_no_forbidden_status_is_declared(self) -> None:
        self.assertEqual(self.readiness["forbidden_statuses_declared"], [])
        self.assertEqual(
            sorted(self.readiness["forbidden_statuses_checked"]), sorted(FORBIDDEN_STATUSES)
        )

    def test_the_next_report_is_the_third_source(self) -> None:
        self.assertEqual(
            self.readiness["next_report_to_approve"], "SOURCE_REVIEW_PMID-23344087.md"
        )
        self.assertTrue((BATCH / "SOURCE_REVIEW_PMID-23344087.md").is_file())


# ── blinding e determinismo ───────────────────────────────────────────────────


class TestBlinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = load_json(APPROVAL / "second_review_blinding_check.json")
        cls.directory = CURATION / "annotation_packets/second_review"

    # 30. packet byte-identical
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

    def test_the_previous_phase_is_untouched(self) -> None:
        self.assertTrue(self.check["previous_phase_byte_identical"])
        recomputed = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(PREVIOUS.iterdir())
            if path.is_file()
        }
        self.assertEqual(recomputed, self.check["previous_phase_hashes"])

    def test_nothing_from_this_review_leaks_into_the_blind_packets(self) -> None:
        # I valori che appaiono solo come vocabolario ammesso non sono decisioni:
        # il test cerca cio' che questa fase ha deciso, non le parole che usa.
        leaks = (
            REVIEWER_ID,
            "approve_with_corrections",
            "audit_split_confirmed_with_more_units",
            ENGINEERED_MODELS_ID,
            H3122_KRAS_ID,
            CUTO1_ID,
            "engineered-isogenic-models",
            "does_not_support",
            "named_patient_subset",
            "isolated_cng_case_identifier",
            "narrowest_case_identifier",
            "first_review_complete",
            "human_approved_llm_assisted_source_review",
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
            payload = json.loads(path.read_text(encoding="utf-8"))
            text = json.dumps(payload, ensure_ascii=False)
            with self.subTest(packet=path.name):
                self.assertNotIn('"candidate_status"', text)
                self.assertNotIn('"first_review_annotation"', text)


class TestDeterminism(unittest.TestCase):
    """Due esecuzioni con lo stesso timestamp producono gli stessi byte.

    Se non lo facessero, l'unico modo di sapere che cosa e' cambiato fra due
    versioni di un artefatto sarebbe leggerlo per intero: il diff mostrerebbe
    rumore a ogni riga.
    """

    @staticmethod
    def _run_phase(output: Path) -> None:
        """Le tre fasi in ordine, senza far parlare gli script nel report dei test."""
        from benchmarks.mtb_evidence.evaluation.scripts import (
            build_approved_units_22235099,
            record_author_approval_22235099,
            revise_statement_decisions_22235099,
        )

        arguments = ["--output", str(output), "--timestamp", FIXED_TIMESTAMP]
        with contextlib.redirect_stdout(io.StringIO()):
            for module in (
                record_author_approval_22235099,
                build_approved_units_22235099,
                revise_statement_decisions_22235099,
            ):
                if module.main(arguments) != 0:
                    raise AssertionError(f"{module.__name__} non e' uscito con 0")

    # 35. artefatti deterministici su due esecuzioni
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
                    self.assertEqual(
                        path.read_bytes(), (APPROVAL / path.name).read_bytes()
                    )


# ── regressione ───────────────────────────────────────────────────────────────


class TestRegression(unittest.TestCase):
    def test_the_source_review_report_is_untouched(self) -> None:
        report = BATCH / "SOURCE_REVIEW_PMID-22235099.md"
        text = report.read_text(encoding="utf-8")
        self.assertIn("audit_split_confirmed_with_more_units", text)
        self.assertIn("source_checked_review_proposal", text)
        self.assertIn("first_review_complete              = false", text)

    def test_the_original_approval_packet_is_untouched(self) -> None:
        packet = load_json(BATCH / "annotation_packets/author_approval/AA-PMID-22235099.json")
        self.assertIsNone(packet["decision"])
        self.assertIsNone(packet["decided_by"])
        self.assertIsNone(packet["decided_at"])
        self.assertEqual(packet["reviewed_unit_count"], SOURCE_REVIEW_PROPOSED_UNITS)

    def test_the_source_checked_proposals_are_untouched(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "proposed_profile_units.jsonl")
            if row["canonical_source_id"] == "PMID:22235099"
        ]
        self.assertEqual(len(rows), SOURCE_REVIEW_PROPOSED_UNITS)
        for row in rows:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertEqual(row["review_status"], "source_checked_review_proposal")
                self.assertFalse(row["human_reviewed"])
                self.assertFalse(row["is_propagatable"])

    def test_the_structural_audit_is_unchanged(self) -> None:
        rows = [
            row
            for row in load_jsonl(BATCH / "structural_review_decisions.jsonl")
            if row["canonical_source_id"] == "PMID:22235099"
        ]
        self.assertEqual(rows[0]["audit_unit_count"], AUDIT_PROPOSED_UNITS)
        self.assertEqual(rows[0]["reviewed_unit_count"], SOURCE_REVIEW_PROPOSED_UNITS)
        self.assertFalse(rows[0]["human_reviewed"])

    def test_the_audit_scope_is_unchanged(self) -> None:
        rows = load_jsonl(AUDIT / "audit_scope.jsonl")
        self.assertEqual(len(rows), 9)

    def test_the_statement_repository_still_has_147_statements(self) -> None:
        rows = load_jsonl(
            REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl"
        )
        self.assertEqual(len(rows), 147)

    # 34. nessuna rete
    def test_no_network_is_needed(self) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts.build_approved_units_22235099 import (
            parse_args,
        )

        args = parse_args([])
        self.assertFalse(hasattr(args, "allow_network"))
        for name in ("requests", "urllib.request", "httpx"):
            with self.subTest(module=name):
                for path in sorted(APPROVAL.glob("*")):
                    self.assertNotIn(name, path.read_text(encoding="utf-8"))

    def test_the_retriever_is_not_implemented(self) -> None:
        matches = list(REPO_ROOT.rglob("*QualifiedEvidenceRetriever*"))
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
