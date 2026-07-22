"""Scope, unita' di annotazione, gold dei link e guardie di freeze."""

from __future__ import annotations

import unittest

from backend.pipeline.evidence.corpus_manifest import (
    AWAITING_SECOND_REVIEW,
    BLOCKED,
    FROZEN,
    content_hash,
    evaluate_freeze,
)
from backend.pipeline.evidence.profile_unit import (
    AWAITING_SOURCE_REVIEW,
    COHORT_RESOLVED,
    COHORT_SINGLE,
    COHORT_UNRESOLVED,
    HUMAN_REVIEWED,
    MACHINE_EXTRACTED,
    SOURCE_CHECKED,
    UNKNOWN,
    UNREVIEWED,
    FieldProvenance,
    ProfileUnitError,
    SourceClinicalProfileUnit,
    blind_id,
    unit_id,
    validate_units,
)
from backend.pipeline.evidence.qualification_gold import (
    AMBIGUOUS_LINK,
    CONFLICTING_LINK,
    GOLD_ADJUDICATED,
    GOLD_AWAITING_SECOND,
    GOLD_CANDIDATE,
    GOLD_DISAGREEMENT,
    INVALID_LINK,
    PARTIAL_LINK,
    VALID_LINK,
    AnnotationDecision,
    QualificationGoldError,
    StatementQualificationGold,
    agreement_rate,
    candidate_from_link,
    gold_link_id,
    validate_gold,
)


def make_unit(**overrides: object) -> SourceClinicalProfileUnit:
    payload: dict = {
        "profile_unit_id": "PU-PMID-1-cohort-1",
        "canonical_source_id": "PMID:1",
    }
    payload.update(overrides)
    return SourceClinicalProfileUnit(**payload)  # type: ignore[arg-type]


def decision(annotator: str, status: str = VALID_LINK, **overrides: object) -> AnnotationDecision:
    payload: dict = {"annotator_id": annotator, "link_status": status}
    payload.update(overrides)
    return AnnotationDecision(**payload)  # type: ignore[arg-type]


# ── unita' di annotazione ─────────────────────────────────────────────────────


class TestProfileUnit(unittest.TestCase):
    def test_single_cohort_source_needs_one_unit(self) -> None:
        unit = make_unit(cohort_state=COHORT_SINGLE)
        self.assertTrue(unit.is_propagatable)

    def test_unresolved_cohort_never_propagates(self) -> None:
        """Con due coorti indistinguibili, propagare significa scegliere a caso."""
        unit = make_unit(cohort_state=COHORT_UNRESOLVED, setting="metastatico")
        self.assertFalse(unit.is_propagatable)

    def test_resolved_cohort_propagates(self) -> None:
        self.assertTrue(make_unit(cohort_state=COHORT_RESOLVED).is_propagatable)

    def test_multi_cohort_source_produces_distinct_unit_ids(self) -> None:
        first = unit_id("PMID:1", "cohort-1")
        second = unit_id("PMID:1", "cohort-2")
        self.assertNotEqual(first, second)

    def test_unknown_is_not_counted_as_known(self) -> None:
        unit = make_unit(setting=UNKNOWN, therapy_line="")
        self.assertNotIn("setting", unit.known_dimensions())
        self.assertNotIn("therapy_line", unit.known_dimensions())

    def test_known_dimension_without_provenance_is_flagged(self) -> None:
        unit = make_unit(setting="adiuvante")
        self.assertFalse(unit.provenance_complete())
        self.assertEqual(unit.missing_provenance(), ("setting",))

    def test_provenance_makes_the_unit_complete(self) -> None:
        unit = make_unit(
            setting="adiuvante",
            provenance=(
                FieldProvenance(
                    field_name="setting",
                    value_origin="primary_source_text",
                    source_locator="pubmed:1#methods",
                ),
            ),
        )
        self.assertTrue(unit.provenance_complete())
        self.assertEqual(validate_units([unit]), [])

    def test_multi_intervention_unit_keeps_every_intervention(self) -> None:
        unit = make_unit(
            intervention=("osimertinib", "gefitinib"),
            provenance=(
                FieldProvenance(field_name="intervention", value_origin="primary_source_text"),
            ),
        )
        self.assertIn("intervention", unit.known_dimensions())
        self.assertEqual(len(unit.intervention), 2)

    def test_duplicate_unit_ids_are_rejected(self) -> None:
        problems = validate_units([make_unit(), make_unit()])
        self.assertTrue(any("duplicato" in problem for problem in problems))

    def test_machine_extracted_cannot_claim_a_human_status(self) -> None:
        """L'automatismo che si dichiara revisionato trasforma se stesso in gold."""
        unit = make_unit(extraction_status=MACHINE_EXTRACTED, review_status=HUMAN_REVIEWED)
        problems = validate_units([unit])
        self.assertTrue(any("stato umano" in problem for problem in problems))

    def test_unresolved_cohort_must_request_human_review(self) -> None:
        unit = make_unit(cohort_state=COHORT_UNRESOLVED, requires_human_review=False)
        problems = validate_units([unit])
        self.assertTrue(any("requires_human_review" in problem for problem in problems))

    def test_invalid_status_is_refused_at_construction(self) -> None:
        with self.assertRaises(ProfileUnitError):
            make_unit(review_status="definitely_reviewed")
        with self.assertRaises(ProfileUnitError):
            make_unit(extraction_status="hallucinated")

    def test_blind_id_hides_the_identifier(self) -> None:
        blind = blind_id("PMID:29151359", "cohort-1")
        self.assertNotIn("29151359", blind)
        self.assertEqual(blind, blind_id("PMID:29151359", "cohort-1"))

    def test_no_cross_cohort_propagation(self) -> None:
        """Due coorti della stessa fonte non condividono i qualificatori."""
        first = make_unit(profile_unit_id="PU-a", cohort_id="cohort-1", setting="adiuvante",
                          provenance=(FieldProvenance(field_name="setting", value_origin="primary_source_text"),))
        second = make_unit(profile_unit_id="PU-b", cohort_id="cohort-2")
        self.assertEqual(second.setting, UNKNOWN)
        self.assertNotEqual(first.setting, second.setting)


# ── gold dei collegamenti ─────────────────────────────────────────────────────


class TestQualificationGold(unittest.TestCase):
    def test_candidate_is_not_a_gold(self) -> None:
        record = candidate_from_link("S1", "PU-1", predicted_status=VALID_LINK)
        self.assertEqual(record.state, GOLD_CANDIDATE)
        self.assertFalse(record.is_evaluable)
        self.assertEqual(record.final_status, "")

    def test_prediction_is_kept_inert_in_the_note(self) -> None:
        record = candidate_from_link("S1", "PU-1", predicted_status=CONFLICTING_LINK)
        self.assertIn(CONFLICTING_LINK, record.note)
        self.assertIsNone(record.first_annotation)

    def test_first_review_alone_awaits_the_second(self) -> None:
        record = StatementQualificationGold(
            gold_link_id="GL-1",
            statement_id="S1",
            profile_unit_id="PU-1",
            first_annotation=decision("ann-a"),
        )
        self.assertEqual(record.state, GOLD_AWAITING_SECOND)
        self.assertIsNone(record.agreement)
        self.assertFalse(record.is_evaluable)

    def test_two_agreeing_reviews_produce_a_verdict(self) -> None:
        record = StatementQualificationGold(
            gold_link_id="GL-1",
            statement_id="S1",
            profile_unit_id="PU-1",
            first_annotation=decision("ann-a"),
            second_annotation=decision("ann-b"),
        )
        self.assertTrue(record.agreement)
        self.assertEqual(record.state, GOLD_ADJUDICATED)
        self.assertEqual(record.final_status, VALID_LINK)
        self.assertTrue(record.is_evaluable)

    def test_disagreement_blocks_the_verdict(self) -> None:
        record = StatementQualificationGold(
            gold_link_id="GL-1",
            statement_id="S1",
            profile_unit_id="PU-1",
            first_annotation=decision("ann-a", VALID_LINK),
            second_annotation=decision("ann-b", INVALID_LINK),
        )
        self.assertFalse(record.agreement)
        self.assertEqual(record.state, GOLD_DISAGREEMENT)
        self.assertEqual(record.final_status, "")
        self.assertFalse(record.is_evaluable)

    def test_adjudication_resolves_a_disagreement(self) -> None:
        record = StatementQualificationGold(
            gold_link_id="GL-1",
            statement_id="S1",
            profile_unit_id="PU-1",
            first_annotation=decision("ann-a", VALID_LINK),
            second_annotation=decision("ann-b", INVALID_LINK),
            adjudicator="adj-1",
            adjudication=decision("adj-1", PARTIAL_LINK),
        )
        self.assertEqual(record.final_status, PARTIAL_LINK)
        self.assertTrue(record.is_evaluable)

    def test_adjudication_needs_a_named_adjudicator(self) -> None:
        with self.assertRaises(QualificationGoldError):
            StatementQualificationGold(
                gold_link_id="GL-1",
                statement_id="S1",
                profile_unit_id="PU-1",
                adjudication=decision("adj-1"),
            )

    def test_same_annotator_twice_is_not_a_double_review(self) -> None:
        """Un accordo perfetto fra una annotazione e la sua copia non dice nulla."""
        record = StatementQualificationGold(
            gold_link_id="GL-1",
            statement_id="S1",
            profile_unit_id="PU-1",
            first_annotation=decision("ann-a"),
            second_annotation=decision("ann-a"),
        )
        self.assertFalse(record.has_two_real_reviews)
        self.assertIsNone(record.agreement)
        problems = validate_gold([record])
        self.assertTrue(any("stesso annotatore" in problem for problem in problems))

    def test_agreement_rate_is_none_without_real_pairs(self) -> None:
        rate, count = agreement_rate([candidate_from_link("S1", "PU-1", predicted_status=VALID_LINK)])
        self.assertIsNone(rate)
        self.assertEqual(count, 0)

    def test_agreement_rate_counts_only_real_pairs(self) -> None:
        agreed = StatementQualificationGold(
            gold_link_id="GL-1", statement_id="S1", profile_unit_id="PU-1",
            first_annotation=decision("a"), second_annotation=decision("b"),
        )
        disagreed = StatementQualificationGold(
            gold_link_id="GL-2", statement_id="S2", profile_unit_id="PU-2",
            first_annotation=decision("a", VALID_LINK),
            second_annotation=decision("b", AMBIGUOUS_LINK),
        )
        alone = StatementQualificationGold(
            gold_link_id="GL-3", statement_id="S3", profile_unit_id="PU-3",
            first_annotation=decision("a"),
        )
        rate, count = agreement_rate([agreed, disagreed, alone])
        self.assertEqual(count, 2)
        self.assertAlmostEqual(rate or 0.0, 0.5)

    def test_unknown_rationale_code_is_rejected(self) -> None:
        with self.assertRaises(QualificationGoldError):
            decision("a", rationale_codes=("because_it_looked_right",))

    def test_unknown_dimension_is_rejected(self) -> None:
        with self.assertRaises(QualificationGoldError):
            decision("a", applicable_dimensions=("vibes",))

    def test_gold_link_id_is_deterministic(self) -> None:
        self.assertEqual(gold_link_id("S1", "PU-1"), gold_link_id("S1", "PU-1"))
        self.assertNotEqual(gold_link_id("S1", "PU-1"), gold_link_id("S1", "PU-2"))

    def test_every_link_status_is_representable(self) -> None:
        for status in (VALID_LINK, PARTIAL_LINK, AMBIGUOUS_LINK, CONFLICTING_LINK, INVALID_LINK):
            with self.subTest(status=status):
                record = StatementQualificationGold(
                    gold_link_id="GL-x", statement_id="S", profile_unit_id="PU",
                    first_annotation=decision("a", status),
                    second_annotation=decision("b", status),
                )
                self.assertEqual(record.final_status, status)


# ── freeze ────────────────────────────────────────────────────────────────────


class TestFreezeGuards(unittest.TestCase):
    def _freeze(self, **overrides: object):
        payload: dict = {
            "units": [],
            "gold_records": [],
            "required_second_reviews": 0,
            "unresolved_sources": 0,
            "snapshot_fingerprint": "a" * 64,
            "expected_snapshot_fingerprint": "a" * 64,
            "statement_repository_hash": "b" * 64,
            "expected_statement_repository_hash": "b" * 64,
        }
        payload.update(overrides)
        return evaluate_freeze(**payload)  # type: ignore[arg-type]

    def _reviewed_gold(self) -> StatementQualificationGold:
        return StatementQualificationGold(
            gold_link_id="GL-1", statement_id="S1", profile_unit_id="PU-1",
            first_annotation=decision("a"), second_annotation=decision("b"),
        )

    def test_complete_corpus_freezes(self) -> None:
        result = self._freeze(gold_records=[self._reviewed_gold()], required_second_reviews=1)
        self.assertEqual(result.status, FROZEN)
        self.assertEqual(result.blockers, ())

    def test_missing_second_review_blocks_the_freeze(self) -> None:
        record = StatementQualificationGold(
            gold_link_id="GL-1", statement_id="S1", profile_unit_id="PU-1",
            first_annotation=decision("a"),
        )
        result = self._freeze(gold_records=[record], required_second_reviews=1)
        self.assertNotEqual(result.status, FROZEN)
        self.assertTrue(any("seconda revisione" in blocker for blocker in result.blockers))

    def test_missing_review_is_awaiting_not_broken(self) -> None:
        """Un lavoro non finito non e' un lavoro rotto."""
        record = StatementQualificationGold(
            gold_link_id="GL-1", statement_id="S1", profile_unit_id="PU-1",
            first_annotation=decision("a"),
        )
        result = self._freeze(gold_records=[record], required_second_reviews=1)
        self.assertEqual(result.status, AWAITING_SECOND_REVIEW)

    def test_disagreement_blocks_the_freeze(self) -> None:
        record = StatementQualificationGold(
            gold_link_id="GL-1", statement_id="S1", profile_unit_id="PU-1",
            first_annotation=decision("a", VALID_LINK),
            second_annotation=decision("b", INVALID_LINK),
        )
        result = self._freeze(gold_records=[record], required_second_reviews=1)
        self.assertEqual(result.status, BLOCKED)
        self.assertTrue(any("disagreement" in blocker for blocker in result.blockers))

    def test_incomplete_provenance_blocks_the_freeze(self) -> None:
        unit = make_unit(setting="adiuvante")
        result = self._freeze(
            units=[unit], gold_records=[self._reviewed_gold()], required_second_reviews=1
        )
        self.assertEqual(result.status, BLOCKED)
        self.assertTrue(any("provenance" in blocker for blocker in result.blockers))

    def test_sourceless_clinical_values_block_the_freeze(self) -> None:
        unit = make_unit(
            setting="adiuvante",
            extraction_status=UNREVIEWED,
            provenance=(FieldProvenance(field_name="setting", value_origin="machine_extraction"),),
        )
        result = self._freeze(
            units=[unit], gold_records=[self._reviewed_gold()], required_second_reviews=1
        )
        self.assertEqual(result.status, BLOCKED)
        self.assertTrue(any("nessuna fonte" in blocker for blocker in result.blockers))

    def test_unresolved_identifiers_block_the_freeze(self) -> None:
        result = self._freeze(
            gold_records=[self._reviewed_gold()], required_second_reviews=1, unresolved_sources=3
        )
        self.assertEqual(result.status, BLOCKED)
        self.assertTrue(any("non risolto" in blocker for blocker in result.blockers))

    def test_snapshot_mismatch_is_detected(self) -> None:
        result = self._freeze(
            gold_records=[self._reviewed_gold()],
            required_second_reviews=1,
            snapshot_fingerprint="c" * 64,
        )
        self.assertEqual(result.status, BLOCKED)
        self.assertTrue(any("snapshot_fingerprint" in blocker for blocker in result.blockers))

    def test_repository_hash_mismatch_is_detected(self) -> None:
        result = self._freeze(
            gold_records=[self._reviewed_gold()],
            required_second_reviews=1,
            statement_repository_hash="d" * 64,
        )
        self.assertEqual(result.status, BLOCKED)
        self.assertTrue(
            any("statement_repository_hash" in blocker for blocker in result.blockers)
        )

    def test_all_blockers_are_reported_together(self) -> None:
        unit = make_unit(setting="adiuvante")
        result = self._freeze(
            units=[unit],
            gold_records=[self._reviewed_gold()],
            required_second_reviews=1,
            unresolved_sources=1,
            snapshot_fingerprint="e" * 64,
        )
        self.assertGreaterEqual(len(result.blockers), 3)

    def test_content_hash_is_order_sensitive_but_stable(self) -> None:
        self.assertEqual(content_hash([1, 2, 3]), content_hash([1, 2, 3]))
        self.assertNotEqual(content_hash([1, 2, 3]), content_hash([3, 2, 1]))


if __name__ == "__main__":
    unittest.main()
