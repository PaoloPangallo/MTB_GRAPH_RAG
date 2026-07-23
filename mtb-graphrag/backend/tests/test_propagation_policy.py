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


if __name__ == "__main__":
    unittest.main()
