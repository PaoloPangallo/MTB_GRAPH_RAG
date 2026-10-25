"""Perimetro dell'audit, classificazione strutturale, guardie e blinding.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano LLM.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.corpus_manifest import content_hash
from backend.pipeline.evidence.propagation_guards import (
    ALL_RULE_IDS,
    GUARD_V1_RULE_IDS,
    AbsenceInferenceError,
    ClinicalToPreclinicalError,
    CrossArmError,
    CrossCohortError,
    EvidenceStrengthError,
    PreclinicalToClinicalError,
    PropagationError,
    ProvenanceError,
    SubgroupToPopulationError,
    run_guards,
)
from benchmarks.mtb_evidence.evaluation.cohort_split_audit import (
    CLINICAL_PRECLINICAL_SPLIT,
    INSUFFICIENT_SOURCE_INFORMATION,
    MULTI_ARM_CLINICAL_SPLIT,
    MULTI_COHORT_CLINICAL_SPLIT,
    MULTI_PRECLINICAL_SPLIT,
    SINGLE_PROPAGATABLE,
    SOURCE_UNAVAILABLE,
    SPLIT_LIKELIHOODS,
    SPLIT_NOT_INDICATED,
    SPLIT_REQUIRED,
    STRUCTURE_STATES,
    assess_split,
    classify_structure,
    detect_signals,
    screen_source,
    structure_flags,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_audit_scope import (
    ALREADY_REVIEWED,
    EXPECTED_UNITS,
    ScopeMismatch,
    check_scope,
    derive_scope,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT = REPO_ROOT / "benchmarks/mtb_evidence/v3/cohort_split_audit"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"
CORPUS = REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification_corpus"
REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/first_review"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def text(*sections: tuple[str, str]) -> dict:
    return {
        "abstract_available": True,
        "abstract_sections": [{"label": label, "text": body} for label, body in sections],
    }


def unit(**overrides) -> dict:
    payload = {"profile_unit_id": "PU-x", "canonical_source_id": "PMID:1", "unit_type": "unspecified"}
    payload.update(overrides)
    return payload


# ── perimetro ─────────────────────────────────────────────────────────────────


class TestAuditScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.resolutions = load_jsonl(CURATION / "cohort_resolution_decisions.jsonl")
        cls.scope = load_jsonl(AUDIT / "audit_scope.jsonl")
        cls.payload = json.loads((AUDIT / "audit_scope.json").read_text(encoding="utf-8"))

    def test_scope_matches_the_declared_set(self) -> None:
        derived = derive_scope(self.resolutions)
        self.assertEqual(sorted(derived), sorted(EXPECTED_UNITS))

    def test_the_already_reviewed_unit_is_excluded(self) -> None:
        ids = {row["profile_unit_id"] for row in self.scope}
        self.assertNotIn(ALREADY_REVIEWED, ids)

    def test_scope_size_is_nine_not_eight(self) -> None:
        """La specifica prevedeva 8; il criterio ne seleziona 9.

        PMID 22277784 non era `cohort_partially_resolved` ma
        `insufficient_source_information`, quindi non c'era nulla da sottrarre.
        """
        self.assertEqual(len(self.scope), 9)
        self.assertEqual(self.payload["specification_expected_count"], 8)
        self.assertIn("insufficient_source_information", self.payload["specification_discrepancy"])

    def test_the_reviewed_source_was_in_the_weaker_bucket(self) -> None:
        row = next(
            item
            for item in self.resolutions
            if item["profile_unit_id"] == ALREADY_REVIEWED
        )
        self.assertEqual(row["resolution_state"], "insufficient_source_information")

    def test_check_scope_rejects_a_missing_unit(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_scope(list(EXPECTED_UNITS)[:-1])

    def test_check_scope_rejects_an_extra_unit(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_scope([*EXPECTED_UNITS, "PU-PMID-99999999-cohort-1"])

    def test_check_scope_rejects_the_reviewed_unit(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_scope([*EXPECTED_UNITS, ALREADY_REVIEWED])

    def test_scope_hash_is_stable(self) -> None:
        self.assertEqual(self.payload["audit_scope_hash"], content_hash(self.scope))

    def test_scope_is_order_invariant(self) -> None:
        forward = derive_scope(self.resolutions)
        backward = derive_scope(list(reversed(self.resolutions)))
        self.assertEqual(forward, backward)

    def test_no_clinical_gold_is_used(self) -> None:
        manifest = json.loads((AUDIT / "audit_scope_manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["clinical_gold_used"])


# ── classificazione ───────────────────────────────────────────────────────────


class TestStructureClassification(unittest.TestCase):
    def _classify(self, record, unit_payload=None, full_text=True):
        assessment = assess_split(record)
        payload = unit_payload or {"abstract_available": bool(record)}
        flags = structure_flags(assessment, payload)
        return classify_structure(assessment, payload, flags, full_text_consulted=full_text)

    def test_single_propagatable_requires_full_text(self) -> None:
        record = text(("METHODS", "We treated patients with drug X."))
        state, _ = self._classify(record, full_text=True)
        self.assertEqual(state, SINGLE_PROPAGATABLE)

    def test_abstract_only_negative_is_insufficient_not_single(self) -> None:
        """L'assenza di segnali in un abstract non conclude «unita' singola»."""
        record = text(("METHODS", "We treated patients with drug X."))
        state, reason = self._classify(record, full_text=False)
        self.assertEqual(state, INSUFFICIENT_SOURCE_INFORMATION)
        self.assertIn("quattro unita'", reason)

    def test_clinical_plus_preclinical_requires_a_split(self) -> None:
        record = text(("RESULTS", "In patients and in Ba/F3 cell lines in vitro."))
        state, _ = self._classify(record)
        self.assertEqual(state, CLINICAL_PRECLINICAL_SPLIT)

    def test_multiple_arms_are_detected(self) -> None:
        record = text(("METHODS", "Patients were randomly assigned to arm A or arm B."))
        state, _ = self._classify(record)
        self.assertEqual(state, MULTI_ARM_CLINICAL_SPLIT)

    def test_multiple_cohorts_are_detected(self) -> None:
        record = text(("METHODS", "Patients enrolled in two cohorts were analysed."))
        state, _ = self._classify(record)
        self.assertEqual(state, MULTI_COHORT_CLINICAL_SPLIT)

    def test_multiple_preclinical_models_are_detected(self) -> None:
        record = text(("METHODS", "Cell lines in vitro and xenograft models in vivo."))
        state, _ = self._classify(record)
        self.assertEqual(state, MULTI_PRECLINICAL_SPLIT)

    def test_missing_source_is_unavailable(self) -> None:
        state, _ = self._classify(None, {"abstract_available": False}, full_text=False)
        self.assertEqual(state, SOURCE_UNAVAILABLE)

    def test_every_state_is_from_the_declared_vocabulary(self) -> None:
        for row in load_jsonl(AUDIT / "source_structure_classification.jsonl"):
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertIn(row["structure_state"], STRUCTURE_STATES)
                self.assertIn(row["split_likelihood"], SPLIT_LIKELIHOODS)

    def test_every_scoped_unit_is_classified(self) -> None:
        scope = {row["profile_unit_id"] for row in load_jsonl(AUDIT / "audit_scope.jsonl")}
        classified = {
            row["profile_unit_id"]
            for row in load_jsonl(AUDIT / "source_structure_classification.jsonl")
        }
        self.assertEqual(scope, classified)

    def test_signals_are_recorded_with_spans(self) -> None:
        for row in load_jsonl(AUDIT / "detector_signals.jsonl"):
            for signal in row["signals"]:
                with self.subTest(unit=row["profile_unit_id"], signal=signal["signal_id"]):
                    self.assertTrue(signal["matched_text"])
                    self.assertGreaterEqual(signal["char_end"], signal["char_start"])


# ── proposte ──────────────────────────────────────────────────────────────────


class TestSplitProposals(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proposals = load_jsonl(AUDIT / "proposed_profile_units.jsonl")
        cls.summary = load_jsonl(AUDIT / "split_proposals.jsonl")
        cls.classifications = {
            row["profile_unit_id"]: row
            for row in load_jsonl(AUDIT / "source_structure_classification.jsonl")
        }

    def test_no_unit_is_invented(self) -> None:
        """Le proposte esistono solo dove la classificazione le sostiene."""
        for row in self.proposals:
            parent = row["parent_profile_unit_id"]
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertEqual(
                    self.classifications[parent]["structure_state"],
                    CLINICAL_PRECLINICAL_SPLIT,
                )

    def test_parent_is_preserved(self) -> None:
        parents = {row["parent_profile_unit_id"] for row in self.proposals}
        existing = {row["profile_unit_id"] for row in load_jsonl(AUDIT / "audit_scope.jsonl")}
        self.assertTrue(parents <= existing)

    def test_no_proposal_is_propagatable(self) -> None:
        for row in self.proposals:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertFalse(row["is_propagatable"])
                self.assertFalse(row["is_evaluable"])

    def test_no_proposal_claims_human_review(self) -> None:
        for row in self.proposals:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertFalse(row["human_reviewed"])
                self.assertEqual(row["review_status"], "awaiting_first_review")
                self.assertNotIn(
                    row["cohort_state"],
                    {"superseded_by_reviewed_split", "single_cohort", "resolved_cohort"},
                )

    def test_source_checked_is_distinct_from_human_reviewed(self) -> None:
        for row in self.proposals:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                if row["source_checked"]:
                    self.assertNotEqual(row["review_status"], "human_reviewed")

    def test_provenance_is_complete(self) -> None:
        for row in self.proposals:
            fields = {item["field_name"] for item in row["provenance"]}
            for dimension in row["known_dimensions"]:
                with self.subTest(unit=row["proposed_profile_unit_id"], dimension=dimension):
                    self.assertIn(dimension, fields)

    def test_unknown_is_distinct_from_not_applicable(self) -> None:
        for row in self.proposals:
            for dimension, decision in row["field_decisions"].items():
                if decision == "not_applicable":
                    with self.subTest(unit=row["proposed_profile_unit_id"], dimension=dimension):
                        self.assertIn(dimension, row["not_applicable_dimensions"])
                        self.assertNotIn(dimension, row["known_dimensions"])

    def test_clinical_fields_stay_empty(self) -> None:
        """L'audit propone struttura, non contenuto."""
        for row in self.proposals:
            for dimension in ("setting", "population", "regimen"):
                with self.subTest(unit=row["proposed_profile_unit_id"], dimension=dimension):
                    self.assertIn(row[dimension], ("unknown", "not_applicable"))

    def test_statements_map_to_specific_units(self) -> None:
        mappings = load_jsonl(AUDIT / "statement_unit_mapping_proposals.jsonl")
        self.assertGreater(len(mappings), 0)
        for row in mappings:
            with self.subTest(statement=row["statement_id"]):
                self.assertTrue(row["parent_profile_unit_id"])
                self.assertFalse(row["is_gold"])
                self.assertFalse(row["is_evaluable"])

    def test_not_separable_is_distinct_from_unknown(self) -> None:
        mappings = load_jsonl(AUDIT / "statement_unit_mapping_proposals.jsonl")
        ambiguous = [row for row in mappings if row["candidate_link_status"] == "candidate_ambiguous"]
        for row in ambiguous:
            with self.subTest(statement=row["statement_id"]):
                self.assertTrue(row["not_separable_dimensions"])

    def test_no_statement_is_declared_invalid_from_absence(self) -> None:
        for row in load_jsonl(AUDIT / "statement_unit_mapping_proposals.jsonl"):
            with self.subTest(statement=row["statement_id"]):
                self.assertNotEqual(row["candidate_link_status"], "candidate_invalid")


# ── guardie ───────────────────────────────────────────────────────────────────


class TestPropagationGuards(unittest.TestCase):
    def _rules(self, violations) -> set[str]:
        return {item.rule_id for item in violations}

    def test_clinical_population_does_not_reach_a_model(self) -> None:
        violations = run_guards(
            units=[unit(unit_type="preclinical_in_vitro", population="18 patients")]
        )
        self.assertIn("clinical_population_to_model", self._rules(violations))
        self.assertIs(violations[0].error_type, ClinicalToPreclinicalError)

    def test_therapy_line_does_not_reach_a_model(self) -> None:
        violations = run_guards(
            units=[unit(unit_type="preclinical_in_vitro", therapy_line="second line")]
        )
        self.assertIn("clinical_dimensions_to_model", self._rules(violations))

    def test_stage_does_not_reach_a_model(self) -> None:
        violations = run_guards(units=[unit(unit_type="preclinical_in_vitro", stage="stage IV")])
        self.assertIn("clinical_dimensions_to_model", self._rules(violations))

    def test_model_comparator_does_not_reach_a_cohort(self) -> None:
        violations = run_guards(
            units=[unit(unit_type="clinical_observational_cohort", comparator="parental Ba/F3 cells")]
        )
        self.assertIn("model_comparator_to_patients", self._rules(violations))
        self.assertIs(violations[0].error_type, PreclinicalToClinicalError)

    def test_preclinical_setting_does_not_reach_patients(self) -> None:
        violations = run_guards(
            units=[unit(unit_type="clinical_observational_cohort", setting="preclinical modelling")]
        )
        self.assertIn("preclinical_setting_to_patients", self._rules(violations))

    def test_cohort_properties_do_not_cross_cohorts(self) -> None:
        shared = {"population": "P", "setting": "S", "therapy_line": "L"}
        violations = run_guards(
            units=[
                unit(profile_unit_id="A", cohort_id="c1", unit_type="clinical_trial_arm", **shared),
                unit(profile_unit_id="B", cohort_id="c2", unit_type="clinical_trial_arm", **shared),
            ]
        )
        self.assertIn("cross_cohort_identity", self._rules(violations))
        self.assertTrue(any(v.error_type is CrossCohortError for v in violations))

    def test_intervention_does_not_cross_arms(self) -> None:
        violations = run_guards(
            units=[
                unit(profile_unit_id="A", cohort_id="c1", unit_type="clinical_trial_arm", intervention=["drugX"]),
                unit(profile_unit_id="B", cohort_id="c2", unit_type="clinical_trial_arm", intervention=["drugX"]),
            ]
        )
        self.assertIn("cross_arm_intervention", self._rules(violations))
        self.assertTrue(any(v.error_type is CrossArmError for v in violations))

    def test_subgroup_does_not_become_the_population(self) -> None:
        violations = run_guards(
            units=[
                unit(
                    unit_type="clinical_observational_cohort",
                    cohort_label="EGFR subgroup",
                    population="all enrolled participants",
                )
            ]
        )
        self.assertIn("subgroup_to_population", self._rules(violations))
        self.assertTrue(any(v.error_type is SubgroupToPopulationError for v in violations))

    def test_relative_resistance_is_distinct_from_complete(self) -> None:
        violations = run_guards(
            decisions=[
                {
                    "statement_id": "S",
                    "resistance_qualifier": "complete_resistance",
                    "rationale": "the drug retains partial activity at higher doses",
                }
            ]
        )
        self.assertIn("relative_versus_complete_resistance", self._rules(violations))
        self.assertTrue(any(v.error_type is EvidenceStrengthError for v in violations))

    def test_in_vitro_sensitivity_is_not_clinical_benefit(self) -> None:
        violations = run_guards(
            decisions=[
                {
                    "statement_id": "S",
                    "clinical_or_preclinical": "preclinical",
                    "clinical_response_observed": True,
                }
            ]
        )
        self.assertIn("in_vitro_to_clinical_benefit", self._rules(violations))

    def test_absence_in_text_is_not_evidence_of_absence(self) -> None:
        violations = run_guards(
            decisions=[
                {
                    "statement_id": "S",
                    "candidate_link_status": "candidate_invalid",
                    "rationale": "il farmaco non compare nell'abstract",
                }
            ]
        )
        self.assertIn("absence_is_not_evidence", self._rules(violations))
        self.assertTrue(any(v.error_type is AbsenceInferenceError for v in violations))

    def test_mapping_without_provenance_is_rejected(self) -> None:
        violations = run_guards(
            mappings=[{"source_term": "CH5424802", "mapped_term": "alectinib"}]
        )
        self.assertIn("mapping_needs_provenance", self._rules(violations))
        self.assertTrue(any(v.error_type is ProvenanceError for v in violations))

    def test_sentinel_values_do_not_trigger_negative_rules(self) -> None:
        """`unknown` e' truthy ma non e' un valore: non deve accendere le regole."""
        violations = run_guards(
            units=[
                unit(
                    unit_type="clinical_observational_cohort",
                    evidence_design="case report",
                    population="unknown",
                )
            ]
        )
        self.assertEqual(violations, [])

    def test_every_violation_carries_a_typed_error(self) -> None:
        violations = run_guards(
            units=[unit(unit_type="preclinical_in_vitro", population="12 patients")]
        )
        for item in violations:
            with self.subTest(rule=item.rule_id):
                self.assertTrue(issubclass(item.error_type, PropagationError))
                with self.assertRaises(PropagationError):
                    item.raise_it()

    def test_current_artifacts_have_no_violations(self) -> None:
        rows = load_jsonl(AUDIT / "propagation_guard_results.jsonl")
        self.assertEqual(rows, [])

    def test_all_declared_rules_exist(self) -> None:
        """Ogni regola citata dall'audit esiste ancora.

        L'artefatto elenca le dodici regole che esistevano quando e' stato
        generato. Confrontarlo con l'insieme corrente lo farebbe fallire ogni
        volta che una regola viene aggiunta, che non e' cio' che il controllo
        vuole dire: vuole dire che il summary non e' obsoleto, cioe' che nessuna
        regola che cita e' sparita.
        """
        summary = json.loads(
            (AUDIT / "propagation_guard_summary.json").read_text(encoding="utf-8")
        )
        declared = sorted(summary["rules_available"])
        self.assertEqual(declared, sorted(GUARD_V1_RULE_IDS))
        self.assertTrue(set(declared) <= set(ALL_RULE_IDS))


# ── rilevatore ────────────────────────────────────────────────────────────────


class TestDetector(unittest.TestCase):
    def test_multi_statement_divergence_is_still_detectable(self) -> None:
        record = text(("METHODS", "Patients were randomly assigned to arm A or arm B."))
        self.assertEqual(assess_split(record).likelihood, "split_likely")

    def test_single_statement_multi_cohort_is_detectable_from_the_source(self) -> None:
        """Il rilevatore nuovo non dipende dal numero di statement."""
        record = text(("METHODS", "Two cohorts of patients were enrolled."))
        assessment = assess_split(record)
        self.assertIn(assessment.likelihood, ("split_likely", "split_required"))
        screened = screen_source({"statement_ids": ["only-one"]}, record)
        self.assertTrue(screened["is_single_statement"])
        self.assertNotEqual(screened["split_likelihood"], SPLIT_NOT_INDICATED)

    def test_signal_evidence_is_preserved(self) -> None:
        record = text(("RESULTS", "Ba/F3 cell lines were tested in vitro."))
        assessment = assess_split(record)
        self.assertTrue(assessment.signals)
        for signal in assessment.signals:
            with self.subTest(signal=signal.signal_id):
                self.assertTrue(signal.matched_text)

    def test_split_likelihood_is_deterministic(self) -> None:
        record = text(("RESULTS", "Patients and Ba/F3 cell lines in vitro."))
        self.assertEqual(assess_split(record).likelihood, assess_split(record).likelihood)
        self.assertEqual(assess_split(record).likelihood, SPLIT_REQUIRED)

    def test_title_alone_is_not_enough(self) -> None:
        record = {"abstract_available": True, "abstract_sections": [{"label": "TITLE", "text": ""}]}
        self.assertEqual(assess_split(record).likelihood, "insufficient_information")

    def test_no_llm_is_required(self) -> None:
        import benchmarks.mtb_evidence.evaluation.cohort_split_audit as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        for forbidden in ("openai", "ollama", "llm(", "chat_completion"):
            with self.subTest(token=forbidden):
                self.assertNotIn(forbidden, source.casefold())

    def test_detector_audit_records_the_demonstrated_failure(self) -> None:
        audit = json.loads((AUDIT / "detector_audit.json").read_text(encoding="utf-8"))
        failure = audit["production_detector"]["demonstrated_failure"]
        self.assertEqual(failure["profile_unit_id"], "PU-PMID-22277784-cohort-1")
        self.assertEqual(failure["statement_count"], 10)
        self.assertEqual(failure["classified_as"], "insufficient_source_information")

    def test_proposed_detector_is_not_promoted(self) -> None:
        audit = json.loads((AUDIT / "detector_audit.json").read_text(encoding="utf-8"))
        self.assertFalse(audit["proposed_detector"]["promoted_to_production"])
        self.assertFalse(audit["proposed_detector"]["requires_llm"])
        self.assertTrue(audit["proposed_detector"]["independent_of_statement_count"])


class TestScreening(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(AUDIT / "single_statement_split_screen.jsonl")
        cls.summary = json.loads(
            (AUDIT / "single_statement_screen_summary.json").read_text(encoding="utf-8")
        )

    def test_all_sources_are_screened(self) -> None:
        self.assertEqual(len(self.rows), 102)
        self.assertEqual(self.summary["sources_screened"], 102)

    def test_single_statement_exposure_is_quantified(self) -> None:
        self.assertGreater(self.summary["single_statement_sources"], 0)
        self.assertIn("residual_split_risk_rate", self.summary)

    def test_abstract_only_negatives_are_marked_weak(self) -> None:
        """Un negativo ricavato dal solo abstract non e' un negativo forte."""
        for row in self.rows:
            if row["split_likelihood"] == SPLIT_NOT_INDICATED:
                with self.subTest(unit=row["profile_unit_id"]):
                    self.assertTrue(row["negative_verdict_is_weak"])
        self.assertGreater(self.summary["weak_negative_verdicts"], 0)

    def test_no_unit_was_modified_by_the_screening(self) -> None:
        units = load_jsonl(CORPUS / "source_profile_units.jsonl")
        manifest = json.loads(
            (CORPUS / "qualification_corpus_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["profile_units_hash"], content_hash(units))


# ── blinding e regressione ────────────────────────────────────────────────────


class TestBlindingAndRegression(unittest.TestCase):
    def test_updated_packets_exist_for_every_scoped_unit(self) -> None:
        scope = load_jsonl(AUDIT / "audit_scope.jsonl")
        folder = AUDIT / "annotation_packets/first_review_split_audit"
        for row in scope:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue((folder / f"{row['first_review_packet']}.json").is_file())

    def test_original_packets_are_preserved(self) -> None:
        original = CURATION / "annotation_packets/first_review"
        for row in load_jsonl(AUDIT / "audit_scope.jsonl"):
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue((original / f"{row['first_review_packet']}.json").is_file())

    def test_updated_packet_points_back_to_the_original(self) -> None:
        folder = AUDIT / "annotation_packets/first_review_split_audit"
        for path in sorted(folder.glob("*.json")):
            packet = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=path.name):
                self.assertEqual(packet["supersedes_packet"], packet["blind_annotation_id"])

    def test_second_review_packets_are_byte_identical(self) -> None:
        check = json.loads(
            (AUDIT / "second_review_blinding_check.json").read_text(encoding="utf-8")
        )
        self.assertTrue(check["byte_identical"])
        self.assertEqual(check["changed_files"], [])

    def test_second_review_hashes_still_match_the_files(self) -> None:
        check = json.loads(
            (AUDIT / "second_review_blinding_check.json").read_text(encoding="utf-8")
        )
        folder = CURATION / "annotation_packets/second_review"
        for name, digest in check["hashes_after"].items():
            with self.subTest(packet=name):
                actual = hashlib.sha256((folder / name).read_bytes()).hexdigest()
                self.assertEqual(actual, digest)

    def test_audit_packets_carry_no_final_decision(self) -> None:
        folder = AUDIT / "annotation_packets/first_review_split_audit"
        for path in sorted(folder.glob("*.json")):
            packet = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(packet=path.name):
                self.assertFalse(packet["contains_clinical_gold"])
                self.assertFalse(packet["contains_final_decision"])
                self.assertFalse(packet["contains_other_reviewer_decision"])
                self.assertFalse(packet["contains_reviewed_packet_outcome"])

    def test_audit_packets_do_not_leak_the_reviewed_source(self) -> None:
        folder = AUDIT / "annotation_packets/first_review_split_audit"
        for path in sorted(folder.glob("*"))    :
            content = path.read_text(encoding="utf-8")
            with self.subTest(packet=path.name):
                self.assertNotIn("22277784", content)
                self.assertNotIn("paolo", content.casefold())

    def test_the_first_review_is_unchanged(self) -> None:
        units = load_jsonl(REVIEW / "reviewed_profile_units.jsonl")
        self.assertEqual(len(units), 4)
        for row in units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["review_status"], "first_review_complete")

    def test_the_gold_is_still_provisional(self) -> None:
        for row in load_jsonl(REVIEW / "provisional_gold.jsonl"):
            with self.subTest(gold=row["gold_link_id"]):
                self.assertFalse(row["is_evaluable"])

    def test_the_147_statements_are_still_present(self) -> None:
        statements = load_jsonl(
            REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl"
        )
        self.assertEqual(len(statements), 147)

    def test_the_102_sources_are_still_inventoried(self) -> None:
        self.assertEqual(len(load_jsonl(CORPUS / "source_inventory.jsonl")), 102)

    def test_no_final_metric_is_calculated(self) -> None:
        metrics = json.loads(
            (AUDIT / "structural_audit_metrics.json").read_text(encoding="utf-8")
        )
        self.assertEqual(metrics["metric_kind"], "structural_audit_metrics")
        for key in ("linking_precision", "linking_recall", "linking_f1", "agreement"):
            with self.subTest(metric=key):
                self.assertEqual(metrics["not_calculated"][key], "not_calculated")

    def test_artifacts_contain_no_credentials(self) -> None:
        for path in sorted(AUDIT.rglob("*")):
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").casefold()
            for needle in ("authorization", "api_key", "api-key", "bearer ", "password"):
                with self.subTest(path=path.name, needle=needle):
                    self.assertNotIn(needle, content)

    def test_no_full_text_is_stored(self) -> None:
        for row in load_jsonl(AUDIT / "source_access_audit.jsonl"):
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["full_text_stored"])
                self.assertNotIn("document_text", row)


if __name__ == "__main__":
    unittest.main()
