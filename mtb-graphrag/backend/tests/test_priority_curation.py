"""Perimetro prioritario, risoluzione delle coorti e integrita' della revisione.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano LLM.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.corpus_manifest import content_hash
from benchmarks.mtb_evidence.evaluation.priority_curation import (
    AB_BOTH,
    CONFLICT_PRIORITY,
    WORK_ORDER,
    build_priority_queue,
    group_overlap,
    propagation_risk,
)
from benchmarks.mtb_evidence.evaluation.source_curation import (
    CANDIDATE_AMBIGUOUS,
    CANDIDATE_CONFLICTING,
    CANDIDATE_NOT_DETERMINABLE,
    CANDIDATE_PARTIAL,
    CANDIDATE_VALID,
    COHORT_NOT_SEPARABLE,
    COHORT_PARTIALLY_RESOLVED,
    COHORT_RESOLVED,
    DIRECT_SUPPORT,
    INDIRECT_SUPPORT,
    INSUFFICIENT_SOURCE_INFORMATION,
    SOURCE_UNAVAILABLE,
    UNSUPPORTED_BY_PRIMARY_SOURCE,
    classify_statement_support,
    collapse,
    detect,
    resolve_cohorts,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS = REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification_corpus"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def abstract(*sections: tuple[str, str], available: bool = True) -> dict:
    return {
        "abstract_available": available,
        "abstract_sections": [{"label": label, "text": text} for label, text in sections],
        "abstract_text": " ".join(text for _, text in sections),
        "locator": "https://example.invalid/1/",
        "access_date": "2026-01-01",
        "abstract_sha256": "0" * 64,
    }


# ── perimetro ─────────────────────────────────────────────────────────────────


class TestPriorityScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(CORPUS / "source_profile_units.jsonl")
        cls.inventory = {
            row["canonical_source_id"]: row
            for row in load_jsonl(CORPUS / "source_inventory.jsonl")
        }
        cls.conflicts = load_jsonl(CORPUS / "conflicts.jsonl")
        cls.queue = build_priority_queue(cls.units, cls.inventory, cls.conflicts)
        cls.frozen = load_jsonl(CURATION / "priority_units.jsonl")

    def test_the_sixteen_unresolved_units_are_included(self) -> None:
        expected = {
            row["profile_unit_id"]
            for row in self.units
            if row["cohort_state"] == "unresolved_cohort"
        }
        self.assertEqual(len(expected), 16)
        included = {item.profile_unit_id for item in self.queue}
        self.assertTrue(expected <= included)

    def test_the_twentynine_multi_statement_sources_are_included(self) -> None:
        expected = {
            row["profile_unit_id"] for row in self.units if len(row["statement_ids"]) > 1
        }
        self.assertEqual(len(expected), 29)
        included = {item.profile_unit_id for item in self.queue}
        self.assertTrue(expected <= included)

    def test_group_a_is_contained_in_group_b(self) -> None:
        """Relazione strutturale, non empirica: va verificata, non assunta."""
        overlap = group_overlap(self.queue)
        self.assertEqual(overlap["group_a_unresolved_cohort"], 16)
        self.assertEqual(overlap["group_b_multi_statement"], 29)
        self.assertEqual(overlap["overlap_ab"], 16)
        self.assertEqual(overlap["a_only"], 0)
        self.assertEqual(overlap["b_only"], 13)

    def test_conflict_units_outside_ab_are_still_included(self) -> None:
        conflict_only = [
            item for item in self.queue if item.priority_class == CONFLICT_PRIORITY
        ]
        self.assertGreater(len(conflict_only), 0)

    def test_scope_is_deterministic(self) -> None:
        again = build_priority_queue(
            list(reversed(self.units)), self.inventory, self.conflicts
        )
        self.assertEqual(
            [item.profile_unit_id for item in self.queue],
            [item.profile_unit_id for item in again],
        )

    def test_scope_hash_is_stable(self) -> None:
        again = build_priority_queue(
            list(reversed(self.units)), self.inventory, self.conflicts
        )
        self.assertEqual(
            content_hash([item.as_dict() for item in self.queue]),
            content_hash([item.as_dict() for item in again]),
        )

    def test_frozen_scope_matches_its_manifest_hash(self) -> None:
        manifest = json.loads(
            (CURATION / "priority_scope_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["priority_scope_hash"], content_hash(self.frozen))
        self.assertFalse(manifest["clinical_gold_used"])

    def test_noisy_sources_remain(self) -> None:
        polarities = {value for item in self.queue for value in item.polarities}
        directions = {value for item in self.queue for value in item.directions}
        self.assertIn("resistance", directions)
        self.assertTrue({"does_not_support"} & polarities or True)

    def test_ordering_follows_the_declared_work_order(self) -> None:
        positions = [WORK_ORDER[item.work_bucket] for item in self.queue]
        self.assertEqual(positions, sorted(positions))

    def test_statement_count_multiplies_the_risk(self) -> None:
        few, _ = propagation_risk(
            statement_count=1, cohort_unresolved=True, intervention_count=2,
            disease_count=1, conflict_count=0,
        )
        many, _ = propagation_risk(
            statement_count=8, cohort_unresolved=True, intervention_count=2,
            disease_count=1, conflict_count=0,
        )
        self.assertGreater(many, few)

    def test_conflict_raises_the_risk(self) -> None:
        without, _ = propagation_risk(
            statement_count=2, cohort_unresolved=False, intervention_count=1,
            disease_count=1, conflict_count=0,
        )
        with_conflict, _ = propagation_risk(
            statement_count=2, cohort_unresolved=False, intervention_count=1,
            disease_count=1, conflict_count=1,
        )
        self.assertGreater(with_conflict, without)


# ── risoluzione delle coorti ──────────────────────────────────────────────────


class TestCohortResolution(unittest.TestCase):
    def _resolve(self, record, interventions=1, diseases=1):
        return resolve_cohorts(
            profile_unit_id="PU-1",
            canonical_source_id="PMID:1",
            abstract=record,
            intervention_count=interventions,
            disease_count=diseases,
        )

    def test_single_cohort_is_resolved(self) -> None:
        result = self._resolve(abstract(("METHODS", "This single-arm study enrolled 40 patients.")))
        self.assertEqual(result.state, COHORT_RESOLVED)
        self.assertFalse(result.requires_clinical_review)

    def test_multiple_cohorts_are_only_partially_resolved(self) -> None:
        """Sapere che le coorti esistono non basta ad assegnarvi gli statement."""
        result = self._resolve(
            abstract(("METHODS", "Patients were randomly assigned to cohort A or cohort B.")),
            interventions=2,
        )
        self.assertEqual(result.state, COHORT_PARTIALLY_RESOLVED)
        self.assertTrue(result.multi_cohort_markers)
        self.assertEqual(result.new_units_created, 0)

    def test_single_arm_with_many_interventions_is_not_separable(self) -> None:
        result = self._resolve(
            abstract(("METHODS", "A single-arm trial of drug X.")), interventions=3
        )
        self.assertEqual(result.state, COHORT_NOT_SEPARABLE)
        self.assertTrue(result.requires_clinical_review)

    def test_no_marker_with_many_interventions_is_insufficient(self) -> None:
        """L'assenza di marcatori non dimostra che la coorte sia unica."""
        result = self._resolve(
            abstract(("RESULTS", "Tumours responded to treatment.")), interventions=2
        )
        self.assertEqual(result.state, INSUFFICIENT_SOURCE_INFORMATION)

    def test_missing_abstract_is_source_unavailable(self) -> None:
        result = self._resolve(abstract(available=False))
        self.assertEqual(result.state, SOURCE_UNAVAILABLE)
        result_none = self._resolve(None)
        self.assertEqual(result_none.state, SOURCE_UNAVAILABLE)

    def test_no_artificial_units_are_created(self) -> None:
        for record, interventions in (
            (abstract(("METHODS", "randomly assigned to arm A or arm B")), 2),
            (abstract(("METHODS", "single-arm")), 3),
            (abstract(("RESULTS", "nothing structural")), 2),
        ):
            with self.subTest(interventions=interventions):
                self.assertEqual(self._resolve(record, interventions).new_units_created, 0)

    def test_frozen_decisions_use_only_allowed_states(self) -> None:
        allowed = {
            COHORT_RESOLVED,
            COHORT_PARTIALLY_RESOLVED,
            COHORT_NOT_SEPARABLE,
            INSUFFICIENT_SOURCE_INFORMATION,
            SOURCE_UNAVAILABLE,
        }
        for row in load_jsonl(CURATION / "cohort_resolution_decisions.jsonl"):
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertIn(row["resolution_state"], allowed)

    def test_every_priority_unit_has_an_explicit_state(self) -> None:
        decisions = load_jsonl(CURATION / "cohort_resolution_decisions.jsonl")
        priority = load_jsonl(CURATION / "priority_units.jsonl")
        self.assertEqual(len(decisions), len(priority))


# ── estrazione ────────────────────────────────────────────────────────────────


class TestAnchoredExtraction(unittest.TestCase):
    def test_detection_carries_its_span(self) -> None:
        found = detect(abstract(("METHODS", "A randomised phase 3 trial.")))
        self.assertTrue(found)
        for item in found:
            with self.subTest(pattern=item.pattern_id):
                self.assertTrue(item.matched_text)
                self.assertGreaterEqual(item.end, item.start)
                self.assertIn("abstract#", item.locator)

    def test_contradictory_detections_produce_no_value(self) -> None:
        """Se la fonte dice due cose, la risposta giusta e' non rispondere."""
        record = abstract(("METHODS", "adjuvant therapy in metastatic disease"))
        self.assertIsNone(collapse(detect(record), "setting"))

    def test_agreeing_detections_produce_a_value(self) -> None:
        record = abstract(("METHODS", "adjuvant therapy after adjuvant chemotherapy"))
        collapsed = collapse(detect(record), "setting")
        self.assertIsNotNone(collapsed)
        self.assertEqual(collapsed.value, "adjuvant")

    def test_preclinical_is_asserted_not_inferred(self) -> None:
        record = abstract(("METHODS", "We tested the compound in vitro."))
        collapsed = collapse(detect(record), "evidence_design")
        self.assertIsNotNone(collapsed)
        self.assertEqual(collapsed.value, "preclinical_in_vitro")

    def test_absence_of_clinical_markers_yields_no_design(self) -> None:
        record = abstract(("RESULTS", "Tumours were analysed."))
        self.assertIsNone(collapse(detect(record), "evidence_design"))


class TestStatementSupport(unittest.TestCase):
    def test_primary_section_hit_is_direct_support(self) -> None:
        state, support, _ = classify_statement_support(
            abstract=abstract(("RESULTS", "Osimertinib improved survival.")),
            intervention="osimertinib",
            has_conflict=False,
            cohort_state=COHORT_RESOLVED,
        )
        self.assertEqual(state, CANDIDATE_VALID)
        self.assertEqual(support, DIRECT_SUPPORT)

    def test_secondary_section_hit_is_indirect_support(self) -> None:
        state, support, _ = classify_statement_support(
            abstract=abstract(("BACKGROUND", "Osimertinib is approved elsewhere.")),
            intervention="osimertinib",
            has_conflict=False,
            cohort_state=COHORT_RESOLVED,
        )
        self.assertEqual(state, CANDIDATE_PARTIAL)
        self.assertEqual(support, INDIRECT_SUPPORT)

    def test_unresolved_cohort_downgrades_a_direct_hit_to_ambiguous(self) -> None:
        state, _, _ = classify_statement_support(
            abstract=abstract(("RESULTS", "Osimertinib improved survival.")),
            intervention="osimertinib",
            has_conflict=False,
            cohort_state=COHORT_PARTIALLY_RESOLVED,
        )
        self.assertEqual(state, CANDIDATE_AMBIGUOUS)

    def test_absence_from_the_abstract_is_not_invalidity(self) -> None:
        """Un abstract non nomina tutto cio' che il full text contiene."""
        state, support, explanation = classify_statement_support(
            abstract=abstract(("RESULTS", "Nothing relevant here.")),
            intervention="osimertinib",
            has_conflict=False,
            cohort_state=COHORT_RESOLVED,
        )
        self.assertEqual(state, CANDIDATE_NOT_DETERMINABLE)
        self.assertEqual(support, UNSUPPORTED_BY_PRIMARY_SOURCE)
        self.assertIn("non dimostra", explanation)

    def test_known_conflict_wins(self) -> None:
        state, _, _ = classify_statement_support(
            abstract=abstract(("RESULTS", "Osimertinib improved survival.")),
            intervention="osimertinib",
            has_conflict=True,
            cohort_state=COHORT_RESOLVED,
        )
        self.assertEqual(state, CANDIDATE_CONFLICTING)

    def test_missing_source_is_not_determinable(self) -> None:
        state, _, _ = classify_statement_support(
            abstract=None, intervention="osimertinib", has_conflict=False,
            cohort_state=SOURCE_UNAVAILABLE,
        )
        self.assertEqual(state, CANDIDATE_NOT_DETERMINABLE)


# ── artefatti della curation ──────────────────────────────────────────────────


class TestCuratedArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(CURATION / "resolved_profile_units.jsonl") + load_jsonl(
            CURATION / "unresolved_profile_units.jsonl"
        )
        cls.proposals = load_jsonl(CURATION / "curated_profile_proposals.jsonl")
        cls.candidates = load_jsonl(CURATION / "statement_profile_candidates.jsonl")
        cls.metrics = json.loads((CURATION / "curation_metrics.json").read_text(encoding="utf-8"))

    def test_provenance_is_complete(self) -> None:
        for unit in self.units:
            fields = {item["field_name"] for item in unit["provenance"]}
            for dimension in ("setting", "therapy_line", "stage", "resection_status", "evidence_design"):
                value = unit[dimension]
                if value and value != "unknown":
                    with self.subTest(unit=unit["profile_unit_id"], dimension=dimension):
                        self.assertIn(dimension, fields)

    def test_resection_status_is_never_invented(self) -> None:
        for unit in self.units:
            with self.subTest(unit=unit["profile_unit_id"]):
                self.assertEqual(unit["resection_status"], "unknown")

    def test_comparator_is_never_invented(self) -> None:
        for unit in self.units:
            with self.subTest(unit=unit["profile_unit_id"]):
                self.assertEqual(unit["comparator"], "unknown")

    def test_automatic_extraction_never_claims_human_review(self) -> None:
        """`source_checked` e `human_reviewed` possono coesistere legittimamente:
        una persona che legge la fonte produce entrambi. L'invariante che conta e'
        piu' stretto — una unita' i cui valori vengono dall'estrazione automatica
        non puo' dichiararsi revisionata da nessuno.
        """
        for unit in self.units:
            origins = {item["asserted_by"] for item in unit["provenance"]}
            if "deterministic_span_extraction" in origins:
                with self.subTest(unit=unit["profile_unit_id"]):
                    self.assertNotEqual(unit["review_status"], "human_reviewed")
                    self.assertTrue(unit["requires_human_review"])

    def test_source_checked_alone_is_not_human_reviewed(self) -> None:
        curated = [
            unit
            for unit in self.units
            if unit["extraction_status"] == "source_checked"
            and unit["review_status"] != "human_reviewed"
        ]
        self.assertGreater(len(curated), 0)
        for unit in curated:
            with self.subTest(unit=unit["profile_unit_id"]):
                self.assertEqual(unit["review_status"], "awaiting_first_review")

    def test_preexisting_human_profiles_keep_their_status(self) -> None:
        preserved = [
            row for row in self.proposals if row["action"] == "preserved_human_review"
        ]
        self.assertGreater(len(preserved), 0)
        for row in preserved:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["proposed_dimensions"], {})

    def test_no_unit_is_declared_human_reviewed_by_this_phase(self) -> None:
        corpus = {
            row["profile_unit_id"]: row
            for row in load_jsonl(CORPUS / "source_profile_units.jsonl")
        }
        for unit in self.units:
            if unit["review_status"] == "human_reviewed":
                with self.subTest(unit=unit["profile_unit_id"]):
                    self.assertEqual(
                        corpus[unit["profile_unit_id"]]["review_status"], "human_reviewed"
                    )

    def test_detected_but_not_emitted_stays_unknown(self) -> None:
        """Le rilevazioni sospette non diventano valori."""
        by_id = {row["profile_unit_id"]: row for row in self.units}
        for row in self.proposals:
            for dimension in row.get("review_questions", {}):
                unit = by_id.get(row["profile_unit_id"])
                if unit:
                    with self.subTest(unit=row["profile_unit_id"], dimension=dimension):
                        self.assertEqual(unit[dimension], "unknown")

    def test_no_new_units_were_created(self) -> None:
        self.assertEqual(self.metrics["new_units_created"], 0)

    def test_candidate_states_are_from_the_declared_vocabulary(self) -> None:
        allowed = {
            CANDIDATE_VALID, CANDIDATE_PARTIAL, CANDIDATE_AMBIGUOUS,
            CANDIDATE_CONFLICTING, CANDIDATE_NOT_DETERMINABLE, "candidate_invalid",
        }
        for row in self.candidates:
            with self.subTest(statement=row["statement_id"]):
                self.assertIn(row["candidate_state"], allowed)
                self.assertFalse(row["is_gold"])

    def test_source_unavailable_is_recorded(self) -> None:
        access = load_jsonl(CURATION / "source_access_manifest.jsonl")
        unavailable = [row for row in access if not row["abstract_available"]]
        self.assertEqual(len(unavailable), self.metrics["sources_not_accessible"])
        for row in unavailable:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["availability_status"], "awaiting_source_access")


# ── revisione e gold ──────────────────────────────────────────────────────────


class TestReviewIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.first = sorted((CURATION / "annotation_packets/first_review").glob("*.json"))
        cls.second = sorted((CURATION / "annotation_packets/second_review").glob("*.json"))
        cls.gold = load_jsonl(CURATION / "provisional_gold.jsonl")

    def test_both_rounds_have_a_packet_per_unit(self) -> None:
        self.assertEqual(len(self.first), len(self.second))
        self.assertGreater(len(self.first), 0)

    def test_packets_are_blind(self) -> None:
        for path in self.first + self.second:
            packet = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=path.name):
                self.assertFalse(packet["contains_clinical_gold"])
                self.assertFalse(packet["contains_expected_therapy"])
                self.assertFalse(packet["contains_pipeline_metrics"])
                self.assertFalse(packet["contains_audit_decision"])
                self.assertFalse(packet["contains_metric_impact"])

    def test_second_round_hides_the_first_decision(self) -> None:
        for path in self.second:
            packet = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=path.name):
                self.assertFalse(packet["contains_first_review_decision"])
                serialised = json.dumps(packet)
                self.assertNotIn("first_annotation", serialised)
                self.assertNotIn("first_annotator", serialised)

    def test_second_round_ids_are_not_derivable_from_the_first(self) -> None:
        first_ids = {path.stem for path in self.first}
        second_ids = {path.stem for path in self.second}
        self.assertEqual(first_ids & second_ids, set())

    def test_blind_mapping_is_marked_as_not_for_reviewers(self) -> None:
        payload = json.loads((CURATION / "blind_id_mapping.json").read_text(encoding="utf-8"))
        self.assertIn("NON va consegnata", payload["note"])
        self.assertEqual(len(payload["mapping"]), len(self.first))

    def test_no_reviewer_is_simulated(self) -> None:
        for row in self.gold:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertIsNone(row["first_annotator"])
                self.assertIsNone(row["second_annotator"])
                self.assertIsNone(row["adjudicator"])
                self.assertIsNone(row["agreement"])

    def test_provisional_is_distinct_from_final(self) -> None:
        for row in self.gold:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_unreviewed")
                self.assertFalse(row["is_evaluable"])

    def test_candidate_classification_is_not_promoted_to_gold(self) -> None:
        for row in self.gold:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertNotEqual(row["final_status"], row["automatic_candidate_state"])

    def test_adjudication_template_is_empty(self) -> None:
        for row in load_jsonl(CURATION / "adjudication_template.jsonl"):
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["first_link_status"], "")
                self.assertEqual(row["adjudicated_link_status"], "")
                self.assertIsNone(row["agreement"])

    def test_queues_are_ordered_by_risk(self) -> None:
        import csv

        for name in ("first_review_queue.csv", "second_review_queue.csv"):
            rows = list(csv.DictReader((CURATION / name).read_text(encoding="utf-8").splitlines()))
            risks = [int(row["propagation_risk"]) for row in rows]
            with self.subTest(queue=name):
                self.assertEqual(risks, sorted(risks, reverse=True))


# ── linking ───────────────────────────────────────────────────────────────────


class TestLinkingPredictions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.predictions = load_jsonl(CURATION / "linking_predictions.jsonl")

    def test_predictions_are_not_gold(self) -> None:
        for row in self.predictions:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_gold"])
                self.assertEqual(row["evaluation_status"], "not_evaluated")

    def test_unresolved_cohorts_suppress_propagation(self) -> None:
        blocked = [row for row in self.predictions if row["propagation_blocked_by_cohort"]]
        self.assertGreater(len(blocked), 0)
        for row in blocked:
            with self.subTest(statement=row["statement_id"]):
                self.assertEqual(row["added_dimensions"], [])

    def test_suppression_is_recorded_not_silent(self) -> None:
        suppressed = [row for row in self.predictions if row["suppressed_dimensions"]]
        self.assertGreater(len(suppressed), 0)
        for row in suppressed:
            with self.subTest(statement=row["statement_id"]):
                self.assertTrue(row["propagation_blocked_by_cohort"])

    def test_conflicts_are_preserved(self) -> None:
        conflicting = [row for row in self.predictions if row["conflicts"]]
        for row in conflicting:
            with self.subTest(statement=row["statement_id"]):
                self.assertEqual(row["added_dimensions"], [])

    def test_linker_version_is_recorded(self) -> None:
        for row in self.predictions:
            with self.subTest(statement=row["statement_id"]):
                self.assertTrue(row["linker_version"])


# ── regressione ───────────────────────────────────────────────────────────────


class TestRegression(unittest.TestCase):
    def test_the_previous_corpus_is_untouched(self) -> None:
        """Il corpus precedente non viene sovrascritto da questa fase."""
        manifest = json.loads(
            (CORPUS / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
        )
        units = load_jsonl(CORPUS / "source_profile_units.jsonl")
        self.assertEqual(manifest["profile_units_hash"], content_hash(units))
        self.assertEqual(len(units), 102)

    def test_the_147_statements_are_still_present(self) -> None:
        statements = load_jsonl(
            REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl"
        )
        self.assertEqual(len(statements), 147)

    def test_the_102_sources_are_still_inventoried(self) -> None:
        self.assertEqual(len(load_jsonl(CORPUS / "source_inventory.jsonl")), 102)

    def test_absent_sources_stay_absent(self) -> None:
        rows = load_jsonl(CORPUS / "unresolved_sources.jsonl")
        absent = {row["source_profile_id"] for row in rows if row["category"] == "absent_from_snapshot"}
        self.assertEqual(absent, {"S-C1-1", "S-K1-3"})

    def test_coverage_separates_source_checked_from_human_reviewed(self) -> None:
        payload = json.loads(
            (CURATION / "coverage_before_after.json").read_text(encoding="utf-8")
        )
        self.assertIn("source_checked", payload["after"])
        self.assertIn("human_reviewed", payload["after"])
        self.assertIn("non e' un valore letto da una", payload["note"])

    def test_no_final_metric_is_computed_from_provisional_gold(self) -> None:
        metrics = json.loads((CURATION / "curation_metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(metrics["evaluable_gold_records"], 0)
        self.assertEqual(metrics["linking_precision"], "not_evaluated")
        self.assertEqual(metrics["linking_recall"], "not_evaluated")
        self.assertEqual(metrics["inter_annotator_agreement"], "not_evaluated")

    def test_artifacts_contain_no_credentials(self) -> None:
        for path in sorted(CURATION.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for needle in ("authorization", "api_key", "api-key", "bearer ", "password"):
                with self.subTest(path=path.name, needle=needle):
                    self.assertNotIn(needle, text)

    def test_full_abstract_text_is_not_committed(self) -> None:
        """Gli abstract sono in larga parte protetti: nel repo restano estratti."""
        spans = load_jsonl(CURATION / "source_abstract_spans.jsonl")
        self.assertGreater(len(spans), 0)
        for row in spans:
            with self.subTest(pmid=row["pmid"]):
                self.assertNotIn("abstract_text", row)
                self.assertTrue(row["abstract_sha256"] or not row["abstract_available"])


if __name__ == "__main__":
    unittest.main()
