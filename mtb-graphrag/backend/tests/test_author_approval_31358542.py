"""Approvazione dell'autore su PMID 31358542: stati, gold, blinding.

Tutti offline. Il file protegge i quattro modi in cui questa fase potrebbe
sbagliare: dichiarare piu' di quanto sia stato deciso, far propagare cio' che
non e' ancora indipendente, copiare una decisione nel gold, e lasciar filtrare
la decisione nei packet ciechi.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.corpus_manifest import content_hash
from backend.pipeline.evidence.profile_unit import (
    COHORT_REVIEWED_PENDING_INDEPENDENT,
    COHORT_STATES,
    COHORT_SUPERSEDED_BY_RESTRUCTURE,
    FIRST_REVIEW_COMPLETE,
    HUMAN_ONLY_STATUSES,
    SourceClinicalProfileUnit,
)
from benchmarks.mtb_evidence.evaluation.author_approval import (
    APPROVE_WITH_CORRECTIONS,
    APPROVED_UNIT_ID,
    CITATION_CONTEXT_FALSE_POSITIVE,
    DETECTOR_PRINCIPLE,
    FORBIDDEN_STATUSES,
    PARENT_UNIT_ID,
    REVIEW_METHOD,
    REVIEWER_ID,
    REVIEWER_ROLE,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
APPROVAL = REPO_ROOT / "benchmarks/mtb_evidence/v3/author_approval"
BATCH = REPO_ROOT / "benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"
REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/first_review"

STATEMENT_INVALID = "ES-V2-evidence-100003"
STATEMENT_PARTIAL = "ES-V2-evidence-100004"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── unita' attiva ─────────────────────────────────────────────────────────────


class TestApprovedUnit(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(APPROVAL / "approved_profile_units.jsonl")
        cls.unit = cls.units[0]
        cls.history = load_jsonl(APPROVAL / "parent_unit_history.jsonl")

    def test_exactly_one_active_unit(self) -> None:
        active = [row for row in self.units if row["is_active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["profile_unit_id"], APPROVED_UNIT_ID)

    def test_no_active_preclinical_unit(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["is_preclinical"])
                self.assertTrue(row["is_clinical"])
        self.assertEqual(self.unit["unit_type"], "clinical_observational_cohort")

    def test_the_rejected_split_proposals_are_retained(self) -> None:
        rejected = [row for row in self.history if row["role"] == "rejected_audit_proposal"]
        self.assertEqual(len(rejected), 2)
        for row in rejected:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["review_status"], "rejected")
                self.assertFalse(row["is_active"])
                self.assertTrue(row["rejection_reason"])

    def test_the_parent_unit_is_preserved(self) -> None:
        parent = next(row for row in self.history if row["role"] == "parent_unit")
        self.assertEqual(parent["profile_unit_id"], PARENT_UNIT_ID)
        self.assertEqual(parent["superseded_by"], [APPROVED_UNIT_ID])
        self.assertFalse(parent["is_propagatable"])

    def test_the_parent_state_does_not_call_it_a_split(self) -> None:
        """Lo split e' stato respinto: chiamarlo split direbbe il contrario."""
        parent = next(row for row in self.history if row["role"] == "parent_unit")
        self.assertEqual(parent["cohort_state"], COHORT_SUPERSEDED_BY_RESTRUCTURE)
        self.assertNotIn("split", parent["cohort_state"])

    def test_the_active_unit_supersedes_the_parent(self) -> None:
        self.assertEqual(self.unit["supersedes"], PARENT_UNIT_ID)
        self.assertEqual(self.unit["parent_profile_unit_id"], PARENT_UNIT_ID)

    def test_the_active_unit_is_not_propagatable(self) -> None:
        self.assertFalse(self.unit["is_propagatable"])
        self.assertEqual(self.unit["cohort_state"], COHORT_REVIEWED_PENDING_INDEPENDENT)

    def test_the_new_state_can_never_propagate(self) -> None:
        built = SourceClinicalProfileUnit(
            profile_unit_id="PU-test",
            canonical_source_id="PMID:1",
            cohort_state=COHORT_REVIEWED_PENDING_INDEPENDENT,
        )
        self.assertFalse(built.is_propagatable)
        self.assertIn(COHORT_REVIEWED_PENDING_INDEPENDENT, COHORT_STATES)

    def test_eight_subgroups_are_recorded(self) -> None:
        self.assertEqual(self.unit["analyzed_subgroups_count"], 8)
        self.assertTrue(self.unit["subgroup_overlap"])

    def test_eight_subgroups_do_not_become_eight_units(self) -> None:
        self.assertFalse(self.unit["requires_subgroup_unit_split"])
        self.assertEqual(len(self.units), 1)

    def test_subgroup_results_are_not_globally_propagatable(self) -> None:
        self.assertFalse(self.unit["subgroup_specific_results_globally_propagatable"])

    def test_future_split_needs_four_conditions(self) -> None:
        self.assertEqual(len(self.unit["subgroup_future_split_conditions"]), 4)

    def test_intervention_attribution_is_not_separable(self) -> None:
        self.assertEqual(self.unit["intervention_attribution"], "not_separable")
        self.assertEqual(self.unit["field_decisions"]["intervention"], "not_separable")

    def test_unsupported_fields_stay_unknown(self) -> None:
        for field in self.unit["unknown_fields"]:
            with self.subTest(field=field):
                self.assertEqual(self.unit["field_decisions"][field], "unknown")

    def test_no_clinical_field_is_invented(self) -> None:
        for field in ("therapy_line", "regimen", "comparator", "stage", "setting", "resection_status"):
            with self.subTest(field=field):
                self.assertIn(
                    self.unit["field_decisions"][field], ("unknown", "not_applicable", "confirmed")
                )
        self.assertEqual(self.unit["regimen"], "unknown")
        self.assertEqual(self.unit["stage"], "unknown")

    def test_provenance_completeness_is_one(self) -> None:
        provenance = {item["field_name"] for item in self.unit["provenance"]}
        self.assertTrue(set(self.unit["known_dimensions"]) <= provenance)
        metrics = load_json(APPROVAL / "review_metrics.json")
        self.assertEqual(metrics["qualifier_provenance_completeness"], 1.0)

    def test_every_provenance_entry_carries_the_full_chain(self) -> None:
        for item in self.unit["provenance"]:
            with self.subTest(field=item["field_name"]):
                for key in (
                    "source_identifier",
                    "source_locator",
                    "span_hash",
                    "document_hash",
                    "extraction_method",
                    "reviewer",
                    "review_method",
                    "review_date",
                ):
                    self.assertTrue(item[key], f"{key} mancante")


# ── statement ─────────────────────────────────────────────────────────────────


class TestStatementDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(APPROVAL / "statement_first_review_decisions.jsonl")
        cls.by_id = {row["statement_id"]: row for row in cls.rows}

    def test_both_statements_are_reviewed(self) -> None:
        self.assertEqual(len(self.rows), 2)

    def test_100003_is_candidate_invalid(self) -> None:
        row = self.by_id[STATEMENT_INVALID]
        self.assertEqual(row["previous_candidate_status"], "candidate_ambiguous")
        self.assertEqual(row["first_review_candidate_status"], "candidate_invalid")

    def test_100003_carries_the_aggregate_to_specific_reason(self) -> None:
        row = self.by_id[STATEMENT_INVALID]
        self.assertEqual(row["invalid_reason"], "aggregate_to_specific_intervention_attribution")
        self.assertEqual(row["unsupported_or_not_separable_dimensions"], ["intervention"])

    def test_class_claim_is_distinct_from_drug_specific_claim(self) -> None:
        row = self.by_id[STATEMENT_INVALID]
        self.assertEqual(row["source_claim_scope"], "second_generation_alk_tki_class")
        self.assertEqual(row["statement_claim_scope"], "brigatinib")
        self.assertNotEqual(row["source_claim_scope"], row["statement_claim_scope"])
        self.assertEqual(row["intervention_attribution"], "unsupported_by_this_source")

    def test_100003_is_not_marked_not_determinable(self) -> None:
        """Il full text e' disponibile: il dubbio non c'e'."""
        row = self.by_id[STATEMENT_INVALID]
        self.assertNotIn("not_determinable", row["first_review_candidate_status"])
        self.assertEqual(row["direct_clinical_support"], "false_for_drug_specific_claim")

    def test_100004_stays_candidate_partial(self) -> None:
        row = self.by_id[STATEMENT_PARTIAL]
        self.assertEqual(row["previous_candidate_status"], "candidate_partial")
        self.assertEqual(row["first_review_candidate_status"], "candidate_partial")

    def test_100004_lists_supported_and_unsupported_dimensions(self) -> None:
        row = self.by_id[STATEMENT_PARTIAL]
        self.assertIn("disease", row["supported_dimensions"])
        self.assertIn("ALK rearrangement", row["supported_dimensions"])
        self.assertIn("clinical resistance context", row["supported_dimensions"])
        self.assertEqual(len(row["unsupported_or_not_separable_dimensions"]), 3)

    def test_no_decision_claims_a_preclinical_component(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["has_preclinical_component"])
                self.assertTrue(row["has_clinical_component"])

    def test_decisions_are_not_evaluable(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_evaluable_for_final_metrics"])


# ── revisore ──────────────────────────────────────────────────────────────────


class TestReviewerIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.record = load_jsonl(APPROVAL / "author_approval_records.jsonl")[0]

    def test_the_approval_is_with_corrections(self) -> None:
        self.assertEqual(self.record["author_decision"], APPROVE_WITH_CORRECTIONS)
        self.assertEqual(len(self.record["corrections"]), 1)

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

    def test_human_reviewed_does_not_imply_clinical_review(self) -> None:
        self.assertTrue(self.record["human_reviewed"])
        self.assertFalse(self.record["clinical_reviewed"])

    def test_first_review_is_complete(self) -> None:
        self.assertEqual(self.record["review_status"], FIRST_REVIEW_COMPLETE)
        self.assertIn(FIRST_REVIEW_COMPLETE, HUMAN_ONLY_STATUSES)

    def test_the_source_stays_fully_clinical(self) -> None:
        self.assertEqual(self.record["clinical_preclinical_split"], "rejected")
        self.assertEqual(self.record["final_number_of_profile_units"], 1)
        self.assertEqual(self.record["structural_decision"], "audit_split_not_supported")

    def test_no_forbidden_status_is_declared(self) -> None:
        blob = (APPROVAL / "author_approval_records.jsonl").read_text(encoding="utf-8")
        for status in FORBIDDEN_STATUSES:
            with self.subTest(status=status):
                self.assertNotIn(f'"{status}": true', blob.casefold())

    def test_the_audit_trail_names_who_decided(self) -> None:
        trail = load_jsonl(APPROVAL / "audit_trail.jsonl")
        self.assertEqual(len(trail), 4)
        human = [row for row in trail if row["is_human_decision"]]
        self.assertEqual(len(human), 1)
        self.assertEqual(human[0]["decided_by"], REVIEWER_ID)


# ── gold provvisorio ──────────────────────────────────────────────────────────


class TestProvisionalGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gold = load_jsonl(APPROVAL / "provisional_gold.jsonl")
        cls.touched = [
            row
            for row in cls.gold
            if row["statement_id"] in (STATEMENT_INVALID, STATEMENT_PARTIAL)
            and row["profile_unit_id"] == PARENT_UNIT_ID
        ]

    def test_two_links_are_annotated(self) -> None:
        self.assertEqual(len(self.touched), 2)

    def test_the_gold_is_still_provisional(self) -> None:
        for row in self.touched:
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_first_review")
                self.assertEqual(row["review_stage"], "first_review_complete")

    def test_the_gold_is_not_evaluable(self) -> None:
        for row in self.gold:
            with self.subTest(link=row["gold_link_id"]):
                self.assertFalse(row["is_evaluable"])

    def test_the_second_annotator_is_empty(self) -> None:
        for row in self.touched:
            with self.subTest(link=row["gold_link_id"]):
                self.assertIsNone(row["second_annotator"])
                self.assertIsNone(row["second_annotation"])
                self.assertIsNone(row["agreement"])
                self.assertIsNone(row["adjudication"])
                self.assertTrue(row["requires_second_review"])

    def test_the_decision_lives_in_the_annotation_not_in_final_status(self) -> None:
        for row in self.touched:
            with self.subTest(link=row["gold_link_id"]):
                annotation = row["first_review_annotation"]
                self.assertIn(annotation["candidate_status"], ("candidate_invalid", "candidate_partial"))
                self.assertNotEqual(row["final_status"], annotation["candidate_status"])
                self.assertNotIn("candidate_", row["final_status"])

    def test_the_annotation_records_method_and_role(self) -> None:
        for row in self.touched:
            annotation = row["first_review_annotation"]
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(annotation["reviewer_id"], REVIEWER_ID)
                self.assertEqual(annotation["reviewer_role"], REVIEWER_ROLE)
                self.assertEqual(annotation["review_method"], REVIEW_METHOD)
                self.assertFalse(annotation["independent_review"])
                self.assertFalse(annotation["clinical_reviewer"])

    def test_the_annotation_points_at_the_active_unit(self) -> None:
        for row in self.touched:
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(
                    row["first_review_annotation"]["profile_unit_ids"], [APPROVED_UNIT_ID]
                )

    def test_the_previous_gold_is_unchanged(self) -> None:
        """La fase precedente resta com'era: le sue dieci annotazioni sono intatte."""
        previous = load_jsonl(REVIEW / "provisional_gold.jsonl")
        annotated = [row for row in previous if row.get("first_annotator")]
        self.assertEqual(len(annotated), 10)
        for row in previous:
            if row["statement_id"] in (STATEMENT_INVALID, STATEMENT_PARTIAL):
                if row["profile_unit_id"] == PARENT_UNIT_ID:
                    with self.subTest(link=row["gold_link_id"]):
                        self.assertIsNone(row["first_annotator"])

    def test_the_gold_keeps_every_previous_record(self) -> None:
        previous = load_jsonl(REVIEW / "provisional_gold.jsonl")
        self.assertEqual(len(self.gold), len(previous))


# ── rilevatore ────────────────────────────────────────────────────────────────


class TestDetectorReferenceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.case = load_jsonl(APPROVAL / "detector_reference_cases.jsonl")[0]

    def test_the_case_is_registered(self) -> None:
        self.assertTrue(self.case["detector_reference_case"])
        self.assertEqual(self.case["profile_unit_id"], PARENT_UNIT_ID)
        self.assertEqual(self.case["reference_case_status"], "first_review_confirmed")

    def test_it_is_a_citation_context_false_positive(self) -> None:
        self.assertEqual(self.case["reference_case_type"], CITATION_CONTEXT_FALSE_POSITIVE)
        self.assertEqual(self.case["detector_original_verdict"], "split_required")
        self.assertEqual(self.case["reviewed_verdict"], "split_not_supported")

    def test_the_citation_context_is_preserved(self) -> None:
        self.assertTrue(self.case["section"])
        self.assertTrue(self.case["sentence"])
        self.assertTrue(self.case["bibliographic_reference"])
        self.assertTrue(self.case["citation_context"])
        self.assertIn("in vitro", self.case["sentence"])

    def test_the_absence_of_own_preclinical_work_is_recorded(self) -> None:
        self.assertFalse(self.case["own_preclinical_methods_present"])
        self.assertFalse(self.case["own_preclinical_figures_present"])
        self.assertFalse(self.case["own_preclinical_results_present"])

    def test_the_principle_is_stated(self) -> None:
        self.assertEqual(self.case["principle"], DETECTOR_PRINCIPLE)
        self.assertIn("!=", DETECTOR_PRINCIPLE)

    def test_it_is_a_regression_case_not_a_performance_estimate(self) -> None:
        self.assertTrue(self.case["use_as_regression_case"])
        self.assertFalse(self.case["use_for_detector_performance_estimation"])

    def test_the_detector_is_not_promoted(self) -> None:
        readiness = load_json(APPROVAL / "readiness.json")
        self.assertFalse(readiness["detector_promotion_ready"])


# ── metriche e readiness ──────────────────────────────────────────────────────


class TestMetricsAndReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = load_json(APPROVAL / "review_metrics.json")
        cls.readiness = load_json(APPROVAL / "readiness.json")

    def test_descriptive_counters_are_updated(self) -> None:
        self.assertEqual(self.metrics["author_approval_packets_completed"], 1)
        self.assertEqual(self.metrics["first_review_sources_completed"], 1)
        self.assertEqual(self.metrics["first_review_statements_reviewed"], 2)
        self.assertEqual(self.metrics["first_review_structural_splits_rejected"], 1)
        self.assertEqual(self.metrics["first_review_candidate_invalid"], 1)
        self.assertEqual(self.metrics["first_review_candidate_partial"], 1)
        self.assertEqual(self.metrics["detector_reference_hard_negatives"], 1)

    def test_coverage_separates_the_review_stages(self) -> None:
        coverage = self.metrics["coverage_by_review_stage"]
        for stage in (
            "source_checked_proposal",
            "first_review_confirmed",
            "second_review_confirmed",
            "final_adjudicated",
        ):
            with self.subTest(stage=stage):
                self.assertIn(stage, coverage)
        self.assertEqual(coverage["second_review_confirmed"], 0)
        self.assertEqual(coverage["final_adjudicated"], 0)

    def test_no_final_metric_is_calculated(self) -> None:
        for name in (
            "linking_precision",
            "linking_recall",
            "linking_f1",
            "inter_annotator_agreement",
            "detector_accuracy",
            "clinical_applicability_accuracy",
            "retrieval_quality",
        ):
            with self.subTest(metric=name):
                self.assertEqual(self.metrics["not_calculated"][name], "not_calculated")

    def test_readiness_keeps_the_gold_closed(self) -> None:
        self.assertFalse(self.readiness["gold_evaluable"])
        self.assertFalse(self.readiness["ready_for_final_evaluation"])
        self.assertTrue(self.readiness["second_review_required"])

    def test_the_standard_queue_is_not_resumed(self) -> None:
        self.assertFalse(self.readiness["standard_queue_resumed"])

    def test_two_approvals_remain_pending(self) -> None:
        self.assertEqual(self.readiness["author_approvals_completed"], 1)
        self.assertEqual(self.readiness["author_approvals_pending"], 2)
        self.assertEqual(self.readiness["clinical_preclinical_false_positives_confirmed"], 1)

    def test_hashes_match_the_artifacts(self) -> None:
        self.assertEqual(
            self.metrics["hashes"]["statement_decisions"],
            content_hash(load_jsonl(APPROVAL / "statement_first_review_decisions.jsonl")),
        )
        self.assertEqual(
            self.metrics["hashes"]["provisional_gold"],
            content_hash(load_jsonl(APPROVAL / "provisional_gold.jsonl")),
        )


# ── blinding ──────────────────────────────────────────────────────────────────


class TestBlinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = load_json(APPROVAL / "second_review_blinding_check.json")
        cls.directory = CURATION / "annotation_packets/second_review"

    def test_the_packets_are_byte_identical(self) -> None:
        self.assertTrue(self.check["byte_identical"])
        self.assertEqual(self.check["changed_files"], [])
        self.assertEqual(self.check["file_count_before"], self.check["file_count_after"])

    def test_the_recorded_hashes_still_match_the_files(self) -> None:
        recomputed = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(self.directory.iterdir())
            if path.is_file()
        }
        self.assertEqual(recomputed, self.check["hashes_after"])

    def test_the_batch_recorded_the_same_hashes(self) -> None:
        """Il blinding regge attraverso le fasi, non solo dentro una."""
        previous = load_json(BATCH / "second_review_blinding_check.json")
        self.assertEqual(previous["hashes_after"], self.check["hashes_after"])

    def test_nothing_from_this_review_leaks_into_the_blind_packets(self) -> None:
        # Solo termini che questa fase puo' aver prodotto. `candidate_partial`
        # e simili sono vocabolario preesistente e compaiono legittimamente nei
        # packet di altre fonti: cercarli proverebbe qualcosa che non e' vero.
        needles = (
            "paolo",
            "pangallo",
            "approve_with_corrections",
            "audit_split_not_supported",
            "citation_context_false_positive",
            "aggregate_to_specific",
            "analyzed_subgroups_count",
            "reviewed_pending_independent_review",
            "superseded_by_reviewed_restructure",
            "human_approved_llm_assisted_source_review",
        )
        for path in sorted(self.directory.iterdir()):
            if not path.is_file():
                continue
            blob = path.read_text(encoding="utf-8", errors="replace").casefold()
            for needle in needles:
                with self.subTest(packet=path.name, needle=needle):
                    self.assertNotIn(needle, blob)


# ── regressione ───────────────────────────────────────────────────────────────


class TestRegression(unittest.TestCase):
    def test_the_batch_artifacts_are_unchanged(self) -> None:
        units = load_jsonl(BATCH / "proposed_profile_units.jsonl")
        self.assertEqual(len(units), 9)
        proposal = next(
            row for row in units if row["proposed_profile_unit_id"] == APPROVED_UNIT_ID
        )
        self.assertEqual(proposal["review_status"], "source_checked_review_proposal")
        self.assertFalse(proposal["human_reviewed"])

    def test_the_source_review_report_is_untouched(self) -> None:
        report = BATCH / "SOURCE_REVIEW_PMID-31358542.md"
        self.assertTrue(report.is_file())
        self.assertIn("audit_split_not_supported", report.read_text(encoding="utf-8"))

    def test_the_original_approval_packet_is_untouched(self) -> None:
        packet = load_json(
            BATCH / "annotation_packets/author_approval/AA-PMID-31358542.json"
        )
        self.assertIsNone(packet["decision"])
        self.assertIsNone(packet["decided_by"])

    def test_the_structural_audit_is_unchanged(self) -> None:
        rows = load_jsonl(REPO_ROOT / "benchmarks/mtb_evidence/v3/cohort_split_audit/audit_scope.jsonl")
        self.assertEqual(len(rows), 9)

    def test_the_statement_repository_still_has_147_statements(self) -> None:
        rows = load_jsonl(
            REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl"
        )
        self.assertEqual(len(rows), 147)

    def test_no_network_is_needed(self) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts.record_author_approval import parse_args

        args = parse_args([])
        self.assertFalse(hasattr(args, "allow_network"))


if __name__ == "__main__":
    unittest.main()
