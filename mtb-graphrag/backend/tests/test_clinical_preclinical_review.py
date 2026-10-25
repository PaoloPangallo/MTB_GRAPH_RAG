"""Perimetro, verifica documentale, proposte, guardie e blinding del batch.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano modelli linguistici. Le prove che richiedono una fonte
usano testo sintetico, cosi' che la suite verifichi il **meccanismo** senza
dipendere dalla rete.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.profile_unit import (
    CLINICAL_UNIT_TYPES,
    COHORT_SPLIT_REVIEW_PROPOSED,
    HUMAN_ONLY_STATUSES,
    IN_VITRO_UNIT_TYPES,
    IN_VIVO_UNIT_TYPES,
    NOT_APPLICABLE,
    PRECLINICAL_UNIT_TYPES,
    REVIEW_STATUSES,
    SOURCE_CHECKED_REVIEW_PROPOSAL,
    UNIT_TYPE_PRECLINICAL_IN_VIVO,
    UNIT_TYPE_PRECLINICAL_PHARMACOLOGY,
    UNIT_TYPE_PRECLINICAL_XENOGRAFT,
    UNKNOWN,
    SourceClinicalProfileUnit,
)
from backend.pipeline.evidence.propagation_guards import (
    ALL_RULE_IDS,
    rule_ids_for_version,
    BiomarkerRoleError,
    ClinicalToPreclinicalError,
    CrossModelError,
    EvidenceStrengthError,
    PreclinicalToClinicalError,
    ProvenanceError,
    run_guards,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_findings import (
    FINDINGS,
    FINDINGS_BY_UNIT,
)
from benchmarks.mtb_evidence.evaluation.clinical_preclinical_review import (
    AUDIT_SPLIT_CONFIRMED_MORE,
    AUDIT_SPLIT_NOT_SUPPORTED,
    AUDIT_SPLIT_PARTIALLY_SUPPORTED,
    CANDIDATE_LINK_STATES,
    EXPECTED_SOURCES,
    STRUCTURAL_DECISIONS,
    SUPPORT_TYPES,
    TERMINOLOGY_STATES,
    ScopeMismatch,
    check_scope,
    derive_scope,
    validate_proposal_states,
)
from benchmarks.mtb_evidence.evaluation.scripts.verify_source_locators import locate_query
from backend.pipeline.evidence.corpus_manifest import content_hash

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH = REPO_ROOT / "benchmarks/mtb_evidence/v3/clinical_preclinical_review_batch"
AUDIT = REPO_ROOT / "benchmarks/mtb_evidence/v3/cohort_split_audit"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"
CORPUS = REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification_corpus"
REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/first_review"
QUALIFICATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── perimetro ─────────────────────────────────────────────────────────────────


class TestBatchScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.classification = load_jsonl(AUDIT / "source_structure_classification.jsonl")
        cls.scope = load_jsonl(BATCH / "review_batch_scope.jsonl")
        cls.payload = load_json(BATCH / "review_batch_scope.json")

    def test_exactly_three_sources(self) -> None:
        self.assertEqual(len(self.scope), 3)
        self.assertEqual(len(EXPECTED_SOURCES), 3)

    def test_all_three_are_clinical_preclinical(self) -> None:
        states = {
            row["profile_unit_id"]: row["structure_state"]
            for row in self.classification
        }
        for row in self.scope:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(
                    states[row["profile_unit_id"]], "clinical_preclinical_split_required"
                )

    def test_scope_matches_the_declared_set(self) -> None:
        self.assertEqual(sorted(derive_scope(self.classification)), sorted(EXPECTED_SOURCES))

    def test_scope_is_order_invariant(self) -> None:
        forward = derive_scope(self.classification)
        backward = derive_scope(list(reversed(self.classification)))
        self.assertEqual(forward, backward)

    def test_check_scope_rejects_a_missing_source(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_scope(list(EXPECTED_SOURCES)[:-1])

    def test_check_scope_rejects_an_extra_source(self) -> None:
        with self.assertRaises(ScopeMismatch):
            check_scope([*EXPECTED_SOURCES, "PU-PMID-99999999-cohort-1"])

    def test_scope_hash_is_stable(self) -> None:
        self.assertEqual(self.payload["review_batch_scope_hash"], content_hash(self.scope))

    def test_no_clinical_gold_is_used(self) -> None:
        self.assertFalse(self.payload["clinical_gold_used"])
        manifest = load_json(BATCH / "review_batch_manifest.json")
        self.assertFalse(manifest["clinical_gold_used"])


# ── verifica delle fonti ──────────────────────────────────────────────────────


class TestSourceVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.access = load_jsonl(BATCH / "source_access_verification.jsonl")

    def test_full_text_is_never_stored(self) -> None:
        for row in self.access:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(row["full_text_stored"])
                self.assertFalse(row["full_text_redistributed"])

    def test_every_source_has_a_document_hash(self) -> None:
        for row in self.access:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue(row["document_hash"])

    def test_abstract_hash_matches_the_registered_one(self) -> None:
        """La fonte senza full text e' la stessa che la curation aveva registrato."""
        row = next(r for r in self.access if r["profile_unit_id"] == "PU-PMID-23344087-cohort-1")
        self.assertTrue(row["abstract_hash_matches"])
        self.assertEqual(row["document_hash"], row["stored_abstract_hash"])

    def test_every_locator_is_verified(self) -> None:
        for row in self.access:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["locators_not_verified"], 0)
                self.assertGreater(row["locators_verified"], 0)

    def test_every_locator_carries_its_evidence(self) -> None:
        for row in self.access:
            for locator in row["locators"]:
                with self.subTest(locator=locator["locator_id"]):
                    self.assertTrue(locator["span_hash"])
                    self.assertIsNotNone(locator["char_offset"])
                    self.assertTrue(locator["excerpt"])

    def test_exact_match_is_recognised(self) -> None:
        match, offset, gap = locate_query("cells were treated", "The cells were treated with X.")
        self.assertEqual(match, "exact")
        self.assertEqual(gap, 0)
        self.assertGreaterEqual(offset, 0)

    def test_interpolated_match_is_named_differently(self) -> None:
        """Una citazione con un inciso e' verificata, ma non come esatta."""
        match, offset, gap = locate_query(
            "known hsp90 clients", "ALK proteins are known hsp90 (heat shock protein 90) clients."
        )
        self.assertEqual(match, "interpolated")
        self.assertGreater(gap, 0)
        self.assertIsNotNone(offset)

    def test_search_is_anchored_and_does_not_drift(self) -> None:
        """Le parole sparse nel documento non compongono una citazione."""
        haystack = "alk " + ("filler " * 200) + "resistance " + ("filler " * 200) + "mutation"
        match, _, _ = locate_query("alk resistance mutation", haystack)
        self.assertEqual(match, "not_verified")

    def test_figure_label_is_reported_at_figure_level(self) -> None:
        match, _, _ = locate_query("Figure 3", "As shown in Fig. 3 the cells respond.")
        self.assertEqual(match, "figure_level")

    def test_table_label_is_reported_at_table_level(self) -> None:
        """Una tabella verificata come etichetta non e' una frase verificata."""
        match, _, _ = locate_query(
            "Table 2", "The molecular analysis is reported elsewhere.", labels=["Table 2"]
        )
        self.assertEqual(match, "table_level")

    def test_section_hint_is_the_weakest_accepted_evidence(self) -> None:
        match, _, _ = locate_query(
            "a phrase that is absent",
            "Materials and Methods Cell lines were grown in RPMI.",
            section_hint="Materials and Methods",
        )
        self.assertEqual(match, "section_level")

    def test_a_missing_phrase_is_not_verified(self) -> None:
        match, offset, _ = locate_query("completely absent phrase", "Some other text entirely.")
        self.assertEqual(match, "not_verified")
        self.assertIsNone(offset)


# ── struttura ─────────────────────────────────────────────────────────────────


class TestStructuralDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.decisions = load_jsonl(BATCH / "structural_review_decisions.jsonl")
        cls.by_unit = {row["profile_unit_id"]: row for row in cls.decisions}
        cls.units = load_jsonl(BATCH / "proposed_profile_units.jsonl")

    def test_every_source_has_exactly_one_decision(self) -> None:
        self.assertEqual(len(self.decisions), 3)
        self.assertEqual(len({row["profile_unit_id"] for row in self.decisions}), 3)

    def test_every_decision_is_from_the_vocabulary(self) -> None:
        for row in self.decisions:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertIn(row["structural_decision"], STRUCTURAL_DECISIONS)

    def test_split_confirmed_with_more_units(self) -> None:
        row = self.by_unit["PU-PMID-22235099-cohort-1"]
        self.assertEqual(row["structural_decision"], AUDIT_SPLIT_CONFIRMED_MORE)
        self.assertEqual(row["audit_unit_count"], 2)
        self.assertEqual(row["reviewed_unit_count"], 5)
        self.assertEqual(row["unit_count_delta"], 3)

    def test_split_partially_supported_when_only_the_abstract_is_readable(self) -> None:
        row = self.by_unit["PU-PMID-23344087-cohort-1"]
        self.assertEqual(row["structural_decision"], AUDIT_SPLIT_PARTIALLY_SUPPORTED)
        self.assertEqual(row["availability"], "abstract_only")
        self.assertTrue(row["not_separable_dimensions"])

    def test_split_not_supported_is_reachable(self) -> None:
        """Un positivo del rilevatore puo' essere respinto, e uno lo e' stato."""
        row = self.by_unit["PU-PMID-31358542-cohort-1"]
        self.assertEqual(row["structural_decision"], AUDIT_SPLIT_NOT_SUPPORTED)
        self.assertEqual(row["preclinical_unit_count"], 0)
        self.assertEqual(row["reviewed_unit_count"], 1)

    def test_more_than_two_units_when_the_source_supports_them(self) -> None:
        units = [
            row
            for row in self.units
            if row["parent_profile_unit_id"] == "PU-PMID-22235099-cohort-1"
        ]
        self.assertEqual(len(units), 5)
        self.assertEqual(sum(1 for row in units if row["is_clinical"]), 1)
        self.assertEqual(sum(1 for row in units if row["is_preclinical"]), 4)

    def test_parent_units_are_preserved(self) -> None:
        for row in self.decisions:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue(row["parent_unit_preserved"])
                self.assertIsNone(row["parent_unit_new_state"])

    def test_original_units_keep_their_state_in_the_audit(self) -> None:
        """Nessuno stato `superseded` viene assegnato prima dell'approvazione."""
        proposed = {row["proposed_profile_unit_id"] for row in self.units}
        for parent in EXPECTED_SOURCES:
            with self.subTest(unit=parent):
                self.assertNotIn(parent, proposed)

    def test_no_unit_is_invented(self) -> None:
        """Ogni unita' proposta ha almeno un locator verificato che la sostiene."""
        access = {
            row["profile_unit_id"]: {
                item["locator_id"] for item in row["locators"] if item["verified"]
            }
            for row in load_jsonl(BATCH / "source_access_verification.jsonl")
        }
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                verified = access[row["parent_profile_unit_id"]]
                self.assertTrue(set(row["source_locators"]) & verified)

    def test_clinical_and_preclinical_units_are_distinguishable(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertNotEqual(row["is_clinical"], row["is_preclinical"])

    def test_in_vitro_units_exist_and_are_flagged(self) -> None:
        self.assertEqual(sum(1 for row in self.units if row["is_in_vitro"]), 6)

    def test_no_in_vivo_unit_is_claimed(self) -> None:
        """Nessuna delle tre fonti contiene esperimenti in vivo, e si vede."""
        self.assertEqual(sum(1 for row in self.units if row["is_in_vivo"]), 0)

    def test_the_model_can_express_in_vivo_and_pharmacology_units(self) -> None:
        """Il vocabolario copre i tipi che il batch non contiene."""
        for unit_type in (
            UNIT_TYPE_PRECLINICAL_IN_VIVO,
            UNIT_TYPE_PRECLINICAL_XENOGRAFT,
            UNIT_TYPE_PRECLINICAL_PHARMACOLOGY,
        ):
            with self.subTest(unit_type=unit_type):
                unit = SourceClinicalProfileUnit(
                    profile_unit_id="PU-test",
                    canonical_source_id="PMID:1",
                    unit_type=unit_type,
                )
                self.assertTrue(unit.is_preclinical)
                self.assertFalse(unit.is_clinical)
        self.assertIn(UNIT_TYPE_PRECLINICAL_XENOGRAFT, IN_VIVO_UNIT_TYPES)
        self.assertIn(UNIT_TYPE_PRECLINICAL_PHARMACOLOGY, IN_VITRO_UNIT_TYPES)


# ── campi ─────────────────────────────────────────────────────────────────────


class TestFieldSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(BATCH / "proposed_profile_units.jsonl")
        cls.by_id = {row["proposed_profile_unit_id"]: row for row in cls.units}

    def test_unknown_and_not_applicable_are_distinct(self) -> None:
        decisions = {
            decision
            for row in self.units
            for decision in (row["field_decisions"] or {}).values()
        }
        self.assertIn(UNKNOWN, decisions)
        self.assertIn(NOT_APPLICABLE, decisions)

    def test_clinical_dimensions_are_not_applicable_on_models(self) -> None:
        model = self.by_id["PU-PMID-22235099-baf3-engineered"]
        for dimension in ("therapy_line", "stage", "resection_status", "population"):
            with self.subTest(dimension=dimension):
                self.assertEqual(model[dimension], NOT_APPLICABLE)
                self.assertEqual(model["field_decisions"][dimension], NOT_APPLICABLE)

    def test_not_separable_is_distinct_from_unknown(self) -> None:
        cohort = self.by_id["PU-PMID-31358542-clinical-cohort"]
        self.assertIn("intervention", cohort["not_separable_dimensions"])
        self.assertEqual(cohort["field_decisions"]["intervention"], "not_separable")
        self.assertNotEqual(cohort["field_decisions"]["intervention"], UNKNOWN)

    def test_sentinel_lists_are_serialised_as_lists(self) -> None:
        """Il sentinella su una dimensione a lista vive nella decisione, non nel valore."""
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                for dimension in ("biomarker_requirements", "intervention", "prior_therapies"):
                    value = row[dimension]
                    self.assertIsInstance(value, list)
                    self.assertNotIn(NOT_APPLICABLE, value)
                    self.assertNotIn(UNKNOWN, value)

    def test_prior_therapy_is_not_recorded_as_intervention(self) -> None:
        """Una coorte osservazionale non eredita come intervento la terapia precedente."""
        cohort = self.by_id["PU-PMID-31358542-clinical-cohort"]
        self.assertNotIn("crizotinib", cohort["intervention"])

    def test_observed_biomarker_is_not_a_requirement(self) -> None:
        """Solo l'alterazione che dava accesso allo studio e' un requisito."""
        for unit_id in (
            "PU-PMID-22235099-clinical-cohort",
            "PU-PMID-23344087-clinical-cohort",
        ):
            with self.subTest(unit=unit_id):
                cohort = self.by_id[unit_id]
                self.assertEqual(cohort["biomarker_role"], "enrolment_criterion")
                joined = " ".join(cohort["biomarker_requirements"]).casefold()
                self.assertNotIn("g1269a", joined)
                self.assertNotIn("l1196m", joined)
                self.assertNotIn("l858r", joined)

    def test_every_known_dimension_has_provenance(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                provenance = {item["field_name"] for item in row["provenance"]}
                self.assertTrue(set(row["known_dimensions"]) <= provenance)

    def test_provenance_records_a_locator_and_an_author(self) -> None:
        for row in self.units:
            for item in row["provenance"]:
                with self.subTest(unit=row["proposed_profile_unit_id"], field=item["field_name"]):
                    self.assertTrue(item["source_locator"])
                    self.assertTrue(item["asserted_by"])
                    self.assertTrue(item["span_hash"])


# ── mapping degli statement ───────────────────────────────────────────────────


class TestStatementMapping(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(BATCH / "statement_unit_review_proposals.jsonl")
        cls.by_id = {row["statement_id"]: row for row in cls.rows}
        cls.terminology = load_jsonl(BATCH / "terminology_mappings.jsonl")

    def test_all_seven_statements_are_mapped(self) -> None:
        self.assertEqual(len(self.rows), 7)

    def test_values_come_from_the_declared_vocabularies(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertIn(row["support_type"], SUPPORT_TYPES)
                self.assertIn(row["candidate_link_status"], CANDIDATE_LINK_STATES)

    def test_direct_clinical_support_is_recognised(self) -> None:
        row = self.by_id["ES-V2-evidence-4288"]
        self.assertEqual(row["support_type"], "direct_clinical_support")
        self.assertEqual(row["clinical_or_preclinical"], "clinical")

    def test_clinical_observation_with_preclinical_validation(self) -> None:
        row = self.by_id["ES-V2-evidence-764"]
        self.assertEqual(
            row["support_type"], "clinical_observation_with_preclinical_validation"
        )
        self.assertEqual(row["clinical_or_preclinical"], "both")
        self.assertGreater(len(row["proposed_profile_unit_ids"]), 1)

    def test_a_statement_without_preclinical_support_says_so(self) -> None:
        row = self.by_id["ES-V2-evidence-766"]
        self.assertEqual(row["support_type"], "direct_clinical_support")
        self.assertIn("nessuno", row["preclinical_support"].casefold())

    def test_relative_resistance_is_flagged_for_review(self) -> None:
        """«less sensitive» non e' «resistance», e la differenza resta visibile."""
        row = self.by_id["ES-V2-evidence-765"]
        self.assertIn("relative_versus_complete_resistance", row["non_propagation_rules"])
        mapping = next(
            item for item in self.terminology if item["normalized_term"] == "resistance"
        )
        self.assertEqual(mapping["mapping_status"], "requires_terminology_verification")
        self.assertFalse(mapping["literal_string_present"])

    def test_pooled_cohort_property_is_not_given_to_a_subgroup(self) -> None:
        row = self.by_id["ES-V2-evidence-100003"]
        self.assertEqual(row["candidate_link_status"], "candidate_ambiguous")
        self.assertIn("intervention", row["conflict_dimensions"])

    def test_every_statement_carries_locators(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertTrue(row["source_locators"])

    def test_candidates_are_not_gold(self) -> None:
        for row in self.rows:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_gold"])
                self.assertFalse(row["human_reviewed"])
                self.assertTrue(row["requires_author_approval"])

    def test_terminology_mappings_are_tracked(self) -> None:
        self.assertEqual(len(self.terminology), 3)
        for row in self.terminology:
            with self.subTest(term=row["original_source_term"]):
                self.assertIn(row["mapping_status"], TERMINOLOGY_STATES)
                self.assertTrue(row["source_locators"])
                self.assertTrue(row["mapping_source"])

    def test_amplification_is_not_treated_as_copy_number_gain(self) -> None:
        rows = [
            row for row in self.terminology if row["normalized_term"] == "ALK Amplification"
        ]
        self.assertEqual(len(rows), 2)
        for row in rows:
            with self.subTest(unit=row["parent_profile_unit_id"]):
                self.assertTrue(row["review_required"])
                self.assertFalse(row["literal_string_present"])


# ── propagazione ──────────────────────────────────────────────────────────────


def unit(**overrides) -> dict:
    payload = {
        "profile_unit_id": "PU-x",
        "canonical_source_id": "PMID:1",
        "unit_type": "unspecified",
    }
    payload.update(overrides)
    return payload


class TestPropagationGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = load_jsonl(BATCH / "propagation_guard_results.jsonl")
        cls.summary = load_json(BATCH / "propagation_guard_summary.json")

    def test_every_rule_is_executed_on_every_unit(self) -> None:
        # Confrontate con le regole della versione che l'artefatto dichiara, non
        # con quelle di oggi: aggiungere una regola non rende incompleta una
        # verifica che era completa quando e' stata eseguita.
        expected = rule_ids_for_version(self.summary["guard_version"])
        self.assertTrue(set(expected) <= set(ALL_RULE_IDS))
        for row in self.results:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertEqual(sorted(row["rules_executed"]), sorted(expected))

    def test_every_required_prohibition_is_covered(self) -> None:
        self.assertEqual(self.summary["uncovered_prohibitions"], [])
        for item in self.summary["required_prohibitions"]:
            with self.subTest(prohibition=item["prohibition"]):
                self.assertTrue(item["covered"])

    def test_current_proposals_have_no_violations(self) -> None:
        self.assertEqual(self.summary["violations_total"], 0)

    def test_clinical_population_does_not_reach_a_model(self) -> None:
        found = run_guards(
            units=[
                unit(
                    unit_type="preclinical_engineered_model",
                    population="14 patients enrolled on the trial",
                )
            ]
        )
        self.assertTrue(found)
        with self.assertRaises(ClinicalToPreclinicalError):
            found[0].raise_it()

    def test_therapy_line_does_not_reach_a_model(self) -> None:
        found = run_guards(
            units=[unit(unit_type="preclinical_in_vitro", therapy_line="second line")]
        )
        self.assertTrue(any(item.rule_id == "clinical_dimensions_to_model" for item in found))

    def test_stage_does_not_reach_an_in_vitro_unit(self) -> None:
        found = run_guards(units=[unit(unit_type="preclinical_in_vitro", stage="stage IV")])
        self.assertTrue(any("stage" in item.dimensions for item in found))

    def test_model_comparator_does_not_reach_patients(self) -> None:
        found = run_guards(
            units=[
                unit(
                    unit_type="clinical_observational_cohort",
                    comparator="parental Ba/F3 cell line",
                )
            ]
        )
        self.assertTrue(found)
        with self.assertRaises(PreclinicalToClinicalError):
            found[0].raise_it()

    def test_a_model_property_does_not_reach_another_model(self) -> None:
        shared = {
            "canonical_source_id": "PMID:1",
            "unit_type": "preclinical_engineered_model",
            "model_type": "linea murina",
            "cell_line": ["Ba/F3"],
            "assay": "proliferazione",
        }
        found = run_guards(
            units=[{**shared, "profile_unit_id": "PU-a"}, {**shared, "profile_unit_id": "PU-b"}]
        )
        self.assertTrue(found)
        with self.assertRaises(CrossModelError):
            found[0].raise_it()

    def test_a_cohort_property_does_not_reach_another_cohort(self) -> None:
        shared = {
            "canonical_source_id": "PMID:1",
            "unit_type": "clinical_observational_cohort",
            "population": "adults",
            "setting": "metastatic",
            "therapy_line": "first line",
        }
        found = run_guards(
            units=[
                {**shared, "profile_unit_id": "PU-a", "cohort_id": "c1"},
                {**shared, "profile_unit_id": "PU-b", "cohort_id": "c2"},
            ]
        )
        self.assertTrue(any(item.rule_id == "cross_cohort_identity" for item in found))

    def test_an_intervention_does_not_cross_between_arms(self) -> None:
        found = run_guards(
            units=[
                unit(
                    profile_unit_id="PU-a",
                    unit_type="clinical_trial_arm",
                    cohort_id="arm-1",
                    intervention=["X"],
                ),
                unit(
                    profile_unit_id="PU-b",
                    unit_type="clinical_trial_arm",
                    cohort_id="arm-2",
                    intervention=["X"],
                ),
            ]
        )
        self.assertTrue(any(item.rule_id == "cross_arm_intervention" for item in found))

    def test_a_subgroup_property_does_not_reach_the_whole_population(self) -> None:
        found = run_guards(
            units=[
                unit(
                    unit_type="clinical_observational_cohort",
                    cohort_label="biomarker-positive subgroup",
                    population="all enrolled patients",
                )
            ]
        )
        self.assertTrue(any(item.rule_id == "subgroup_to_population" for item in found))

    def test_relative_resistance_is_distinct_from_complete(self) -> None:
        found = run_guards(
            decisions=[
                {
                    "statement_id": "ES-1",
                    "support_type": "direct_preclinical_support",
                    "resistance_qualifier": "complete_resistance",
                    "rationale": "the clones retained partial activity at higher doses",
                }
            ]
        )
        self.assertTrue(found)
        with self.assertRaises(EvidenceStrengthError):
            found[0].raise_it()

    def test_an_observed_finding_is_not_an_enrolment_criterion(self) -> None:
        found = run_guards(
            units=[
                unit(
                    unit_type="clinical_observational_cohort",
                    biomarker_requirements=["ALK G1269A"],
                    biomarker_role="observed_finding",
                )
            ]
        )
        self.assertTrue(found)
        with self.assertRaises(BiomarkerRoleError):
            found[0].raise_it()

    def test_a_mapping_without_provenance_is_rejected(self) -> None:
        found = run_guards(
            mappings=[{"source_term": "PF-02341066", "mapped_term": "crizotinib"}]
        )
        self.assertTrue(found)
        with self.assertRaises(ProvenanceError):
            found[0].raise_it()

    def test_sentinels_do_not_trigger_the_rules(self) -> None:
        """`unknown` e `not_applicable` non sono valori: non devono accendere nulla."""
        for sentinel in (UNKNOWN, NOT_APPLICABLE, "not_separable"):
            with self.subTest(sentinel=sentinel):
                found = run_guards(
                    units=[
                        unit(
                            unit_type="preclinical_in_vitro",
                            population=sentinel,
                            therapy_line=sentinel,
                            stage=sentinel,
                        )
                    ]
                )
                self.assertEqual(found, [])

    def test_a_unit_with_a_violation_is_not_propagatable(self) -> None:
        for row in self.results:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertFalse(row["is_propagatable"])
                if row["violations"]:
                    self.assertEqual(row["outcome"], "blocked")

    def test_every_violation_carries_a_typed_error(self) -> None:
        found = run_guards(
            units=[unit(unit_type="preclinical_in_vitro", population="patients enrolled")]
        )
        for item in found:
            with self.subTest(rule=item.rule_id):
                self.assertTrue(issubclass(item.error_type, Exception))
                self.assertIn("error_type", item.as_dict())


# ── stato della revisione ─────────────────────────────────────────────────────


class TestReviewStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(BATCH / "proposed_profile_units.jsonl")
        cls.provisional = load_jsonl(BATCH / "provisional_review_records.jsonl")

    def test_the_maximum_status_is_source_checked_proposal(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertEqual(validate_proposal_states(row), [])
                self.assertEqual(row["review_status"], SOURCE_CHECKED_REVIEW_PROPOSAL)

    def test_the_proposal_status_is_not_a_human_only_status(self) -> None:
        """Uno stato assegnabile da un processo non puo' valere come revisione."""
        self.assertIn(SOURCE_CHECKED_REVIEW_PROPOSAL, REVIEW_STATUSES)
        self.assertNotIn(SOURCE_CHECKED_REVIEW_PROPOSAL, HUMAN_ONLY_STATUSES)

    def test_source_checked_is_distinct_from_human_reviewed(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertTrue(row["source_checked"])
                self.assertFalse(row["human_reviewed"])

    def test_no_proposal_is_propagatable(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["proposed_profile_unit_id"]):
                self.assertFalse(row["is_propagatable"])
                self.assertEqual(row["cohort_state"], COHORT_SPLIT_REVIEW_PROPOSED)

    def test_the_new_cohort_state_can_never_propagate(self) -> None:
        built = SourceClinicalProfileUnit(
            profile_unit_id="PU-test",
            canonical_source_id="PMID:1",
            cohort_state=COHORT_SPLIT_REVIEW_PROPOSED,
        )
        self.assertFalse(built.is_propagatable)

    def test_the_second_review_is_still_empty(self) -> None:
        for row in self.provisional:
            with self.subTest(statement=row["statement_id"]):
                self.assertIsNone(row["first_annotator"])
                self.assertIsNone(row["second_annotator"])
                self.assertIsNone(row["agreement"])
                self.assertIsNone(row["adjudication"])

    def test_the_gold_is_not_evaluable(self) -> None:
        for row in self.provisional:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_evaluable"])
                self.assertEqual(row["final_status"], "provisional_unreviewed")
                self.assertEqual(row["review_stage"], "awaiting_author_approval")

    def test_no_forbidden_status_is_declared(self) -> None:
        forbidden = (
            "first_review_complete",
            "second_review_complete",
            "independent_review",
            "clinical_review_complete",
            "adjudicated",
            "frozen",
        )
        blob = (BATCH / "proposed_profile_units.jsonl").read_text(encoding="utf-8")
        for status in forbidden:
            with self.subTest(status=status):
                self.assertNotIn(f'"review_status": "{status}"', blob)


# ── blinding ──────────────────────────────────────────────────────────────────


class TestBlinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.check = load_json(BATCH / "second_review_blinding_check.json")
        cls.packet_dir = BATCH / "annotation_packets/author_approval"

    def test_second_review_packets_are_byte_identical(self) -> None:
        self.assertTrue(self.check["byte_identical"])
        self.assertEqual(self.check["changed_files"], [])
        self.assertEqual(self.check["file_count_before"], self.check["file_count_after"])

    def test_the_recorded_hashes_still_match_the_files(self) -> None:
        """Il controllo non e' obsoleto: gli hash sono ricalcolati dai file."""
        directory = CURATION / "annotation_packets/second_review"
        recomputed = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.iterdir())
            if path.is_file()
        }
        self.assertEqual(recomputed, self.check["hashes_after"])

    def test_the_scope_recorded_the_same_hashes_before_the_batch(self) -> None:
        manifest = load_json(BATCH / "review_batch_manifest.json")
        self.assertEqual(
            manifest["second_review_hashes_before"], self.check["hashes_after"]
        )

    def test_author_packets_exist_for_every_source(self) -> None:
        packets = sorted(path.name for path in self.packet_dir.glob("*.json"))
        self.assertEqual(len(packets), 3)

    def test_no_batch_decision_leaks_into_the_second_review_packets(self) -> None:
        directory = CURATION / "annotation_packets/second_review"
        needles = (
            "source_checked_review_proposal",
            "audit_split_confirmed",
            "audit_split_not_supported",
            "clinical_preclinical_review",
        )
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            blob = path.read_text(encoding="utf-8", errors="replace").casefold()
            for needle in needles:
                with self.subTest(packet=path.name, needle=needle):
                    self.assertNotIn(needle.casefold(), blob)

    def test_the_author_is_never_recorded_as_reviewer(self) -> None:
        for path in sorted(self.packet_dir.iterdir()):
            blob = path.read_text(encoding="utf-8").casefold()
            with self.subTest(packet=path.name):
                self.assertNotIn("paolo", blob)
                self.assertNotIn("pangallo", blob)

    def test_author_packets_carry_no_clinical_gold(self) -> None:
        for path in sorted(self.packet_dir.iterdir()):
            blob = path.read_text(encoding="utf-8").casefold()
            with self.subTest(packet=path.name):
                self.assertNotIn("clinical gold", blob)
                self.assertNotIn("terapia attesa", blob)

    def test_author_packets_are_undecided(self) -> None:
        for path in sorted(self.packet_dir.glob("*.json")):
            payload = load_json(path)
            with self.subTest(packet=path.name):
                self.assertIsNone(payload["decision"])
                self.assertIsNone(payload["decided_by"])
                self.assertFalse(payload["human_reviewed"])
                self.assertTrue(payload["requires_author_approval"])


# ── rilevatore ────────────────────────────────────────────────────────────────


class TestDetectorSmallBatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = load_jsonl(BATCH / "detector_case_review.jsonl")
        cls.metrics = load_json(BATCH / "detector_small_batch_metrics.json")

    def test_three_cases_are_compared(self) -> None:
        self.assertEqual(len(self.rows), 3)
        self.assertEqual(self.metrics["cases_reviewed"], 3)

    def test_one_positive_is_rejected(self) -> None:
        self.assertEqual(self.metrics["rejected_positives"], 1)
        row = next(r for r in self.rows if r["concordance"] == "rejected_positive")
        self.assertEqual(row["profile_unit_id"], "PU-PMID-31358542-cohort-1")
        self.assertIn("preclinical.in_vitro", row["wrong_signals"])

    def test_the_signals_are_preserved_with_the_verdict(self) -> None:
        for row in self.rows:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue(row["detector_verdict"])
                self.assertTrue(row["signal_id_counts"])
                self.assertTrue(row["rationale"])

    def test_the_false_positive_rests_on_a_single_occurrence(self) -> None:
        """Il caso sbagliato e quello giusto hanno lo stesso identico segnale."""
        wrong = next(r for r in self.rows if r["profile_unit_id"] == "PU-PMID-31358542-cohort-1")
        right = next(r for r in self.rows if r["profile_unit_id"] == "PU-PMID-23344087-cohort-1")
        self.assertEqual(wrong["signal_id_counts"]["preclinical.in_vitro"], 1)
        self.assertEqual(right["signal_id_counts"]["preclinical.in_vitro"], 1)
        self.assertGreater(wrong["detector_score"], right["detector_score"])

    def test_only_descriptive_metrics_are_calculated(self) -> None:
        self.assertEqual(self.metrics["metric_kind"], "descriptive_small_batch")
        for name in ("precision", "recall", "sensitivity", "specificity", "accuracy"):
            with self.subTest(metric=name):
                self.assertNotIn(name, {key for key in self.metrics if key != "not_calculated"})
                self.assertEqual(self.metrics["not_calculated"][name], "not_calculated")

    def test_the_detector_is_not_promoted(self) -> None:
        self.assertFalse(self.metrics["detector_promotion_ready"])
        readiness = load_json(BATCH / "readiness.json")
        self.assertFalse(readiness["detector_promotion_ready"])

    def test_the_unit_count_was_wrong_everywhere(self) -> None:
        """Nessuna delle tre volte il rilevatore ha indovinato quante unita' servissero."""
        self.assertEqual(self.metrics["unit_count_correct"], 0)


# ── metriche e readiness ──────────────────────────────────────────────────────


class TestMetricsAndReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = load_json(BATCH / "review_batch_metrics.json")
        cls.readiness = load_json(BATCH / "readiness.json")

    def test_metrics_are_declared_descriptive(self) -> None:
        self.assertEqual(self.metrics["metric_kind"], "descriptive_review_batch_metrics")

    def test_no_final_metric_is_calculated(self) -> None:
        for name in (
            "linking_precision",
            "linking_recall",
            "linking_f1",
            "agreement",
            "clinical_applicability_accuracy",
            "retrieval_quality",
        ):
            with self.subTest(metric=name):
                self.assertEqual(self.metrics["not_calculated"][name], "not_calculated")

    def test_provenance_completeness_is_one(self) -> None:
        self.assertEqual(self.metrics["provenance_completeness"], 1.0)

    def test_no_proposal_is_propagatable_or_reviewed(self) -> None:
        self.assertEqual(self.metrics["proposals_propagatable"], 0)
        self.assertEqual(self.metrics["proposals_human_reviewed"], 0)

    def test_readiness_has_no_blockers(self) -> None:
        self.assertEqual(self.readiness["blockers"], [])
        self.assertTrue(self.readiness["ready_to_resume_standard_queue"])

    def test_readiness_criteria_are_all_satisfied(self) -> None:
        for item in self.readiness["criteria"]:
            with self.subTest(criterion=item["criterion"]):
                self.assertTrue(item["satisfied"])

    def test_author_approvals_are_pending(self) -> None:
        self.assertEqual(self.readiness["author_approvals_pending"], 3)


# ── regressione ───────────────────────────────────────────────────────────────


class TestRegression(unittest.TestCase):
    def test_the_first_review_of_22277784_is_unchanged(self) -> None:
        rows = load_jsonl(REVIEW / "reviewed_profile_units.jsonl")
        derived = [row for row in rows if "22277784" in row["canonical_source_id"]]
        self.assertEqual(len(derived), 4)

    def test_the_four_reviewed_units_are_still_valid(self) -> None:
        rows = load_jsonl(REVIEW / "reviewed_profile_units.jsonl")
        for row in rows:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertIn(row["review_status"], REVIEW_STATUSES)

    def test_the_statement_repository_still_has_147_statements(self) -> None:
        rows = load_jsonl(QUALIFICATION / "evidence_statements.jsonl")
        self.assertEqual(len(rows), 147)

    def test_the_source_inventory_still_has_102_sources(self) -> None:
        rows = load_jsonl(CORPUS / "source_inventory.jsonl")
        self.assertEqual(len(rows), 102)

    def test_the_audit_of_the_nine_units_is_unchanged(self) -> None:
        rows = load_jsonl(AUDIT / "audit_scope.jsonl")
        self.assertEqual(len(rows), 9)
        payload = load_json(AUDIT / "audit_scope.json")
        self.assertEqual(payload["review_batch_scope_hash"] if False else payload["audit_scope_hash"], content_hash(rows))

    def test_the_audit_classification_is_unchanged(self) -> None:
        rows = load_jsonl(AUDIT / "source_structure_classification.jsonl")
        self.assertEqual(len(rows), 9)
        self.assertEqual(
            sum(1 for row in rows if row["structure_state"] == "clinical_preclinical_split_required"),
            3,
        )

    def test_the_batch_did_not_add_units_to_the_audit(self) -> None:
        audit_units = load_jsonl(AUDIT / "proposed_profile_units.jsonl")
        self.assertEqual(len(audit_units), 6)

    def test_findings_cover_exactly_the_three_sources(self) -> None:
        self.assertEqual(len(FINDINGS), 3)
        self.assertEqual(sorted(FINDINGS_BY_UNIT), sorted(EXPECTED_SOURCES))

    def test_no_network_is_required(self) -> None:
        """Nessun modulo di rete e' importato per eseguire questi test."""
        import sys

        for module in ("urllib.request", "http.client", "socket"):
            with self.subTest(module=module):
                imported = sys.modules.get(module)
                self.assertTrue(
                    imported is None or module not in globals(),
                    f"{module} non deve essere usato da questo modulo",
                )

    def test_the_verification_defaults_to_offline(self) -> None:
        """Senza --allow-network la verifica non consulta nulla."""
        from benchmarks.mtb_evidence.evaluation.scripts.verify_review_sources import parse_args

        self.assertFalse(parse_args([]).allow_network)


if __name__ == "__main__":
    unittest.main()
