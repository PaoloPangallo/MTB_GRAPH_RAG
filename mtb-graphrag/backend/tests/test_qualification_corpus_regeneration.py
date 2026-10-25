"""Rigenerazione versionata del qualification corpus: versioni, hash, blinding.

Tutti offline. Il file protegge le cose che una rigenerazione puo' rompere senza
produrre un errore, perche' il risultato resta un corpus sintatticamente valido:

- il corpus precedente riscritto invece che superato;
- l'impronta del grafo congelato cambiata da una fase che non tocca il grafo;
- un flag serializzato trasportato invece che ricalcolato — e quindi un dato
  vecchio che sopravvive alla migrazione che esiste per eliminarlo;
- una parent sostituita o una proposta respinta rientrate fra le unita' attive;
- un qualificatore `prototype_only` diventato filtrabile;
- una decisione candidate copiata nel gold;
- un `not_separable` risolto in un valore concreto;
- e la piu' silenziosa di tutte: un risultato che cambia se si legge gli
  artefatti in un altro ordine, cioe' una precedenza che non e' una precedenza.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.pipeline.evidence.corpus_regeneration import (
    DERIVED_POLICY_FIELDS,
    NON_HASHED_FIELDS,
    READY_FOR_PROTOTYPE,
    REGENERATION_STATUSES,
    CaseLevelGeneralizedError,
    DuplicateActiveIdentityError,
    HardFilterWithoutFinalError,
    NotSeparableCollapseError,
    SnapshotFingerprintChangedError,
    StaleSerializedFlagError,
    SupersededUnitActiveError,
    UnverifiedMappingPromotedError,
    corpus_fingerprint,
    merge_records,
    migrate_policy,
    semantic_identity,
    stable_hash,
    strip_volatile,
    validate_active_units,
    validate_decisions,
    validate_fingerprints,
    validate_gold,
    validate_integrity,
    validate_mappings,
    validate_policy_fields,
)
from backend.pipeline.evidence.profile_unit import PROFILE_UNIT_VERSION
from backend.pipeline.evidence.propagation_policy import FINAL, NONE, PROTOTYPE_ONLY

REPO_ROOT = Path(__file__).resolve().parents[2]
V3 = REPO_ROOT / "benchmarks/mtb_evidence/v3"
CORPUS = V3 / "qualification_corpus_v2"
PREVIOUS_CORPUS = V3 / "qualification_corpus"
PREVIOUS_VIEWS = V3 / "qualification"
SECOND_REVIEW = V3 / "priority_curation/annotation_packets/second_review"
SCHEMA = REPO_ROOT / "schemas/qualification_corpus_manifest_v2.schema.json"

FIXED_TIMESTAMP = "2026-07-24T18:00:00+00:00"
FROZEN_KG = "ffc97bc7c660f19478c33d28d1599b70e442525f0fae34b512e5efbf0796a9ae"

REVIEWED_SOURCES = ("22277784", "31358542", "22235099", "23344087")


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


def unit(**overrides) -> dict:
    payload = {
        "profile_unit_id": "PU-x",
        "canonical_source_id": "PMID:1",
        "cohort_id": "cohort-1",
        "review_status": "awaiting_source_review",
        "cohort_state": "single_cohort",
    }
    payload.update(overrides)
    return payload


# ── versionamento ─────────────────────────────────────────────────────────────


class TestVersioning(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_json(CORPUS / "qualification_corpus_manifest.json")
        cls.previous = load_json(PREVIOUS_CORPUS / "qualification_corpus_manifest.json")

    def test_the_new_version_is_distinct(self) -> None:
        self.assertNotEqual(self.manifest["corpus_version"], self.previous["corpus_version"])
        self.assertEqual(self.manifest["corpus_version"], "qualification_corpus/2.0")

    def test_the_manifest_points_at_the_previous_version(self) -> None:
        self.assertEqual(
            self.manifest["previous_corpus_version"], self.previous["corpus_version"]
        )
        self.assertTrue((REPO_ROOT / self.manifest["previous_corpus_manifest"]).is_file())
        self.assertTrue((REPO_ROOT / self.manifest["previous_corpus_directory"]).is_dir())

    def test_the_previous_corpus_is_untouched(self) -> None:
        # Il puntatore e' non distruttivo: la versione precedente resta leggibile
        # esattamente com'era, e il manifest la cita invece di sostituirla.
        self.assertEqual(self.previous["corpus_version"], "qualification_corpus/1.0")
        self.assertEqual(len(load_jsonl(PREVIOUS_CORPUS / "source_profile_units.jsonl")), 102)
        self.assertEqual(len(load_jsonl(PREVIOUS_VIEWS / "qualification_links.jsonl")), 10)

    def test_the_frozen_kg_fingerprint_is_unchanged(self) -> None:
        self.assertEqual(self.manifest["frozen_kg_snapshot_fingerprint"], FROZEN_KG)
        self.assertEqual(self.previous["snapshot_fingerprint"], FROZEN_KG)

    def test_the_corpus_fingerprint_changed(self) -> None:
        self.assertNotEqual(
            self.manifest["qualification_corpus_fingerprint"],
            self.manifest["previous_corpus_fingerprint"],
        )

    def test_the_corpus_fingerprint_is_not_a_kg_snapshot(self) -> None:
        # Chiamare la seconda «nuovo snapshot del KG» direbbe che il grafo e'
        # cambiato, e il grafo non e' stato toccato.
        self.assertNotEqual(
            self.manifest["qualification_corpus_fingerprint"],
            self.manifest["frozen_kg_snapshot_fingerprint"],
        )
        self.assertNotEqual(
            self.manifest["qualified_evidence_snapshot_fingerprint"],
            self.manifest["frozen_kg_snapshot_fingerprint"],
        )

    def test_the_required_manifest_fields_are_present(self) -> None:
        for key in (
            "corpus_version",
            "previous_corpus_version",
            "previous_corpus_fingerprint",
            "qualification_corpus_fingerprint",
            "frozen_kg_snapshot_fingerprint",
            "regeneration_reason",
            "migration_id",
            "schema_versions",
            "propagation_policy_version",
            "generated_at",
            "source_sha",
            "regeneration_status",
        ):
            with self.subTest(field=key):
                self.assertIn(key, self.manifest)
                self.assertTrue(self.manifest[key])

    def test_the_status_is_ready_for_prototype_and_never_frozen(self) -> None:
        self.assertIn(self.manifest["regeneration_status"], REGENERATION_STATUSES)
        self.assertEqual(self.manifest["regeneration_status"], READY_FOR_PROTOTYPE)
        self.assertNotEqual(self.manifest["regeneration_status"], "frozen")

    def test_the_manifest_validates_against_the_schema(self) -> None:
        try:
            import jsonschema
        except ImportError:  # pragma: no cover - dipendenza opzionale
            self.skipTest("jsonschema non installato")
        schema = load_json(SCHEMA)
        jsonschema.validators.validator_for(schema)(schema).validate(self.manifest)

    def test_the_manifest_declares_what_is_not_hashed(self) -> None:
        self.assertEqual(self.manifest["non_hashed_fields"], list(NON_HASHED_FIELDS))
        self.assertIn("generated_at", self.manifest["non_hashed_fields"])

    def test_the_fingerprint_is_recomputable_from_the_declared_inputs(self) -> None:
        components = {
            key: self.manifest["component_hashes"][key]
            for key in self.manifest["fingerprint_inputs"]
        }
        self.assertEqual(
            corpus_fingerprint(components),
            self.manifest["qualification_corpus_fingerprint"],
        )


# ── migrazione della politica ─────────────────────────────────────────────────


class TestPolicyMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(CORPUS / "source_profile_units.jsonl")
        cls.active = load_jsonl(CORPUS / "active_source_profile_units.jsonl")
        cls.scope = load_json(CORPUS / "qualification_scope.json")
        cls.stale = load_jsonl(CORPUS / "obsolete_serialized_flags.jsonl")

    def test_the_obsolete_flags_are_gone(self) -> None:
        self.assertEqual(self.scope["obsolete_serialized_flags_after"], 0)
        self.assertGreater(self.scope["obsolete_serialized_flags_before"], 0)

    def test_the_derived_count_matches_the_recorded_rows(self) -> None:
        # Il conteggio non e' codificato: viene derivato dagli artefatti, e questo
        # test verifica che il numero e le righe raccontino la stessa cosa.
        self.assertEqual(
            self.scope["obsolete_serialized_flags_before"], len(self.stale)
        )
        self.assertEqual(
            sum(self.scope["obsolete_serialized_flags_by_artifact"].values()),
            len(self.stale),
        )

    def test_no_flag_was_carried_over_without_recomputation(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(migrate_policy(row).stale_serialized_fields, ())

    def test_the_policy_is_applied_to_every_unit(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                for key in DERIVED_POLICY_FIELDS:
                    self.assertIn(key, row)

    def test_no_unit_is_final(self) -> None:
        self.assertEqual(
            [u["profile_unit_id"] for u in self.units if u["propagation_eligibility"] == FINAL],
            [],
        )
        self.assertEqual([u for u in self.units if u["is_propagatable"]], [])

    def test_no_qualifier_is_hard_filterable(self) -> None:
        self.assertEqual([u for u in self.units if u["is_hard_filterable"]], [])

    def test_first_reviews_are_prototype_only(self) -> None:
        reviewed = [
            u
            for u in self.active
            if u["review_status"] in ("first_review_complete", "human_reviewed")
        ]
        self.assertTrue(reviewed)
        for row in reviewed:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["propagation_eligibility"], PROTOTYPE_ONLY)
                self.assertTrue(row["may_display_qualifiers"])
                self.assertFalse(row["is_propagatable"])
                self.assertTrue(row["requires_second_independent_review"])

    def test_unreviewed_units_are_none(self) -> None:
        for row in self.units:
            if row["review_status"] not in ("awaiting_source_review", "awaiting_first_review"):
                continue
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["propagation_eligibility"], NONE)
                self.assertFalse(row["is_propagatable"])
                self.assertFalse(row["is_evaluable"])

    def test_a_transported_flag_is_rejected(self) -> None:
        found = validate_policy_fields([unit(is_propagatable=True)])
        self.assertTrue(found)
        with self.assertRaises(StaleSerializedFlagError):
            found[0].raise_it()

    def test_a_hard_filterable_prototype_is_rejected(self) -> None:
        found = validate_policy_fields(
            [
                unit(
                    review_status="first_review_complete",
                    propagation_eligibility=PROTOTYPE_ONLY,
                    is_hard_filterable=True,
                )
            ]
        )
        self.assertTrue(any(isinstance(f.error_type, type) for f in found))
        with self.assertRaises(HardFilterWithoutFinalError):
            next(
                f for f in found if f.error_type is HardFilterWithoutFinalError
            ).raise_it()


# ── revisioni integrate ───────────────────────────────────────────────────────


class TestIntegratedReviews(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.active = by_id(load_jsonl(CORPUS / "active_source_profile_units.jsonl"))
        cls.historical = by_id(load_jsonl(CORPUS / "historical_source_profile_units.jsonl"))
        cls.decisions = load_jsonl(CORPUS / "review_decisions.jsonl")
        cls.manifest = load_json(CORPUS / "qualification_corpus_manifest.json")

    def _active_for(self, pmid: str) -> list[str]:
        return sorted(k for k in self.active if pmid in k)

    def _historical_for(self, pmid: str) -> list[str]:
        return sorted(k for k in self.historical if pmid in k)

    def test_all_four_reviews_are_declared_integrated(self) -> None:
        self.assertEqual(
            sorted(self.manifest["integrated_reviews"]),
            sorted(f"PMID:{pmid}" for pmid in REVIEWED_SOURCES),
        )

    def test_22277784_keeps_one_clinical_and_three_preclinical(self) -> None:
        active = self._active_for("22277784")
        self.assertEqual(len(active), 4)
        clinical = [k for k in active if self.active[k]["is_clinical"]]
        self.assertEqual(len(clinical), 1)
        self.assertEqual(len([k for k in active if self.active[k]["is_preclinical"]]), 3)
        self.assertIn("PU-PMID-22277784-cohort-1", self.historical)

    def test_31358542_keeps_one_clinical_unit_and_two_rejected_proposals(self) -> None:
        active = self._active_for("31358542")
        self.assertEqual(active, ["PU-PMID-31358542-clinical-cohort"])
        for proposal in (
            "PU-PMID-31358542-clinical-component",
            "PU-PMID-31358542-preclinical-component",
        ):
            with self.subTest(proposal=proposal):
                self.assertIn(proposal, self.historical)
                self.assertFalse(self.historical[proposal]["is_active"])

    def test_31358542_has_no_active_preclinical_unit(self) -> None:
        for unit_id in self._active_for("31358542"):
            self.assertFalse(self.active[unit_id]["is_preclinical"])

    def test_22235099_keeps_four_units_and_the_consolidation(self) -> None:
        active = self._active_for("22235099")
        self.assertEqual(
            active,
            [
                "PU-PMID-22235099-clinical-cohort",
                "PU-PMID-22235099-cuto1-comparative",
                "PU-PMID-22235099-engineered-isogenic-models",
                "PU-PMID-22235099-h3122-kras-engineered",
            ],
        )
        consolidated = self.active["PU-PMID-22235099-engineered-isogenic-models"]
        self.assertEqual(consolidated["model_instance_count"], 2)
        for replaced in (
            "PU-PMID-22235099-baf3-engineered",
            "PU-PMID-22235099-nih3t3-engineered",
        ):
            with self.subTest(unit=replaced):
                self.assertIn(replaced, self.historical)
                self.assertFalse(self.historical[replaced]["is_active"])

    def test_22235099_keeps_cuto1_distinct_from_the_clinical_case(self) -> None:
        cuto1 = self.active["PU-PMID-22235099-cuto1-comparative"]
        self.assertEqual(cuto1["derived_from_clinical_case"], "patient_10")
        self.assertFalse(cuto1["derivation_is_identity"])
        self.assertEqual(cuto1["biomarker_requirements"], [])
        self.assertEqual(cuto1["cross_context_biomarker_propagation"], "forbidden")

    def test_22235099_keeps_the_negative_experiment_negative(self) -> None:
        negative = self.active["PU-PMID-22235099-h3122-kras-engineered"]
        self.assertEqual(negative["assertion_polarity"], "does_not_support")
        self.assertEqual(negative["experiment_role"], "negative_experiment")
        self.assertFalse(negative["cohort_generalizable"])

    def test_23344087_keeps_two_units_and_two_unapproved_hypotheses(self) -> None:
        active = self._active_for("23344087")
        self.assertEqual(
            active,
            [
                "PU-PMID-23344087-clinical-cohort",
                "PU-PMID-23344087-preclinical-unresolved-panel",
            ],
        )
        for proposal in (
            "PU-PMID-23344087-engineered-clones",
            "PU-PMID-23344087-patient-derived",
        ):
            with self.subTest(proposal=proposal):
                self.assertIn(proposal, self.historical)
                self.assertFalse(self.historical[proposal]["is_active"])

    def test_23344087_panel_stays_unresolved(self) -> None:
        panel = self.active["PU-PMID-23344087-preclinical-unresolved-panel"]
        self.assertEqual(panel["preclinical_model_composition"], "not_separable")
        self.assertEqual(panel["component_to_statement_mapping"], "not_separable")
        self.assertEqual(panel["cellular_background_of_mutant_clones"], "unknown")
        self.assertEqual(panel["source_basis"], "abstract_only")
        self.assertEqual(panel["structural_confidence"], "partial")
        self.assertFalse(panel["full_text_verified"])

    def test_the_statement_decisions_survive(self) -> None:
        by_statement = {str(row["statement_id"]): row for row in self.decisions}
        expected = {
            "ES-V2-evidence-100003": "candidate_invalid",
            "ES-V2-evidence-100004": "candidate_partial",
            "ES-V2-evidence-764": "candidate_valid",
            "ES-V2-evidence-4288": "candidate_partial",
            "ES-V2-evidence-766": "candidate_partial",
            "ES-V2-evidence-765": "candidate_partial",
            "ES-V2-evidence-767": "candidate_ambiguous",
        }
        for statement_id, status in expected.items():
            with self.subTest(statement=statement_id):
                self.assertEqual(
                    by_statement[statement_id]["first_review_candidate_status"], status
                )

    def test_the_case_level_annotations_survive(self) -> None:
        granularity = Counter(
            str(row.get("evidence_granularity") or "") for row in self.decisions
        )
        self.assertEqual(granularity["case_level"], 2)
        self.assertEqual(granularity["named_patient_subset"], 1)
        subset = next(
            row
            for row in self.decisions
            if row.get("evidence_granularity") == "named_patient_subset"
        )
        self.assertEqual(subset["case_identifiers"], ["patient_7", "patient_8"])

    def test_the_history_is_preserved_for_every_reviewed_source(self) -> None:
        for pmid in REVIEWED_SOURCES:
            with self.subTest(pmid=pmid):
                self.assertIn(f"PU-PMID-{pmid}-cohort-1", self.historical)


# ── unita' ────────────────────────────────────────────────────────────────────


class TestUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.units = load_jsonl(CORPUS / "source_profile_units.jsonl")
        cls.active = load_jsonl(CORPUS / "active_source_profile_units.jsonl")
        cls.historical = load_jsonl(CORPUS / "historical_source_profile_units.jsonl")

    def test_active_and_historical_partition_the_corpus(self) -> None:
        self.assertEqual(len(self.active) + len(self.historical), len(self.units))
        self.assertEqual(
            {u["profile_unit_id"] for u in self.active}
            & {u["profile_unit_id"] for u in self.historical},
            set(),
        )

    def test_no_active_unit_is_superseded(self) -> None:
        for row in self.active:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue(row["is_active"])
                self.assertFalse(row.get("superseded_by"))

    def test_no_rejected_proposal_is_active(self) -> None:
        for row in self.active:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertFalse(str(row["review_status"]).startswith("rejected"))
                self.assertNotIn("replaced_by", str(row["review_status"]))

    def test_no_duplicate_semantic_identity(self) -> None:
        identities = Counter(semantic_identity(row) for row in self.active)
        self.assertEqual([i for i, n in identities.items() if n > 1], [])
        self.assertEqual(validate_active_units(self.active), [])

    def test_every_unit_carries_the_current_schema_version(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertEqual(row["schema_version"], PROFILE_UNIT_VERSION)

    def test_every_unit_records_the_layers_that_produced_it(self) -> None:
        for row in self.units:
            with self.subTest(unit=row["profile_unit_id"]):
                self.assertTrue(row["contributing_layers"])
                self.assertIn(row["canonical_layer"], row["contributing_layers"])

    def test_provenance_is_complete_for_known_dimensions(self) -> None:
        self.assertEqual(validate_integrity(self.units), [])

    def test_a_superseded_unit_declared_active_is_rejected(self) -> None:
        found = validate_active_units([unit(superseded_by=["PU-y"])])
        self.assertTrue(found)
        with self.assertRaises(SupersededUnitActiveError):
            found[0].raise_it()

    def test_two_units_for_the_same_cohort_are_rejected(self) -> None:
        found = validate_active_units(
            [unit(profile_unit_id="PU-a"), unit(profile_unit_id="PU-b")]
        )
        self.assertTrue(found)
        with self.assertRaises(DuplicateActiveIdentityError):
            found[0].raise_it()

    def test_a_resolved_not_separable_is_rejected(self) -> None:
        found = validate_integrity(
            [unit(preclinical_model_composition="SNU-2535 e cloni derivati")]
        )
        self.assertTrue(found)
        with self.assertRaises(NotSeparableCollapseError):
            found[0].raise_it()


# ── link e viste ──────────────────────────────────────────────────────────────


class TestLinksAndViews(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.links = load_jsonl(CORPUS / "qualification_links.jsonl")
        cls.views = load_jsonl(CORPUS / "qualified_evidence_views.jsonl")
        cls.active = {
            row["profile_unit_id"]
            for row in load_jsonl(CORPUS / "active_source_profile_units.jsonl")
        }
        cls.historical = {
            row["profile_unit_id"]
            for row in load_jsonl(CORPUS / "historical_source_profile_units.jsonl")
        }
        cls.statements = load_jsonl(CORPUS / "evidence_statements.jsonl")

    def test_links_point_only_at_active_units(self) -> None:
        for link in self.links:
            with self.subTest(link=link["qualification_link_id"]):
                self.assertIn(link["source_profile_unit_id"], self.active)
                self.assertNotIn(link["source_profile_unit_id"], self.historical)
                self.assertTrue(link["unit_is_active"])

    def test_no_link_allows_hard_filtering(self) -> None:
        for link in self.links:
            with self.subTest(link=link["qualification_link_id"]):
                self.assertFalse(link["hard_filter_allowed"])

    def test_no_none_qualifier_is_applied(self) -> None:
        for link in self.links:
            if link["propagation_eligibility"] != NONE:
                continue
            with self.subTest(link=link["qualification_link_id"]):
                self.assertEqual(link["added_dimensions"], [])

    def test_prototype_qualifiers_are_visible(self) -> None:
        applied = [
            added
            for link in self.links
            for added in link["added_dimensions"]
            if added["propagation_eligibility"] == PROTOTYPE_ONLY
        ]
        self.assertTrue(applied)
        for added in applied:
            with self.subTest(dimension=added["dimension"]):
                self.assertTrue(added["display_allowed"])
                self.assertFalse(added["hard_filter_allowed"])

    def test_one_view_per_statement_in_prototype_mode(self) -> None:
        self.assertEqual(len(self.views), len(self.statements))
        for view in self.views:
            with self.subTest(statement=view["statement_id"]):
                self.assertEqual(view["view_mode"], "prototype")

    def test_native_fields_are_available_and_untouched(self) -> None:
        by_statement = {str(s["evidence_statement_id"]): s for s in self.statements}
        for view in self.views:
            with self.subTest(statement=view["statement_id"]):
                self.assertFalse(view["native_fields_overwritten"])
                self.assertEqual(view["base_statement"], by_statement[view["statement_id"]])

    def test_no_view_is_hard_filterable(self) -> None:
        for view in self.views:
            with self.subTest(statement=view["statement_id"]):
                self.assertEqual(view["hard_filterable_dimensions"], [])
                self.assertEqual(view["final_dimensions"], [])
                self.assertFalse(view["hard_filtering_allowed"])

    def test_every_qualifier_carries_its_full_origin(self) -> None:
        for view in self.views:
            for dimension, value in view["qualified_dimensions"].items():
                with self.subTest(statement=view["statement_id"], dimension=dimension):
                    for key in (
                        "value",
                        "source_profile_unit_id",
                        "source_identifier",
                        "review_status",
                        "propagation_eligibility",
                        "display_allowed",
                        "hard_filter_allowed",
                        "provenance",
                        "source_locators",
                    ):
                        self.assertIn(key, value)
                    self.assertTrue(value["provenance"])

    def test_the_three_absences_stay_distinct(self) -> None:
        # `unknown`, `not_applicable` e `not_separable` non sono sinonimi: dicono
        # rispettivamente che nessuno lo sa, che la domanda non si pone, e che la
        # fonte conferma i componenti ma non la loro relazione.
        panel_view = next(
            view
            for view in self.views
            if "PU-PMID-23344087-preclinical-unresolved-panel"
            in view["linked_source_profile_units"]
        )
        self.assertTrue(panel_view["not_applicable_dimensions"])
        self.assertIn("preclinical_model_composition", panel_view["not_separable_dimensions"])
        self.assertNotEqual(
            panel_view["unknown_dimensions"], panel_view["not_applicable_dimensions"]
        )

    def test_the_negative_experiment_adds_no_positive_support(self) -> None:
        negative = [
            link
            for link in self.links
            if link["source_profile_unit_id"] == "PU-PMID-22235099-h3122-kras-engineered"
        ]
        self.assertTrue(negative)
        for link in negative:
            with self.subTest(link=link["qualification_link_id"]):
                self.assertEqual(link["assertion_polarity"], "does_not_support")
                self.assertEqual(link["added_dimensions"], [])

    def test_the_clinical_population_does_not_reach_the_cell_models(self) -> None:
        models = [
            link
            for link in self.links
            if link["source_profile_unit_id"].startswith("PU-PMID-22277784-baf3")
        ]
        self.assertTrue(models)
        for link in models:
            for added in link["added_dimensions"]:
                if added["dimension"] != "population":
                    continue
                with self.subTest(link=link["qualification_link_id"]):
                    self.assertNotIn("patients", str(added["value"]).casefold())

    def test_a_mixed_view_refuses_to_merge_two_populations(self) -> None:
        mixed = next(
            view for view in self.views if view["statement_id"] == "ES-V2-evidence-100005"
        )
        self.assertIn("population", [c["dimension"] for c in mixed["conflicts"]])
        self.assertNotIn("population", mixed["qualified_dimensions"])

    def test_the_unresolved_panel_is_flagged_on_its_links(self) -> None:
        panel = [
            link
            for link in self.links
            if link["source_profile_unit_id"]
            == "PU-PMID-23344087-preclinical-unresolved-panel"
        ]
        self.assertTrue(panel)
        for link in panel:
            with self.subTest(link=link["qualification_link_id"]):
                self.assertIn("preclinical_model_composition", link["not_separable_fields"])


# ── gold ──────────────────────────────────────────────────────────────────────


class TestProvisionalGold(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gold = load_jsonl(CORPUS / "statement_qualification_gold.jsonl")
        cls.source = load_jsonl(
            V3 / "author_approval_23344087/provisional_gold.jsonl"
        )

    def test_the_gold_is_carried_over_intact(self) -> None:
        self.assertEqual(self.gold, self.source)
        self.assertEqual(len(self.gold), 94)

    def test_no_record_is_evaluable(self) -> None:
        for row in self.gold:
            with self.subTest(link=row.get("gold_link_id")):
                self.assertFalse(row.get("is_evaluable"))

    def test_the_annotated_records_stay_provisional(self) -> None:
        # Dieci link dalla prima revisione di PMID 22277784, piu' due, tre e due
        # dalle tre approvazioni: il gold accumula, non sostituisce.
        annotated = [row for row in self.gold if row.get("first_annotator")]
        self.assertEqual(len(annotated), 17)
        for row in annotated:
            with self.subTest(link=row["gold_link_id"]):
                self.assertEqual(row["final_status"], "provisional_first_review")
                self.assertIsNone(row["second_annotator"])
                self.assertIsNone(row["agreement"])
                self.assertIsNone(row["adjudication"])

    def test_no_candidate_decision_is_copied_into_final_status(self) -> None:
        self.assertEqual(validate_gold(self.gold), [])

    def test_an_evaluable_record_without_a_second_review_is_rejected(self) -> None:
        found = validate_gold(
            [{"gold_link_id": "GL-x", "is_evaluable": True, "second_annotator": None}]
        )
        self.assertTrue(found)


# ── determinismo ──────────────────────────────────────────────────────────────


class TestDeterminism(unittest.TestCase):
    @staticmethod
    def _run(output: Path, *, reverse: bool = False) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts import (
            rebuild_qualification_views,
            regenerate_qualification_corpus,
        )

        base = ["--output", str(output), "--timestamp", FIXED_TIMESTAMP]
        with contextlib.redirect_stdout(io.StringIO()):
            if regenerate_qualification_corpus.main(
                base + (["--reverse-input-order"] if reverse else [])
            ):
                raise AssertionError("regenerate_qualification_corpus non e' uscito con 0")
            if rebuild_qualification_views.main(base):
                raise AssertionError("rebuild_qualification_views non e' uscito con 0")

    @staticmethod
    def _digests(directory: Path) -> dict[str, str]:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.iterdir())
            if path.is_file()
        }

    def test_two_regenerations_produce_identical_files(self) -> None:
        digests = []
        for _ in range(2):
            with TemporaryDirectory() as temporary:
                output = Path(temporary) / "corpus"
                self._run(output)
                digests.append(self._digests(output))
        self.assertEqual(digests[0], digests[1])
        self.assertTrue(digests[0])

    def test_the_committed_corpus_matches_a_fresh_run(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "corpus"
            self._run(output)
            for path in sorted(output.iterdir()):
                with self.subTest(artifact=path.name):
                    self.assertEqual(path.read_bytes(), (CORPUS / path.name).read_bytes())

    def test_reversing_the_input_order_changes_nothing(self) -> None:
        # Se cambiasse, la precedenza dipenderebbe dall'ordine di lettura e non
        # sarebbe una precedenza.
        with TemporaryDirectory() as temporary:
            forward = Path(temporary) / "forward"
            reverse = Path(temporary) / "reverse"
            self._run(forward)
            self._run(reverse, reverse=True)
            for path in sorted(forward.iterdir()):
                if path.name == "qualification_scope.json":
                    continue
                with self.subTest(artifact=path.name):
                    self.assertEqual(
                        path.read_bytes(), (reverse / path.name).read_bytes()
                    )

    def test_the_fingerprint_is_stable_across_runs(self) -> None:
        manifest = load_json(CORPUS / "qualification_corpus_manifest.json")
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "corpus"
            self._run(output)
            fresh = load_json(output / "qualification_corpus_manifest.json")
        self.assertEqual(
            fresh["qualification_corpus_fingerprint"],
            manifest["qualification_corpus_fingerprint"],
        )

    def test_volatile_fields_do_not_enter_the_hash(self) -> None:
        first = stable_hash({"value": 1, "generated_at": "2020-01-01"})
        second = stable_hash({"value": 1, "generated_at": "2030-12-31"})
        self.assertEqual(first, second)
        self.assertNotIn("generated_at", strip_volatile({"generated_at": "x", "a": 1}))

    def test_no_machine_path_appears_in_the_artifacts(self) -> None:
        for path in sorted(CORPUS.glob("*")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(artifact=path.name):
                self.assertNotIn("C:\\Users", text)
                self.assertNotIn("/home/", text)
                self.assertNotIn(str(REPO_ROOT), text)


# ── merge canonico ────────────────────────────────────────────────────────────


class TestCanonicalMerge(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = load_jsonl(CORPUS / "canonical_merge_audit.jsonl")
        cls.units = load_jsonl(CORPUS / "source_profile_units.jsonl")

    def test_every_unit_has_an_audit_row(self) -> None:
        self.assertEqual(
            {row["entity_id"] for row in self.audit},
            {row["profile_unit_id"] for row in self.units},
        )

    def test_no_conflict_is_unresolved(self) -> None:
        self.assertEqual([row for row in self.audit if row["conflicts"]], [])
        for row in self.audit:
            with self.subTest(entity=row["entity_id"]):
                self.assertEqual(row["conflict_status"], "resolved")

    def test_the_audit_names_the_winning_artifact_for_each_field(self) -> None:
        multi = [row for row in self.audit if len(row["candidate_sources"]) > 1]
        self.assertTrue(multi)
        for row in multi:
            with self.subTest(entity=row["entity_id"]):
                self.assertIn(row["selected_source"], row["candidate_sources"])
                self.assertTrue(row["field_decisions"])
                self.assertTrue(row["source_artifact_hashes"])

    def test_unmodified_fields_are_preserved(self) -> None:
        multi = [row for row in self.audit if len(row["candidate_sources"]) > 1]
        self.assertTrue(any(row["preserved_fields"] for row in multi))

    def test_a_higher_layer_overrides_only_what_it_declares(self) -> None:
        from backend.pipeline.evidence.corpus_regeneration import SourceLayer

        low = SourceLayer("low", 1, "a.jsonl")
        high = SourceLayer("high", 2, "b.jsonl")
        merged = merge_records(
            "U", [(low, {"disease": "D", "stage": "unknown"}), (high, {"stage": "IV"})]
        )
        self.assertEqual(merged.record, {"disease": "D", "stage": "IV"})
        self.assertEqual(merged.conflicts, [])

    def test_two_equal_ranked_layers_that_disagree_conflict(self) -> None:
        from backend.pipeline.evidence.corpus_regeneration import SourceLayer

        merged = merge_records(
            "U",
            [
                (SourceLayer("a", 1, "a.jsonl"), {"stage": "III"}),
                (SourceLayer("b", 1, "b.jsonl"), {"stage": "IV"}),
            ],
        )
        self.assertTrue(merged.has_conflicts)

    def test_policy_fields_never_enter_the_merge(self) -> None:
        from backend.pipeline.evidence.corpus_regeneration import SourceLayer

        merged = merge_records(
            "U", [(SourceLayer("a", 1, "a.jsonl"), {"is_propagatable": True, "disease": "D"})]
        )
        self.assertNotIn("is_propagatable", merged.record)


# ── blinding e immutabilita' ──────────────────────────────────────────────────


class TestBlindingAndImmutability(unittest.TestCase):
    def test_the_seventy_packets_are_byte_identical(self) -> None:
        manifest = load_json(CORPUS / "qualification_corpus_manifest.json")
        packets = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(SECOND_REVIEW.iterdir())
            if path.is_file()
        }
        self.assertEqual(len(packets), 70)
        self.assertEqual(
            manifest["component_hashes"]["second_review_packets_hash"], stable_hash(packets)
        )

    def test_no_first_review_decision_leaks_into_the_blind_packets(self) -> None:
        # `candidate_ambiguous` **compare** nei packet, e non e' una violazione:
        # e' la classificazione automatica prodotta prima di ogni revisione umana,
        # etichettata come tale. Cercare il vocabolario darebbe falsi allarmi; il
        # test cerca cio' che soltanto una decisione di prima revisione porta con
        # se' — un revisore, una annotazione, un livello di propagazione.
        leaks = (
            "paolo_pangallo",
            "first_review_annotation",
            "first_annotator",
            "first_review_candidate_status",
            "human_approved_llm_assisted_source_review",
            "prototype_only",
            "qualification_corpus/2.0",
            "provisional_first_review",
        )
        for path in sorted(SECOND_REVIEW.iterdir()):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for token in leaks:
                with self.subTest(packet=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_the_candidate_vocabulary_stays_labelled_automatic(self) -> None:
        for path in sorted(SECOND_REVIEW.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for candidate in payload.get("candidate_statements") or []:
                with self.subTest(packet=path.name):
                    self.assertIn("automatic_classification", candidate)
                    self.assertNotIn("first_review_candidate_status", candidate)

    def test_the_source_phases_are_untouched(self) -> None:
        expectations = {
            "priority_curation/resolved_profile_units.jsonl": 13,
            "cohort_split_audit/proposed_profile_units.jsonl": 6,
            "clinical_preclinical_review_batch/proposed_profile_units.jsonl": 9,
            "first_review/reviewed_profile_units.jsonl": 4,
            "author_approval/approved_profile_units.jsonl": 1,
            "author_approval_22235099/approved_profile_units.jsonl": 4,
            "author_approval_23344087/approved_profile_units.jsonl": 2,
        }
        for relative, count in expectations.items():
            with self.subTest(artifact=relative):
                self.assertEqual(len(load_jsonl(V3 / relative)), count)

    def test_the_stale_flags_are_still_there_in_the_source_artifacts(self) -> None:
        # La rigenerazione non riscrive gli artefatti di origine: i 99 flag
        # obsoleti restano dove sono, e sparire dal corpus nuovo e' un'altra cosa
        # che riscriverli retroattivamente.
        previous = load_jsonl(PREVIOUS_CORPUS / "source_profile_units.jsonl")
        self.assertEqual(sum(1 for row in previous if row.get("is_propagatable")), 86)

    def test_a_changed_frozen_fingerprint_is_rejected(self) -> None:
        found = validate_fingerprints(
            frozen_kg_before="a" * 64,
            frozen_kg_after="b" * 64,
            blind_packets_before={},
            blind_packets_after={},
        )
        self.assertTrue(found)
        with self.assertRaises(SnapshotFingerprintChangedError):
            found[0].raise_it()


# ── diff, metriche, readiness ─────────────────────────────────────────────────


class TestDiffMetricsReadiness(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.diff = load_json(CORPUS / "corpus_regeneration_diff.json")
        cls.metrics = load_json(CORPUS / "regeneration_metrics.json")
        cls.readiness = load_json(CORPUS / "readiness.json")

    def test_the_acceptance_gates_are_zero(self) -> None:
        self.assertEqual(self.diff["unexpected_change"], 0)
        self.assertEqual(self.diff["unresolved_conflict"], 0)
        self.assertEqual(self.diff["obsolete_serialized_flags_after"], 0)

    def test_every_change_is_classified(self) -> None:
        from backend.pipeline.evidence.corpus_regeneration import CHANGE_CLASSES

        for change in self.diff["changes"]:
            with self.subTest(entity=change["entity_id"]):
                self.assertIn(change["change_class"], CHANGE_CLASSES)

    def test_the_diff_reports_both_fingerprints(self) -> None:
        self.assertEqual(self.diff["frozen_kg_snapshot_fingerprint"], FROZEN_KG)
        self.assertNotEqual(
            self.diff["qualification_corpus_fingerprint"],
            self.diff["previous_corpus_fingerprint"],
        )

    def test_the_markdown_diff_exists_and_names_the_gates(self) -> None:
        text = (CORPUS / "CORPUS_REGENERATION_DIFF.md").read_text(encoding="utf-8")
        self.assertIn("unexpected_change", text)
        self.assertIn("unresolved_conflict", text)
        self.assertIn(FROZEN_KG, text)

    def test_only_descriptive_metrics_are_calculated(self) -> None:
        self.assertEqual(self.metrics["metric_kind"], "descriptive_corpus_metrics")
        for key, value in self.metrics["not_calculated"].items():
            with self.subTest(metric=key):
                self.assertEqual(value, "not_calculated")
        for forbidden in ("precision", "recall", "f1", "agreement", "accuracy"):
            with self.subTest(metric=forbidden):
                self.assertNotIn(forbidden, self.metrics)

    def test_the_counts_match_the_artifacts(self) -> None:
        self.assertEqual(
            self.metrics["evidence_statement_count"],
            len(load_jsonl(CORPUS / "evidence_statements.jsonl")),
        )
        self.assertEqual(
            self.metrics["total_profile_units"],
            len(load_jsonl(CORPUS / "source_profile_units.jsonl")),
        )
        self.assertEqual(
            self.metrics["qualification_links"],
            len(load_jsonl(CORPUS / "qualification_links.jsonl")),
        )
        self.assertEqual(
            self.metrics["prototype_views"],
            len(load_jsonl(CORPUS / "qualified_evidence_views.jsonl")),
        )

    def test_the_prototype_is_ready_and_the_final_evaluation_is_not(self) -> None:
        self.assertTrue(self.readiness["prototype_qualified_evidence_view_ready"])
        self.assertTrue(self.readiness["ready_for_prototype_retriever_implementation"])
        self.assertTrue(self.readiness["qualification_corpus_internally_consistent"])
        self.assertTrue(self.readiness["author_approval_batch_complete"])
        self.assertTrue(self.readiness["propagation_policy_migration_complete"])
        for gate in (
            "hard_filtering_available",
            "final_evaluation_ready",
            "gold_evaluable",
            "detector_promotion_ready",
            "standard_queue_resumed",
        ):
            with self.subTest(gate=gate):
                self.assertFalse(self.readiness[gate])

    def test_the_readiness_is_dimension_specific(self) -> None:
        by_dimension = self.readiness["readiness_by_dimension"]
        self.assertEqual(by_dimension["evidence_statement_native_fields"], "ready")
        self.assertEqual(by_dimension["first_review_qualifiers"], "prototype_ready")
        self.assertNotEqual(by_dimension["first_review_qualifiers"], "final_ready")
        self.assertEqual(by_dimension["hard_filtering"], "not_available")

    def test_the_unresolved_panel_cannot_be_filtered_by_component(self) -> None:
        self.assertEqual(
            self.readiness["readiness_by_dimension"]["component_level_filtering_23344087"],
            "not_available",
        )
        self.assertFalse(self.readiness["unresolved_panel_component_filtering_available"])

    def test_the_pre_existing_gap_is_recorded_not_hidden(self) -> None:
        findings = load_jsonl(CORPUS / "guard_findings.jsonl")
        self.assertEqual(len(findings), self.readiness["pre_existing_guard_findings"])
        for row in findings:
            with self.subTest(subject=row["subject"]):
                self.assertFalse(row["blocking"])
                self.assertFalse(row["introduced_by_this_regeneration"])
                self.assertEqual(row["classification"], "pre_existing_gap")

    def test_the_mappings_stay_unverified(self) -> None:
        mappings = load_jsonl(CORPUS / "terminology_mappings.jsonl")
        self.assertEqual(validate_mappings(mappings), [])
        self.assertGreater(self.metrics["terminology_mappings_pending"], 0)

    def test_a_promoted_mapping_is_rejected(self) -> None:
        found = validate_mappings([{"mapping_id": "TM-x", "promoted_to_verified_synonym": True}])
        self.assertTrue(found)
        with self.assertRaises(UnverifiedMappingPromotedError):
            found[0].raise_it()

    def test_a_generalized_case_level_decision_is_rejected(self) -> None:
        found = validate_decisions(
            [
                {
                    "statement_id": "ES-x",
                    "evidence_granularity": "case_level",
                    "cohort_generalizable": True,
                }
            ]
        )
        self.assertTrue(found)
        with self.assertRaises(CaseLevelGeneralizedError):
            found[0].raise_it()

    def test_the_recorded_decisions_are_not_generalized(self) -> None:
        self.assertEqual(
            validate_decisions(load_jsonl(CORPUS / "review_decisions.jsonl")), []
        )


# ── regressione ───────────────────────────────────────────────────────────────


class TestRegression(unittest.TestCase):
    def test_the_statement_repository_still_has_147_statements(self) -> None:
        self.assertEqual(len(load_jsonl(CORPUS / "evidence_statements.jsonl")), 147)

    def test_the_statements_are_unchanged_from_the_adapter(self) -> None:
        adapter = load_jsonl(
            REPO_ROOT
            / "benchmarks/mtb_evidence/evaluation/results/adapter_v1/evidence_statements.jsonl"
        )
        self.assertEqual(load_jsonl(CORPUS / "evidence_statements.jsonl"), adapter)

    def test_no_network_is_needed(self) -> None:
        from benchmarks.mtb_evidence.evaluation.scripts.regenerate_qualification_corpus import (
            parse_args,
        )

        args = parse_args([])
        self.assertFalse(hasattr(args, "allow_network"))
        for path in sorted(CORPUS.glob("*")):
            text = path.read_text(encoding="utf-8")
            for name in ("requests", "urllib.request", "httpx"):
                with self.subTest(artifact=path.name, module=name):
                    self.assertNotIn(name, text)

    def test_the_retriever_is_not_implemented(self) -> None:
        self.assertEqual(list(REPO_ROOT.rglob("*QualifiedEvidenceRetriever*")), [])


if __name__ == "__main__":
    unittest.main()
