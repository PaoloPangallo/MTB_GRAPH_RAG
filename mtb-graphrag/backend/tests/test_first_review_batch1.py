"""Provenienza della prima revisione e cecità del secondo revisore.

Tutti offline: leggono artefatti congelati, non aprono connessioni, non toccano
Neo4j e non chiamano LLM.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from backend.pipeline.evidence.corpus_manifest import content_hash
from backend.pipeline.evidence.profile_unit import (
    COHORT_SUPERSEDED,
    NOT_APPLICABLE,
    UNIT_DIMENSIONS,
    UNKNOWN,
    SourceClinicalProfileUnit,
    validate_units,
)
from benchmarks.mtb_evidence.evaluation.first_review_batch1 import (
    COMPLETE_RESISTANCE,
    INTERVENTION_MAPPINGS,
    ORIGINAL_UNIT_ID,
    PACKET_ID,
    RELATIVE_REDUCED_SENSITIVITY,
    REVIEW_METADATA,
    SPLIT_DECISION,
    STATEMENT_DECISIONS,
)
from benchmarks.mtb_evidence.evaluation.scripts.build_first_review_artifacts import (
    check_propagation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW = REPO_ROOT / "benchmarks/mtb_evidence/v3/first_review"
CURATION = REPO_ROOT / "benchmarks/mtb_evidence/v3/priority_curation"

EXPECTED_UNITS = (
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


class TestSourceVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.verification = load_jsonl(REVIEW / f"locator_verification_{PACKET_ID}.jsonl")
        cls.summary = json.loads(
            (REVIEW / f"source_verification_{PACKET_ID}.json").read_text(encoding="utf-8")
        )

    def test_pmid_matches_the_access_manifest(self) -> None:
        access = [
            row
            for row in load_jsonl(CURATION / "source_access_manifest.jsonl")
            if "22277784" in row["pmids"]
        ]
        self.assertEqual(len(access), 1)
        self.assertEqual(self.summary["abstract_sha256"], access[0]["abstract_sha256"])

    def test_every_locator_has_an_explicit_status(self) -> None:
        self.assertEqual(len(self.verification), 10)
        for row in self.verification:
            with self.subTest(locator=row["locator_id"]):
                self.assertIn(
                    row["status"],
                    {"verified", "source_locator_not_verified", "source_not_accessible"},
                )

    def test_match_type_is_recorded_for_every_verified_locator(self) -> None:
        """Una corrispondenza debole non deve poter passare per una esatta."""
        for row in self.verification:
            if row["status"] == "verified":
                with self.subTest(locator=row["locator_id"]):
                    self.assertIn(
                        row["match_type"],
                        {"exact", "prefix", "interpolated", "label", "inline_reference"},
                    )

    def test_document_hash_is_recorded(self) -> None:
        self.assertRegex(self.summary["full_text_document_sha256"], r"^[0-9a-f]{64}$")

    def test_full_text_is_not_stored(self) -> None:
        for row in self.verification:
            with self.subTest(locator=row["locator_id"]):
                self.assertNotIn("document_text", row)
                self.assertNotIn("full_text", row)


class TestSplitUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(REVIEW / "reviewed_profile_units.jsonl")
        cls.superseded = load_jsonl(REVIEW / "superseded_profile_units.jsonl")

    def test_original_unit_is_preserved(self) -> None:
        self.assertEqual(len(self.superseded), 1)
        self.assertEqual(self.superseded[0]["profile_unit_id"], ORIGINAL_UNIT_ID)

    def test_original_unit_is_not_propagatable(self) -> None:
        original = self.superseded[0]
        self.assertEqual(original["cohort_state"], COHORT_SUPERSEDED)
        self.assertFalse(original["is_propagatable"])

    def test_original_unit_points_to_its_successors(self) -> None:
        self.assertEqual(
            sorted(self.superseded[0]["superseded_by"]), sorted(EXPECTED_UNITS)
        )

    def test_four_derived_units_exist(self) -> None:
        self.assertEqual(len(self.units), 4)
        self.assertEqual(
            sorted(unit["profile_unit_id"] for unit in self.units), sorted(EXPECTED_UNITS)
        )

    def test_unit_identity_is_deterministic(self) -> None:
        first = content_hash(self.units)
        second = content_hash(load_jsonl(REVIEW / "reviewed_profile_units.jsonl"))
        self.assertEqual(first, second)

    def test_every_derived_unit_points_back(self) -> None:
        for unit in self.units:
            with self.subTest(unit=unit["profile_unit_id"]):
                self.assertEqual(unit["supersedes"], ORIGINAL_UNIT_ID)

    def test_provenance_is_complete(self) -> None:
        for unit in self.units:
            fields = {item["field_name"] for item in unit["provenance"]}
            for dimension in unit["known_dimensions"]:
                with self.subTest(unit=unit["profile_unit_id"], dimension=dimension):
                    self.assertIn(dimension, fields)

    def test_provenance_names_the_review_method(self) -> None:
        """La provenance deve dire come il valore e' stato prodotto, non solo da chi."""
        for unit in self.units:
            for item in unit["provenance"]:
                with self.subTest(unit=unit["profile_unit_id"], field=item["field_name"]):
                    self.assertIn("llm_assisted", item["asserted_by"])
                    self.assertTrue(item["span_hash"])

    def test_clinical_and_preclinical_are_distinct(self) -> None:
        clinical = [unit for unit in self.units if unit["is_clinical"]]
        preclinical = [unit for unit in self.units if unit["is_preclinical"]]
        self.assertEqual(len(clinical), 1)
        self.assertEqual(len(preclinical), 3)

    def test_clinical_population_does_not_reach_the_cell_models(self) -> None:
        for unit in self.units:
            if unit["is_preclinical"]:
                with self.subTest(unit=unit["profile_unit_id"]):
                    self.assertNotIn("patient", unit["population"].casefold())
                    self.assertEqual(unit["population"], "engineered Ba/F3 cell models")

    def test_preclinical_setting_does_not_reach_the_patient_cohort(self) -> None:
        clinical = next(unit for unit in self.units if unit["is_clinical"])
        self.assertNotIn("preclinical", clinical["setting"].casefold())
        self.assertIn("crizotinib", clinical["setting"].casefold())

    def test_cell_model_units_declare_therapy_line_not_applicable(self) -> None:
        """`not_applicable` non e' `unknown`: la domanda non si pone."""
        for unit in self.units:
            if unit["is_preclinical"]:
                with self.subTest(unit=unit["profile_unit_id"]):
                    self.assertEqual(unit["therapy_line"], NOT_APPLICABLE)
                    self.assertIn("therapy_line", unit["not_applicable_dimensions"])
                    self.assertNotIn("therapy_line", unit["known_dimensions"])

    def test_clinical_unknowns_stay_unknown(self) -> None:
        clinical = next(unit for unit in self.units if unit["is_clinical"])
        for dimension in ("stage", "therapy_line", "resection_status", "regimen"):
            with self.subTest(dimension=dimension):
                self.assertEqual(clinical[dimension], UNKNOWN)
                self.assertEqual(clinical["field_decisions"][dimension], "unknown")

    def test_unknown_and_not_applicable_are_never_conflated(self) -> None:
        for unit in self.units:
            for dimension in UNIT_DIMENSIONS:
                decision = unit["field_decisions"].get(dimension)
                value = unit[dimension]
                if decision == "not_applicable":
                    with self.subTest(unit=unit["profile_unit_id"], dimension=dimension):
                        # Le dimensioni a lista non possono portare il sentinella
                        # stringa: resta la decisione a distinguerle.
                        self.assertIn(value, (NOT_APPLICABLE, []))
                        self.assertIn(dimension, unit["not_applicable_dimensions"])
                        self.assertNotIn(dimension, unit["known_dimensions"])
                elif decision == "unknown":
                    with self.subTest(unit=unit["profile_unit_id"], dimension=dimension):
                        self.assertIn(value, (UNKNOWN, []))
                        self.assertNotIn(dimension, unit["not_applicable_dimensions"])

    def test_units_validate(self) -> None:
        rebuilt = [
            SourceClinicalProfileUnit(
                profile_unit_id=unit["profile_unit_id"],
                canonical_source_id=unit["canonical_source_id"],
                unit_type=unit["unit_type"],
                cohort_state=unit["cohort_state"],
                extraction_status=unit["extraction_status"],
                review_status=unit["review_status"],
                requires_human_review=unit["requires_human_review"],
            )
            for unit in self.units
        ]
        self.assertEqual(validate_units(rebuilt), [])


class TestPropagationGuard(unittest.TestCase):
    """Il controllo deve fallire su dati scorretti, altrimenti non controlla nulla."""

    def test_clinical_unit_citing_a_cell_line_drug_is_rejected(self) -> None:
        bad = SourceClinicalProfileUnit(
            profile_unit_id="PU-bad",
            canonical_source_id="PMID:1",
            unit_type="clinical_observational_cohort",
            population="18 patients treated with 17-AAG",
        )
        self.assertTrue(check_propagation([bad], []))

    def test_preclinical_unit_with_a_patient_population_is_rejected(self) -> None:
        bad = SourceClinicalProfileUnit(
            profile_unit_id="PU-bad",
            canonical_source_id="PMID:1",
            unit_type="preclinical_in_vitro",
            population="18 patients",
        )
        self.assertTrue(check_propagation([bad], []))

    def test_preclinical_setting_on_a_clinical_cohort_is_rejected(self) -> None:
        bad = SourceClinicalProfileUnit(
            profile_unit_id="PU-bad",
            canonical_source_id="PMID:1",
            unit_type="clinical_observational_cohort",
            setting="preclinical modelling",
        )
        self.assertTrue(check_propagation([bad], []))

    def test_preclinical_only_statement_must_deny_clinical_response(self) -> None:
        unit = SourceClinicalProfileUnit(
            profile_unit_id="PU-pre",
            canonical_source_id="PMID:1",
            unit_type="preclinical_in_vitro",
        )
        decision = {
            "statement_id": "S1",
            "profile_unit_ids": ("PU-pre",),
            "clinical_response_observed": None,
        }
        self.assertTrue(check_propagation([unit], [decision]))

    def test_the_real_units_pass(self) -> None:
        units = load_jsonl(REVIEW / "reviewed_profile_units.jsonl")
        rebuilt = [
            SourceClinicalProfileUnit(
                profile_unit_id=unit["profile_unit_id"],
                canonical_source_id=unit["canonical_source_id"],
                unit_type=unit["unit_type"],
                population=unit["population"],
                setting=unit["setting"],
                therapy_line=unit["therapy_line"],
                stage=unit["stage"],
                resection_status=unit["resection_status"],
                prior_therapies=tuple(unit["prior_therapies"]),
            )
            for unit in units
        ]
        self.assertEqual(check_propagation(rebuilt, STATEMENT_DECISIONS), [])


class TestStatementDecisions(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.decisions = load_jsonl(REVIEW / "statement_first_review_decisions.jsonl")

    def test_ten_statements_are_decided(self) -> None:
        self.assertEqual(len(self.decisions), 10)

    def test_eight_valid_decisions(self) -> None:
        valid = [
            row for row in self.decisions if row["first_review_link_status"] == "valid_link"
        ]
        self.assertEqual(len(valid), 8)

    def test_two_partial_decisions(self) -> None:
        partial = [
            row for row in self.decisions if row["first_review_link_status"] == "partial_link"
        ]
        self.assertEqual(len(partial), 2)

    def test_preclinical_only_statements_deny_clinical_response(self) -> None:
        for row in self.decisions:
            if row["evidence_design"] == "preclinical_in_vitro":
                with self.subTest(statement=row["statement_id"]):
                    self.assertIs(row["clinical_response_observed"], False)

    def test_mixed_statements_keep_both_components(self) -> None:
        mixed = [
            row for row in self.decisions if row["evidence_design"] == "mixed_clinical_and_preclinical"
        ]
        self.assertGreater(len(mixed), 0)
        for row in mixed:
            with self.subTest(statement=row["statement_id"]):
                self.assertTrue(row["has_clinical_component"])
                self.assertTrue(row["has_preclinical_component"])

    def test_relative_sensitivity_is_distinct_from_complete_resistance(self) -> None:
        qualified = [row for row in self.decisions if row["resistance_qualifier"]]
        self.assertGreater(len(qualified), 0)
        for row in qualified:
            with self.subTest(statement=row["statement_id"]):
                self.assertEqual(row["resistance_qualifier"], RELATIVE_REDUCED_SENSITIVITY)
                self.assertNotEqual(row["resistance_qualifier"], COMPLETE_RESISTANCE)

    def test_ch5424802_is_recorded_as_a_mapping(self) -> None:
        row = next(
            item for item in self.decisions if item["statement_id"] == "ES-V2-evidence-1347"
        )
        self.assertEqual(row["intervention_mapping"], "CH5424802 -> alectinib")
        self.assertEqual(row["mapping_status"], "requires_terminology_verification")

    def test_mapping_is_not_treated_as_a_literal_source_string(self) -> None:
        """La fonte del 2012 usa il codice di sviluppo, non il nome commerciale."""
        mappings = load_jsonl(REVIEW / "intervention_mappings.jsonl")
        alectinib = next(item for item in mappings if item["source_term"] == "CH5424802")
        self.assertFalse(alectinib["literal_string_present_in_source"])
        self.assertEqual(
            alectinib["mapping_status"], "requires_source_or_terminology_verification"
        )

    def test_no_decision_is_evaluable_for_final_metrics(self) -> None:
        for row in self.decisions:
            with self.subTest(statement=row["statement_id"]):
                self.assertFalse(row["is_evaluable_for_final_metrics"])
                self.assertFalse(row["independent_review"])
                self.assertFalse(row["clinical_reviewer"])

    def test_mutation_is_recorded_for_the_late_statements(self) -> None:
        for statement_id in (
            "ES-V2-evidence-441",
            "ES-V2-evidence-442",
            "ES-V2-evidence-443",
            "ES-V2-evidence-444",
        ):
            row = next(item for item in self.decisions if item["statement_id"] == statement_id)
            with self.subTest(statement=statement_id):
                self.assertTrue(row["mutation"])
                self.assertTrue(row["has_clinical_component"])
                self.assertTrue(row["has_preclinical_component"])


class TestGoldStaysProvisional(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gold = load_jsonl(REVIEW / "provisional_gold.jsonl")
        cls.reviewed = [row for row in cls.gold if row.get("review_stage") == "first_review_complete"]

    def test_ten_records_carry_the_first_review(self) -> None:
        self.assertEqual(len(self.reviewed), 10)

    def test_gold_is_still_provisional(self) -> None:
        for row in self.reviewed:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_first_review")

    def test_is_evaluable_is_false_everywhere(self) -> None:
        for row in self.gold:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertFalse(row["is_evaluable"])

    def test_link_status_lives_outside_final_status(self) -> None:
        """La decisione di prima revisione non diventa il verdetto."""
        for row in self.reviewed:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertIn(
                    row["first_review_annotation"]["link_status"],
                    {"valid_link", "partial_link"},
                )
                self.assertNotIn(row["final_status"], {"valid_link", "partial_link"})

    def test_second_review_is_still_empty(self) -> None:
        for row in self.gold:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertIsNone(row["second_annotator"])
                self.assertIsNone(row["adjudication"])

    def test_agreement_is_null(self) -> None:
        for row in self.gold:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertIsNone(row["agreement"])

    def test_reviewed_records_require_a_second_review(self) -> None:
        for row in self.reviewed:
            with self.subTest(gold=row["gold_link_id"]):
                self.assertTrue(row["requires_second_review"])


class TestSecondReviewStaysBlind(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        mapping = json.loads(
            (CURATION / "blind_id_mapping.json").read_text(encoding="utf-8")
        )
        row = next(
            item
            for item in mapping["mapping"]
            if item["first_review_blind_id"] == PACKET_ID
        )
        cls.second_id = row["second_review_blind_id"]
        cls.path = CURATION / "annotation_packets/second_review" / f"{cls.second_id}.json"
        cls.text = cls.path.read_text(encoding="utf-8")
        cls.packet = json.loads(cls.text)

    def test_packet_exists_and_is_flagged_blind(self) -> None:
        self.assertTrue(self.path.is_file())
        self.assertFalse(self.packet["contains_first_review_decision"])
        self.assertFalse(self.packet["contains_clinical_gold"])
        self.assertFalse(self.packet["contains_metric_impact"])

    def test_packet_does_not_name_the_first_reviewer(self) -> None:
        self.assertNotIn("paolo", self.text.casefold())

    def test_packet_does_not_contain_the_four_proposed_units(self) -> None:
        for unit_id in EXPECTED_UNITS:
            with self.subTest(unit=unit_id):
                self.assertNotIn(unit_id, self.text)

    def test_packet_does_not_contain_the_first_review_rationale(self) -> None:
        for decision in STATEMENT_DECISIONS:
            with self.subTest(statement=decision["statement_id"]):
                self.assertNotIn(decision["rationale"], self.text)

    def test_link_statuses_appear_only_as_allowed_vocabulary(self) -> None:
        """`valid_link` compare, ma come elenco dei valori ammessi.

        E' necessario: il secondo revisore deve sapere che cosa puo' rispondere.
        Il test verifica che non compaia in nessun'altra chiave.
        """
        for key, value in self.packet.items():
            if key == "allowed_values":
                continue
            with self.subTest(key=key):
                self.assertNotIn("valid_link", json.dumps(value))

    def test_second_blind_id_is_not_derived_from_the_first(self) -> None:
        self.assertNotEqual(self.second_id, PACKET_ID)
        self.assertNotIn(PACKET_ID.removeprefix("BA-"), self.second_id)


class TestMetricsAndRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.metrics = json.loads(
            (REVIEW / "first_review_metrics.json").read_text(encoding="utf-8")
        )

    def test_descriptive_counters_match_the_artifacts(self) -> None:
        self.assertEqual(self.metrics["first_review_packets_completed"], 1)
        self.assertEqual(self.metrics["first_review_statements_reviewed"], 10)
        self.assertEqual(self.metrics["first_review_profile_units_created"], 4)
        self.assertEqual(self.metrics["first_review_valid_link_decisions"], 8)
        self.assertEqual(self.metrics["first_review_partial_link_decisions"], 2)

    def test_no_final_metric_is_calculated(self) -> None:
        for key in (
            "linking_precision",
            "linking_recall",
            "linking_f1",
            "inter_annotator_agreement",
            "final_accuracy",
        ):
            with self.subTest(metric=key):
                self.assertEqual(self.metrics[key], "not_calculated")

    def test_coverage_is_split_by_review_stage(self) -> None:
        coverage = self.metrics["coverage_by_review_stage"]
        self.assertGreater(coverage["first_review_proposed"], 0)
        self.assertEqual(coverage["second_review_confirmed"], 0)
        self.assertEqual(coverage["final_adjudicated"], 0)

    def test_provenance_completeness_holds(self) -> None:
        self.assertEqual(self.metrics["qualifier_provenance_completeness"], 1.0)

    def test_review_metadata_never_claims_more_than_it_is(self) -> None:
        self.assertFalse(REVIEW_METADATA["independent_review"])
        self.assertFalse(REVIEW_METADATA["clinical_reviewer"])
        self.assertFalse(REVIEW_METADATA["is_evaluable_for_final_metrics"])
        self.assertTrue(REVIEW_METADATA["requires_second_independent_review"])
        self.assertEqual(REVIEW_METADATA["review_status"], "first_review_complete")

    def test_no_forbidden_status_is_claimed(self) -> None:
        forbidden = {
            "clinical_review_complete",
            "independent_review_complete",
            "second_review_complete",
            "adjudicated",
            "frozen",
        }
        text = json.dumps(REVIEW_METADATA) + json.dumps(SPLIT_DECISION)
        for status in forbidden:
            with self.subTest(status=status):
                self.assertNotIn(status, text)

    def test_previous_curation_artifacts_are_untouched(self) -> None:
        units = load_jsonl(CURATION / "unresolved_profile_units.jsonl")
        original = [row for row in units if row["profile_unit_id"] == ORIGINAL_UNIT_ID]
        self.assertEqual(len(original), 1)
        self.assertNotEqual(original[0]["cohort_state"], COHORT_SUPERSEDED)

    def test_the_147_statements_are_still_present(self) -> None:
        statements = load_jsonl(
            REPO_ROOT / "benchmarks/mtb_evidence/v3/qualification/evidence_statements.jsonl"
        )
        self.assertEqual(len(statements), 147)

    def test_artifacts_contain_no_credentials(self) -> None:
        for path in sorted(REVIEW.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
            for needle in ("authorization", "api_key", "api-key", "bearer ", "password"):
                with self.subTest(path=path.name, needle=needle):
                    self.assertNotIn(needle, text)


if __name__ == "__main__":
    unittest.main()
