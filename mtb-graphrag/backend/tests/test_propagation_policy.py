"""Confini fra prototipo e propagazione definitiva.

Il file protegge una distinzione che si perde con facilita': mostrare un
qualificatore e usarlo per escludere evidenza non sono la stessa operazione, e
il secondo richiede una conferma che il primo non richiede.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.profile_unit import (
    ADJUDICATED,
    AWAITING_FIRST_REVIEW,
    AWAITING_SOURCE_REVIEW,
    COHORT_RESOLVED,
    COHORT_SINGLE,
    COHORT_UNRESOLVED,
    DISAGREEMENT,
    FIRST_REVIEW_COMPLETE,
    FROZEN,
    SECOND_REVIEW_COMPLETE,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
    UNIT_DIMENSIONS,
    SourceClinicalProfileUnit,
)
from backend.pipeline.evidence import evidence_granularity as granularity_module
from backend.pipeline.evidence.evidence_granularity import (
    GRANULARITY_CASE,
    GRANULARITY_COHORT,
    GRANULARITY_LEVELS,
    GRANULARITY_NAMED_PATIENT_SUBSET,
    EvidenceGranularityError,
    constraints_for,
    granularity_of,
    is_non_generalizable,
)
from backend.pipeline.evidence.propagation_guards import (
    ALL_RULE_IDS,
    GUARD_V1_RULE_IDS,
    GUARD_V12_RULE_IDS,
    CaseLevelEnrolmentError,
    CaseLevelPropagationError,
    PropagationError,
    rule_ids_for_version,
    run_guards,
)
from backend.pipeline.evidence import source_basis as source_basis_module
from backend.pipeline.evidence.source_basis import (
    ABSTRACT_ONLY,
    BASIS_UNKNOWN,
    CONFIDENCE_FULL,
    CONFIDENCE_PARTIAL,
    FULL_TEXT,
    NOT_SEPARABLE,
    SOURCE_BASES,
    STRUCTURAL_CONFIDENCES,
    confidence_for,
    constraints_for_basis,
    is_partial,
)
from backend.pipeline.evidence.propagation_policy import (
    AGREEMENT_AGREED,
    FINAL,
    NONE,
    PROTOTYPE_ONLY,
    EvaluabilityError,
    NonIndependentPropagationError,
    PrototypeHardFilterError,
    UnreviewedPropagationError,
    decide,
    eligibility_for,
    propagated_dimensions,
    validate_unit,
)
from backend.pipeline.evidence.qualification import (
    DimensionValue,
    EvidenceQualificationLink,
    QualifiedEvidenceView,
    build_view,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY = REPO_ROOT / "benchmarks/mtb_evidence/v3/propagation_policy"
REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/first_review"
APPROVAL = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"

PMID_22277784_UNITS = (
    "PU-PMID-22277784-clinical-crizotinib-resistant",
    "PU-PMID-22277784-baf3-crizotinib-panel",
    "PU-PMID-22277784-baf3-next-generation-alk-inhibitors",
    "PU-PMID-22277784-baf3-17aag",
)


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def unit(**overrides) -> dict:
    payload = {
        "profile_unit_id": "PU-x",
        "review_status": AWAITING_SOURCE_REVIEW,
        "cohort_state": COHORT_SINGLE,
    }
    payload.update(overrides)
    return payload


# ── i livelli ─────────────────────────────────────────────────────────────────


class TestEligibilityLevels(unittest.TestCase):
    def test_machine_extracted_is_none(self) -> None:
        decision = decide(review_status=AWAITING_SOURCE_REVIEW)
        self.assertEqual(decision.eligibility, NONE)
        self.assertFalse(decision.is_propagatable)
        self.assertFalse(decision.is_evaluable)
        self.assertFalse(decision.may_display_qualifiers)

    def test_awaiting_first_review_is_none(self) -> None:
        self.assertEqual(decide(review_status=AWAITING_FIRST_REVIEW).eligibility, NONE)

    def test_source_checked_proposal_is_none(self) -> None:
        decision = decide(review_status=SOURCE_CHECKED_REVIEW_PROPOSAL)
        self.assertEqual(decision.eligibility, NONE)
        self.assertFalse(decision.is_propagatable)

    def test_non_independent_first_review_is_prototype_only(self) -> None:
        decision = decide(review_status=FIRST_REVIEW_COMPLETE, independent_review=False)
        self.assertEqual(decision.eligibility, PROTOTYPE_ONLY)
        self.assertFalse(decision.is_propagatable)
        self.assertFalse(decision.is_evaluable)
        self.assertTrue(decision.requires_second_independent_review)

    def test_prototype_only_may_be_displayed_but_never_filter(self) -> None:
        decision = decide(review_status=FIRST_REVIEW_COMPLETE)
        self.assertTrue(decision.may_display_qualifiers)
        self.assertFalse(decision.may_hard_filter)
        self.assertFalse(decision.may_enter_final_metrics)

    def test_second_review_with_agreement_can_be_final(self) -> None:
        decision = decide(
            review_status=SECOND_REVIEW_COMPLETE, agreement=AGREEMENT_AGREED, gold_covered=True
        )
        self.assertEqual(decision.eligibility, FINAL)
        self.assertTrue(decision.is_propagatable)
        self.assertTrue(decision.may_hard_filter)
        self.assertTrue(decision.is_evaluable)

    def test_second_review_without_agreement_is_not_final(self) -> None:
        """Due revisioni non sono due accordi."""
        decision = decide(review_status=SECOND_REVIEW_COMPLETE)
        self.assertEqual(decision.eligibility, PROTOTYPE_ONLY)
        self.assertFalse(decision.is_propagatable)

    def test_unresolved_disagreement_is_not_propagatable(self) -> None:
        decision = decide(review_status=DISAGREEMENT)
        self.assertIn(decision.eligibility, (NONE, PROTOTYPE_ONLY))
        self.assertFalse(decision.is_propagatable)

    def test_adjudicated_can_be_final(self) -> None:
        decision = decide(review_status=ADJUDICATED, gold_covered=True)
        self.assertEqual(decision.eligibility, FINAL)
        self.assertTrue(decision.is_propagatable)

    def test_frozen_can_be_final(self) -> None:
        decision = decide(review_status=FROZEN)
        self.assertEqual(decision.eligibility, FINAL)
        self.assertTrue(decision.is_propagatable)

    def test_an_unresolved_cohort_never_becomes_final(self) -> None:
        """Nemmeno una adjudication dice a quale braccio si applichi il valore."""
        decision = decide(review_status=ADJUDICATED, cohort_state=COHORT_UNRESOLVED)
        self.assertEqual(decision.eligibility, PROTOTYPE_ONLY)
        self.assertFalse(decision.is_propagatable)

    def test_evaluability_needs_gold_coverage(self) -> None:
        decision = decide(
            review_status=SECOND_REVIEW_COMPLETE, agreement=AGREEMENT_AGREED, gold_covered=False
        )
        self.assertEqual(decision.eligibility, FINAL)
        self.assertFalse(decision.is_evaluable)

    def test_sentinels_are_not_propagated_qualifiers(self) -> None:
        payload = unit(setting="unknown", stage="not_applicable", therapy_line="not_separable")
        self.assertEqual(propagated_dimensions(payload, UNIT_DIMENSIONS), [])


# ── validatore ────────────────────────────────────────────────────────────────


class TestValidator(unittest.TestCase):
    def test_unreviewed_propagation_is_rejected(self) -> None:
        found = validate_unit(unit(is_propagatable=True))
        self.assertTrue(found)
        with self.assertRaises(UnreviewedPropagationError):
            found[0].raise_it()

    def test_non_independent_first_review_cannot_declare_propagation(self) -> None:
        found = validate_unit(
            unit(review_status=FIRST_REVIEW_COMPLETE, is_propagatable=True)
        )
        self.assertTrue(found)
        with self.assertRaises(NonIndependentPropagationError):
            found[0].raise_it()

    def test_hard_filter_use_is_rejected_for_prototype(self) -> None:
        found = validate_unit(
            unit(review_status=FIRST_REVIEW_COMPLETE, used_as_hard_filter=True)
        )
        self.assertTrue(found)
        with self.assertRaises(PrototypeHardFilterError):
            found[0].raise_it()

    def test_evaluability_without_gold_is_rejected(self) -> None:
        found = validate_unit(unit(review_status=FIRST_REVIEW_COMPLETE, is_evaluable=True))
        self.assertTrue(found)
        with self.assertRaises(EvaluabilityError):
            found[0].raise_it()

    def test_a_declared_eligibility_must_match_the_policy(self) -> None:
        found = validate_unit(
            unit(review_status=FIRST_REVIEW_COMPLETE, propagation_eligibility=FINAL)
        )
        self.assertTrue(any(item.rule_id == "declared_eligibility_mismatch" for item in found))

    def test_a_correct_unit_produces_no_violation(self) -> None:
        payload = unit(
            review_status=FIRST_REVIEW_COMPLETE,
            propagation_eligibility=PROTOTYPE_ONLY,
            is_propagatable=False,
            is_evaluable=False,
        )
        self.assertEqual(validate_unit(payload), [])


# ── schema ────────────────────────────────────────────────────────────────────


class TestSchemaContract(unittest.TestCase):
    def test_cohort_resolution_is_necessary_not_sufficient(self) -> None:
        built = SourceClinicalProfileUnit(
            profile_unit_id="PU-x", canonical_source_id="PMID:1", cohort_state=COHORT_SINGLE
        )
        self.assertTrue(built.cohort_is_resolved)
        self.assertFalse(built.is_propagatable)
        self.assertEqual(built.propagation_eligibility, NONE)

    def test_review_and_propagation_are_separate_concepts(self) -> None:
        built = SourceClinicalProfileUnit(
            profile_unit_id="PU-x",
            canonical_source_id="PMID:1",
            cohort_state=COHORT_RESOLVED,
            review_status=FIRST_REVIEW_COMPLETE,
        )
        self.assertEqual(built.review_status, FIRST_REVIEW_COMPLETE)
        self.assertEqual(built.propagation_eligibility, PROTOTYPE_ONLY)
        self.assertTrue(built.may_display_qualifiers)
        self.assertFalse(built.is_propagatable)

    def test_the_serialised_record_carries_all_three_notions(self) -> None:
        built = SourceClinicalProfileUnit(
            profile_unit_id="PU-x", canonical_source_id="PMID:1", review_status=FIRST_REVIEW_COMPLETE
        )
        record = built.as_dict()
        for key in (
            "cohort_is_resolved",
            "propagation_eligibility",
            "may_display_qualifiers",
            "is_propagatable",
        ):
            with self.subTest(key=key):
                self.assertIn(key, record)


# ── vista ─────────────────────────────────────────────────────────────────────


def dimension(eligibility: str) -> DimensionValue:
    return DimensionValue(
        dimension="setting",
        value="metastatic",
        value_origin="reviewed_source_profile",
        source_profile_id="S-1",
        source_identifier="PMID:1",
        qualification_link_id="QL-1",
        review_status=FIRST_REVIEW_COMPLETE,
        propagation_eligibility=eligibility,
    )


def view_with(eligibility: str) -> QualifiedEvidenceView:
    return QualifiedEvidenceView(
        base_statement={"evidence_statement_id": "ES-1"},
        qualified_dimensions={"setting": dimension(eligibility)},
    )


class TestViewBoundaries(unittest.TestCase):
    def test_the_view_can_show_a_prototype_qualifier(self) -> None:
        view = view_with(PROTOTYPE_ONLY)
        self.assertIn("setting", view.qualified_dimensions)
        self.assertEqual(view.prototype_only_dimensions, ("setting",))
        self.assertEqual(view.hard_filterable_dimensions, ())

    def test_the_view_refuses_to_hard_filter_on_a_prototype(self) -> None:
        with self.assertRaises(PrototypeHardFilterError):
            view_with(PROTOTYPE_ONLY).assert_hard_filterable("setting")

    def test_a_final_qualifier_may_hard_filter(self) -> None:
        view = view_with(FINAL)
        self.assertEqual(view.hard_filterable_dimensions, ("setting",))
        view.assert_hard_filterable("setting")

    def test_filtering_on_a_missing_dimension_is_refused(self) -> None:
        with self.assertRaises(PrototypeHardFilterError):
            view_with(FINAL).assert_hard_filterable("therapy_line")

    def test_the_serialised_view_separates_the_two_sets(self) -> None:
        record = view_with(PROTOTYPE_ONLY).as_dict()
        self.assertEqual(record["hard_filterable_dimensions"], [])
        self.assertEqual(record["prototype_only_dimensions"], ["setting"])

    def test_native_statement_fields_are_untouched(self) -> None:
        """La politica riguarda i qualificatori aggiunti, non il grafo congelato."""
        statement = {
            "evidence_statement_id": "ES-1",
            "disease": {"label": "NSCLC"},
            "direction": "resistance",
        }
        view = build_view(statement, [])
        self.assertEqual(view.base_statement["disease"]["label"], "NSCLC")
        self.assertEqual(view.base_statement["direction"], "resistance")
        self.assertEqual(view.qualified_dimensions, {})

    def test_an_unreviewed_profile_contributes_nothing(self) -> None:
        link = EvidenceQualificationLink(
            qualification_link_id="QL-1",
            statement_id="ES-1",
            source_profile_id="S-1",
            match_method="pubmed",
            match_status="exact_source_match",
            added_dimensions=(),
        )
        view = build_view({"evidence_statement_id": "ES-1"}, [link])
        self.assertEqual(view.qualified_dimensions, {})


# ── artefatti ─────────────────────────────────────────────────────────────────


class TestNormalizedArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(POLICY / "unit_eligibility_before_after.jsonl")
        cls.validation = load_json(POLICY / "policy_validation_results.json")
        cls.readiness = load_json(POLICY / "readiness_before_after.json")
        cls.reviewed = load_jsonl(REVIEW / "reviewed_profile_units.jsonl")
        cls.by_id = {row["profile_unit_id"]: row for row in cls.reviewed}

    def test_the_four_units_still_exist(self) -> None:
        self.assertEqual(len(self.reviewed), 4)
        for unit_id in PMID_22277784_UNITS:
            with self.subTest(unit=unit_id):
                self.assertIn(unit_id, self.by_id)

    def test_the_four_units_keep_their_first_review(self) -> None:
        for unit_id in PMID_22277784_UNITS:
            row = self.by_id[unit_id]
            with self.subTest(unit=unit_id):
                self.assertEqual(row["review_status"], FIRST_REVIEW_COMPLETE)
                self.assertEqual(row["reviewer"], "paolo_pangallo")
                self.assertEqual(row["cohort_state"], COHORT_RESOLVED)
                self.assertTrue(row["provenance"])
                self.assertTrue(row["known_dimensions"])

    def test_the_statement_links_still_reference_the_four_units(self) -> None:
        """Gli statement non vivono sull'unita' ma nelle decisioni: restano li'."""
        decisions = load_jsonl(REVIEW / "statement_first_review_decisions.jsonl")
        referenced = {
            unit_id for row in decisions for unit_id in row.get("profile_unit_ids") or ()
        }
        for unit_id in PMID_22277784_UNITS:
            with self.subTest(unit=unit_id):
                self.assertIn(unit_id, referenced)

    def test_the_four_units_are_no_longer_propagatable(self) -> None:
        for unit_id in PMID_22277784_UNITS:
            row = self.by_id[unit_id]
            with self.subTest(unit=unit_id):
                self.assertFalse(row["is_propagatable"])
                self.assertEqual(row["propagation_eligibility"], PROTOTYPE_ONLY)
                self.assertFalse(row["is_evaluable"])
                self.assertTrue(row["requires_second_independent_review"])

    def test_the_four_units_stay_distinct(self) -> None:
        self.assertEqual(len({row["profile_unit_id"] for row in self.reviewed}), 4)
        clinical = [row for row in self.reviewed if row["is_clinical"]]
        preclinical = [row for row in self.reviewed if row["is_preclinical"]]
        self.assertEqual(len(clinical), 1)
        self.assertEqual(len(preclinical), 3)

    def test_the_31358542_unit_is_semantically_unchanged(self) -> None:
        approved = load_jsonl(APPROVAL / "approved_profile_units.jsonl")[0]
        self.assertEqual(approved["review_status"], FIRST_REVIEW_COMPLETE)
        self.assertFalse(approved["is_propagatable"])
        self.assertFalse(approved["is_evaluable"])
        self.assertTrue(approved["requires_second_independent_review"])
        row = next(
            item
            for item in self.rows
            if item["profile_unit_id"] == "PU-PMID-31358542-clinical-cohort"
        )
        self.assertEqual(row["after"]["propagation_eligibility"], PROTOTYPE_ONLY)

    def test_no_unit_is_final_propagatable(self) -> None:
        final = [row for row in self.rows if row["after"]["propagation_eligibility"] == FINAL]
        self.assertEqual(final, [])

    def test_violations_go_to_zero(self) -> None:
        self.assertEqual(self.validation["violations_after_count"], 0)
        self.assertGreater(self.validation["violations_before_count"], 0)

    def test_stale_flags_are_counted_apart_from_violations(self) -> None:
        """Un dato vecchio non e' una politica violata, e i due numeri lo dicono."""
        self.assertGreater(self.validation["stale_serialized_flags"], 0)
        self.assertEqual(self.validation["violations_after_count"], 0)
        self.assertIn("rigenerazione", self.validation["stale_flag_note"])

    def test_qualifiers_are_not_lost_only_downgraded(self) -> None:
        metrics = self.validation["metrics"]
        self.assertEqual(metrics["hard_filter_eligible_qualifiers"], 0)
        self.assertGreater(metrics["prototype_visible_qualifiers"], 0)

    def test_readiness_is_honest_about_hard_filtering(self) -> None:
        self.assertFalse(self.readiness["hard_filtering_available"])
        self.assertFalse(self.readiness["gold_evaluable"])
        self.assertTrue(self.readiness["after"]["review_and_propagation_distinct"])
        self.assertTrue(self.readiness["after"]["prototype_and_final_distinct"])

    def test_every_unit_has_a_reason(self) -> None:
        for row in self.rows:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue(row["reason"])


# ── invarianti conservati ─────────────────────────────────────────────────────


class TestUnchanged(unittest.TestCase):
    def test_statement_decisions_are_unchanged(self) -> None:
        decisions = load_jsonl(REVIEW / "statement_first_review_decisions.jsonl")
        self.assertEqual(len(decisions), 10)
        approval = load_jsonl(APPROVAL / "statement_first_review_decisions.jsonl")
        self.assertEqual(len(approval), 2)
        self.assertEqual(approval[0]["first_review_candidate_status"], "candidate_invalid")

    def test_provisional_gold_is_unchanged(self) -> None:
        gold = load_jsonl(APPROVAL / "provisional_gold.jsonl")
        annotated = [row for row in gold if row.get("first_annotator")]
        self.assertEqual(len(annotated), 12)
        for row in gold:
            with self.subTest(link=row["gold_link_id"]):
                self.assertFalse(row["is_evaluable"])

    def test_provenance_completeness_is_still_one(self) -> None:
        for row in load_jsonl(REVIEW / "reviewed_profile_units.jsonl"):
            with self.subTest(unit=row["profile_unit_id"]):
                provenance = {item["field_name"] for item in row["provenance"]}
                self.assertTrue(set(row["known_dimensions"]) <= provenance)

    def test_second_review_packets_are_byte_identical(self) -> None:
        check = load_json(APPROVAL / "second_review_blinding_check.json")
        directory = CURATION / "annotation_packets/second_review"
        recomputed = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.iterdir())
            if path.is_file()
        }
        self.assertEqual(recomputed, check["hashes_after"])
        self.assertTrue(check["byte_identical"])

    def test_the_superseded_parent_is_untouched(self) -> None:
        rows = load_jsonl(REVIEW / "superseded_profile_units.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["is_propagatable"])
        self.assertEqual(len(rows[0]["superseded_by"]), 4)


# ── granularita' dell'evidenza ────────────────────────────────────────────────


def decision(**overrides) -> dict:
    payload = {"statement_id": "S-x", "evidence_granularity": GRANULARITY_CASE}
    payload.update(overrides)
    return payload


class TestEvidenceGranularityVocabulary(unittest.TestCase):
    """Il vocabolario, prima delle regole che lo usano."""

    def test_only_the_narrow_levels_block_generalization(self) -> None:
        self.assertTrue(is_non_generalizable(GRANULARITY_CASE))
        self.assertTrue(is_non_generalizable(GRANULARITY_NAMED_PATIENT_SUBSET))
        self.assertFalse(is_non_generalizable(GRANULARITY_COHORT))

    def test_a_subset_of_named_patients_is_not_a_single_case(self) -> None:
        # Due pazienti nominati non sono un caso singolo, e non sono un
        # sottogruppo: il livello proprio esiste per non doverli chiamare con un
        # nome che dice il numero sbagliato.
        self.assertNotEqual(GRANULARITY_NAMED_PATIENT_SUBSET, GRANULARITY_CASE)
        self.assertIn(GRANULARITY_NAMED_PATIENT_SUBSET, GRANULARITY_LEVELS)

    def test_unknown_granularity_does_not_block(self) -> None:
        # Non sapere il denominatore non e' sapere che e' piccolo: e' un problema
        # diverso, e trattarlo come case-level lo nasconderebbe.
        self.assertFalse(is_non_generalizable("unknown"))

    def test_constraints_are_derived_not_hand_written(self) -> None:
        constraints = constraints_for(GRANULARITY_NAMED_PATIENT_SUBSET)
        self.assertFalse(constraints["cohort_generalizable"])
        self.assertEqual(constraints["population_level_propagation"], "forbidden")
        self.assertEqual(constraints["frequency_inference"], "forbidden")
        self.assertEqual(constraints["enrolment_requirement_promotion"], "forbidden")

    def test_the_legacy_boolean_is_still_understood(self) -> None:
        self.assertEqual(granularity_of({"case_level": True}), GRANULARITY_CASE)


class TestCaseLevelGuards(unittest.TestCase):
    """Una regola che non fallisce mai non protegge niente.

    Ogni regola ha qui un esempio che deve fallire e uno che deve passare: senza
    il secondo, una regola sempre attiva sembrerebbe corretta quanto una regola
    giusta.
    """

    def test_a_case_declared_generalizable_fails(self) -> None:
        found = run_guards(decisions=[decision(cohort_generalizable=True)])
        self.assertTrue(any(item.rule_id == "case_level_to_cohort_population" for item in found))

    def test_a_case_scoped_to_the_cohort_fails(self) -> None:
        found = run_guards(decisions=[decision(population_scope="cohort")])
        self.assertTrue(any(item.rule_id == "case_level_to_cohort_population" for item in found))

    def test_a_named_subset_scoped_to_the_population_fails(self) -> None:
        found = run_guards(
            decisions=[
                decision(
                    evidence_granularity=GRANULARITY_NAMED_PATIENT_SUBSET,
                    population_scope="general_population",
                    subset_size=2,
                    cohort_size=14,
                )
            ]
        )
        self.assertTrue(found)
        with self.assertRaises(CaseLevelPropagationError):
            found[0].raise_it()

    def test_a_case_that_stays_a_case_passes(self) -> None:
        found = run_guards(
            decisions=[
                decision(
                    population_scope="single_patient",
                    cohort_generalizable=False,
                    frequency_inference="forbidden",
                )
            ]
        )
        self.assertEqual(found, [])

    def test_a_frequency_computed_on_named_patients_fails(self) -> None:
        found = run_guards(decisions=[decision(frequency="2/14")])
        self.assertTrue(any(item.rule_id == "case_level_frequency_inference" for item in found))

    def test_frequency_inference_declared_allowed_fails(self) -> None:
        found = run_guards(decisions=[decision(frequency_inference="allowed")])
        self.assertTrue(any(item.rule_id == "case_level_frequency_inference" for item in found))

    def test_a_cohort_level_frequency_passes(self) -> None:
        found = run_guards(
            decisions=[decision(evidence_granularity=GRANULARITY_COHORT, frequency="4/11")]
        )
        self.assertEqual(found, [])

    def test_an_acquired_finding_promoted_to_enrolment_fails(self) -> None:
        found = run_guards(decisions=[decision(biomarker_requirements=["EGFR L858R"])])
        self.assertTrue(found)
        with self.assertRaises(CaseLevelEnrolmentError):
            next(
                item
                for item in found
                if item.rule_id == "case_level_to_enrolment_requirement"
            ).raise_it()

    def test_an_acquired_finding_left_where_it_was_passes(self) -> None:
        found = run_guards(
            decisions=[
                decision(
                    acquired_resistance_findings=["EGFR L858R"],
                    enrolment_requirement_promotion="forbidden",
                    population_scope="single_patient",
                )
            ]
        )
        self.assertEqual(found, [])

    def test_the_errors_belong_to_both_families(self) -> None:
        # Chi esegue la pipeline intercetta PropagationError; chi ragiona sulla
        # granularita' intercetta EvidenceGranularityError. Entrambi devono
        # vedere la stessa violazione.
        found = run_guards(decisions=[decision(cohort_generalizable=True)])
        with self.assertRaises(PropagationError):
            found[0].raise_it()
        with self.assertRaises(EvidenceGranularityError):
            found[0].raise_it()

    def test_the_rules_do_not_name_a_source(self) -> None:
        text = Path(granularity_module.__file__).read_text(encoding="utf-8")
        for token in ("22235099", "PMID:", "crizotinib", "ALK"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


class TestSourceBasisVocabulary(unittest.TestCase):
    """Quanta fonte ha visto una revisione, e cosa questo le permette di dire."""

    def test_an_abstract_only_review_is_partial(self) -> None:
        self.assertTrue(is_partial(ABSTRACT_ONLY))
        self.assertEqual(confidence_for(ABSTRACT_ONLY), CONFIDENCE_PARTIAL)

    def test_a_full_text_review_is_not_capped(self) -> None:
        self.assertFalse(is_partial(FULL_TEXT))
        self.assertEqual(confidence_for(FULL_TEXT), CONFIDENCE_FULL)

    def test_an_abstract_only_basis_cannot_claim_full_text_verification(self) -> None:
        constraints = constraints_for_basis(ABSTRACT_ONLY)
        self.assertFalse(constraints["full_text_verified"])
        self.assertFalse(constraints["full_text_stored"])
        self.assertTrue(constraints["requires_full_text_or_independent_review"])

    def test_the_confidence_is_a_ceiling_not_a_value(self) -> None:
        # Un full text puo' comunque non risolvere una struttura: la funzione dice
        # il tetto, e leggerla come garanzia sarebbe l'errore opposto a quello che
        # il modulo previene.
        self.assertEqual(confidence_for(FULL_TEXT), CONFIDENCE_FULL)
        self.assertIn(CONFIDENCE_PARTIAL, STRUCTURAL_CONFIDENCES)

    def test_not_separable_is_not_unknown(self) -> None:
        # Le due assenze hanno la stessa forma nei campi e significati opposti su
        # chi debba fare qualcosa: cercare meglio, oppure smettere di cercare.
        self.assertNotEqual(NOT_SEPARABLE, BASIS_UNKNOWN)
        self.assertIn(BASIS_UNKNOWN, SOURCE_BASES)
        self.assertNotIn(NOT_SEPARABLE, SOURCE_BASES)

    def test_the_module_does_not_name_a_source(self) -> None:
        text = Path(source_basis_module.__file__).read_text(encoding="utf-8")
        for token in ("23344087", "PMID:", "crizotinib", "SNU-2535"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


class TestGuardVersioning(unittest.TestCase):
    def test_the_frozen_tuples_stay_frozen(self) -> None:
        self.assertEqual(len(GUARD_V1_RULE_IDS), 12)
        self.assertEqual(len(GUARD_V12_RULE_IDS), 3)
        self.assertEqual(
            len(ALL_RULE_IDS),
            len(set(ALL_RULE_IDS)),
            "un rule_id duplicato renderebbe ambiguo quale regola ha fallito",
        )

    def test_an_older_artifact_is_read_at_its_own_version(self) -> None:
        # Aggiungere una regola non deve invalidare retroattivamente una verifica
        # che era completa quando e' stata eseguita.
        self.assertEqual(len(rule_ids_for_version("propagation_guards/1.1")), 14)
        self.assertEqual(len(rule_ids_for_version("propagation_guards/1.2")), 17)

    def test_an_unknown_version_falls_back_to_the_current_rules(self) -> None:
        self.assertEqual(rule_ids_for_version("propagation_guards/9.9"), ALL_RULE_IDS)


if __name__ == "__main__":
    unittest.main()
